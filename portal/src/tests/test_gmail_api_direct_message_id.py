#!/usr/bin/env python3
"""
Test script to call Gmail API DIRECTLY (bypassing MCP) to read message ID and extract Message-ID header.

This proves that Gmail API DOES return the Message-ID header when called with format='full'.
"""

import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import google.auth
import json

# Gmail API scopes - need full Gmail access to read messages
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Message ID to test
MESSAGE_ID = '19bbfc2b288b8f4a'


def get_gmail_service():
    """
    Authenticate and return Gmail API service.

    Tries multiple authentication methods:
    1. Existing token files
    2. gcloud application-default credentials
    3. OAuth flow with credentials.json
    """
    creds = None

    # Try gcloud application-default credentials FIRST
    try:
        print("🔑 Trying gcloud application-default credentials...")
        creds, project = google.auth.default(scopes=SCOPES)
        print(f"✅ Using gcloud credentials (project: {project})")
    except Exception as e:
        print(f"⚠️  gcloud credentials not available: {str(e)}")

        # Token file locations to check
        token_paths = [
            os.path.expanduser('~/gmail_token.json'),
            os.path.expanduser('~/.config/gmail_token.json'),
            os.path.expanduser('~/Desktop/gmail_token.json'),
        ]

        # Try to load existing credentials
        for token_path in token_paths:
            if os.path.exists(token_path):
                print(f"✅ Found token file: {token_path}")
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                break

        # If no valid credentials, authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("🔄 Refreshing expired token...")
                creds.refresh(Request())
            else:
                print("🔑 No valid credentials found. Starting OAuth flow...")
                print("\n" + "="*80)
                print("IMPORTANT: You need to create OAuth2 credentials:")
                print("1. Go to https://console.cloud.google.com/apis/credentials")
                print("2. Create OAuth 2.0 Client ID (Desktop app)")
                print("3. Download the JSON file and save as 'credentials.json' in this directory")
                print("="*80 + "\n")

                # Look for credentials.json
                creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')

                if not os.path.exists(creds_path):
                    print(f"❌ ERROR: credentials.json not found at {creds_path}")
                    print("\nAlternatively, you can use gcloud application-default credentials:")
                    print("Run: gcloud auth application-default login --scopes=https://www.googleapis.com/auth/gmail.readonly")
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


def get_message_with_headers(service, message_id):
    """
    Get message with ALL headers using format='full'.

    Args:
        service: Gmail API service
        message_id: Gmail message ID

    Returns:
        Full message object with all headers
    """
    print(f"📧 Fetching message {message_id} with format='full'...")

    # Call Gmail API with format='full' to get ALL headers
    message = service.users().messages().get(
        userId='me',
        id=message_id,
        format='full'  # CRITICAL: This returns all headers
    ).execute()

    print(f"✅ Message retrieved successfully\n")

    return message


def extract_message_id_header(message):
    """
    Extract the Message-ID header from Gmail message payload.

    Args:
        message: Full Gmail message object

    Returns:
        Message-ID header value (with angle brackets)
    """
    # Headers are in message['payload']['headers']
    payload = message.get('payload', {})
    headers = payload.get('headers', [])

    print(f"📋 Message has {len(headers)} headers\n")

    # Find Message-ID header
    message_id_header = None

    for header in headers:
        name = header.get('name', '')
        value = header.get('value', '')

        if name.lower() == 'message-id':
            message_id_header = value
            print(f"🎯 FOUND Message-ID header: {message_id_header}\n")
            break

    return message_id_header


def print_all_headers(message):
    """Print all headers in the message for inspection."""
    payload = message.get('payload', {})
    headers = payload.get('headers', [])

    print("="*80)
    print("ALL HEADERS:")
    print("="*80)

    for header in headers:
        name = header.get('name', '')
        value = header.get('value', '')

        # Highlight important headers
        if name.lower() in ['message-id', 'in-reply-to', 'references', 'thread-index']:
            print(f"⭐ {name}: {value}")
        else:
            print(f"   {name}: {value}")

    print("="*80 + "\n")


