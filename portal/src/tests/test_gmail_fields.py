"""
Quick test to see what fields are returned by Gmail MCP search
"""
from mcp_gmail_client import MCPGmailClient
import json

# Search for the email we just sent
with MCPGmailClient() as mcp:
    print("🔍 Public Records Request - Police R US - Data sent to POST")
    emails = mcp.search_emails('subject:"Public Records Request - Police R US - Data sent to POST"', max_results=10)

    print(f"\n📧 Found {len(emails)} emails\n")

    for i, email in enumerate(emails):
        print(f"--- Email {i+1} ---")
        print(json.dumps(email, indent=2))
        print()
