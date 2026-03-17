#!/usr/bin/env python3
"""
Test script for MCP Gmail client extensions (send_email, search_thread, get_attachments).

Tests the new methods added for email-based request system:
- send_email() - Send emails and replies
- search_thread() - Get all messages in a thread
- get_attachments() - Download email attachments

Usage:
    python test_mcp_gmail_extensions.py
"""

import logging
from mcp_gmail_client import MCPGmailClient
from supabase_integration import SupabaseIntegration

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_supabase_portal_methods():
    """Test SupabaseIntegration portal helper methods"""
    logger.info("\n========== Testing SupabaseIntegration Portal Methods ==========")

    try:
        db = SupabaseIntegration()
        logger.info("✅ Connected to Supabase")

        # Get a sample portal ID from database
        result = db.supabase.table('portals').select('id, agency_name, portal_type, contact_email').limit(5).execute()

        if not result.data:
            logger.warning("⚠️ No portals found in database")
            return False

        logger.info(f"\nFound {len(result.data)} portals to test:")
        for portal in result.data:
            logger.info(f"  - {portal['agency_name']} (type: {portal.get('portal_type', 'N/A')}, email: {portal.get('contact_email', 'N/A')})")

        # Test get_portal_type()
        logger.info("\n--- Testing get_portal_type() ---")
        test_portal_id = result.data[0]['id']
        portal_type = db.get_portal_type(test_portal_id)
        logger.info(f"✅ get_portal_type('{test_portal_id}'): {portal_type}")

        # Test get_portal()
        logger.info("\n--- Testing get_portal() ---")
        portal = db.get_portal(test_portal_id)
        if portal:
            logger.info(f"✅ get_portal() returned:")
            logger.info(f"   Agency: {portal.get('agency_name')}")
            logger.info(f"   Type: {portal.get('portal_type')}")
            logger.info(f"   Contact Email: {portal.get('contact_email')}")
            logger.info(f"   Portal URL: {portal.get('portal_url')}")
        else:
            logger.error("❌ get_portal() returned empty dict")
            return False

        # Test get_portal_contact_email()
        logger.info("\n--- Testing get_portal_contact_email() ---")
        contact_email = db.get_portal_contact_email(test_portal_id)
        logger.info(f"✅ get_portal_contact_email('{test_portal_id}'): {contact_email}")

        # Test with invalid portal ID
        logger.info("\n--- Testing with invalid portal ID ---")
        invalid_type = db.get_portal_type('invalid-id-12345')
        invalid_portal = db.get_portal('invalid-id-12345')
        invalid_email = db.get_portal_contact_email('invalid-id-12345')

        logger.info(f"get_portal_type(invalid): {invalid_type} (should default to 'portal')")
        logger.info(f"get_portal(invalid): {invalid_portal} (should be empty dict)")
        logger.info(f"get_portal_contact_email(invalid): {invalid_email} (should be None)")

        logger.info("\n✅ All SupabaseIntegration portal methods working correctly")
        return True

    except Exception as e:
        logger.error(f"❌ Error testing SupabaseIntegration: {str(e)}")
        return False


def test_send_email():
    """Test send_email() method"""
    logger.info("\n========== Testing send_email() ==========")

    try:
        with MCPGmailClient() as mcp:
            # Test sending a new email (creates new thread)
            logger.info("\n--- Test 1: Send new email (new thread) ---")

            # Using your own email for testing
            result = mcp.send_email(
                to='admin@mljusticelab.com',
                subject='[TEST] Email-Based Request System Test',
                body='This is a test email from the email-based request system.\n\nTesting send_email() method.\n\nPlease ignore this message.',
                thread_id=None  # New thread
            )

            logger.info(f"Send result: {result}")

            if result['success']:
                logger.info(f"✅ Email sent successfully!")
                logger.info(f"   Message ID: {result['message_id']}")
                logger.info(f"   Thread ID: {result['thread_id']}")

                # Store thread_id for reply test
                thread_id = result['thread_id']

                # Test sending a reply in the same thread
                logger.info("\n--- Test 2: Send reply in existing thread ---")

                reply_result = mcp.send_email(
                    to='admin@mljusticelab.com',
                    subject='Re: [TEST] Email-Based Request System Test',
                    body='This is a reply in the same thread.\n\nTesting send_email() with thread_id parameter.',
                    thread_id=thread_id  # Reply to previous email
                )

                logger.info(f"Reply result: {reply_result}")

                if reply_result['success']:
                    logger.info(f"✅ Reply sent successfully!")
                    logger.info(f"   Message ID: {reply_result['message_id']}")
                    logger.info(f"   Thread ID: {reply_result['thread_id']}")
                    logger.info(f"   Same thread? {reply_result['thread_id'] == thread_id}")
                    return True
                else:
                    logger.error(f"❌ Reply send failed: {reply_result.get('error')}")
                    return False
            else:
                logger.error(f"❌ Email send failed: {result.get('error')}")
                return False

    except Exception as e:
        logger.error(f"❌ Error testing send_email: {str(e)}")
        return False


