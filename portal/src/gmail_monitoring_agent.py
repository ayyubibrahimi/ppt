import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import json
from gmail_llm_helper import GmailLLMHelper, fuzzy_match_portal
from llm_helper import LLMHelper
from mcp_gmail_client import MCPGmailClient
from workflow_state_helper import WorkflowStateHelper

logger = logging.getLogger(__name__)


class GmailMonitoringAgent:
    """
    Monitors Gmail for agency emails and updates request analysis.
    Runs in parallel with PortalAgent's browser-based monitoring.
    """

    def __init__(self, db, llm_client, check_interval_minutes: int = 5):
        """
        Initialize Gmail monitoring agent.

        Args:
            db: SupabaseIntegration instance
            llm_client: LLM client for analysis
            check_interval_minutes: How often to check Gmail (default: 5 minutes)
        """
        self.db = db
        self.llm_helper = LLMHelper(llm_client)  # Reuse existing LLM helper
        self.gmail_helper = GmailLLMHelper(llm_client)  # New Gmail-specific helper
        self.workflow_state_helper = WorkflowStateHelper(llm_client)  # Workflow state determination
        self.check_interval_minutes = check_interval_minutes

        # MCP client connection (will be initialized when needed)
        self.mcp_client = None

        # Stats
        self.last_run_time = None
        self.total_runs = 0
        self.successful_runs = 0

    def run_monitoring_cycle(self, user_id: str, portal_type_filter: str = 'all') -> Dict[str, Any]:
        """
        Execute one Gmail monitoring cycle.

        Args:
            user_id: User ID to monitor emails for
            portal_type_filter: Filter by portal type - 'all', 'email', or 'portal' (default: all)

        Returns:
            Dict with success status and statistics
        """
        emails_processed = 0
        emails_skipped = 0
        errors = []
        changes_detected = 0

        try:
            logger.info(f"📧 Starting Gmail monitoring cycle for user: {user_id}")

            # For email-based requests, use direct thread monitoring instead of inbox search
            if portal_type_filter == 'email':
                return self._monitor_email_requests_directly(user_id)

            # For portal requests, use inbox search (existing flow)
            # 1. Fetch new emails from Gmail
            emails = self._fetch_new_emails(user_id)

            if not emails:
                logger.info("📭 No new emails found")
                return {
                    'success': True,
                    'emails_processed': 0,
                    'emails_skipped': 0,
                    'changes_detected': 0,
                    'summary': 'No new emails'
                }

            logger.info(f"📬 Found {len(emails)} emails to process")

            # 2. Process each email
            for email in emails:
                try:
                    email_id = email.get('id', 'unknown')
                    subject = email.get('subject', 'No subject')

                    logger.debug(f"Processing email {email_id}: {subject}")

                    # Skip if already processed
                    if self._is_email_processed(email_id):
                        logger.debug(f"⏭️  Email {email_id} already processed, skipping")
                        emails_skipped += 1
                        continue

                    # Extract request info with LLM
                    match_info = self.gmail_helper.extract_request_info(subject)

                    if match_info['request_number'] == 'UNKNOWN':
                        logger.warning(f"⚠️  Could not extract request number from: {subject}")
                        errors.append(f"Failed to extract request number: {subject}")
                        continue

                    # Match to database request
                    request = self._match_email_to_request(
                        user_id,
                        match_info['request_number'],
                        match_info['agency_name']
                    )

                    if not request:
                        logger.warning(f"⚠️  No matching request found for {match_info['request_number']} / {match_info['agency_name']}")
                        errors.append(f"No match for {subject}")
                        continue

                    # Filter by portal_type if specified
                    if portal_type_filter != 'all':
                        request_portal_type = request.get('portal_type', 'portal')
                        if request_portal_type != portal_type_filter:
                            logger.debug(f"⏭️  Skipping request {match_info['request_number']} (portal_type={request_portal_type}, filter={portal_type_filter})")
                            emails_skipped += 1
                            continue

                    # Read full email body if needed
                    if 'body' not in email or not email['body']:
                        email = self._read_full_email(email_id)

                    # Analyze email content using existing LLM prompt
                    analysis = self._analyze_email_content(email, request)

                    if not analysis:
                        logger.error(f"❌ Failed to analyze email {email_id}")
                        errors.append(f"Analysis failed for {email_id}")
                        continue

                    # Update database with new analysis
                    success = self.db.update_gmail_analysis(
                        request_id=request['id'],
                        analysis=analysis,
                        email_id=email_id
                    )

                    if success:
                        emails_processed += 1
                        changes_detected += 1
                        logger.info(f"✅ Updated request {request['request_number']} from email {email_id}")
                    else:
                        logger.error(f"❌ Failed to update database for email {email_id}")
                        errors.append(f"Database update failed for {email_id}")

                except Exception as e:
                    logger.error(f"❌ Error processing email {email.get('id', 'unknown')}: {str(e)}")
                    errors.append(f"Email processing error: {str(e)}")

            # Update stats
            self.total_runs += 1
            if not errors:
                self.successful_runs += 1
            self.last_run_time = datetime.now()

            summary = f"{emails_processed} processed, {emails_skipped} skipped, {len(errors)} errors"
            logger.info(f"✅ Gmail monitoring cycle complete: {summary}")

            return {
                'success': True,
                'emails_processed': emails_processed,
                'emails_skipped': emails_skipped,
                'changes_detected': changes_detected,
                'errors': errors,
                'summary': summary
            }

        except Exception as e:
            logger.error(f"❌ Gmail monitoring cycle failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'emails_processed': emails_processed,
                'emails_skipped': emails_skipped
            }

    def _monitor_email_requests_directly(self, user_id: str) -> Dict[str, Any]:
        """
        Monitor email-based requests directly by thread ID (bypasses inbox search).

        For email-based requests (portal_type='email'), we already know the gmail_thread_id,
        so we can directly fetch and monitor each thread without searching the inbox.

        Args:
            user_id: User ID to monitor requests for

        Returns:
            Dict with success status and statistics
        """
        requests_processed = 0
        requests_skipped = 0
        errors = []
        changes_detected = 0

        try:
            # Query database for all email-based requests for this user
            result = self.db.supabase.table('requests').select('*').eq(
                'user_id', user_id
            ).eq('portal_type', 'email').execute()

            email_requests = result.data or []
            logger.info(f"📧 Found {len(email_requests)} email-based requests to monitor")

            if not email_requests:
                return {
                    'success': True,
                    'emails_processed': 0,
                    'emails_skipped': 0,
                    'changes_detected': 0,
                    'summary': 'No email-based requests found'
                }

            # Process each email-based request
            for request in email_requests:
                try:
                    request_id = request['id']
                    request_number = request['request_number']
                    gmail_thread_id = request.get('gmail_thread_id')

                    if not gmail_thread_id:
                        logger.warning(f"⚠️  Request {request_number} has no gmail_thread_id, skipping")
                        requests_skipped += 1
                        continue

                    logger.info(f"📧 Monitoring email request {request_number} (thread: {gmail_thread_id})")

                    # Analyze email content using thread ID
                    analysis = self._analyze_email_content(None, request)

                    if not analysis:
                        logger.error(f"❌ Failed to analyze request {request_number}")
                        errors.append(f"Analysis failed for {request_number}")
                        continue

                    # Update database with new analysis (use thread_id as email_id for email-based requests)
                    self.db.update_gmail_analysis(request_id, analysis, gmail_thread_id)
                    logger.info(f"✅ Updated request {request_number}")
                    requests_processed += 1
                    changes_detected += 1

                except Exception as e:
                    logger.error(f"❌ Error monitoring request {request.get('request_number', 'unknown')}: {str(e)}")
                    errors.append(f"Error for {request.get('request_number', 'unknown')}: {str(e)}")
                    continue

            summary = f"{requests_processed} processed, {requests_skipped} skipped, {len(errors)} errors"
            logger.info(f"✅ Email request monitoring complete: {summary}")

            # STEP 2: Update workflow states for all monitored email requests (after monitoring completes)
            logger.info(f"🔄 Updating workflow states for {len(email_requests)} email requests")
            workflow_states_updated = self._update_workflow_states_for_requests(email_requests, user_id)
            logger.info(f"✅ Updated workflow states for {workflow_states_updated} requests")

            return {
                'success': True,
                'emails_processed': requests_processed,
                'emails_skipped': requests_skipped,
                'changes_detected': changes_detected,
                'workflow_states_updated': workflow_states_updated,
                'errors': errors,
                'summary': summary
            }

        except Exception as e:
            logger.error(f"❌ Failed to monitor email requests: {str(e)}")
            return {
                'success': False,
                'emails_processed': 0,
                'emails_skipped': 0,
                'changes_detected': 0,
                'error': str(e),
                'summary': f'Error: {str(e)}'
            }

    def _fetch_new_emails(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Fetch unprocessed emails from Gmail via MCP.

        Args:
            user_id: User ID to fetch emails for

        Returns:
            List of email dicts with id, subject, from, date, body (preview)
        """
        try:
            # Get user's email address from database
            user_email = self.db.get_user_email(user_id)

            if not user_email:
                logger.error(f"No email found for user {user_id}")
                return []

            # Search Gmail via MCP
            # Query: from NextRequest (don't filter by 'to' since emails may be forwarded/aliased)
            query = "from:messages@nextrequest.com in:inbox"

            logger.debug(f"Searching Gmail with query: {query}")

            # Connect to Gmail MCP server and search
            with MCPGmailClient() as mcp:
                emails = mcp.search_emails(query, max_results=50)

            logger.info(f"Fetched {len(emails)} emails from Gmail for user {user_id}")
            return emails

        except Exception as e:
            logger.error(f"Failed to fetch emails: {str(e)}")
            return []

    def _read_full_email(self, email_id: str) -> Dict[str, Any]:
        """
        Read full email body from Gmail via MCP.

        Args:
            email_id: Gmail message ID

        Returns:
            Email dict with complete body content
        """
        try:
            # Connect to Gmail MCP server and read email
            with MCPGmailClient() as mcp:
                email = mcp.read_email(email_id)

            if email:
                logger.debug(f"Read full email {email_id}")
                return email
            else:
                logger.warning(f"Failed to read email {email_id}")
                return {'id': email_id, 'body': ''}

        except Exception as e:
            logger.error(f"Failed to read email {email_id}: {str(e)}")
            return {'id': email_id, 'body': ''}

    def _is_email_processed(self, email_id: str) -> bool:
        """
        Check if email ID has already been processed.

        Args:
            email_id: Gmail message ID

        Returns:
            True if email already processed, False otherwise
        """
        try:
            # Query database for any request with this email_id in processed_gmail_ids
            # Use @> operator for JSONB array containment in Postgres
            result = self.db.supabase.table('requests').select('id').filter(
                'processed_gmail_ids', 'cs', f'["{email_id}"]'
            ).execute()

            return len(result.data) > 0

        except Exception as e:
            logger.error(f"Error checking if email processed: {str(e)}")
            # Return False to allow processing (fail open)
            return False

    def _match_email_to_request(
        self,
        user_id: str,
        request_number: str,
        agency_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Match email to database request using two-step strategy.

        Args:
            user_id: User ID
            request_number: Extracted request number (e.g., "25-507")
            agency_name: Extracted agency name (e.g., "City of Hollister")

        Returns:
            Matching request dict, or None if no match found
        """
        try:
            # Query: Get all requests with this request_number for this user
            result = self.db.supabase.table('requests').select('*').eq(
                'user_id', user_id
            ).eq('request_number', request_number).execute()

            candidates = result.data

            if not candidates:
                logger.warning(f"No requests found for user {user_id} with request_number {request_number}")
                return None

            # Fast path: If only one match, use it
            if len(candidates) == 1:
                logger.info(f"Single match found for {request_number}")
                return candidates[0]

            # Multiple matches: Fuzzy match agency_name against portal_name
            logger.info(f"Multiple matches ({len(candidates)}) for {request_number}, using fuzzy matching")
            best_match = fuzzy_match_portal(agency_name, candidates)

            return best_match

        except Exception as e:
            logger.error(f"Error matching email to request: {str(e)}")
            return None

    def _analyze_email_content(
        self,
        email: Dict[str, Any],
        request: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Analyze email using Gmail-specific prompt with COMPLETE thread context.

        This method fetches ALL email bodies in the thread and provides them
        to the LLM for complete timeline extraction (no incremental accumulation).

        Args:
            email: Current email dict with id, subject, from, date, body
            request: Request dict from database

        Returns:
            RequestDetailAnalysis object from LLM, or None if analysis fails
        """
        try:
            # 1. Fetch COMPLETE conversation by searching Gmail for this request
            #    This gets ALL emails for this request (no limit, no missing correspondence)
            all_messages = self._fetch_all_thread_emails(
                request_number=request['request_number'],
                request_id=request['id'],
                portal_type=request.get('portal_type', 'portal'),
                gmail_thread_id=request.get('gmail_thread_id'),
                email_subject=request.get('email_subject')  # Use stored subject if available
            )

            # Note: Sorting already done in _fetch_all_thread_emails

            # 2. Extract request context
            request_text = request.get('request_text', 'Not available')
            current_status = request.get('current_status', 'Unknown')
            portal_name = request.get('portal_name', '')

            # 3. Call Gmail-specific analysis with COMPLETE conversation thread
            analysis = self.gmail_helper.analyze_gmail_request_thread(
                request_number=request['request_number'],
                request_text=request_text,
                portal_name=portal_name,
                email_thread=all_messages,  # Complete bidirectional conversation
                current_status=current_status
            )

            return analysis

        except Exception as e:
            logger.error(f"Failed to analyze email content: {str(e)}")
            return None

    def _fetch_all_thread_emails(
        self,
        request_number: str,
        request_id: str,
        portal_type: str = 'portal',
        gmail_thread_id: Optional[str] = None,
        email_subject: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch COMPLETE conversation thread including emails AND sent messages.

        Supports BOTH portal-based and email-based requests:
        - Portal requests: Search Gmail by request number in subject
        - Email requests: Search by subject (stored in DB), filter by thread_id

        This builds the full bidirectional conversation timeline:
        - ALL emails from agency TO user (from Gmail)
        - ALL messages from user TO agency (from database)

        Sorted chronologically to match portal's complete view.

        Args:
            request_number: Request number to search for (e.g., "25-131" or thread_id for email)
            request_id: Database ID of the request (to fetch sent messages)
            portal_type: 'portal' or 'email' to determine search strategy
            gmail_thread_id: Gmail thread ID (required for email-based requests)
            email_subject: Email subject (for email-based requests, stored in DB)

        Returns:
            List of messages with complete bodies, sorted chronologically (newest first)
        """
        all_messages = []

        # Get user's email address for direction detection
        user_email = None
        try:
            request_result = self.db.supabase.table('requests').select('user_id').eq('id', request_id).single().execute()
            if request_result.data:
                user_id = request_result.data['user_id']
                user_email = self.db.get_user_email(user_id)
                logger.info(f"User email for direction detection: {user_email}")
        except Exception as e:
            logger.warning(f"Could not fetch user email for direction detection: {e}")

        # 1. Fetch ALL emails for this request from Gmail
        try:
            with MCPGmailClient() as mcp:
                if portal_type == 'email':
                    # Email-based request: fetch thread directly by ID.
                    # InboxClassifier ensures gmail_thread_id points to the live
                    # conversation thread before monitoring runs, so no subject
                    # search or thread_id filtering is needed here.
                    if gmail_thread_id:
                        logger.info(f"🔍 Fetching thread directly: {gmail_thread_id}")
                        emails = mcp.search_thread(gmail_thread_id)
                        logger.info(f"📧 Found {len(emails)} message(s) in thread {gmail_thread_id}")
                    else:
                        logger.warning(f"No gmail_thread_id for email request {request_number}, skipping")
                        emails = []
                else:
                    # Portal-based request: Search by request number in subject
                    logger.info(f"🔍 Searching Gmail for ALL emails matching request {request_number}")
                    search_query = f"subject:{request_number}"
                    emails = mcp.search_emails(search_query, max_results=100)  # Generous limit per request
                    logger.info(f"📧 Found {len(emails)} emails for request")

                # Fetch full body for each email
                for email_summary in emails:
                    try:
                        email_id = email_summary.get('id')
                        email = mcp.read_email(email_id)

                        if email and email.get('body'):
                            # Determine direction: check if email is FROM the user
                            from_address = email.get('from', '').lower()
                            direction = 'incoming'  # Default: Agency → User

                            if user_email and user_email.lower() in from_address:
                                direction = 'outgoing'  # User → Agency

                            logger.info(f"📨 Email from: {from_address}, user_email: {user_email}, direction: {direction}, date: {email.get('date', 'NO DATE')}")

                            email_dict = {
                                'type': 'email',
                                'date': email.get('date', ''),
                                'from': email.get('from', ''),
                                'subject': email.get('subject', ''),
                                'body': email.get('body', ''),
                                'direction': direction
                            }
                            all_messages.append(email_dict)
                            logger.debug(f"   ✓ [{direction}] {email.get('subject', 'No subject')[:60]}")
                        else:
                            logger.warning(f"Email {email_id} has no body, skipping")

                    except Exception as e:
                        logger.warning(f"Could not fetch email {email_id}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Failed to search Gmail for request {request_number}: {e}")
            # Continue with just sent messages if Gmail search fails

        # 2. Fetch ALL sent messages (user → agency) from database
        logger.debug(f"📤 Fetching sent messages for request {request_id}")

        try:
            sent_messages = self.db.supabase.table('message_drafts').select('*').eq(
                'request_id', request_id
            ).eq('draft_status', 'sent').execute()

            for msg in sent_messages.data or []:
                message_dict = {
                    'type': 'sent_message',  # Mark as outgoing message
                    'date': msg.get('sent_at', msg.get('created_at', '')),
                    'from': 'You',  # User sent this
                    'subject': msg.get('draft_subject', 'Message to agency'),
                    'body': msg.get('draft_message', ''),
                    'direction': 'outgoing'  # User → Agency
                }
                all_messages.append(message_dict)
                logger.debug(f"   ✓ {msg.get('draft_subject', 'No subject')[:60]}")

        except Exception as e:
            logger.warning(f"Could not fetch sent messages: {e}")
            # Continue with just emails if database fetch fails

        # 3. Sort ALL messages chronologically (oldest first - natural conversation order)
        # This allows LLM to easily see who sent the most recent message
        # IMPORTANT: Parse dates to timestamps for proper timezone-aware sorting
        from email.utils import parsedate_to_datetime

        def get_timestamp(msg):
            try:
                date_str = msg.get('date', '')
                if date_str:
                    dt = parsedate_to_datetime(date_str)
                    return dt.timestamp()
                return 0
            except:
                return 0

        all_messages.sort(key=get_timestamp, reverse=False)

        logger.info(f"✅ Complete conversation: {len(all_messages)} messages total "
                   f"({sum(1 for m in all_messages if m['direction'] == 'incoming')} incoming, "
                   f"{sum(1 for m in all_messages if m['direction'] == 'outgoing')} outgoing)")

        return all_messages

    def _build_timeline_from_emails(
        self,
        request: Dict[str, Any],
        new_email: Dict[str, Any]
    ) -> str:
        """
        DEPRECATED: This method used incremental timeline accumulation (lossy).
        Now using _fetch_all_thread_emails() + analyze_gmail_request_thread()
        for complete context extraction.

        Kept for backward compatibility but no longer used in production.

        Args:
            request: Request dict from database
            new_email: New email dict

        Returns:
            Combined timeline text
        """
        try:
            # Get existing timeline from latest_analysis_gmail (if exists)
            existing_analysis = request.get('latest_analysis_gmail', {})
            existing_timeline = existing_analysis.get('all_timeline_events', [])

            # Format new email as timeline event
            email_date = self.gmail_helper.parse_email_date(new_email.get('date', ''))
            sender = self.gmail_helper.identify_sender(
                new_email.get('from', ''),
                new_email.get('body', '')
            )

            # Truncate body for timeline (full body is in "LATEST EMAIL" section)
            body_preview = new_email.get('body', '')[:200]
            if len(new_email.get('body', '')) > 200:
                body_preview += '...'

            new_event = f"{email_date}: {sender} {body_preview}"

            # Combine timelines
            updated_timeline = existing_timeline + [new_event]

            # Return as formatted text
            return "\n".join(updated_timeline)

        except Exception as e:
            logger.error(f"Error building timeline: {str(e)}")
            # Return just the new email on error
            return f"Latest email: {new_email.get('subject', 'Unknown')}"

    def _update_workflow_states_for_requests(self, requests: List[Dict], user_id: str) -> int:
        """
        Update workflow states for all email requests based on current database state.
        This runs AFTER monitoring completes so it sees the final state.

        Args:
            requests: List of request records from monitoring
            user_id: User ID for logging

        Returns:
            Number of workflow states successfully updated
        """
        updated_count = 0

        for request in requests:
            try:
                request_id = request['id']
                request_number = request.get('request_number', 'unknown')

                # Re-fetch request from database to get CURRENT state (after monitoring updates)
                request_data_result = self.db.supabase.table('requests').select('*').eq('id', request_id).execute()

                if not request_data_result.data:
                    logger.warning(f"Could not fetch request {request_number} for workflow state update")
                    continue

                request_data = request_data_result.data[0]

                # Build request_data dict from DATABASE state
                # For email requests, use latest_analysis_gmail instead of latest_analysis
                request_info = {
                    'id': request_data['id'],
                    'current_status': request_data.get('current_status', 'Unknown'),
                    'agent_attention_needed': request_data.get('agent_attention_needed', False),
                    'agent_attention_reason': request_data.get('agent_attention_reason', ''),
                    'agent_attention_priority': request_data.get('agent_attention_priority', 'low'),
                    'latest_analysis': request_data.get('latest_analysis_gmail', {})  # Use gmail analysis for email requests
                }

                # Check for pending draft
                draft_info = None
                try:
                    drafts = self.db.supabase.table('message_drafts').select('*').eq(
                        'request_id', request_id
                    ).in_('draft_status', ['drafted', 'pending_approval', 'edited']).execute()

                    if drafts.data:
                        latest_draft = drafts.data[0]
                        draft_info = {
                            'has_pending_draft': True,
                            'draft_message': latest_draft.get('draft_message', ''),
                            'draft_created_at': latest_draft.get('created_at', ''),
                            'draft_message_type': latest_draft.get('draft_message_type', 'unknown'),
                            'draft_status': latest_draft.get('draft_status', 'unknown')
                        }
                except Exception as e:
                    logger.warning(f"⚠️  Failed to check drafts for {request_number}: {e}")

                # Check for documents
                documents_status = None
                try:
                    docs = self.db.supabase.table('document_downloads').select('*').eq(
                        'request_id', request_id
                    ).execute()

                    if docs.data:
                        documents_status = {
                            'total_documents': len(docs.data),
                            'all_uploaded': all(d['download_status'] == 'uploaded_to_drive' for d in docs.data),
                            'any_pending': any(d['download_status'] in ['pending', 'completed'] for d in docs.data)
                        }
                except Exception as e:
                    logger.warning(f"⚠️  Failed to check documents for {request_number}: {e}")

                # Determine workflow state based on COMPLETE database state
                workflow_state = self.workflow_state_helper.determine_workflow_state(
                    request_data=request_info,
                    draft_info=draft_info,
                    documents_status=documents_status
                )

                # Update workflow state in database
                success = self.db.update_workflow_state_only(request_id, workflow_state)
                if success:
                    updated_count += 1
                    logger.info(f"🔄 Updated workflow_state for {request_number}")

            except Exception as e:
                logger.error(f"❌ Failed to update workflow state for request {request.get('request_number', 'unknown')}: {str(e)}")

        return updated_count
