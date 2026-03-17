#!/usr/bin/env python3
"""
Test script to send an email via MCP and capture the COMPLETE raw response.

This script investigates what data MCP returns when sending an email,
specifically looking for RFC 2822 Message-ID header information.
"""

import json
import logging
import sys
import subprocess
import queue
import threading
import time
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RawMCPClient:
    """
    Minimal MCP client that exposes raw responses for debugging.
    """

    def __init__(self):
        self.process = None
        self.request_id = 1
        self.pending_requests = {}
        self.reader_thread = None
        self.initialized = False
        self.raw_responses = []  # Store all raw responses for analysis

    def connect(self):
        """Start the Gmail MCP server process"""
        try:
            logger.info("Starting Gmail MCP server...")

            self.process = subprocess.Popen(
                ['npx', '@gongrzhe/server-gmail-autoauth-mcp'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            # Start background thread to read responses
            self.reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self.reader_thread.start()

            # Initialize
            init_result = self._send_request('initialize', {
                'protocolVersion': '2024-11-05',
                'capabilities': {
                    'roots': {'listChanged': True},
                    'sampling': {}
                },
                'clientInfo': {
                    'name': 'test-raw-mcp-client',
                    'version': '1.0.0'
                }
            })

            if init_result:
                logger.info(f"MCP server initialized: {init_result.get('serverInfo', {}).get('name')}")
                self.initialized = True
                return True
            else:
                logger.error("Failed to initialize MCP server")
                return False

        except Exception as e:
            logger.error(f"Failed to connect: {str(e)}")
            return False

    def _read_responses(self):
        """Background thread to read responses"""
        try:
            while self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    break

                try:
                    response = json.loads(line.strip())

                    # IMPORTANT: Store raw response for analysis
                    self.raw_responses.append(response)

                    if 'id' in response:
                        request_id = response['id']
                        if request_id in self.pending_requests:
                            self.pending_requests[request_id].put(response)

                except json.JSONDecodeError:
                    logger.debug(f"Non-JSON line: {line.strip()}")

        except Exception as e:
            logger.error(f"Error in response reader: {str(e)}")

    def _send_request(self, method: str, params: Dict[str, Any], timeout: int = 30) -> Optional[Dict[str, Any]]:
        """
        Send JSON-RPC request and return the COMPLETE response (not just result).
        """
        try:
            request_id = self.request_id
            self.request_id += 1

            request = {
                'jsonrpc': '2.0',
                'id': request_id,
                'method': method,
                'params': params
            }

            # Create response queue
            response_queue = queue.Queue()
            self.pending_requests[request_id] = response_queue

            # Send request
            request_json = json.dumps(request) + '\n'
            self.process.stdin.write(request_json)
            self.process.stdin.flush()

            logger.debug(f"Sent MCP request: {method}")
            logger.debug(f"Request params: {json.dumps(params, indent=2)}")

            # Wait for response
            try:
                response = response_queue.get(timeout=timeout)
                del self.pending_requests[request_id]

                # Log the COMPLETE raw response
                logger.info("=" * 80)
                logger.info(f"RAW RESPONSE FOR {method}:")
                logger.info(json.dumps(response, indent=2))
                logger.info("=" * 80)

                if 'error' in response:
                    logger.error(f"MCP error: {response['error']}")
                    return None

                # Return the ENTIRE response (not just result)
                return response

            except queue.Empty:
                logger.error(f"Request timeout for {method}")
                del self.pending_requests[request_id]
                return None

        except Exception as e:
            logger.error(f"Failed to send request: {str(e)}")
            return None

    def send_test_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Send a test email and capture the COMPLETE raw response.

        Returns:
            Complete MCP response dict
        """
        try:
            logger.info(f"Sending test email to {to}")
            logger.info(f"Subject: {subject}")
            logger.info(f"Body: {body[:100]}...")

            arguments = {
                'to': [to],  # MCP expects array
                'subject': subject,
                'body': body
            }

            # Send the email and get COMPLETE response
            full_response = self._send_request('tools/call', {
                'name': 'send_email',
                'arguments': arguments
            })

            return full_response

        except Exception as e:
            logger.error(f"Failed to send test email: {str(e)}")
            return {'error': str(e)}

    def close(self):
        """Close MCP server"""
        try:
            if self.process:
                self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.info("MCP server closed")
        except Exception as e:
            logger.error(f"Error closing MCP server: {str(e)}")


def analyze_response(response: Dict[str, Any]) -> str:
    """
    Analyze the response structure and look for Message-ID related fields.

    Returns:
        Analysis report as string
    """
    report = []
    report.append("\n" + "=" * 80)
    report.append("RESPONSE ANALYSIS")
    report.append("=" * 80)

    def recursive_search(obj, path="", depth=0):
        """Recursively search for all keys and values"""
        indent = "  " * depth

        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                report.append(f"{indent}{key}: {type(value).__name__}")

                # Check if key or value contains "message" or "id"
                if any(term in key.lower() for term in ['message', 'id', 'thread', 'header']):
                    report.append(f"{indent}  >>> INTERESTING KEY: {key}")
                    report.append(f"{indent}  >>> VALUE: {value}")

                # Recurse into nested structures
                if isinstance(value, (dict, list)):
                    recursive_search(value, current_path, depth + 1)
                elif isinstance(value, str) and any(term in value.lower() for term in ['message-id', 'messageid']):
                    report.append(f"{indent}  >>> INTERESTING VALUE: {value}")

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                current_path = f"{path}[{i}]"
                if isinstance(item, (dict, list)):
                    recursive_search(item, current_path, depth + 1)
                else:
                    report.append(f"{indent}[{i}]: {type(item).__name__} = {item[:100] if isinstance(item, str) else item}")

    report.append("\nFull structure:")
    recursive_search(response)

    report.append("\n" + "=" * 80)
    report.append("SEARCHING FOR MESSAGE-ID INDICATORS")
    report.append("=" * 80)

    # Convert entire response to JSON string for text search
    response_str = json.dumps(response, indent=2)

    message_id_patterns = [
        'Message-ID',
        'message-id',
        'messageId',
        'message_id',
        'MessageID',
        'RFC2822',
        'rfc2822',
        'headers',
        'Headers',
        'In-Reply-To',
        'in-reply-to',
        'References',
        'references'
    ]

    found_patterns = []
    for pattern in message_id_patterns:
        if pattern in response_str:
            found_patterns.append(pattern)
            report.append(f"✓ Found pattern: '{pattern}'")

    if not found_patterns:
        report.append("✗ No Message-ID related patterns found in response")

    report.append("=" * 80)

    return "\n".join(report)


def main():
    """Main test function"""

    print("=" * 80)
    print("MCP RAW SEND EMAIL TEST")
    print("=" * 80)
    print("This script sends a test email and captures the COMPLETE raw response")
    print("to investigate what data MCP returns, specifically looking for Message-ID.")
    print("=" * 80)
    print()

    client = RawMCPClient()

    try:
        # Connect to MCP server
        if not client.connect():
            print("Failed to connect to MCP server")
            sys.exit(1)

        # Give server time to initialize
        time.sleep(2)

        # Send test email
        print("\nSending test email...")
        response = client.send_test_email(
            to='ayyub.ibrahimi@gmail.com',
            subject='MCP Test - Raw Response Investigation',
            body='''This is a test email to investigate MCP's send_email response.

We're looking for:
1. RFC 2822 Message-ID header
2. Gmail message ID
3. Thread ID
4. Any other metadata returned by the MCP server

Test timestamp: ''' + time.strftime('%Y-%m-%d %H:%M:%S')
        )

        # Analyze the response
        analysis = analyze_response(response)
        print(analysis)

        # Save to output file
        output_file = '/Users/ayyubibrahim/Desktop/info-agent/info-agent/portal/src/test_mcp_send_raw_output.txt'

        with open(output_file, 'w') as f:
            f.write("MCP SEND EMAIL - COMPLETE RAW RESPONSE CAPTURE\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Test executed: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("COMPLETE RAW RESPONSE:\n")
            f.write("=" * 80 + "\n")
            f.write(json.dumps(response, indent=2))
            f.write("\n\n")

            f.write(analysis)
            f.write("\n\n")

            f.write("ALL RAW RESPONSES CAPTURED DURING SESSION:\n")
            f.write("=" * 80 + "\n")
            for i, raw_resp in enumerate(client.raw_responses, 1):
                f.write(f"\n--- Response {i} ---\n")
                f.write(json.dumps(raw_resp, indent=2))
                f.write("\n")

        print(f"\nComplete output saved to: {output_file}")

    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        client.close()

    print("\nTest complete!")


if __name__ == '__main__':
    main()
