#!/usr/bin/env python3
"""
PRIORITY TEST #1: Direct Gmail API Threading Test

This script tests if using Gmail API directly with proper RFC 2822 Message-ID headers
fixes the recipient-side threading issue.

Test Approach:
1. Send email #1 via Gmail API
2. Extract RFC 2822 Message-ID header from sent email
3. Send email #2 via Gmail API with proper In-Reply-To and References headers
4. Report results: Do both emails share the same thread?

Success Criteria:
- Recipient sees ONE conversation with both messages (not two separate conversations)
"""

import os
import sys
from datetime import datetime
from email.mime.text import MIMEText
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import google.auth

# Gmail API scopes - need full access to send emails
SCOPES = ['https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.readonly']

# Test configuration
RECIPIENT_EMAIL = 'ayyub.ibrahimi@gmail.com'  # Change to test recipient
TEST_SUBJECT = f"Gmail API Threading Test {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def get_gmail_service():
    """
    Authenticate and return Gmail API service using OAuth credentials.json.
    """
    creds = None

    # Token file locations to check
    token_paths = [
        os.path.expanduser('~/gmail_token.json'),
        os.path.expanduser('~/.config/gmail_token.json'),
        os.path.expanduser('~/Desktop/gmail_token.json'),
    ]

    # Try to load existing credentials
    for token_path in token_paths:
        if os.path.exists(token_path):
            print(f"🔑 Found existing token: {token_path}")
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                print(f"✅ Loaded credentials from {token_path}")
                break
            except Exception as e:
                print(f"⚠️  Could not load token from {token_path}: {str(e)}")
                continue

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("🔑 Starting OAuth authentication flow...")
            print("   A browser window will open for you to authorize access.")
            print()

            # Look for credentials.json
            creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')

            if not os.path.exists(creds_path):
                print(f"❌ ERROR: credentials.json not found at {creds_path}")
                print("\nPlease ensure credentials.json exists with OAuth 2.0 credentials.")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for next run
        token_path = os.path.expanduser('~/gmail_token.json')
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        print(f"💾 Saved credentials to {token_path}")

    # Build Gmail service
    service = build('gmail', 'v1', credentials=creds)
    print("✅ Gmail API service initialized\n")

    return service


def create_email_message(to, subject, body, in_reply_to=None, references=None):
    """
    Create a MIME email message with proper threading headers.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
        in_reply_to: Message-ID of email being replied to (with angle brackets)
        references: Space-separated list of Message-IDs in thread (with angle brackets)

    Returns:
        Base64 encoded email message
    """
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject

    # Add threading headers if this is a reply
    if in_reply_to:
        message['In-Reply-To'] = in_reply_to
        print(f"  ✅ Set In-Reply-To: {in_reply_to}")

    if references:
        message['References'] = references
        print(f"  ✅ Set References: {references}")

    # Encode the message
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    return raw_message


def send_email(service, raw_message, thread_id=None):
    """
    Send an email via Gmail API.

    Args:
        service: Gmail API service
        raw_message: Base64 encoded email message
        thread_id: Optional thread ID for sender-side threading

    Returns:
        Sent message object containing id, threadId, labelIds
    """
    body = {'raw': raw_message}

    # Add thread_id for sender-side threading
    if thread_id:
        body['threadId'] = thread_id
        print(f"  ✅ Set threadId: {thread_id}")

    sent_message = service.users().messages().send(
        userId='me',
        body=body
    ).execute()

    return sent_message


def get_message_id_header(service, gmail_message_id):
    """
    Get the RFC 2822 Message-ID header from a sent email.

    Args:
        service: Gmail API service
        gmail_message_id: Gmail message ID (internal Gmail identifier)

    Returns:
        Message-ID header value (with angle brackets, e.g., <CABc123@mail.gmail.com>)
    """
    print(f"  📧 Fetching message {gmail_message_id} with format='full'...")

    # Get full message with all headers
    message = service.users().messages().get(
        userId='me',
        id=gmail_message_id,
        format='full'
    ).execute()

    # Extract Message-ID header
    payload = message.get('payload', {})
    headers = payload.get('headers', [])

    for header in headers:
        if header.get('name', '').lower() == 'message-id':
            message_id = header.get('value', '')
            print(f"  ✅ Found Message-ID: {message_id}")
            return message_id

    print(f"  ❌ WARNING: Message-ID header not found!")
    return None


