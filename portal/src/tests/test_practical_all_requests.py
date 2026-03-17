#!/usr/bin/env python3
"""
Test practical completeness comparison on ALL requests.

Compares Gmail vs Portal using the new practical completeness metric
that focuses on "Does Gmail have the important information?"
rather than strict field-by-field matching.
"""

import logging
from gmail_llm_helper import GmailLLMHelper
from supabase_integration import SupabaseIntegration
from llm import gpt_4o
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.WARNING, format='%(message)s')

def test_practical_all():
    print("=" * 80)
    print("🧪 PRACTICAL COMPLETENESS TEST: ALL Requests")
    print("=" * 80)

    # Initialize
    db = SupabaseIntegration()
    gmail_helper = GmailLLMHelper(llm_client=gpt_4o)

    # Get ALL requests with both analyses
    print("\n📊 Fetching ALL requests with both Gmail and Portal analyses...")
    user_id = "8bb0051b-4282-4a29-b70e-88234430bcb7"

    result = db.supabase.table('requests').select(
        'request_number, portal_name, latest_analysis, latest_analysis_gmail'
    ).eq('user_id', user_id).not_.is_(
        'latest_analysis', 'null'
    ).not_.is_(
        'latest_analysis_gmail', 'null'
    ).execute()

    if not result.data:
        print("❌ No requests found with both analyses")
        return

    requests = result.data
    print(f"✅ Found {len(requests)} requests to compare")

    # Track statistics
    passed = 0
    failed = 0
    scores = []

    # Compare each request
    for i, req in enumerate(requests, 1):
        request_num = req['request_number']
        portal = req['portal_name'].split('//')[1].split('.')[0]

        print(f"\n{'=' * 80}")
        print(f"Request #{i}: {request_num} ({portal})")
        print('=' * 80)

        try:
            # Run practical completeness assessment
            assessment = gmail_helper.compare_practical_completeness(
                portal_analysis=req['latest_analysis'],
                gmail_analysis=req['latest_analysis_gmail'],
                request_number=request_num
            )

            # Track results
            scores.append(assessment.practical_score)

            if assessment.verdict == "PASS":
                passed += 1
                status_emoji = "✅"
            else:
                failed += 1
                status_emoji = "❌"

            # Display results
            print(f"\n{status_emoji} Verdict: {assessment.verdict}")
            print(f"📈 Practical Score: {assessment.practical_score:.2f}/1.0")

            print(f"\n💬 Summary:")
            print(f"   {assessment.summary}")

            if assessment.critical_gaps:
                print(f"\n❌ Critical Gaps:")
                for gap in assessment.critical_gaps:
                    print(f"   - {gap}")

            if assessment.minor_gaps and len(assessment.minor_gaps) <= 3:
                print(f"\n⚠️  Minor Gaps (First 3):")
                for gap in assessment.minor_gaps[:3]:
                    print(f"   - {gap}")
            elif assessment.minor_gaps:
                print(f"\n⚠️  Minor Gaps: {len(assessment.minor_gaps)} items (system events, etc.)")

        except Exception as e:
            print(f"\n❌ Error comparing: {e}")
            failed += 1
            continue

    # Overall statistics
    print("\n" + "=" * 80)
    print("📈 OVERALL STATISTICS")
    print("=" * 80)

    total = passed + failed
    print(f"\n✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {failed}/{total}")
    print(f"📊 Pass Rate: {(passed / total * 100):.1f}%")

    if scores:
        avg_score = sum(scores) / len(scores)
        print(f"\n📊 Average Practical Score: {avg_score:.2f}/1.0")

        # Score distribution
        high = sum(1 for s in scores if s >= 0.8)
        medium = sum(1 for s in scores if 0.6 <= s < 0.8)
        low = sum(1 for s in scores if s < 0.6)

        print(f"\n📊 Score Distribution:")
        print(f"   🌟 High (≥0.8):   {high}/{total} ({high/total*100:.1f}%)")
        print(f"   👍 Medium (0.6-0.8): {medium}/{total} ({medium/total*100:.1f}%)")
        print(f"   👎 Low (<0.6):    {low}/{total} ({low/total*100:.1f}%)")

    print("\n" + "=" * 80)
    print("✅ TEST COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    test_practical_all()
