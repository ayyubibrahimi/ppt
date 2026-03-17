#!/usr/bin/env python3
"""
Deep inspection of MCP Gmail read_email response to find Message-ID header.

This script reads a specific email using MCP and searches exhaustively for
any occurrence of Message-ID in the response.
"""

import json
import re
from datetime import datetime
from mcp_gmail_client import MCPGmailClient


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80 + "\n")


def search_for_message_id_patterns(text: str, context_name: str):
    """Search for various Message-ID patterns in text."""
    print(f"\n--- Searching in: {context_name} ---")

    # Various search patterns
    patterns = [
        (r"Message-ID[:\s]*([^\s\n]+)", "Message-ID: <value>"),
        (r"message-id[:\s]*([^\s\n]+)", "message-id: <value> (lowercase)"),
        (r"messageId[:\s]*([^\s\n]+)", "messageId: <value> (camelCase)"),
        (r"<[^@\s]+@mail\.gmail\.com>", "Email format: <...@mail.gmail.com>"),
        (r"<[^@\s]+@[^>\s]+>", "Any email-like format: <...@...>"),
        (r"CAA[A-Za-z0-9+/=_-]+@mail\.gmail\.com", "Gmail Message-ID format"),
    ]

    found_any = False
    for pattern, description in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        matches_list = list(matches)
        if matches_list:
            print(f"  ✓ Found {len(matches_list)} match(es) for: {description}")
            for i, match in enumerate(matches_list[:5], 1):  # Show first 5
                # Get context around the match
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].replace('\n', ' ')
                print(f"    [{i}] ...{context}...")
            if len(matches_list) > 5:
                print(f"    ... and {len(matches_list) - 5} more")
            found_any = True

    if not found_any:
        print("  ✗ No matches found")

    return found_any


def recursive_search_dict(data, path="root"):
    """Recursively search through dictionary/list structures."""
    findings = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}"

            # Check if key name contains message-id related terms
            if any(term in key.lower() for term in ['message', 'id', 'header']):
                findings.append({
                    'path': current_path,
                    'key': key,
                    'value': str(value)[:200],  # First 200 chars
                    'type': type(value).__name__
                })

            # Recurse into value
            findings.extend(recursive_search_dict(value, current_path))

    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"
            findings.extend(recursive_search_dict(item, current_path))

    elif isinstance(data, str):
        # Search for message-id patterns in string values
        if any(pattern in data.lower() for pattern in ['message-id', 'messageid', '@mail.gmail.com']):
            findings.append({
                'path': path,
                'key': 'string_value',
                'value': data[:200],
                'type': 'string_match'
            })

    return findings