def main():
    """Main test function."""
    print("="*80)
    print("PRIORITY TEST #1: DIRECT GMAIL API THREADING TEST")
    print("="*80)
    print(f"Recipient: {RECIPIENT_EMAIL}")
    print(f"Subject: {TEST_SUBJECT}")
    print("="*80 + "\n")

    try:
        # Get Gmail service
        service = get_gmail_service()

        # ========================================================================
        # STEP 1: Send Email #1
        # ========================================================================
        print("="*80)
        print("STEP 1: Sending Email #1")
        print("="*80)

        email1_body = f"""This is Email #1 in a threading test.

Test Details:
- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Purpose: Test if Gmail API with proper RFC 2822 headers fixes recipient-side threading
- Expected Result: This email and the reply should appear in ONE conversation

This email is sent via Gmail API directly (not MCP).
"""

        raw_message1 = create_email_message(
            to=RECIPIENT_EMAIL,
            subject=TEST_SUBJECT,
            body=email1_body
        )

        sent1 = send_email(service, raw_message1)

        print(f"\n✅ Email #1 sent successfully!")
        print(f"  Gmail Message ID: {sent1['id']}")
        print(f"  Gmail Thread ID: {sent1['threadId']}")
        print()

        # ========================================================================
        # STEP 2: Extract Message-ID Header from Email #1
        # ========================================================================
        print("="*80)
        print("STEP 2: Extracting Message-ID Header from Email #1")
        print("="*80)

        message_id_header = get_message_id_header(service, sent1['id'])

        if not message_id_header:
            print("❌ ERROR: Could not extract Message-ID header from Email #1")
            print("Cannot proceed with threading test.")
            sys.exit(1)

        print()

        # ========================================================================
        # STEP 3: Send Email #2 as Reply with Proper Threading Headers
        # ========================================================================
        print("="*80)
        print("STEP 3: Sending Email #2 as Reply (with proper RFC 2822 headers)")
        print("="*80)

        email2_body = f"""This is Email #2 - a REPLY to Email #1.

Threading Headers Set:
- In-Reply-To: {message_id_header}
- References: {message_id_header}
- threadId: {sent1['threadId']} (for sender-side threading)

Expected Result:
- Sender side: Both emails in same thread (thread_id: {sent1['threadId']})
- Recipient side: Both emails in SAME CONVERSATION ✅

If recipient sees TWO separate conversations, this test FAILS ❌.
"""

        raw_message2 = create_email_message(
            to=RECIPIENT_EMAIL,
            subject=TEST_SUBJECT,  # Same subject for threading
            body=email2_body,
            in_reply_to=message_id_header,  # RFC 2822 Message-ID!
            references=message_id_header  # RFC 2822 Message-ID!
        )

        sent2 = send_email(service, raw_message2, thread_id=sent1['threadId'])

        print(f"\n✅ Email #2 sent successfully!")
        print(f"  Gmail Message ID: {sent2['id']}")
        print(f"  Gmail Thread ID: {sent2['threadId']}")
        print()

        # ========================================================================
        # STEP 4: Report Results
        # ========================================================================
        print("="*80)
        print("TEST COMPLETE - RESULTS")
        print("="*80)
        print()

        print("📧 Email #1:")
        print(f"   Gmail Message ID: {sent1['id']}")
        print(f"   Gmail Thread ID: {sent1['threadId']}")
        print(f"   RFC 2822 Message-ID: {message_id_header}")
        print()

        print("📧 Email #2 (Reply):")
        print(f"   Gmail Message ID: {sent2['id']}")
        print(f"   Gmail Thread ID: {sent2['threadId']}")
        print(f"   In-Reply-To: {message_id_header}")
        print(f"   References: {message_id_header}")
        print()

        print("✅ Sender-Side Threading:")
        if sent1['threadId'] == sent2['threadId']:
            print(f"   ✅ SUCCESS: Both emails share thread_id {sent1['threadId']}")
        else:
            print(f"   ❌ FAILED: Different thread IDs!")
            print(f"      Email #1: {sent1['threadId']}")
            print(f"      Email #2: {sent2['threadId']}")
        print()

        print("❓ Recipient-Side Threading (MANUAL VERIFICATION REQUIRED):")
        print(f"   1. Check inbox of {RECIPIENT_EMAIL}")
        print(f"   2. Search for subject: \"{TEST_SUBJECT}\"")
        print(f"   3. Count conversations:")
        print(f"      - ONE conversation with 2 messages = ✅ TEST PASSED")
        print(f"      - TWO separate conversations = ❌ TEST FAILED")
        print()

        print("="*80)
        print("NEXT STEPS:")
        print("="*80)
        print("1. Check the recipient inbox manually")
        print("2. If ONE conversation → Gmail API threading works! Use it for sending.")
        print("3. If TWO conversations → Need to investigate further (MCP server issue?)")
        print("="*80)
        print()

        # Save results to file
        output_file = '/Users/ayyubibrahim/Desktop/info-agent/info-agent/portal/src/test_gmail_threading_solution_results.txt'
        with open(output_file, 'w') as f:
            f.write("="*80 + "\n")
            f.write("PRIORITY TEST #1: DIRECT GMAIL API THREADING TEST - RESULTS\n")
            f.write("="*80 + "\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Recipient: {RECIPIENT_EMAIL}\n")
            f.write(f"Subject: {TEST_SUBJECT}\n")
            f.write("="*80 + "\n\n")

            f.write("Email #1:\n")
            f.write(f"  Gmail Message ID: {sent1['id']}\n")
            f.write(f"  Gmail Thread ID: {sent1['threadId']}\n")
            f.write(f"  RFC 2822 Message-ID: {message_id_header}\n\n")

            f.write("Email #2 (Reply):\n")
            f.write(f"  Gmail Message ID: {sent2['id']}\n")
            f.write(f"  Gmail Thread ID: {sent2['threadId']}\n")
            f.write(f"  In-Reply-To: {message_id_header}\n")
            f.write(f"  References: {message_id_header}\n\n")

            f.write("Sender-Side Threading:\n")
            if sent1['threadId'] == sent2['threadId']:
                f.write(f"  ✅ SUCCESS: Both emails share thread_id {sent1['threadId']}\n\n")
            else:
                f.write(f"  ❌ FAILED: Different thread IDs\n")
                f.write(f"     Email #1: {sent1['threadId']}\n")
                f.write(f"     Email #2: {sent2['threadId']}\n\n")

            f.write("Recipient-Side Threading: (MANUAL VERIFICATION REQUIRED)\n")
            f.write(f"  Check inbox: {RECIPIENT_EMAIL}\n")
            f.write(f"  Search for: \"{TEST_SUBJECT}\"\n")
            f.write("  Expected: ONE conversation with 2 messages\n\n")

        print(f"📄 Results saved to: {output_file}\n")

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