def print_message_structure(message):
    """Print the complete message structure."""
    print("="*80)
    print("COMPLETE MESSAGE STRUCTURE:")
    print("="*80)

    # Pretty print the entire message
    print(json.dumps(message, indent=2, default=str))

    print("="*80 + "\n")


def main():
    """Main test function."""
    print("="*80)
    print("GMAIL API DIRECT TEST - Message-ID Header Extraction")
    print("="*80)
    print(f"Target Message ID: {MESSAGE_ID}\n")

    try:
        # Get Gmail service
        service = get_gmail_service()

        # Get message with full headers
        message = get_message_with_headers(service, MESSAGE_ID)

        # Extract Message-ID header
        message_id_header = extract_message_id_header(message)

        # Print all headers
        print_all_headers(message)

        # Print results
        print("="*80)
        print("RESULTS:")
        print("="*80)
        print(f"Gmail Message ID: {MESSAGE_ID}")
        print(f"Message-ID Header: {message_id_header}")
        print(f"Message-ID Found: {'✅ YES' if message_id_header else '❌ NO'}")
        print("="*80 + "\n")

        # Save complete structure to file
        output_file = '/Users/ayyubibrahim/Desktop/info-agent/info-agent/portal/src/test_gmail_api_direct_message_id.txt'

        with open(output_file, 'w') as f:
            f.write("="*80 + "\n")
            f.write("GMAIL API DIRECT TEST - Message-ID Header Extraction\n")
            f.write("="*80 + "\n")
            f.write(f"Target Message ID: {MESSAGE_ID}\n\n")

            f.write("="*80 + "\n")
            f.write("RESULTS:\n")
            f.write("="*80 + "\n")
            f.write(f"Gmail Message ID: {MESSAGE_ID}\n")
            f.write(f"Message-ID Header: {message_id_header}\n")
            f.write(f"Message-ID Found: {'YES' if message_id_header else 'NO'}\n")
            f.write("="*80 + "\n\n")

            f.write("="*80 + "\n")
            f.write("ALL HEADERS:\n")
            f.write("="*80 + "\n")

            payload = message.get('payload', {})
            headers = payload.get('headers', [])

            for header in headers:
                name = header.get('name', '')
                value = header.get('value', '')

                if name.lower() in ['message-id', 'in-reply-to', 'references', 'thread-index']:
                    f.write(f"*** {name}: {value}\n")
                else:
                    f.write(f"    {name}: {value}\n")

            f.write("="*80 + "\n\n")

            f.write("="*80 + "\n")
            f.write("COMPLETE MESSAGE STRUCTURE:\n")
            f.write("="*80 + "\n")
            f.write(json.dumps(message, indent=2, default=str))
            f.write("\n" + "="*80 + "\n")

        print(f"📄 Full output saved to: {output_file}\n")

        # Final verdict
        print("="*80)
        print("CONCLUSION:")
        print("="*80)

        if message_id_header:
            print("✅ SUCCESS: Gmail API DOES return the Message-ID header with format='full'")
            print(f"✅ The Message-ID header is: {message_id_header}")
            print("\nThis proves that:")
            print("1. Gmail API provides the Message-ID header")
            print("2. It's available in the payload.headers array")
            print("3. MCP server should be able to access this header")
        else:
            print("❌ UNEXPECTED: Message-ID header not found")
            print("This could mean:")
            print("1. The message doesn't have a Message-ID header (unusual)")
            print("2. There's an issue with the API call")
            print("3. Check the complete message structure in the output file")

        print("="*80 + "\n")

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

        # Save error to output file
        output_file = '/Users/ayyubibrahim/Desktop/info-agent/info-agent/portal/src/test_gmail_api_direct_message_id.txt'
        with open(output_file, 'w') as f:
            f.write("="*80 + "\n")
            f.write("GMAIL API DIRECT TEST - ERROR\n")
            f.write("="*80 + "\n")
            f.write(f"Target Message ID: {MESSAGE_ID}\n\n")
            f.write(f"ERROR: {str(e)}\n\n")
            f.write(traceback.format_exc())

        print(f"📄 Error details saved to: {output_file}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
