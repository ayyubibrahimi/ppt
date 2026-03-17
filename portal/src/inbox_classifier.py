import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage

from mcp_gmail_client import MCPGmailClient
from supabase_integration import SupabaseIntegration

logger = logging.getLogger(__name__)

NEEDS_REVIEW_AFTER_DAYS = 3


class ClassificationResult(BaseModel):
    matched_request_id: Optional[str] = Field(
        default=None,
        description="The request_id this email belongs to, or null if no confident match"
    )


class InboxClassifierAgent:
    """
    Scans unmatched inbox emails and links them to the correct FOIA request thread.

    Runs before GmailMonitoringAgent each cycle so that gmail_thread_id is always
    pointing to the live conversation thread by the time monitoring fetches it.

    Two resolution paths:
      - auto: agency replied on the original submission thread (same thread_id)
      - classifier: agency started a new thread; we found and linked it

    Supports dry_run=True to audit all decisions without writing to the DB.
    """

    def __init__(self, db: SupabaseIntegration, llm_client):
        self.db = db
        self.llm_client = llm_client

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_classification_cycle(
        self,
        user_id: str,
        retroactive: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Classify unmatched inbox emails against open FOIA requests for one user.

        Args:
            user_id: User to process
            retroactive: If True, scans full inbox history and processes ALL email
                         requests regardless of current thread_resolution_status.
            dry_run: If True, runs the full pipeline but writes nothing to the DB.
                     All decisions are recorded in results['decisions'] for audit.

        Returns:
            Dict with counts and a 'decisions' list. Each decision has:
              request_number, request_id, agency, action, reason,
              email_from, email_subject, original_thread_id, new_thread_id
        """
        decisions: List[Dict] = []
        results = {
            'auto_resolved': 0,
            'classifier_resolved': 0,
            'needs_review_flagged': 0,
            'skipped': 0,
            'errors': 0,
            'decisions': decisions,
        }

        try:
            # 1. Resolve user email address
            user_email = self.db.get_user_email(user_id)
            if not user_email:
                logger.error(f"No email address found for user {user_id}")
                return {**results, 'success': False, 'error': 'No user email'}

            # 2. Fetch target requests
            if retroactive:
                raw = self.db.supabase.table('requests').select('*').eq(
                    'user_id', user_id
                ).eq('portal_type', 'email').execute()
                unresolved = self.db._enrich_with_portal_data(raw.data or [])
                logger.info(f"[Retroactive] {len(unresolved)} total email request(s)")
            else:
                unresolved = self.db.get_requests_pending_thread_resolution(user_id)

            if not unresolved:
                logger.info(f"No unresolved email requests for user {user_id}")
                return {**results, 'success': True}

            # 3. All known thread IDs for this user (to avoid re-claiming)
            known_thread_ids = self.db.get_all_email_request_thread_ids(user_id)

            # 4. Date filter: scan inbox only since earliest unresolved request
            since_date = None
            if not retroactive:
                dates = [r['created_at'] for r in unresolved if r.get('created_at')]
                if dates:
                    try:
                        earliest = min(dates)
                        dt = datetime.fromisoformat(earliest.replace('Z', '+00:00'))
                        since_date = dt.strftime('%Y/%m/%d')
                    except Exception:
                        pass

            # 5. Step A — auto-resolution: check original thread for agency reply
            still_unresolved = []
            for request in unresolved:
                agency = self._get_agency_name(request)
                try:
                    auto_sender = self._check_auto_resolve(request, user_email)
                    if auto_sender:
                        decisions.append({
                            'request_number': request.get('request_number'),
                            'request_id': request['id'],
                            'agency': agency,
                            'action': 'auto',
                            'reason': 'Agency reply detected on original submission thread',
                            'auto_sender': auto_sender,
                            'request_text': (request.get('request_text') or '')[:400],
                            'email_from': auto_sender,
                            'email_subject': None,
                            'email_body': None,
                            'email_date': None,
                            'original_thread_id': request.get('gmail_thread_id'),
                            'new_thread_id': None,
                        })
                        if not dry_run:
                            self.db.update_thread_resolution(request['id'], 'auto')
                        results['auto_resolved'] += 1
                        logger.info(f"{'[DRY RUN] ' if dry_run else ''}✅ Auto-resolved: {request.get('request_number')}")
                    else:
                        still_unresolved.append(request)
                except Exception as e:
                    logger.error(f"Error in auto-resolve for {request.get('request_number')}: {e}")
                    still_unresolved.append(request)
                    results['errors'] += 1

            if not still_unresolved:
                logger.info("All requests auto-resolved, nothing left to classify")
                return {**results, 'success': True}

            # 6. Fetch inbox (one MCP session for the whole scan)
            inbox_emails = self._get_all_inbox_emails(since_date=since_date)
            if not inbox_emails:
                logger.info("No inbox emails fetched")
                self._flag_stale_requests(still_unresolved, results, decisions, dry_run)
                return {**results, 'success': True}

            # 7. Filter to unmatched: not already claimed, not sent by user
            unmatched = self._get_unmatched_emails(inbox_emails, known_thread_ids, user_email)
            logger.info(
                f"📬 {len(unmatched)} unmatched inbox email(s) to classify "
                f"against {len(still_unresolved)} request(s)"
            )

            if not unmatched:
                self._flag_stale_requests(still_unresolved, results, decisions, dry_run)
                return {**results, 'success': True}

            # 8. Classify each unmatched email
            classified_request_ids = set()
            with MCPGmailClient() as mcp:
                for email_summary in unmatched:
                    try:
                        full_email = mcp.read_email(email_summary['id'])
                        if not full_email or not full_email.get('body'):
                            results['skipped'] += 1
                            continue

                        email_data = {**email_summary, **full_email}

                        candidates = self._domain_prefilter(email_data, still_unresolved)
                        if not candidates:
                            results['skipped'] += 1
                            continue

                        matched_id = self._llm_classify(email_data, candidates)
                        if matched_id:
                            new_thread_id = (
                                full_email.get('thread_id')
                                or email_summary.get('thread_id')
                            )
                            matched_req = next(
                                (r for r in still_unresolved if r['id'] == matched_id), {}
                            )
                            decisions.append({
                                'request_number': matched_req.get('request_number'),
                                'request_id': matched_id,
                                'agency': self._get_agency_name(matched_req),
                                'action': 'classifier',
                                'reason': f'LLM matched inbox email from {email_data.get("from", "")}',
                                'request_text': (matched_req.get('request_text') or '')[:400],
                                'email_from': email_data.get('from'),
                                'email_subject': email_data.get('subject'),
                                'email_date': email_data.get('date'),
                                'email_body': (email_data.get('body') or '')[:800],
                                'original_thread_id': matched_req.get('gmail_thread_id'),
                                'new_thread_id': new_thread_id,
                            })
                            if not dry_run:
                                self._apply_classification(matched_id, new_thread_id)
                            classified_request_ids.add(matched_id)
                            results['classifier_resolved'] += 1
                            logger.info(
                                f"{'[DRY RUN] ' if dry_run else ''}✅ Classifier resolved "
                                f"{matched_req.get('request_number')} → thread {new_thread_id}"
                            )

                    except Exception as e:
                        logger.error(f"Error classifying email {email_summary.get('id')}: {e}")
                        results['errors'] += 1

            # 9. Flag/record still-unresolved requests (stale → needs_review, fresh → no_match)
            remaining = [r for r in still_unresolved if r['id'] not in classified_request_ids]
            self._flag_stale_requests(remaining, results, decisions, dry_run)

            logger.info(
                f"{'[DRY RUN] ' if dry_run else ''}✅ Classification cycle complete — "
                f"auto: {results['auto_resolved']}, "
                f"classifier: {results['classifier_resolved']}, "
                f"needs_review: {results['needs_review_flagged']}, "
                f"skipped: {results['skipped']}, "
                f"errors: {results['errors']}"
            )
            return {**results, 'success': True}

        except Exception as e:
            logger.error(f"❌ Classification cycle failed for user {user_id}: {e}")
            return {**results, 'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Auto-resolution
    # ------------------------------------------------------------------

    def _check_auto_resolve(self, request: Dict, user_email: str) -> Optional[str]:
        """
        Check if the original submission thread has a reply from the agency.

        Returns:
            The sender address of the first non-user reply if found (truthy),
            or None if the thread has no agency replies (falsy).
        """
        gmail_thread_id = request.get('gmail_thread_id')
        if not gmail_thread_id:
            return None

        try:
            with MCPGmailClient() as mcp:
                thread_messages = mcp.search_thread(gmail_thread_id)

            if not thread_messages:
                return None

            user_email_lower = user_email.lower()
            for msg in thread_messages:
                sender = msg.get('from', '')
                if user_email_lower not in sender.lower():
                    logger.info(
                        f"📨 Agency reply on original thread {gmail_thread_id}: {sender}"
                    )
                    return sender  # return the actual sender address for audit

            return None

        except Exception as e:
            logger.warning(f"Could not check thread {gmail_thread_id} for auto-resolve: {e}")
            return None

    # ------------------------------------------------------------------
    # Inbox fetch
    # ------------------------------------------------------------------

    def _get_all_inbox_emails(self, since_date: Optional[str] = None) -> List[Dict]:
        """
        Fetch inbox email summaries via MCP.

        Args:
            since_date: Gmail date string 'YYYY/MM/DD', or None for full history
        """
        query = 'in:inbox'
        if since_date:
            query += f' after:{since_date}'

        try:
            with MCPGmailClient() as mcp:
                emails = mcp.search_emails(query, max_results=200)
            logger.info(f"Fetched {len(emails)} inbox email(s) (since={since_date})")
            return emails
        except Exception as e:
            logger.error(f"Failed to fetch inbox emails: {e}")
            return []

    # ------------------------------------------------------------------
    # Unmatched filter
    # ------------------------------------------------------------------

    def _get_unmatched_emails(
        self,
        inbox_emails: List[Dict],
        known_thread_ids: set,
        user_email: str,
    ) -> List[Dict]:
        """
        Return emails whose thread is not already linked to any request
        and that were not sent by the user themselves.
        """
        user_email_lower = user_email.lower()
        unmatched = []

        for email in inbox_emails:
            thread_id = email.get('thread_id')
            sender = email.get('from', '').lower()

            if thread_id and thread_id in known_thread_ids:
                continue
            if user_email_lower in sender:
                continue

            unmatched.append(email)

        return unmatched

    # ------------------------------------------------------------------
    # Domain pre-filter
    # ------------------------------------------------------------------

    def _domain_prefilter(self, email: Dict, candidates: List[Dict]) -> List[Dict]:
        """
        Narrow candidates to those whose agency domain or name matches the
        sender's domain. Reduces LLM calls for unrelated inbox mail.
        """
        sender_domain = self._extract_domain(email.get('from', ''))
        sender_keywords = self._domain_to_keywords(sender_domain)

        shortlist = []
        for req in candidates:
            portal_data = req.get('portals') or {}
            contact_email = portal_data.get('contact_email') or ''
            agency_name = portal_data.get('agency_name') or req.get('portal_name', '')

            agency_domain = self._extract_domain(contact_email)
            agency_domain_keywords = self._domain_to_keywords(agency_domain)
            agency_name_keywords = self._normalize_to_keywords(agency_name)

            domain_match = any(k in sender_keywords for k in agency_domain_keywords)
            name_match = any(k in sender_domain for k in agency_name_keywords)

            if domain_match or name_match:
                shortlist.append(req)

        return shortlist

    @staticmethod
    def _extract_domain(address: str) -> str:
        """'Records Dept <records@cityofhollister.gov>' → 'cityofhollister.gov'"""
        match = re.search(r'<[^@]+@([^>]+)>', address)
        if match:
            return match.group(1).lower().strip()
        match = re.search(r'@([\w.\-]+)', address)
        if match:
            return match.group(1).lower().strip()
        return ''

    @staticmethod
    def _domain_to_keywords(domain: str) -> List[str]:
        """'cityofhollister.gov' → ['cityofhollister', 'hollister']"""
        parts = domain.split('.')
        if len(parts) > 1:
            parts = parts[:-1]  # drop TLD
        keywords = []
        for part in parts:
            keywords.append(part)
            keywords.extend(re.split(r'[-_]', part))
        return [k for k in keywords if len(k) > 2]

    @staticmethod
    def _normalize_to_keywords(text: str) -> List[str]:
        """'City of Hollister Police Department' → ['hollister', 'police']"""
        stop_words = {
            'city', 'of', 'the', 'county', 'department', 'dept',
            'office', 'public', 'records', 'and', 'for', 'a'
        }
        words = re.findall(r'[a-zA-Z]+', text.lower())
        return [w for w in words if w not in stop_words and len(w) > 2]

    @staticmethod
    def _get_agency_name(request: Dict) -> str:
        """Extract agency name from request, handling the portals join."""
        portal_data = request.get('portals') or {}
        return portal_data.get('agency_name') or request.get('portal_name', '')

    # ------------------------------------------------------------------
    # LLM classification
    # ------------------------------------------------------------------

    def _llm_classify(self, email: Dict, candidates: List[Dict]) -> Optional[str]:
        """
        Ask the LLM which candidate request (if any) this email is responding to.

        Returns:
            request_id string if confident match found, None otherwise
        """
        candidates_text = ''
        for req in candidates:
            portal_data = req.get('portals') or {}
            agency_name = portal_data.get('agency_name') or req.get('portal_name', '')
            contact_email = portal_data.get('contact_email') or ''
            request_text = (req.get('request_text') or '')[:500]
            created_at = (req.get('created_at') or '')[:10]

            candidates_text += (
                f"\nRequest ID: {req['id']}\n"
                f"Agency: {agency_name}\n"
                f"Contact email: {contact_email}\n"
                f"Submitted: {created_at}\n"
                f"Request text: {request_text}\n"
                "---"
            )

        prompt = f"""You are classifying an incoming email to determine which public records request it belongs to.

INCOMING EMAIL:
From: {email.get('from', '')}
Date: {email.get('date', '')}
Subject: {email.get('subject', '')}
Body:
{(email.get('body') or '')[:2000]}

CANDIDATE REQUESTS:
{candidates_text}

TASK:
Determine which request (if any) this email is responding to.

Use these signals:
1. Agency name in body/signature matches candidate agency name
2. References to FOIA request language, request numbers, or specific information requested
3. Sender email domain matches the agency's contact email domain
4. Date of email is after submission date of the candidate request

Return the request_id of the matching request, or null if no confident match.
Only return a match if you are certain. Do not guess."""

        try:
            structured_llm = self.llm_client.with_structured_output(ClassificationResult)
            messages = [
                SystemMessage(
                    content="You are a precise email classifier for public records requests."
                ),
                HumanMessage(content=prompt),
            ]
            result = structured_llm.invoke(messages)
            return result.matched_request_id or None

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Apply / flag helpers
    # ------------------------------------------------------------------

    def _apply_classification(self, request_id: str, new_thread_id: str) -> bool:
        """Overwrite gmail_thread_id and set status to 'classifier'."""
        return self.db.update_thread_resolution(request_id, 'classifier', new_thread_id)

    def _flag_needs_review(self, request_id: str) -> bool:
        """Mark request as needing human review."""
        return self.db.update_thread_resolution(request_id, 'needs_review')

    def _flag_stale_requests(
        self,
        requests: List[Dict],
        results: Dict,
        decisions: List,
        dry_run: bool,
    ) -> None:
        """
        For each request with no inbox match:
        - If older than NEEDS_REVIEW_AFTER_DAYS → flag needs_review (or record decision)
        - Otherwise → record as no_match (will retry next cycle)
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=NEEDS_REVIEW_AFTER_DAYS)

        for req in requests:
            agency = self._get_agency_name(req)
            created_at_str = req.get('created_at', '')
            days_old = 0
            is_stale = False

            try:
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                days_old = (datetime.now(timezone.utc) - created_at).days
                is_stale = created_at < cutoff
            except Exception:
                pass

            shared = {
                'request_number': req.get('request_number'),
                'request_id': req['id'],
                'agency': agency,
                'request_text': (req.get('request_text') or '')[:400],
                'email_from': None,
                'email_subject': None,
                'email_date': None,
                'email_body': None,
                'original_thread_id': req.get('gmail_thread_id'),
                'new_thread_id': None,
            }

            if is_stale:
                decisions.append({
                    **shared,
                    'action': 'needs_review',
                    'reason': f'No inbox match found, submitted {created_at_str[:10]} ({days_old} days ago)',
                })
                if not dry_run:
                    self._flag_needs_review(req['id'])
                results['needs_review_flagged'] += 1
                logger.info(
                    f"{'[DRY RUN] ' if dry_run else ''}⚠️  needs_review: "
                    f"{req.get('request_number')} ({days_old}d old)"
                )
            else:
                decisions.append({
                    **shared,
                    'action': 'no_match',
                    'reason': f'No inbox match found, submitted {created_at_str[:10]} ({days_old} days ago), not yet stale',
                })
