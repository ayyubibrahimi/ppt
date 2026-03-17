#!/usr/bin/env python3
"""
Enhanced test script for Gmail monitoring with detailed comparison.

Tests 20+ unique requests and provides detailed diagnostics on differences
between Gmail-based and Portal-based analyses.
"""

import sys
import logging
from gmail_monitoring_agent import GmailMonitoringAgent
from supabase_integration import SupabaseIntegration
from llm import gpt_4o
from mcp_gmail_client import MCPGmailClient
import json

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Reduce noise
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def compare_timeline_events(portal_events, gmail_events, request_number):
    """Detailed comparison of timeline events"""
    print(f"\n    🔍 Timeline Comparison for {request_number}:")
    print(f"    Portal: {len(portal_events)} events | Gmail: {len(gmail_events)} events")

    # Show first few events from each
    print("\n    Portal Timeline (first 3):")
    for i, event in enumerate(portal_events[:3], 1):
        print(f"      {i}. {event[:100]}...")

    print("\n    Gmail Timeline (first 3):")
    for i, event in enumerate(gmail_events[:3], 1):
        print(f"      {i}. {event[:100]}...")

    # Find events in portal but not gmail
    if len(portal_events) > len(gmail_events):
        missing = len(portal_events) - len(gmail_events)
        print(f"\n    ⚠️  Gmail missing {missing} events that portal has")


def show_email_sample(request_number, processed_ids):
    """Show a sample email body to understand what Gmail sees"""
    if not processed_ids:
        return

    print(f"\n    📧 Sample Email Body for {request_number}:")
    print("    " + "-" * 76)

    try:
        with MCPGmailClient() as mcp:
            email = mcp.read_email(processed_ids[0])
            if email and email.get('body'):
                # Show first 500 chars of body
                body = email['body'][:500]
                print(f"    {body}")
                if len(email['body']) > 500:
                    print(f"    ... (truncated, full body is {len(email['body'])} chars)")
                print("    " + "-" * 76)
    except Exception as e:
        print(f"    ⚠️  Could not fetch email sample: {e}")


def test_gmail_monitoring_enhanced():
    """Enhanced test with 20+ request comparisons"""

    user_id = "8bb0051b-4282-4a29-b70e-88234430bcb7"

    print("=" * 80)
    print("🧪 ENHANCED GMAIL MONITORING TEST (20+ Requests)")
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
    print("\n📊 MONITORING RESULTS:")
    print("=" * 80)

    if result['success']:
        print(f"✅ Status: SUCCESS")
        print(f"📧 Emails processed: {result['emails_processed']}")
        print(f"⏭️  Emails skipped: {result['emails_skipped']}")
        print(f"🔍 Changes detected: {result['changes_detected']}")

        if result.get('errors'):
            print(f"\n⚠️  Errors: {len(result['errors'])}")
            for i, error in enumerate(result['errors'][:3], 1):
                print(f"  {i}. {error}")

        # Query ALL requests with Gmail analysis
        print("\n" + "=" * 80)
        print("🔍 DETAILED COMPARISON: 20 UNIQUE REQUESTS")
        print("=" * 80)

        requests_result = db.supabase.table('requests').select(
            'request_number, portal_name, last_gmail_check, latest_analysis_gmail, '
            'latest_analysis, processed_gmail_ids'
        ).eq('user_id', user_id).not_.is_('last_gmail_check', 'null').limit(20).execute()

        if not requests_result.data:
            print("  ℹ️  No requests with Gmail analysis found")
            return 0

        print(f"\n📊 Found {len(requests_result.data)} requests to compare")

        # Track statistics
        passed = 0
        failed = 0
        scores = []
        timeline_completeness_scores = []

        # Compare each request
        for idx, req in enumerate(requests_result.data, 1):
            request_num = req['request_number']
            portal_analysis = req.get('latest_analysis')
            gmail_analysis = req.get('latest_analysis_gmail')

            print(f"\n{'=' * 80}")
            print(f"Request #{idx}: {request_num} ({req['portal_name'].split('//')[1].split('.')[0]})")
            print('=' * 80)

            if not portal_analysis:
                print("  ⚠️  No portal analysis available (skipping)")
                continue

            if not gmail_analysis:
                print("  ⚠️  No Gmail analysis available (skipping)")
                continue

            # Show email sample for first 3 requests
            if idx <= 3:
                show_email_sample(request_num, req.get('processed_gmail_ids', []))

            # Compare analyses
            comparison = agent.gmail_helper.compare_analyses(
                portal_analysis=portal_analysis,
                gmail_analysis=gmail_analysis,
                request_number=request_num
            )

            # Update statistics
            scores.append(comparison.overall_quality_score)
            timeline_completeness_scores.append(comparison.timeline_completeness_score)

            if comparison.verdict == "PASS":
                passed += 1
                status_emoji = "✅"
            else:
                failed += 1
                status_emoji = "❌"

            # Display comparison
            print(f"\n  {status_emoji} Verdict: {comparison.verdict}")
            print(f"  📊 Overall Score: {comparison.overall_quality_score:.2f}/1.0")
            print(f"     - Timeline Completeness: {comparison.timeline_completeness_score:.2f}")
            print(f"     - Status Accuracy: {comparison.status_accuracy_score:.2f}")
            print(f"     - Flags Accuracy: {comparison.flags_accuracy_score:.2f}")
            print(f"     - Document/Payment: {comparison.document_payment_score:.2f}")

            # Show summary
            print(f"\n  💬 Summary:")
            print(f"     {comparison.summary}")

            # Show recommendations if any
            if comparison.recommendations and "No improvements" not in comparison.recommendations:
                print(f"\n  ⚠️  Recommendations:")
                print(f"     {comparison.recommendations}")

            # Detailed timeline comparison for lower scores
            if comparison.timeline_completeness_score < 0.8:
                portal_events = portal_analysis.get('all_timeline_events', [])
                gmail_events = gmail_analysis.get('all_timeline_events', [])
                compare_timeline_events(portal_events, gmail_events, request_num)

        # Overall statistics
        print("\n" + "=" * 80)
        print("📈 OVERALL STATISTICS")
        print("=" * 80)
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"📊 Pass Rate: {(passed / (passed + failed) * 100):.1f}%")

        if scores:
            avg_score = sum(scores) / len(scores)
            avg_timeline = sum(timeline_completeness_scores) / len(timeline_completeness_scores)
            print(f"\n📊 Average Overall Score: {avg_score:.2f}/1.0")
            print(f"📊 Average Timeline Completeness: {avg_timeline:.2f}/1.0")

            # Identify common issues
            print("\n🔍 Common Issues Identified:")
            low_timeline = [s for s in timeline_completeness_scores if s < 0.8]
            if low_timeline:
                print(f"  • {len(low_timeline)}/{len(scores)} requests have timeline completeness < 0.8")
                print(f"    → Gmail may be missing early timeline events from emails")

            perfect_timeline = [s for s in timeline_completeness_scores if s >= 0.95]
            if perfect_timeline:
                print(f"  • {len(perfect_timeline)}/{len(scores)} requests have excellent timeline (≥0.95)")
                print(f"    → These show Gmail can extract complete timelines")

        return 0

    else:
        print(f"❌ Status: FAILED")
        print(f"❌ Error: {result.get('error', 'Unknown error')}")
        return 1


if __name__ == '__main__':
    exit_code = test_gmail_monitoring_enhanced()
    sys.exit(exit_code)
