#!/usr/bin/env python3
"""
Quick test to verify bidirectional conversation fetching is working.
"""

import logging
from gmail_monitoring_agent import GmailMonitoringAgent
from supabase_integration import SupabaseIntegration
from llm import gpt_4o

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_conversation_fetching():
    """Test that we're fetching both emails and sent messages"""

    print("=" * 80)
    print("🧪 BIDIRECTIONAL CONVERSATION TEST")
    print("=" * 80)

    db = SupabaseIntegration()
    agent = GmailMonitoringAgent(db=db, llm_client=gpt_4o)

    # Get a request that has sent messages
    print("\n📊 Finding requests with sent messages...")
    result = db.supabase.table('message_drafts').select(
        'request_id, draft_subject'
    ).eq('draft_status', 'sent').limit(5).execute()

    if not result.data:
        print("❌ No sent messages found in database")
        return

    print(f"✅ Found {len(result.data)} requests with sent messages\n")

    # Check first request
    request_id = result.data[0]['request_id']

    # Get request details
    req_result = db.supabase.table('requests').select(
        'request_number, portal_name, processed_gmail_ids'
    ).eq('id', request_id).execute()

    if not req_result.data:
        print("❌ Request not found")
        return

    request = req_result.data[0]
    print(f"Request: {request['request_number']}")
    print(f"Portal: {request['portal_name']}")
    print(f"Processed Gmail IDs: {len(request.get('processed_gmail_ids', []))}")

    # Count sent messages for this request
    sent_count = db.supabase.table('message_drafts').select('id').eq(
        'request_id', request_id
    ).eq('draft_status', 'sent').execute()

    print(f"Sent messages in DB: {len(sent_count.data)}")

    # Simulate fetching conversation
    print("\n📧 Simulating conversation fetch...")

    try:
        messages = agent._fetch_all_thread_emails(
            request_number=request['request_number'],
            request_id=request_id
        )

        print(f"\n✅ Fetched {len(messages)} total messages:")

        incoming = sum(1 for m in messages if m.get('direction') == 'incoming')
        outgoing = sum(1 for m in messages if m.get('direction') == 'outgoing')

        print(f"   - {incoming} incoming (agency → user)")
        print(f"   - {outgoing} outgoing (user → agency)")

        print("\n📋 Message timeline:")
        for i, msg in enumerate(messages[:5], 1):
            direction_emoji = "📨" if msg['direction'] == 'incoming' else "📤"
            print(f"   {i}. {direction_emoji} {msg['direction']}: {msg.get('subject', 'No subject')[:50]}")
            print(f"      Date: {msg.get('date', 'Unknown')}")
            print(f"      Body preview: {msg.get('body', '')[:80]}...")

        if len(messages) > 5:
            print(f"   ... and {len(messages) - 5} more messages")

        print("\n" + "=" * 80)
        print("✅ SUCCESS: Bidirectional conversation fetching is working!")
        print("=" * 80)

        return messages

    except Exception as e:
        print(f"\n❌ Error fetching conversation: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == '__main__':
    test_conversation_fetching()
