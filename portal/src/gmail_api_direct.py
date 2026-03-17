"""
Gmail API Direct Access Module

This module provides direct Gmail API access for sending emails with proper
RFC 2822 threading headers. Used as a hybrid approach:
- MCP server for reading/searching emails
- Gmail API for sending threaded replies

Why Direct API:
- MCP server doesn't properly set In-Reply-To and References headers
- Recipients see replies as separate conversations
- Gmail API provides full control over email headers

Authentication:
- Uses OAuth credentials from credentials.json
- Stores token in ~/gmail_token.json for reuse
- Requires GMAIL_SEND and GMAIL_READONLY scopes
"""

import os
import base64
from email.mime.text import MIMEText
from typing import Optional, Dict, Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import logging

logger = logging.getLogger(__name__)

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]


class GmailAPIClient:
    """Direct Gmail API client for sending threaded emails."""

    def __init__(self, credentials_path: str = None, token_path: str = None):
        """
        Initialize Gmail API client.

        Args:
            credentials_path: Path to OAuth credentials.json (defaults to ./credentials.json)
            token_path: Path to store/load token (defaults to ~/gmail_token.json)
        """
        if credentials_path is None:
            credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')

        if token_path is None:
            token_path = os.path.expanduser('~/gmail_token.json')

        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API using OAuth credentials."""
        creds = None

        # Try to load existing token
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
                logger.info(f"✅ Loaded Gmail API credentials from {self.token_path}")
            except Exception as e:
                logger.warning(f"⚠️  Could not load token from {self.token_path}: {e}")

        # Refresh or authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("🔄 Refreshing expired Gmail API token...")
                creds.refresh(Request())
            else:
                logger.info("🔑 Starting OAuth authentication flow for Gmail API...")

                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"credentials.json not found at {self.credentials_path}\n"
                        f"Please create OAuth 2.0 Desktop App credentials and save as credentials.json"
                    )

                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
            logger.info(f"💾 Saved Gmail API credentials to {self.token_path}")

        # Build Gmail service
        self.service = build('gmail', 'v1', credentials=creds)
        logger.info("✅ Gmail API service initialized")

    def get_message_id_header(self, gmail_message_id: str) -> Optional[str]:
        """
        Get the RFC 2822 Message-ID header from a Gmail message.

        Args:
            gmail_message_id: Gmail internal message ID (e.g., "19bbb36ee4b985fb")

        Returns:
            Message-ID header value with angle brackets (e.g., "<CABc123@mail.gmail.com>")
            or None if not found
        """
        try:
            # Fetch message with full headers
            message = self.service.users().messages().get(
                userId='me',
                id=gmail_message_id,
                format='full'
            ).execute()

            # Extract Message-ID from headers
            headers = message.get('payload', {}).get('headers', [])
            for header in headers:
                if header.get('name', '').lower() == 'message-id':
                    message_id = header.get('value', '')
                    logger.debug(f"📧 Extracted Message-ID: {message_id} from Gmail ID: {gmail_message_id}")
                    return message_id

            logger.warning(f"⚠️  No Message-ID header found in message {gmail_message_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Error getting Message-ID header: {e}")
            return None

    def send_threaded_email(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an email with proper RFC 2822 threading headers.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            thread_id: Gmail thread ID for sender-side threading
            in_reply_to: RFC 2822 Message-ID of email being replied to (with angle brackets)
            references: Space-separated list of Message-IDs in thread (with angle brackets)

        Returns:
            Dictionary with:
                - success: bool
                - message_id: Gmail internal message ID
                - thread_id: Gmail thread ID
                - error: Optional error message
        """
        try:
            # Create MIME message
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject

            # Add threading headers
            if in_reply_to:
                message['In-Reply-To'] = in_reply_to
                logger.info(f"📧 Set In-Reply-To: {in_reply_to}")

            if references:
                message['References'] = references
                logger.info(f"📧 Set References: {references}")

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # Send with thread_id for sender-side threading
            body_params = {
                'raw': raw_message,
                'threadId': thread_id
            }

            logger.info(f"📧 Sending threaded email via Gmail API...")
            logger.info(f"   To: {to}")
            logger.info(f"   Subject: {subject}")
            logger.info(f"   Thread ID: {thread_id}")

            sent_message = self.service.users().messages().send(
                userId='me',
                body=body_params
            ).execute()

            logger.info(f"✅ Email sent successfully!")
            logger.info(f"   Gmail Message ID: {sent_message['id']}")
            logger.info(f"   Gmail Thread ID: {sent_message['threadId']}")

            return {
                'success': True,
                'message_id': sent_message['id'],
                'thread_id': sent_message['threadId']
            }

        except Exception as e:
            logger.error(f"❌ Error sending email via Gmail API: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an email (new or reply).

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            thread_id: Optional Gmail thread ID for replies
            in_reply_to: Optional RFC 2822 Message-ID for replies

        Returns:
            Dictionary with:
                - success: bool
                - message_id: Gmail internal message ID
                - thread_id: Gmail thread ID
                - error: Optional error message
        """
        # If this is a reply, use send_threaded_email
        if thread_id and in_reply_to:
            # Use in_reply_to as references too (for single reply in thread)
            return self.send_threaded_email(
                to=to,
                subject=subject,
                body=body,
                thread_id=thread_id,
                in_reply_to=in_reply_to,
                references=in_reply_to
            )

        # Otherwise, send new email without threading
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            logger.info(f"📧 Sending new email via Gmail API...")
            logger.info(f"   To: {to}")
            logger.info(f"   Subject: {subject}")

            sent_message = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()

            logger.info(f"✅ Email sent successfully!")
            logger.info(f"   Gmail Message ID: {sent_message['id']}")
            logger.info(f"   Gmail Thread ID: {sent_message['threadId']}")

            return {
                'success': True,
                'message_id': sent_message['id'],
                'thread_id': sent_message['threadId']
            }

        except Exception as e:
            logger.error(f"❌ Error sending email via Gmail API: {e}")
            return {
                'success': False,
                'error': str(e)
            }


# Convenience function for quick usage
def send_threaded_reply(
    to: str,
    subject: str,
    body: str,
    thread_id: str,
    in_reply_to: str
) -> Dict[str, Any]:
    """
    Quick function to send a threaded reply using Gmail API.

    Args:
        to: Recipient email address
        subject: Email subject (should start with "Re: ")
        body: Email body
        thread_id: Gmail thread ID
        in_reply_to: RFC 2822 Message-ID of email being replied to

    Returns:
        Dictionary with success status and message details
    """
    client = GmailAPIClient()
    return client.send_threaded_email(
        to=to,
        subject=subject,
        body=body,
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=in_reply_to
    )
