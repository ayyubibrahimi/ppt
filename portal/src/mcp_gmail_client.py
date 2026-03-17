import subprocess
import json
import logging
import threading
import queue
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class MCPGmailClient:
    """
    MCP (Model Context Protocol) client for Gmail server.
    Communicates with @gongrzhe/server-gmail-autoauth-mcp via stdio.
    """

    def __init__(self):
        """Initialize MCP client and start Gmail server process"""
        self.process = None
        self.request_id = 1
        self.pending_requests = {}
        self.response_queue = queue.Queue()
        self.reader_thread = None
        self.initialized = False

    def connect(self):
        """Start the Gmail MCP server process and initialize connection"""
        try:
            logger.info("📧 Starting Gmail MCP server...")

            # Start the MCP server process
            self.process = subprocess.Popen(
                ['npx', '@gongrzhe/server-gmail-autoauth-mcp'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            # Start background thread to read responses
            self.reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self.reader_thread.start()

            # Initialize the connection
            init_result = self._send_request('initialize', {
                'protocolVersion': '2024-11-05',
                'capabilities': {
                    'roots': {'listChanged': True},
                    'sampling': {}
                },
                'clientInfo': {
                    'name': 'gmail-monitoring-agent',
                    'version': '1.0.0'
                }
            })

            if init_result:
                logger.info(f"✅ Gmail MCP server initialized: {init_result.get('serverInfo', {}).get('name')}")
                self.initialized = True
                return True
            else:
                logger.error("❌ Failed to initialize Gmail MCP server")
                return False

        except Exception as e:
            logger.error(f"❌ Failed to connect to Gmail MCP server: {str(e)}")
            return False

    def _read_responses(self):
        """Background thread to read responses from MCP server"""
        try:
            while self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    break

                try:
                    response = json.loads(line.strip())

                    # Handle response
                    if 'id' in response:
                        request_id = response['id']
                        if request_id in self.pending_requests:
                            self.pending_requests[request_id].put(response)

                except json.JSONDecodeError:
                    logger.debug(f"Non-JSON line from MCP server: {line.strip()}")

        except Exception as e:
            logger.error(f"Error in response reader thread: {str(e)}")

    def _send_request(self, method: str, params: Dict[str, Any], timeout: int = 30) -> Optional[Dict[str, Any]]:
        """
        Send a JSON-RPC request to the MCP server.

        Args:
            method: RPC method name
            params: Method parameters
            timeout: Request timeout in seconds

        Returns:
            Response result dict, or None if request failed
        """
        try:
            request_id = self.request_id
            self.request_id += 1

            request = {
                'jsonrpc': '2.0',
                'id': request_id,
                'method': method,
                'params': params
            }

            # Create response queue for this request
            response_queue = queue.Queue()
            self.pending_requests[request_id] = response_queue

            # Send request
            request_json = json.dumps(request) + '\n'
            self.process.stdin.write(request_json)
            self.process.stdin.flush()

            logger.debug(f"Sent MCP request: {method}")

            # Wait for response
            try:
                response = response_queue.get(timeout=timeout)
                del self.pending_requests[request_id]

                if 'error' in response:
                    logger.error(f"MCP error: {response['error']}")
                    return None

                return response.get('result')

            except queue.Empty:
                logger.error(f"MCP request timeout for {method}")
                del self.pending_requests[request_id]
                return None

        except Exception as e:
            logger.error(f"Failed to send MCP request: {str(e)}")
            return None

    def search_emails(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Search Gmail using MCP server.

        Args:
            query: Gmail search query (e.g., "from:messages@nextrequest.com")
            max_results: Maximum number of emails to return

        Returns:
            List of email dicts with id, subject, from, date, snippet
        """
        try:
            if not self.initialized:
                logger.warning("MCP client not initialized, connecting...")
                if not self.connect():
                    return []

            result = self._send_request('tools/call', {
                'name': 'search_emails',
                'arguments': {
                    'query': query,
                    'maxResults': max_results
                }
            })

            if not result:
                return []

            # Parse the result
            # MCP returns: {"content": [{"type": "text", "text": "...email data..."}]}
            if 'content' in result and len(result['content']) > 0:
                content_text = result['content'][0].get('text', '')

                # Parse emails from text response
                emails = self._parse_email_list(content_text)
                logger.info(f"Found {len(emails)} emails from Gmail")
                return emails

            return []

        except Exception as e:
            logger.error(f"Failed to search emails: {str(e)}")
            return []

    def read_email(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Read full email content from Gmail.

        Args:
            message_id: Gmail message ID

        Returns:
            Email dict with full body, or None if failed
        """
        try:
            if not self.initialized:
                logger.warning("MCP client not initialized, connecting...")
                if not self.connect():
                    return None

            result = self._send_request('tools/call', {
                'name': 'read_email',
                'arguments': {
                    'messageId': message_id
                }
            })

            if not result:
                return None

            # Parse the result
            if 'content' in result and len(result['content']) > 0:
                content_text = result['content'][0].get('text', '')

                # Parse email from text response
                email = self._parse_email_detail(content_text, message_id)
                return email

            return None

        except Exception as e:
            logger.error(f"Failed to read email {message_id}: {str(e)}")
            return None

    def _parse_email_list(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse email list from MCP text response.

        Expected format:
        ID: 19b90e924ba42d76
        Subject: [External Message Added] City of Manteca request #25-501
        From: City of Manteca <messages@nextrequest.com>
        Date: Tue, 06 Jan 2026 01:25:56 +0000

        ID: 19b90c333bcecb0b
        Subject: ...
        """
        emails = []
        current_email = {}

        for line in text.split('\n'):
            line = line.strip()

            if line.startswith('ID: '):
                # Save previous email if exists
                if current_email and 'id' in current_email:
                    emails.append(current_email)

                # Start new email
                current_email = {'id': line[4:].strip()}

            elif line.startswith('Subject: '):
                current_email['subject'] = line[9:].strip()

            elif line.startswith('From: '):
                current_email['from'] = line[6:].strip()

            elif line.startswith('Date: '):
                current_email['date'] = line[6:].strip()

            elif line.startswith('Thread ID: '):
                current_email['thread_id'] = line[11:].strip()

        # Add last email
        if current_email and 'id' in current_email:
            emails.append(current_email)

        return emails

    def _parse_email_detail(self, text: str, message_id: str) -> Dict[str, Any]:
        """
        Parse detailed email from MCP text response.

        Expected format:
        Thread ID: 19b90e924ba42d76
        Subject: [External Message Added] City of Manteca request #25-501
        From: City of Manteca <messages@nextrequest.com>
        To: admin@mljusticelab.com
        Date: Tue, 06 Jan 2026 01:25:56 +0000

        [email body content]
        """
        email = {'id': message_id}
        body_lines = []
        in_body = False

        for line in text.split('\n'):

            if line.strip().startswith('Thread ID: '):
                email['thread_id'] = line.strip()[11:]

            elif line.strip().startswith('Subject: '):
                email['subject'] = line.strip()[9:]

            elif line.strip().startswith('From: '):
                email['from'] = line.strip()[6:]

            elif line.strip().startswith('To: '):
                email['to'] = line.strip()[4:]

            elif line.strip().startswith('Date: '):
                email['date'] = line.strip()[6:]
                in_body = True  # Body starts after headers

            elif in_body:
                body_lines.append(line)

        raw_body = '\n'.join(body_lines).strip()

        # Clean email body for LLM analysis
        email['body'] = self._clean_email_body(raw_body)
        return email

    def _clean_email_body(self, body: str) -> str:
        """
        Clean email body by removing HTML artifacts, footers, and noise.

        Removes:
        - HTML tags
        - Decorative separators
        - Email footers (technical support, disclaimers)
        - NextRequest system headers

        Args:
            body: Raw email body text

        Returns:
            Cleaned body text suitable for LLM analysis
        """
        # Remove HTML tags
        body = re.sub(r'<[^>]+>', '', body)

        # Remove decorative separators (lines of asterisks, equals, hyphens)
        body = re.sub(r'^[*=\-]{10,}$', '', body, flags=re.MULTILINE)

        # Remove common email footer patterns
        footer_patterns = [
            r'Questions about your request\?.*?$',
            r'Technical support:.*?$',
            r'See our.*?help.*?$',
            r'Reply to this email or sign in.*?$',
            r'This is an automated message.*?$',
            r'Do not reply to this email.*?$',
            r'Please do not reply.*?$',
            r'To unsubscribe.*?$',
        ]

        for pattern in footer_patterns:
            body = re.sub(pattern, '', body, flags=re.IGNORECASE | re.MULTILINE)

        # Remove NextRequest system header
        body = re.sub(r'^.*?A message was sent to you regarding record request.*?:?\s*$', '', body, flags=re.MULTILINE)

        # Remove excessive blank lines (keep max 2 consecutive)
        body = re.sub(r'\n{3,}', '\n\n', body)

        # Strip leading/trailing whitespace
        body = body.strip()

        return body

    # ========== Email Sending Methods (for Email-Based Request System) ==========

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send email via Gmail API.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            thread_id: Optional - if provided, sends as reply in thread (sender-side threading)
            in_reply_to: Optional - Message-ID of email being replied to (recipient-side threading)

        Returns:
            {
                'success': bool,
                'message_id': str,
                'thread_id': str,
                'error': str (if failed)
            }

        Use cases:
        1. New request submission (thread_id=None, in_reply_to=None)
        2. Reply messages (thread_id=existing, in_reply_to=message_id of last agency email)

        Note: For proper threading on recipient's side, BOTH thread_id and in_reply_to should be provided.
        """
        try:
            if not self.initialized:
                logger.warning("MCP client not initialized, connecting...")
                if not self.connect():
                    return {'success': False, 'error': 'Failed to connect to Gmail MCP server'}

            logger.info(f"📧 Sending email to {to}" + (f" (thread: {thread_id})" if thread_id else " (new thread)"))

            # Prepare arguments
            # IMPORTANT: MCP server expects 'to' as an array, not a string
            arguments = {
                'to': [to] if isinstance(to, str) else to,  # Convert string to array
                'subject': subject,
                'body': body
            }

            # Add threading parameters if replying to existing thread
            if thread_id:
                arguments['threadId'] = thread_id

            # CRITICAL: Add inReplyTo for proper recipient-side threading
            # This sets the In-Reply-To and References headers per RFC 2822
            if in_reply_to:
                arguments['inReplyTo'] = in_reply_to
                logger.info(f"📧 Setting In-Reply-To header: {in_reply_to}")

            result = self._send_request('tools/call', {
                'name': 'send_email',
                'arguments': arguments
            })

            if not result:
                return {'success': False, 'error': 'No response from MCP server'}

            # Parse the result
            # Format: "Email sent successfully with ID: 19bba87d16a99e37"
            if 'content' in result and len(result['content']) > 0:
                content_text = result['content'][0].get('text', '')

                # Extract message_id from send response
                # Pattern: "Email sent successfully with ID: <message_id>"
                import re
                match = re.search(r'ID:\s*(\S+)', content_text)

                if not match:
                    logger.error(f"Could not extract message_id from response: {content_text}")
                    return {'success': False, 'error': 'Could not extract message_id from response'}

                message_id = match.group(1)
                logger.info(f"✅ Email sent successfully (message_id: {message_id})")

                # Now read the email we just sent to get the thread_id
                # This is necessary because send_email only returns message_id, not thread_id
                import time
                time.sleep(1)  # Brief wait for Gmail to index the email

                try:
                    read_result = self._send_request('tools/call', {
                        'name': 'read_email',
                        'arguments': {
                            'messageId': message_id
                        }
                    })

                    if read_result and 'content' in read_result:
                        email_text = read_result['content'][0].get('text', '')

                        # Extract thread_id: "Thread ID: 19bba87d16a99e37"
                        thread_match = re.search(r'Thread ID:\s*(\S+)', email_text)

                        if thread_match:
                            captured_thread_id = thread_match.group(1)
                            logger.info(f"✅ Captured thread_id: {captured_thread_id}")

                            return {
                                'success': True,
                                'message_id': message_id,
                                'thread_id': captured_thread_id,
                                'error': None
                            }
                        else:
                            logger.warning("Could not extract thread_id from email, using message_id as fallback")
                            return {
                                'success': True,
                                'message_id': message_id,
                                'thread_id': message_id,  # For new emails, thread_id == message_id
                                'error': None
                            }
                except Exception as e:
                    logger.warning(f"Could not read sent email to get thread_id: {str(e)}, using message_id as fallback")
                    return {
                        'success': True,
                        'message_id': message_id,
                        'thread_id': message_id,  # Fallback: for new emails, they're the same
                        'error': None
                    }

            return {'success': False, 'error': 'Invalid response format from MCP server'}

        except Exception as e:
            logger.error(f"❌ Failed to send email: {str(e)}")
            return {'success': False, 'error': str(e)}

    def search_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages in a thread by Gmail thread ID.

        Args:
            thread_id: Gmail thread ID

        Returns:
            List of message dicts (same format as search_emails)
        """
        try:
            if not self.initialized:
                logger.warning("MCP client not initialized, connecting...")
                if not self.connect():
                    return []

            logger.info(f"🔍 Fetching thread {thread_id}")

            result = self._send_request('tools/call', {
                'name': 'get_thread',
                'arguments': {
                    'threadId': thread_id
                }
            })

            if not result:
                logger.warning(f"No response when fetching thread {thread_id}")
                return []

            # Parse the result
            if 'content' in result and len(result['content']) > 0:
                content_text = result['content'][0].get('text', '')

                # Parse messages from text response (same format as email list)
                messages = self._parse_email_list(content_text)
                logger.info(f"Found {len(messages)} messages in thread {thread_id}")
                return messages

            return []

        except Exception as e:
            logger.error(f"❌ Failed to fetch thread {thread_id}: {str(e)}")
            return []

    def get_attachments(self, message_id: str, save_path: str = '/tmp') -> List[Dict[str, Any]]:
        """
        Download all attachments from an email using MCP's download_attachment tool.

        Args:
            message_id: Gmail message ID
            save_path: Directory to save attachments (default: /tmp)

        Returns:
            [
                {
                    'filename': 'document.pdf',
                    'filepath': '/tmp/document.pdf',
                    'mime_type': 'application/pdf',
                    'size': 12345,
                    'attachment_id': 'ANGjdJ...'
                },
                ...
            ]
        """
        import re
        import os

        try:
            if not self.initialized:
                logger.warning("MCP client not initialized, connecting...")
                if not self.connect():
                    return []

            logger.info(f"📎 Fetching attachments for message {message_id}")

            # First, read the email to get attachment metadata
            read_result = self._send_request('tools/call', {
                'name': 'read_email',
                'arguments': {
                    'messageId': message_id
                }
            })

            if not read_result or 'content' not in read_result:
                logger.debug(f"No email content for message {message_id}")
                return []

            email_text = read_result['content'][0].get('text', '')

            # Parse attachment info from email text
            # Format: "- filename (mime_type, size, ID: attachment_id)"
            # Fixed to handle filenames with spaces and parentheses (e.g., "checklist (dragged).pdf")
            # Non-greedy match (.+?) for filename, mime type must contain / to prevent false matches
            pattern = r'- (.+?) \(([\w]+/[\w\-\+\.]+), ([\d\.]+ [KMG]?B), ID: ([A-Za-z0-9_-]+)\)'
            matches = re.findall(pattern, email_text)

            if not matches:
                logger.debug(f"No attachments found in message {message_id}")
                return []

            logger.info(f"Found {len(matches)} attachment(s) to download")

            attachments = []

            for filename, mime_type, size_str, attachment_id in matches:
                try:
                    logger.info(f"Downloading: {filename} ({size_str})")

                    # Download attachment using MCP tool
                    download_result = self._send_request('tools/call', {
                        'name': 'download_attachment',
                        'arguments': {
                            'messageId': message_id,
                            'attachmentId': attachment_id,
                            'filename': filename,
                            'savePath': save_path
                        }
                    })

                    if download_result and 'content' in download_result:
                        response_text = download_result['content'][0].get('text', '')

                        # Check for success
                        if 'downloaded successfully' in response_text.lower():
                            filepath = os.path.join(save_path, filename)

                            # Get actual file size
                            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0

                            attachments.append({
                                'filename': filename,
                                'filepath': filepath,
                                'mime_type': mime_type,
                                'size': file_size,
                                'attachment_id': attachment_id
                            })

                            logger.info(f"✅ Downloaded: {filename} ({file_size} bytes)")
                        else:
                            logger.warning(f"Download may have failed for {filename}: {response_text}")
                    else:
                        logger.warning(f"No response from download_attachment for {filename}")

                except Exception as e:
                    logger.error(f"Failed to download {filename}: {str(e)}")
                    continue

            logger.info(f"Successfully downloaded {len(attachments)}/{len(matches)} attachments")
            return attachments

        except Exception as e:
            logger.error(f"❌ Failed to get attachments for {message_id}: {str(e)}")
            return []

    def get_message_id_header(self, gmail_message_id: str) -> Optional[str]:
        """
        Extract the RFC 2822 Message-ID header from an email.

        CRITICAL: This returns the Message-ID header (e.g., '<CABc123xyz@mail.gmail.com>')
        NOT the Gmail message ID (e.g., '19bbb39d2ea20fa0').

        The Message-ID header is required for proper email threading via In-Reply-To header.

        Args:
            gmail_message_id: Gmail's internal message ID

        Returns:
            Message-ID header with angle brackets (e.g., '<abc@mail.gmail.com>') or None
        """
        try:
            # Read the full email to get headers
            email = self.read_email(gmail_message_id)

            if not email:
                return None

            # The email body/text should contain the Message-ID header
            # We need to parse it from the raw response
            result = self._send_request('tools/call', {
                'name': 'read_email',
                'arguments': {
                    'messageId': gmail_message_id
                }
            })

            if not result or 'content' not in result:
                return None

            email_text = result['content'][0].get('text', '')

            # Look for Message-ID header (with angle brackets!)
            # Format: "Message-ID: <CABc123xyz@mail.gmail.com>"
            match = re.search(r'Message-ID:\s*(<[^>]+>)', email_text, re.IGNORECASE)

            if match:
                message_id_header = match.group(1)  # Returns "<CABc123xyz@mail.gmail.com>"
                logger.info(f"📧 Extracted Message-ID header: {message_id_header}")
                return message_id_header
            else:
                logger.warning(f"⚠️  Could not find Message-ID header in email {gmail_message_id}")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to extract Message-ID header: {str(e)}")
            return None

    def _extract_field(self, text: str, field_name: str) -> Optional[str]:
        """
        Extract field value from MCP response text.

        Args:
            text: Response text
            field_name: Field name to extract (e.g., 'Message ID', 'Thread ID')

        Returns:
            Field value or None if not found
        """
        pattern = rf'{field_name}:\s*(\S+)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1) if match else None

    def _parse_attachments(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse attachments from MCP text response.

        Expected format:
        Attachment 1:
        Filename: document.pdf
        MIME Type: application/pdf
        Size: 12345 bytes
        Content: <base64_encoded_data>

        Attachment 2:
        ...
        """
        import base64

        attachments = []
        current_attachment = {}

        for line in text.split('\n'):
            line = line.strip()

            if line.startswith('Attachment '):
                # Save previous attachment if exists
                if current_attachment and 'filename' in current_attachment:
                    attachments.append(current_attachment)

                # Start new attachment
                current_attachment = {}

            elif line.startswith('Filename: '):
                current_attachment['filename'] = line[10:].strip()

            elif line.startswith('MIME Type: '):
                current_attachment['mime_type'] = line[11:].strip()

            elif line.startswith('Size: '):
                size_str = line[6:].strip().replace(' bytes', '')
                try:
                    current_attachment['size'] = int(size_str)
                except ValueError:
                    current_attachment['size'] = 0

            elif line.startswith('Content: '):
                # Decode base64 content
                base64_content = line[9:].strip()
                try:
                    current_attachment['content'] = base64.b64decode(base64_content)
                except Exception as e:
                    logger.error(f"Failed to decode attachment content: {str(e)}")
                    current_attachment['content'] = b''

        # Add last attachment
        if current_attachment and 'filename' in current_attachment:
            attachments.append(current_attachment)

        return attachments

    def close(self):
        """Close the MCP server connection"""
        try:
            if self.process:
                self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.info("Gmail MCP server closed")
        except Exception as e:
            logger.error(f"Error closing MCP server: {str(e)}")

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
