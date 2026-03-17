"""
Email-based request submission agent.

Lightweight agent for submitting FOIA requests via email (no browser automation needed).
Uses Gmail MCP for all email operations.
"""

import logging
from typing import Dict, Any, Optional
from mcp_gmail_client import MCPGmailClient
from supabase_integration import SupabaseIntegration
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailAgent:
    """
    Email-based request submission agent.
    Uses Gmail API/MCP for all operations (no browser needed).
    """

    def __init__(self, llm_client, user_email: str):
        """
        Initialize EmailAgent.

        Args:
            llm_client: LLM client (for future use - template-based for now)
            user_email: User's email address (sender)
        """
        self.llm_client = llm_client
        self.user_email = user_email
        self.mcp_client = MCPGmailClient()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close MCP client"""
        if self.mcp_client:
            self.mcp_client.close()

    def _format_foia_email(
        self,
        request_text: str,
        user_info: Dict[str, str],
        agency_name: str = None,
        request_category: str = ''
    ) -> Dict[str, str]:
        """
        Format FOIA request email using template.

        Args:
            request_text: Request text from user
            user_info: User details (full_name, email, address, phone)
            agency_name: Agency name (makes subject more unique for monitoring)
            request_category: Request category from user_notes (e.g., "UOF data 2024")

        Returns:
            {
                'subject': 'Public Records Request - [Agency Name] - [Category]',
                'body': 'Dear Records Custodian,\n\n...'
            }
        """
        # Build subject with agency name and category for uniqueness
        # Priority: request_category > topic from user_info > generic
        category = request_category or user_info.get('topic', 'Information Request')

        if agency_name:
            subject = f"Public Records Request - {agency_name} - {category}"
        else:
            subject = f"Public Records Request - {category}"

        # Get user details with fallbacks
        full_name = user_info.get('full_name', user_info.get('requester_name', 'N/A'))
        email = user_info.get('email', user_info.get('requester_email', self.user_email))
        address = user_info.get('address', user_info.get('street_address', 'N/A'))
        phone = user_info.get('phone', user_info.get('requester_phone', 'N/A'))

        # Just use the request text as-is, no boilerplate
        body = request_text

        return {
            'subject': subject,
            'body': body
        }

    def submit_request(
        self,
        agency_email: str,
        request_text: str,
        user_info: Dict[str, str],
        db: SupabaseIntegration,
        portal_id: str,
        submission_queue_id: str,
        request_category: str = ''
    ) -> Dict[str, Any]:
        """
        Submit FOIA request via email.

        Steps:
        1. Format email body from request_text + user_info
        2. Send via Gmail MCP to agency_email
        3. Capture thread_id from send response
        4. Create requests table entry with gmail_thread_id
        5. Mark submission_queue entry as 'completed'

        Args:
            agency_email: Agency contact email (e.g., 'records@sfpd.org')
            request_text: FOIA request text from user
            user_info: Dict with user details (full_name, email, address, etc.)
            db: SupabaseIntegration instance
            portal_id: Portal ID (for database linking)
            submission_queue_id: Queue entry ID to mark complete

        Returns:
            {
                'success': bool,
                'thread_id': str,
                'request_id': str,  # Database ID
                'error': str (if failed)
            }
        """
        try:
            logger.info(f"📧 Submitting email request to {agency_email}")

            # Fetch agency_name from portals table for unique subject
            agency_name = None
            try:
                portal_result = db.supabase.table('portals').select('agency_name').eq('id', portal_id).single().execute()
                if portal_result.data:
                    agency_name = portal_result.data.get('agency_name')
                    logger.info(f"📋 Agency: {agency_name}")
            except Exception as e:
                logger.warning(f"⚠️  Could not fetch agency_name: {e}")

            # Format email
            email = self._format_foia_email(request_text, user_info, agency_name, request_category)
            logger.info(f"📝 Subject: {email['subject']}")

            # Send via Gmail
            with self.mcp_client:
                send_result = self.mcp_client.send_email(
                    to=agency_email,
                    subject=email['subject'],
                    body=email['body'],
                    thread_id=None  # New thread
                )

            if not send_result['success']:
                logger.error(f"❌ Email send failed: {send_result.get('error')}")
                return {'success': False, 'error': send_result.get('error')}

            thread_id = send_result['thread_id']
            logger.info(f"✅ Email sent, thread_id: {thread_id}")

            # Get user_id from user_info or submission queue data
            user_id = user_info.get('user_id')
            if not user_id:
                logger.error("❌ user_id not found in user_info")
                return {'success': False, 'error': 'user_id missing from user_info'}

            # Create request in database
            request_data = {
                'user_id': user_id,
                'request_number': thread_id,  # Use thread_id as identifier
                'request_text': request_text,
                'portal_type': 'email',
                'gmail_thread_id': thread_id,
                'current_status': 'Submitted',
                'portal_name': agency_email,  # Store email address in portal_name
                'email_subject': email['subject'],  # Store subject for efficient monitoring
                'user_notes': request_category  # Category/tag for frontend filtering
            }

            request_result = db.supabase.table('requests').insert(request_data).execute()

            if not request_result.data:
                logger.error("❌ Failed to create request in database")
                return {'success': False, 'error': 'Database insert failed'}

            request_id = request_result.data[0]['id']
            logger.info(f"✅ Request created: {request_id}")

            # Mark submission complete (matching portal pattern)
            db.supabase.table('submission_queue').update({
                'status': 'completed',
                'submitted_request_id': request_id,
                'submitted_request_number': thread_id,
                'linked_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'queued_for_analysis': True  # Email sent and request created successfully
            }).eq('id', submission_queue_id).execute()

            logger.info(f"✅ Submission queue entry marked complete")

            return {
                'success': True,
                'thread_id': thread_id,
                'request_id': request_id
            }

        except Exception as e:
            logger.error(f"❌ Request submission failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
