#!/usr/bin/env python3
"""
Test script to capture COMPLETE raw MCP response when reading an email.

Goal: Determine what email metadata MCP provides, specifically looking for
RFC 2822 Message-ID headers that can be used for email threading.

Usage:
    python test_mcp_read_raw.py
"""

import json
import logging
import sys
import time
from typing import Optional, Dict, Any
from mcp_gmail_client import MCPGmailClient

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def capture_raw_mcp_response(client: MCPGmailClient, message_id: str) -> Optional[Dict[str, Any]]:
    """
    Send raw read_email request and capture COMPLETE response.

    This bypasses the parsing methods to see the actual raw JSON from MCP.
    """
    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"READING EMAIL: {message_id}")
        logger.info(f"{'='*80}\n")

        # Send the raw MCP request
        result = client._send_request('tools/call', {
            'name': 'read_email',
            'arguments': {
                'messageId': message_id
            }
        })

        return result

    except Exception as e:
        logger.error(f"Failed to capture raw response: {str(e)}")
        return None


def print_full_response(response: Dict[str, Any], output_file: str):
    """
    Print the COMPLETE response with detailed analysis.
    """
    output = []

    output.append("\n" + "="*80)
    output.append("COMPLETE RAW MCP RESPONSE")
    output.append("="*80 + "\n")

    # Pretty print the full JSON
    output.append("Full JSON Response:")
    output.append("-" * 80)
    output.append(json.dumps(response, indent=2, default=str))
    output.append("\n")

    # Analyze top-level keys
    output.append("Top-level keys in response:")
    output.append("-" * 80)
    for key in response.keys():
        output.append(f"  - {key}: {type(response[key]).__name__}")
    output.append("\n")

    # Analyze content field (if exists)
    if 'content' in response:
        output.append("Content field analysis:")
        output.append("-" * 80)
        content = response['content']
        output.append(f"Type: {type(content).__name__}")
        output.append(f"Length: {len(content) if isinstance(content, (list, dict)) else 'N/A'}")

        if isinstance(content, list) and len(content) > 0:
            output.append(f"\nFirst content item:")
            first_item = content[0]
            output.append(f"  Type: {type(first_item).__name__}")
            if isinstance(first_item, dict):
                output.append(f"  Keys: {list(first_item.keys())}")

                # Show text content if available
                if 'text' in first_item:
                    text = first_item['text']
                    output.append(f"\n  Text content ({len(text)} chars):")
                    output.append("  " + "-" * 76)
                    output.append(text)
                    output.append("  " + "-" * 76)
        output.append("\n")

    # Search for Message-ID related fields
    output.append("Searching for Message-ID related fields:")
    output.append("-" * 80)

    message_id_variants = [
        'message-id', 'messageId', 'message_id', 'Message-ID',
        'MessageID', 'msg_id', 'id', 'headers'
    ]

    def search_dict(d, path=""):
        """Recursively search dictionary for message ID fields"""
        findings = []
        if isinstance(d, dict):
            for key, value in d.items():
                current_path = f"{path}.{key}" if path else key

                # Check if key matches any variant
                if any(variant.lower() in key.lower() for variant in message_id_variants):
                    findings.append(f"  FOUND at {current_path}:")
                    findings.append(f"    Value: {value}")
                    findings.append("")

                # Recurse into nested structures
                findings.extend(search_dict(value, current_path))

        elif isinstance(d, list):
            for i, item in enumerate(d):
                findings.extend(search_dict(item, f"{path}[{i}]"))

        return findings

    findings = search_dict(response)

    if findings:
        output.extend(findings)
    else:
        output.append("  No Message-ID fields found in response structure")

    output.append("\n")

    # Look for headers in text content
    if 'content' in response and isinstance(response['content'], list):
        for item in response['content']:
            if isinstance(item, dict) and 'text' in item:
                text = item['text']

                output.append("Analyzing text content for email headers:")
                output.append("-" * 80)

                # Look for common email header patterns
                import re

                header_patterns = [
                    (r'Message-ID:\s*(.+)', 'Message-ID'),
                    (r'message-id:\s*(.+)', 'message-id (lowercase)'),
                    (r'In-Reply-To:\s*(.+)', 'In-Reply-To'),
                    (r'References:\s*(.+)', 'References'),
                    (r'Thread ID:\s*(.+)', 'Thread ID'),
                    (r'ID:\s*(.+)', 'ID'),
                    (r'^From:\s*(.+)', 'From'),
                    (r'^To:\s*(.+)', 'To'),
                    (r'^Date:\s*(.+)', 'Date'),
                    (r'^Subject:\s*(.+)', 'Subject'),
                ]

                found_headers = []
                for pattern, name in header_patterns:
                    matches = re.findall(pattern, text, re.MULTILINE | re.IGNORECASE)
                    if matches:
                        found_headers.append(f"  {name}: {matches[0][:100]}")  # Limit to 100 chars

                if found_headers:
                    output.extend(found_headers)
                else:
                    output.append("  No standard email headers found in text")

                output.append("\n")

    # Summary
    output.append("="*80)
    output.append("SUMMARY")
    output.append("="*80)
    output.append(f"Response contains {len(response)} top-level fields")
    output.append(f"Response size: {len(json.dumps(response, default=str))} bytes")

    if findings:
        output.append(f"Found {len([f for f in findings if 'FOUND' in f])} potential Message-ID fields")
    else:
        output.append("No Message-ID fields found in JSON structure")

    output.append("\n")

    # Write to file
    full_output = '\n'.join(output)

    with open(output_file, 'w') as f:
        f.write(full_output)

    # Also print to console
    print(full_output)

    logger.info(f"\n✅ Full output saved to: {output_file}")


def main():
    """Main test function"""

    output_file = '/Users/ayyubibrahim/Desktop/info-agent/info-agent/portal/src/test_mcp_read_raw_output.txt'

    try:
        # Initialize MCP client
        logger.info("Initializing MCP Gmail client...")
        client = MCPGmailClient()

        if not client.connect():
            logger.error("Failed to connect to MCP server")
            sys.exit(1)

        logger.info("✅ Connected to MCP Gmail server\n")

        # First, search for a recent email to get a message ID
        logger.info("Searching for recent NextRequest emails...")
        emails = client.search_emails('from:messages@nextrequest.com', max_results=5)

        if not emails:
            logger.error("No emails found. Try a different search query.")
            sys.exit(1)

        logger.info(f"Found {len(emails)} emails\n")

        # Use the first email
        test_message_id = emails[0]['id']
        test_subject = emails[0].get('subject', 'Unknown')

        logger.info(f"Testing with email:")
        logger.info(f"  Message ID: {test_message_id}")
        logger.info(f"  Subject: {test_subject}")
        logger.info(f"  From: {emails[0].get('from', 'Unknown')}\n")

        # Capture raw response
        raw_response = capture_raw_mcp_response(client, test_message_id)

        if not raw_response:
            logger.error("Failed to capture raw response")
            sys.exit(1)

        # Print and save full analysis
        print_full_response(raw_response, output_file)

        # Close client
        client.close()

        logger.info("\n" + "="*80)
        logger.info("TEST COMPLETE")
        logger.info("="*80)
        logger.info(f"Results saved to: {output_file}")
        logger.info("\nNext steps:")
        logger.info("1. Review the output file to see what fields MCP provides")
        logger.info("2. Look for Message-ID header in the text content")
        logger.info("3. Check if we can access raw headers/payload fields")
        logger.info("4. Determine if we need to modify MCP server or use different API\n")

    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ Test failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
