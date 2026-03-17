"""
Check raw MCP output to see if thread_id is included in search results
"""
from mcp_gmail_client import MCPGmailClient

with MCPGmailClient() as mcp:
    # Monkey patch the parser to see raw output
    original_parse = mcp._parse_email_list

    def debug_parse(text):
        print("=== RAW MCP OUTPUT ===")
        print(text)
        print("=== END RAW OUTPUT ===\n")
        return original_parse(text)

    mcp._parse_email_list = debug_parse

    print("Searching for emails with subject 'Public Records Request'...")
    emails = mcp.search_emails('subject:"Public Records Request - Police R US - Data sent to POST"', max_results=5)

    print(f"\nParsed {len(emails)} emails")