def main():
    """Main test function."""
    message_id = "19bbfc2b288b8f4a"
    output_file = "/Users/ayyubibrahim/Desktop/info-agent/info-agent/portal/src/test_mcp_read_message_id_search.txt"

    print_section(f"MCP Gmail Message-ID Deep Search Test")
    print(f"Testing with message ID: {message_id}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Redirect output to both console and file
    import sys

    class Tee:
        def __init__(self, *files):
            self.files = files
        def write(self, data):
            for f in self.files:
                f.write(data)
                f.flush()
        def flush(self):
            for f in self.files:
                f.flush()

    with open(output_file, 'w') as f:
        original_stdout = sys.stdout
        sys.stdout = Tee(sys.stdout, f)

        try:
            # Initialize MCP client using context manager
            print_section("1. Initializing MCP Gmail Client")

            with MCPGmailClient() as client:
                print("✓ Client connected via context manager")

                # Read email using _send_request for RAW response
                print_section("2. Fetching Email via MCP _send_request")
                print(f"Calling: _send_request('tools/call', {{'name': 'read_email', 'arguments': {{'messageId': '{message_id}'}}}})")

                raw_response = client._send_request('tools/call', {
                    'name': 'read_email',
                    'arguments': {
                        'messageId': message_id
                    }
                })

                print("✓ Response received")
                print(f"Response type: {type(raw_response)}")

                # Print full JSON structure
                print_section("3. Complete JSON Response Structure")
                json_str = json.dumps(raw_response, indent=2, ensure_ascii=False)
                print(json_str)

                # Print response size
                print_section("4. Response Statistics")
                print(f"JSON size: {len(json_str)} characters")
                print(f"JSON lines: {len(json_str.splitlines())} lines")

                # Search entire JSON text for patterns
                print_section("5. Pattern Search in Complete JSON Text")
                search_for_message_id_patterns(json_str, "Complete JSON Response")

                # Search in specific fields if they exist
                print_section("6. Field-by-Field Search")

                if isinstance(raw_response, dict):
                    for key in ['body', 'text', 'content', 'raw', 'payload', 'headers']:
                        if key in raw_response:
                            value = raw_response[key]
                            if isinstance(value, str):
                                search_for_message_id_patterns(value, f"Field: {key}")
                            elif isinstance(value, (dict, list)):
                                search_for_message_id_patterns(
                                    json.dumps(value, indent=2),
                                    f"Field: {key} (as JSON)"
                                )

                # Recursive dictionary search
                print_section("7. Recursive Structure Search")
                print("Searching for keys/values containing 'message', 'id', or 'header'...\n")

                findings = recursive_search_dict(raw_response)

                if findings:
                    print(f"Found {len(findings)} potentially relevant items:\n")
                    for i, finding in enumerate(findings, 1):
                        print(f"[{i}] Path: {finding['path']}")
                        print(f"    Key: {finding['key']}")
                        print(f"    Type: {finding['type']}")
                        print(f"    Value preview: {finding['value']}")
                        print()
                else:
                    print("No potentially relevant items found")

                # Search for Gmail-specific patterns
                print_section("8. Gmail-Specific Pattern Search")

                gmail_patterns = [
                    (r"CAA[A-Za-z0-9+/=_-]{20,}@mail\.gmail\.com", "Gmail Message-ID format"),
                    (r"[0-9a-f]{16}", "16-character hex ID (like Gmail's internal IDs)"),
                    (r"@mail\.gmail\.com", "Any @mail.gmail.com reference"),
                    (r"References:", "Email References header"),
                    (r"In-Reply-To:", "Email In-Reply-To header"),
                ]

                for pattern, description in gmail_patterns:
                    print(f"\nSearching for: {description}")
                    matches = re.finditer(pattern, json_str, re.IGNORECASE)
                    matches_list = list(matches)
                    if matches_list:
                        print(f"  ✓ Found {len(matches_list)} match(es)")
                        for i, match in enumerate(matches_list[:3], 1):
                            print(f"    [{i}] {match.group()}")
                        if len(matches_list) > 3:
                            print(f"    ... and {len(matches_list) - 3} more")
                    else:
                        print("  ✗ Not found")

                # Summary
                print_section("9. Summary")
                print(f"Message ID tested: {message_id}")
                print(f"Response keys: {list(raw_response.keys()) if isinstance(raw_response, dict) else 'N/A'}")
                print(f"Full output saved to: {output_file}")

                # Try using the high-level read_email method
                print_section("10. Comparison with read_email Method")
                try:
                    print("Calling: client.read_email(message_id)")
                    email_response = client.read_email(message_id)
                    print("\n✓ read_email response:")
                    print(json.dumps(email_response, indent=2, ensure_ascii=False))

                    print("\nSearching read_email response for Message-ID...")
                    search_for_message_id_patterns(
                        json.dumps(email_response, indent=2),
                        "read_email response"
                    )
                except Exception as e:
                    print(f"✗ Error calling read_email: {e}")

                # Try the dedicated get_message_id_header method
                print_section("11. Using get_message_id_header Method")
                try:
                    print("Calling: client.get_message_id_header(message_id)")
                    message_id_header = client.get_message_id_header(message_id)
                    if message_id_header:
                        print(f"✓ Message-ID header found: {message_id_header}")
                    else:
                        print("✗ Message-ID header NOT found")
                except Exception as e:
                    print(f"✗ Error calling get_message_id_header: {e}")

                print_section("Test Complete")
                print(f"✓ All searches completed")
                print(f"✓ Output saved to: {output_file}")

        except Exception as e:
            print(f"\n❌ Error during test: {e}")
            import traceback
            traceback.print_exc()

        finally:
            sys.stdout = original_stdout

    print(f"\n✓ Test complete. Output saved to: {output_file}")


if __name__ == "__main__":
    main()
