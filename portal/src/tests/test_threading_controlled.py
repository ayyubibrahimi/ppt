#!/usr/bin/env python3
"""
Controlled test: Send email #1, then send email #2 as a reply to #1.
Check if they thread properly.
"""

from dotenv import load_dotenv
load_dotenv()

from mcp_gmail_client import MCPGmailClient
import time

def main():
    print("\n" + "="*80)
    print("CONTROLLED THREADING TEST")
    print("="*80)

    with MCPGmailClient() as mcp:
        # STEP 1: Send the first email
        print("\n📧 STEP 1: Sending initial email...")

        result1 = mcp.send_email(
            to=['ayyub.ibrahimi@gmail.com'],
            subject='Threading Test - Initial Email',
            body='This is email #1. The initial email in the conversation.'
        )

        if not result1.get('success'):
            print(f"❌ Failed to send email #1: {result1.get('error')}")
            return

        message_id_1 = result1.get('message_id')
        thread_id_1 = result1.get('thread_id')

        print(f"\n✅ Email #1 sent successfully!")
        print(f"   Message ID: {message_id_1}")
        print(f"   Thread ID: {thread_id_1}")

        # Wait for Gmail to process
        print("\n⏳ Waiting 3 seconds for Gmail to process...")
        time.sleep(3)

        # STEP 2: Send a reply to email #1
        print("\n📧 STEP 2: Sending reply to email #1...")
        print(f"   Using thread_id: {thread_id_1}")
        print(f"   Using in_reply_to: {message_id_1} (Gmail message_id)")

        result2 = mcp.send_email(
            to=['ayyub.ibrahimi@gmail.com'],
            subject='Re: Threading Test - Initial Email',
            body='This is email #2. A reply to email #1.\n\nIf threading works, we should see this IN THE SAME CONVERSATION as email #1.',
            thread_id=thread_id_1,  # Thread to reply to
            in_reply_to=message_id_1  # Message being replied to (Gmail message_id)
        )

        if not result2.get('success'):
            print(f"❌ Failed to send email #2: {result2.get('error')}")
            return

        message_id_2 = result2.get('message_id')
        thread_id_2 = result2.get('thread_id')

        print(f"\n✅ Email #2 sent successfully!")
        print(f"   Message ID: {message_id_2}")
        print(f"   Thread ID: {thread_id_2}")

        # STEP 3: Analysis
        print("\n" + "="*80)
        print("ANALYSIS:")
        print("="*80)

        print(f"\nEmail #1 thread_id: {thread_id_1}")
        print(f"Email #2 thread_id: {thread_id_2}")

        if thread_id_1 == thread_id_2:
            print("\n✅ Thread IDs match on SENDER side (our Gmail account)")
            print("   This means Gmail API grouped them together for us.")
        else:
            print("\n⚠️  Thread IDs DON'T match on sender side!")

        print("\n" + "-"*80)
        print("🔍 NOW CHECK THE RECIPIENT INBOX:")
        print("-"*80)
        print("\n1. Go to ayyub.ibrahimi@gmail.com inbox")
        print("2. Look for subject: 'Threading Test - Initial Email'")
        print("\nQUESTION: Do you see ONE conversation with both messages, or TWO separate conversations?")
        print("\n   ONE conversation = Threading works with Gmail message_id!")
        print("   TWO conversations = We need RFC 2822 Message-ID header")

        # STEP 4: Let's also try to verify by searching
        print("\n" + "-"*80)
        print("VERIFICATION: Searching for the thread...")
        print("-"*80)

        time.sleep(2)  # Wait for indexing

        emails = mcp.search_emails('subject:"Threading Test - Initial Email"', max_results=10)
        print(f"\n📧 Found {len(emails)} email(s) with this subject:")

        for i, email in enumerate(emails):
            print(f"\n   Email {i+1}:")
            print(f"     ID: {email['id']}")
            print(f"     Subject: {email['subject']}")
            print(f"     From: {email['from']}")

        # Try to read them and get their thread_ids
        print("\n📊 Reading emails to check thread_ids...")
        for email in emails:
            full = mcp.read_email(email['id'])
            if full:
                print(f"\n   Message {email['id'][:10]}... -> Thread: {full.get('thread_id')}")

if __name__ == '__main__':
    main()
