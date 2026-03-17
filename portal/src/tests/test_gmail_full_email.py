"""
Test to see what fields are in a full email read
"""
from mcp_gmail_client import MCPGmailClient
import json

# Read the email we just sent
with MCPGmailClient() as mcp:
    print("🔍 Reading email: 19bbaf1765ae0aa8")
    email = mcp.read_email('19bbaf1765ae0aa8')

    print(f"\n📧 Full email fields:\n")
    print(json.dumps(email, indent=2))