def test_search_thread():
    """Test search_thread() method"""
    logger.info("\n========== Testing search_thread() ==========")

    try:
        with MCPGmailClient() as mcp:
            # First, find a thread with multiple messages
            logger.info("Finding a thread with multiple messages...")

            # Search for emails from NextRequest
            emails = mcp.search_emails('from:messages@nextrequest.com', max_results=10)

            if not emails:
                logger.warning("⚠️ No emails found to test search_thread()")
                return False

            # Use the first email's ID as thread_id
            # Note: In Gmail, message IDs can be used as thread IDs if we don't have the actual thread ID
            test_thread_id = emails[0]['id']

            logger.info(f"Testing with thread/message ID: {test_thread_id}")

            # Fetch the thread
            messages = mcp.search_thread(test_thread_id)

            if messages:
                logger.info(f"✅ Found {len(messages)} messages in thread")

                for i, msg in enumerate(messages, 1):
                    logger.info(f"\nMessage {i}:")
                    logger.info(f"   ID: {msg.get('id')}")
                    logger.info(f"   Subject: {msg.get('subject')}")
                    logger.info(f"   From: {msg.get('from')}")
                    logger.info(f"   Date: {msg.get('date')}")

                return True
            else:
                logger.warning("⚠️ No messages found in thread")
                return False

    except Exception as e:
        logger.error(f"❌ Error testing search_thread: {str(e)}")
        return False


def test_get_attachments():
    """Test get_attachments() method"""
    logger.info("\n========== Testing get_attachments() ==========")

    try:
        with MCPGmailClient() as mcp:
            # Search for emails with attachments
            logger.info("Searching for emails with attachments...")

            emails = mcp.search_emails('has:attachment', max_results=5)

            if not emails:
                logger.warning("⚠️ No emails with attachments found")
                return False

            logger.info(f"Found {len(emails)} emails with attachments")

            # Test get_attachments on first email
            test_email = emails[0]
            message_id = test_email['id']

            logger.info(f"\nTesting get_attachments() on email:")
            logger.info(f"   ID: {message_id}")
            logger.info(f"   Subject: {test_email.get('subject')}")

            attachments = mcp.get_attachments(message_id)

            if attachments:
                logger.info(f"\n✅ Found {len(attachments)} attachments:")

                for i, att in enumerate(attachments, 1):
                    logger.info(f"\nAttachment {i}:")
                    logger.info(f"   Filename: {att.get('filename')}")
                    logger.info(f"   MIME Type: {att.get('mime_type')}")
                    logger.info(f"   Size: {att.get('size')} bytes")
                    logger.info(f"   Content Length: {len(att.get('content', b''))} bytes")

                    # Verify content is not empty
                    if att.get('content'):
                        logger.info(f"   ✅ Content downloaded successfully")
                    else:
                        logger.warning(f"   ⚠️ Content is empty")

                return True
            else:
                logger.warning("⚠️ No attachments extracted (may not be supported by MCP server)")
                return False

    except Exception as e:
        logger.error(f"❌ Error testing get_attachments: {str(e)}")
        return False


def main():
    """Run all tests"""
    logger.info("=" * 80)
    logger.info("MCP Gmail Extensions Test Suite")
    logger.info("=" * 80)

    results = {
        'SupabaseIntegration portal methods': test_supabase_portal_methods(),
        'send_email()': test_send_email(),
        'search_thread()': test_search_thread(),
        'get_attachments()': test_get_attachments()
    }

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Test Results Summary")
    logger.info("=" * 80)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status}: {test_name}")

    total_tests = len(results)
    passed_tests = sum(1 for passed in results.values() if passed)

    logger.info(f"\nTotal: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.warning(f"\n⚠️ {total_tests - passed_tests} test(s) failed")
        return 1


if __name__ == '__main__':
    exit(main())
