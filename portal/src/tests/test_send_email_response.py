#!/usr/bin/env python3
"""
Test what's returned when we send an email, specifically looking for Message-ID.
"""

from dotenv import load_dotenv
load_dotenv()

from mcp_gmail_client import MCPGmailClient
import json

def main():
    print("\n" + "="*80)
    print("TESTING EMAIL SEND RESPONSE - Looking for Message-ID")
    print("="*80)

    with MCPGmailClient() as mcp:
        print("\n📧 Sending test email...")

        # Send a simple test email
        result = mcp.send_email(
            to=['admin@mljusticelab.com'],
            subject='Test: Checking Message-ID in Response',
            body='This is a test email to check what fields are returned, especially the Message-ID header.'
        )

        print("\n" + "-"*80)
        print("PARSED RESULT FROM send_email():")
        print("-"*80)
        print(json.dumps(result, indent=2))

        if result.get('success'):
            message_id = result.get('message_id')
            print(f"\n✅ Email sent successfully!")
            print(f"   Gmail Message ID: {message_id}")

            # Now read the email we just sent to see what fields are available
            print("\n" + "-"*80)
            print("READING THE EMAIL WE JUST SENT:")
            print("-"*80)

            import time
            time.sleep(2)  # Give Gmail time to index

            # Get the raw MCP response for read_email
            raw_result = mcp._send_request('tools/call', {
                'name': 'read_email',
                'arguments': {
                    'messageId': message_id
                }
            })

            print("\nRAW MCP RESPONSE:")
            print(json.dumps(raw_result, indent=2))

            # Check if Message-ID is in the response
            result_str = json.dumps(raw_result)
            if 'Message-ID' in result_str or 'Message-Id' in result_str or 'message-id' in result_str:
                print("\n✅ Found 'Message-ID' somewhere in the response!")

                import re
                match = re.search(r'[Mm]essage-[Ii][Dd]:\s*(<[^>]+>)', result_str)
                if match:
                    print(f"   Message-ID: {match.group(1)}")
            else:
                print("\n❌ 'Message-ID' not found in response")
                print("\nThis means the MCP server's read_email doesn't return the Message-ID header.")
                print("We need an alternative approach to get it.")

if __name__ == '__main__':
    main()
