#!/usr/bin/env python3
"""
Analyze ALL requests with Gmail monitoring to ensure complete coverage.
"""

from dotenv import load_dotenv
load_dotenv()

import logging
from gmail_monitoring_agent import GmailMonitoringAgent
from supabase_integration import SupabaseIntegration
from llm import gpt_4o

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def analyze_all_requests():
    print("=" * 80)
    print("🔍 ANALYZING ALL REQUESTS WITH GMAIL MONITORING")
    print("=" * 80)

    user_id = "8bb0051b-4282-4a29-b70e-88234430bcb7"

    # Initialize
    db = SupabaseIntegration()
    agent = GmailMonitoringAgent(db=db, llm_client=gpt_4o)

    # Get ALL requests
    print(f"\n📊 Fetching all requests for user {user_id}...")
    result = db.supabase.table('requests').select('*').eq('user_id', user_id).execute()

    all_requests = result.data
    print(f"✅ Total requests: {len(all_requests)}")

    # Count by analysis status
    with_both = sum(1 for r in all_requests if r.get('latest_analysis') and r.get('latest_analysis_gmail'))
    only_portal = sum(1 for r in all_requests if r.get('latest_analysis') and not r.get('latest_analysis_gmail'))
    no_analysis = sum(1 for r in all_requests if not r.get('latest_analysis'))

    print(f"\n📈 Current Status:")
    print(f"   With both analyses: {with_both}")
    print(f"   Only portal analysis: {only_portal}")
    print(f"   No portal analysis: {no_analysis}")

    # Analyze requests that need Gmail analysis
    requests_to_analyze = [r for r in all_requests if r.get('latest_analysis') and not r.get('latest_analysis_gmail')]

    if not requests_to_analyze:
        print(f"\n✅ All {with_both} requests already have Gmail analysis!")
        return with_both

    print(f"\n🔄 Analyzing {len(requests_to_analyze)} requests without Gmail analysis...")
    print("=" * 80)

    success_count = 0
    error_count = 0

    for i, request in enumerate(requests_to_analyze, 1):
        request_num = request['request_number']
        print(f"\n[{i}/{len(requests_to_analyze)}] Processing {request_num}...")

        try:
            # Fetch all emails for this request
            messages = agent._fetch_all_thread_emails(request_num, request['id'])

            if not messages:
                print(f"   ⚠️  No emails found for {request_num}")
                continue

            print(f"   📧 Found {len(messages)} messages")

            # Analyze with LLM
            analysis = agent.gmail_helper.analyze_gmail_request_thread(
                request_number=request_num,
                request_text=request.get('request_text', 'Not available'),
                portal_name=request['portal_name'],
                email_thread=messages,
                current_status=request.get('current_status', 'Unknown')
            )

            # Save to database
            db.supabase.table('requests').update({
                'latest_analysis_gmail': analysis.model_dump(),
                'last_gmail_check': 'now()'
            }).eq('id', request['id']).execute()

            print(f"   ✅ Analysis saved")
            success_count += 1

        except Exception as e:
            print(f"   ❌ Error: {e}")
            error_count += 1
            continue

    # Final summary
    print("\n" + "=" * 80)
    print("📊 ANALYSIS COMPLETE")
    print("=" * 80)
    print(f"✅ Successfully analyzed: {success_count}")
    print(f"❌ Errors: {error_count}")
    print(f"📊 Total with both analyses: {with_both + success_count}")

    return with_both + success_count


if __name__ == '__main__':
    total_with_both = analyze_all_requests()
    print(f"\n🎯 Ready to test {total_with_both} requests with practical completeness!")
