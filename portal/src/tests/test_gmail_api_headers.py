#!/usr/bin/env python3
"""
Test accessing Gmail API directly to get Message-ID header.
The MCP server might not expose it, but the Gmail API definitely has it.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    """Get Gmail API service."""
    creds = None
    token_path = os.path.expanduser('~/.config/mcp_gmail/token.pickle')

    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("No valid credentials found. MCP server should have created them.")

    return build('gmail', 'v1', credentials=creds)

def main():
    print("\n" + "="*80)
    print("TESTING GMAIL API DIRECT ACCESS FOR MESSAGE-ID HEADER")
    print("="*80)

    # The agency email we want to reply to
    gmail_message_id = "19bbb39d2ea20fa0"

    try:
        service = get_gmail_service()

        print(f"\n📧 Fetching email {gmail_message_id} with format='full' to get headers...")

        # Get the full message including headers
        message = service.users().messages().get(
            userId='me',
            id=gmail_message_id,
            format='full'  # This gives us all headers
        ).execute()

        print("\n" + "-"*80)
        print("MESSAGE HEADERS:")
        print("-"*80)

        # Extract headers
        headers = message.get('payload', {}).get('headers', [])

        message_id_header = None
        references_header = None
        in_reply_to_header = None

        for header in headers:
            name = header.get('name', '')
            value = header.get('value', '')

            if name.lower() == 'message-id':
                message_id_header = value
                print(f"✅ Message-ID: {value}")
            elif name.lower() == 'references':
                references_header = value
                print(f"📎 References: {value}")
            elif name.lower() == 'in-reply-to':
                in_reply_to_header = value
                print(f"↩️  In-Reply-To: {value}")
            elif name.lower() in ['from', 'to', 'subject', 'date']:
                print(f"   {name}: {value}")

        print("\n" + "="*80)
        print("RESULTS:")
        print("="*80)

        if message_id_header:
            print(f"\n✅ SUCCESS! Found Message-ID header:")
            print(f"   {message_id_header}")
            print(f"\n   This is what we need to pass as in_reply_to parameter!")
            print(f"   Has angle brackets: {'<' in message_id_header and '>' in message_id_header}")
        else:
            print("\n❌ No Message-ID header found!")

        if in_reply_to_header:
            print(f"\n📧 This email is itself a reply to: {in_reply_to_header}")

        if references_header:
            print(f"\n🔗 Thread references: {references_header}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
