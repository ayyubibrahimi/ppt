#!/usr/bin/env python3
"""
Test Gmail API threading with a real Supabase request.

This script:
1. Queries Supabase for an email-based request with a pending draft
2. Sends the draft using Gmail API direct (with proper RFC 2822 headers)
3. Verifies threading on recipient side
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from supabase_integration import SupabaseIntegration
from gmail_api_direct import GmailAPIClient
from mcp_gmail_client import MCPGmailClient
from datetime import datetime

# Test request ID from phase3 document
TEST_REQUEST_ID = '7c0cd416-ba62-4bf7-9d5f-5df557a8091b'


def main():
    print("="*80)
    print("TEST: Gmail API Threading with Real Supabase Request")
    print("="*80)
    print()

    # Initialize database
    db = SupabaseIntegration()

    # Get the test request
    print(f"📋 Fetching request: {TEST_REQUEST_ID}")
    result = db.supabase.table('requests').select('*').eq('id', TEST_REQUEST_ID).execute()

    if not result.data or len(result.data) == 0:
        print(f"❌ Request {TEST_REQUEST_ID} not found in database")
        sys.exit(1)

    request = result.data[0]

    print(f"✅ Found request:")
    print(f"   Portal: {request.get('portal_name')}")
    print(f"   Portal Type: {request.get('portal_type')}")
    print(f"   Subject: {request.get('email_subject')}")
    print(f"   Thread ID: {request.get('gmail_thread_id')}")
    print(f"   Agency Email: {request.get('agency_email')}")
    print()

    # Check if this is an email-based request
    if request.get('portal_type') != 'email':
        print(f"❌ This is not an email-based request (portal_type: {request.get('portal_type')})")
        print("   This test requires an email-based request")
        sys.exit(1)

    # Get approved drafts for this request (ready to send)
    print(f"📧 Fetching approved drafts for request...")
    result = db.supabase.table('message_drafts').select('*').eq('request_id', TEST_REQUEST_ID).eq('draft_status', 'approved').execute()

    drafts = result.data if result.data else []

    if not drafts:
        print(f"⚠️  No approved drafts found for this request")
        print()
        print("Let me check for any drafts (all statuses)...")
        all_drafts = db.supabase.table('message_drafts').select('*').eq('request_id', TEST_REQUEST_ID).execute()
        if all_drafts.data:
            print(f"   Found {len(all_drafts.data)} draft(s) total:")
            for d in all_drafts.data:
                print(f"   - Draft ID: {d['id']}, Status: {d['draft_status']}")
            print()
            print("Would you like to send one of these drafts? (Update status to 'approved' first)")
        sys.exit(0)

    draft = drafts[0]
    print(f"✅ Found pending draft:")
    print(f"   Draft ID: {draft['id']}")
    print(f"   Subject: {draft.get('draft_subject')}")
    print(f"   Message preview: {draft.get('draft_message', '')[:100]}...")
    print()

    # Get thread info
    thread_id = request.get('gmail_thread_id')
    # For email-based requests, portal_name IS the agency email
    agency_email = request.get('agency_email') or request.get('portal_name')
    original_subject = request.get('email_subject')

    if not thread_id or not agency_email:
        print(f"❌ Missing thread_id or agency_email in request")
        print(f"   thread_id: {thread_id}")
        print(f"   agency_email: {agency_email}")
        sys.exit(1)

    # Prepare reply subject
    reply_subject = original_subject
    if not reply_subject.startswith('Re: '):
        reply_subject = f"Re: {reply_subject}"

    print(f"📧 Preparing to send reply:")
    print(f"   To: {agency_email}")
    print(f"   Subject: {reply_subject}")
    print(f"   Thread ID: {thread_id}")
    print()

    # Get the RFC 2822 Message-ID of the last agency email
    print(f"📧 Extracting In-Reply-To Message-ID header...")
    in_reply_to_message_id = None

    try:
        with MCPGmailClient() as mcp:
            # Search for emails in thread
            search_query = f'subject:"{original_subject}"'
            emails = mcp.search_emails(search_query, max_results=20)

            # Find latest agency email
            user_email = db.get_user_email(request['user_id'])

            latest_agency_email = None
            for email_summary in emails:
                full_email = mcp.read_email(email_summary['id'])
                if full_email and full_email.get('thread_id') == thread_id:
                    from_email = full_email.get('from', '')
                    if user_email and user_email.lower() not in from_email.lower():
                        if not latest_agency_email or full_email.get('date', '') > latest_agency_email.get('date', ''):
                            latest_agency_email = full_email

            if latest_agency_email:
                gmail_msg_id = latest_agency_email['id']
                print(f"✅ Found latest agency email: {gmail_msg_id}")

                # Use Gmail API to extract Message-ID
                gmail_client = GmailAPIClient()
                in_reply_to_message_id = gmail_client.get_message_id_header(gmail_msg_id)

                if in_reply_to_message_id:
                    print(f"✅ Extracted Message-ID: {in_reply_to_message_id}")
                else:
                    print(f"⚠️  Could not extract Message-ID header")
            else:
                print(f"⚠️  Could not find agency message in thread")

    except Exception as e:
        print(f"⚠️  Error getting Message-ID: {e}")
        import traceback
        traceback.print_exc()

    print()

    # Send email via Gmail API
    print(f"📧 Sending email via Gmail API with proper threading...")
    print()

    gmail_client = GmailAPIClient()
    result = gmail_client.send_threaded_email(
        to=agency_email,
        subject=reply_subject,
        body=draft['draft_message'],
        thread_id=thread_id,
        in_reply_to=in_reply_to_message_id,
        references=in_reply_to_message_id
    )

    print()

    if result['success']:
        print(f"✅ EMAIL SENT SUCCESSFULLY!")
        print(f"   Gmail Message ID: {result['message_id']}")
        print(f"   Gmail Thread ID: {result['thread_id']}")
        print()

        # Update draft status in database
        print(f"💾 Updating draft status in database...")
        db.supabase.table('message_drafts').update({
            'draft_status': 'sent',
            'sent_at': datetime.now().isoformat()
        }).eq('id', draft['id']).execute()

        print(f"✅ Draft marked as sent in database")
        print()

        print("="*80)
        print("VERIFICATION STEPS:")
        print("="*80)
        print(f"1. Check recipient inbox: {agency_email}")
        print(f"2. Search for subject: \"{original_subject}\"")
        print(f"3. Verify reply appears in SAME conversation thread")
        print(f"4. Expected: ONE conversation with multiple messages ✅")
        print(f"5. If separate: Threading still broken ❌")
        print("="*80)
        print()

    else:
        print(f"❌ EMAIL SEND FAILED")
        print(f"   Error: {result.get('error')}")
        print()


if __name__ == '__main__':
    main()
