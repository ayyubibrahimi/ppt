#!/usr/bin/env python3
"""
Test script for Gmail monitoring system.

Tests the full end-to-end pipeline:
1. Fetch emails from Gmail via MCP
2. Match emails to requests
3. Analyze email content with LLM
4. Update database with Gmail analysis

Usage:
    python test_gmail_monitoring.py <user_id>
"""

import sys
import logging
from gmail_monitoring_agent import GmailMonitoringAgent
from supabase_integration import SupabaseIntegration
from llm import gpt_4o

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_gmail_monitoring():
    """Test Gmail monitoring for a specific user"""

    user_id = "8bb0051b-4282-4a29-b70e-88234430bcb7"

    print("=" * 80)
    print("🧪 GMAIL MONITORING SYSTEM TEST")
    print("=" * 80)
    print(f"User ID: {user_id}")
    print("=" * 80)

    # Initialize database
    print("\n📊 Initializing database connection...")
    db = SupabaseIntegration()

    # Verify user exists
    user_email = db.get_user_email(user_id)
    if not user_email:
        print(f"❌ User {user_id} not found in database")
        return 1

    print(f"✅ User email: {user_email}")

    # Initialize Gmail monitoring agent
    print("\n📧 Initializing Gmail monitoring agent...")
    agent = GmailMonitoringAgent(
        db=db,
        llm_client=gpt_4o,
        check_interval_minutes=5
    )
    print("✅ Agent initialized")

    # Run monitoring cycle
    print("\n🔄 Running Gmail monitoring cycle...")
    print("-" * 80)

    result = agent.run_monitoring_cycle(user_id)

    print("-" * 80)

    # Display results
    print("\n📊 RESULTS:")
    print("=" * 80)

    if result['success']:
        print(f"✅ Status: SUCCESS")
        print(f"📧 Emails processed: {result['emails_processed']}")
        print(f"⏭️  Emails skipped (already processed): {result['emails_skipped']}")
        print(f"🔍 Changes detected: {result['changes_detected']}")

        if result.get('errors'):
            print(f"\n⚠️  Errors encountered ({len(result['errors'])}):")
            for i, error in enumerate(result['errors'][:5], 1):
                print(f"  {i}. {error}")
            if len(result['errors']) > 5:
                print(f"  ... and {len(result['errors']) - 5} more")
        else:
            print(f"✅ No errors")

        print(f"\n📝 Summary: {result['summary']}")

        # Query database to show updated requests
        print("\n" + "=" * 80)
        print("📋 REQUESTS WITH GMAIL ANALYSIS:")
        print("=" * 80)

        requests_result = db.supabase.table('requests').select(
            'request_number, portal_name, last_gmail_check, latest_analysis_gmail, latest_analysis'
        ).eq('user_id', user_id).not_.is_('last_gmail_check', 'null').execute()

        if requests_result.data:
            for req in requests_result.data[:5]:  # Show first 5
                print(f"\n  Request: {req['request_number']}")
                print(f"  Portal: {req['portal_name']}")
                print(f"  Last Gmail check: {req['last_gmail_check']}")
                if req.get('latest_analysis_gmail'):
                    status = req['latest_analysis_gmail'].get('current_status', 'Unknown')
                    events_count = len(req['latest_analysis_gmail'].get('all_timeline_events', []))
                    print(f"  Status (from Gmail): {status}")
                    print(f"  Timeline events: {events_count}")

            if len(requests_result.data) > 5:
                print(f"\n  ... and {len(requests_result.data) - 5} more requests")

            # Run LLM comparison on requests that have both analyses
            print("\n" + "=" * 80)
            print("🔍 ANALYSIS QUALITY COMPARISON (Gmail vs Portal):")
            print("=" * 80)

            comparisons_run = 0
            for req in requests_result.data[:3]:  # Compare first 3 requests
                if req.get('latest_analysis') and req.get('latest_analysis_gmail'):
                    print(f"\n  📊 Comparing request {req['request_number']}...")

                    comparison = agent.gmail_helper.compare_analyses(
                        portal_analysis=req['latest_analysis'],
                        gmail_analysis=req['latest_analysis_gmail'],
                        request_number=req['request_number']
                    )

                    print(f"    Verdict: {comparison.verdict}")
                    print(f"    Overall Score: {comparison.overall_quality_score:.2f}/1.0")
                    print(f"    - Timeline Completeness: {comparison.timeline_completeness_score:.2f}")
                    print(f"    - Status Accuracy: {comparison.status_accuracy_score:.2f}")
                    print(f"    - Flags Accuracy: {comparison.flags_accuracy_score:.2f}")
                    print(f"    - Document/Payment: {comparison.document_payment_score:.2f}")
                    print(f"    Summary: {comparison.summary}")
                    if comparison.recommendations and comparison.recommendations != "None" and "No improvements" not in comparison.recommendations:
                        print(f"    ⚠️  Recommendations: {comparison.recommendations}")

                    comparisons_run += 1

            if comparisons_run == 0:
                print("\n  ℹ️  No requests have both portal and Gmail analyses yet.")
                print("     Run portal monitoring first to enable comparison.")
        else:
            print("  No requests updated via Gmail yet")

        return 0

    else:
        print(f"❌ Status: FAILED")
        print(f"❌ Error: {result.get('error', 'Unknown error')}")
        return 1


if __name__ == '__main__':
    exit_code = test_gmail_monitoring()
   
