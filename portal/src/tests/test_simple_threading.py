#!/usr/bin/env python3
"""
Simple MCP Gmail Threading Test

Tests the simplest possible threading approach:
1. Send Email A
2. Capture message_id and thread_id from response
3. Send Email B with thread_id and in_reply_to set to Email A's values
4. Verify sender-side threading and prompt user to check recipient-side

No Message-ID header extraction, no complex logic - just pure MCP API usage.
"""

import time
from datetime import datetime
from mcp_gmail_client import MCPGmailClient


def main():
    print("=" * 80)
    print("MCP Gmail Threading Test - Simple Approach")
    print("=" * 80)
    print()

    # Initialize MCP client
    print("Initializing MCP Gmail client...")
    client = MCPGmailClient()

    # Generate unique timestamp for this test
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    recipient = "ayyub.ibrahimi@gmail.com"

    print(f"Timestamp: {timestamp}")
    print(f"Recipient: {recipient}")
    print()

    # -------------------------------------------------------------------------
    # Step 1: Send Email A
    # -------------------------------------------------------------------------
    print("STEP 1: Sending Email A...")
    print("-" * 80)

    subject = f"MCP Threading Test {timestamp}"
    body_a = f"""This is Email A in a threading test.

Timestamp: {timestamp}
Test: Simple MCP Threading

This email should start a new thread. Email B should reply to this thread.
"""

    result_a = client.send_email(
        to=recipient,
        subject=subject,
        body=body_a
    )

    # Extract Gmail IDs from Email A
    message_id_a = result_a.get('message_id')
    thread_id_a = result_a.get('thread_id')

    print(f"✓ Email A sent successfully")
    print(f"  Message ID: {message_id_a}")
    print(f"  Thread ID:  {thread_id_a}")
    print()

    # -------------------------------------------------------------------------
    # Step 2: Wait 3 seconds
    # -------------------------------------------------------------------------
    print("STEP 2: Waiting 3 seconds...")
    print("-" * 80)
    time.sleep(3)
    print("✓ Wait complete")
    print()

    # -------------------------------------------------------------------------
    # Step 3: Send Email B as reply
    # -------------------------------------------------------------------------
    print("STEP 3: Sending Email B as reply...")
    print("-" * 80)

    # Use the same subject (Gmail will add Re: if needed)
    subject_b = subject

    body_b = f"""This is Email B replying to Email A.

Timestamp: {timestamp}
Test: Simple MCP Threading
Reply to: {message_id_a}
Thread: {thread_id_a}

This email should appear in the same thread as Email A.
"""

    print(f"Sending with:")
    print(f"  thread_id = {thread_id_a}")
    print(f"  in_reply_to = {message_id_a}")
    print()

    result_b = client.send_email(
        to=recipient,
        subject=subject_b,
        body=body_b,
        thread_id=thread_id_a,
        in_reply_to=message_id_a
    )

    # Extract Gmail IDs from Email B
    message_id_b = result_b.get('message_id')
    thread_id_b = result_b.get('thread_id')

    print(f"✓ Email B sent successfully")
    print(f"  Message ID: {message_id_b}")
    print(f"  Thread ID:  {thread_id_b}")
    print()

    # -------------------------------------------------------------------------
    # Step 4: Print results and verification
    # -------------------------------------------------------------------------
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()

    print("Email A:")
    print(f"  Message ID: {message_id_a}")
    print(f"  Thread ID:  {thread_id_a}")
    print()

    print("Email B:")
    print(f"  Message ID: {message_id_b}")
    print(f"  Thread ID:  {thread_id_b}")
    print()

    # Check sender-side threading
    threads_match = (thread_id_a == thread_id_b)

    print("Sender-Side Threading:")
    if threads_match:
        print(f"  ✓ SUCCESS - Thread IDs match!")
        print(f"  Both emails are in thread: {thread_id_a}")
    else:
        print(f"  ✗ FAILURE - Thread IDs do not match")
        print(f"  Email A thread: {thread_id_a}")
        print(f"  Email B thread: {thread_id_b}")
    print()

    # Prompt for recipient-side verification
    print("Recipient-Side Threading:")
    print(f"  Please check inbox at {recipient}")
    print(f"  Look for subject: {subject}")
    print(f"  Expected: Both emails should appear in the same conversation")
    print()

    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

    return threads_match


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print()
        print("=" * 80)
        print("ERROR")
        print("=" * 80)
        print(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
