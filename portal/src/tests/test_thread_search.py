"""
Test different Gmail search queries to find emails by thread_id
"""
from mcp_gmail_client import MCPGmailClient

thread_id = "19bbaf1765ae0aa8"

with MCPGmailClient() as mcp:
    print(f"Testing different search queries for thread_id: {thread_id}\n")

    # Test 1: Direct thread_id
    print("Test 1: Searching for bare thread_id")
    result1 = mcp.search_emails(thread_id, max_results=10)
    print(f"  Result: {len(result1)} emails found")
    if result1:
        print(f"  Thread IDs: {[e.get('thread_id') for e in result1]}\n")

    # Test 2: rfc822msgid
    print("Test 2: Searching with rfc822msgid:")
    result2 = mcp.search_emails(f"rfc822msgid:{thread_id}", max_results=10)
    print(f"  Result: {len(result2)} emails found")
    if result2:
        print(f"  Thread IDs: {[e.get('thread_id') for e in result2]}\n")

    # Test 3: Using message ID
    print("Test 3: Reading single email to see thread_id")
    email = mcp.read_email(thread_id)
    print(f"  Email thread_id: {email.get('thread_id')}")
    print(f"  Email id: {email.get('id')}\n")

    # Test 4: Can we search all emails and see thread IDs?
    print("Test 4: Search by subject and check thread_ids")
    result4 = mcp.search_emails('subject:"Public Records Request - Information Request"', max_results=10)
    print(f"  Result: {len(result4)} emails found")
    for e in result4:
        print(f"    ID: {e.get('id')}, Thread ID: {e.get('thread_id')}, Subject: {e.get('subject', '')[:50]}")
