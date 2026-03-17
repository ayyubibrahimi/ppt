#!/usr/bin/env python3
"""
Test: Use Gmail message_id directly as in_reply_to and see if threading works.
"""

from dotenv import load_dotenv
load_dotenv()

from mcp_gmail_client import MCPGmailClient

def main():
    print("\n" + "="*80)
    print("TESTING: Using Gmail message_id as in_reply_to")
    print("="*80)

    # The agency email we want to reply to
    agency_message_id = "19bbb39d2ea20fa0"  # Gmail message ID
    thread_id = "19bbb36ee4b985fb"

    print(f"\n📧 Replying to Gmail message: {agency_message_id}")
    print(f"   In thread: {thread_id}")
    print(f"   Using the Gmail message_id directly as in_reply_to...")

    with MCPGmailClient() as mcp:
        result = mcp.send_email(
            to=['ayyub.ibrahimi@gmail.com'],
            subject='Re: Public Records Request - Police R US  - Data sent to POST',
            body='TEST REPLY: Using Gmail message_id as in_reply_to.\n\nIf this appears in the same conversation thread on the recipient side, then Gmail message_id works!',
            thread_id=thread_id,
            in_reply_to=agency_message_id  # Using Gmail message_id directly!
        )

        print("\n" + "-"*80)
        print("RESULT:")
        print("-"*80)
        print(f"Success: {result.get('success')}")
        print(f"Message ID: {result.get('message_id')}")
        print(f"Thread ID: {result.get('thread_id')}")

        if result.get('success'):
            print("\n✅ Email sent!")
            print("\n🔍 CHECK YOUR INBOX:")
            print("   Go to ayyub.ibrahimi@gmail.com")
            print("   Look for the subject: 'Public Records Request - Police R US - Data sent to POST'")
            print("   Does the new reply appear IN THE SAME CONVERSATION?")
            print("   If YES → Gmail message_id works as in_reply_to!")
            print("   If NO → We need the RFC 2822 Message-ID header")

if __name__ == '__main__':
    main()
