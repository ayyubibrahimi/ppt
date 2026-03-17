#!/usr/bin/env python3
"""
Quick EDA script to analyze the current state of message_drafts table
"""

import sys
from dotenv import load_dotenv
from supabase_integration import SupabaseIntegration
from collections import Counter
import json

# Load environment variables
load_dotenv()

def main():
    print("=" * 80)
    print("MESSAGE DRAFTS TABLE - EXPLORATORY DATA ANALYSIS")
    print("=" * 80)
    print()

    # Initialize database connection
    db = SupabaseIntegration()

    # Get all message drafts
    print("📊 Fetching all message drafts...")
    result = db.supabase.table('message_drafts').select('*').execute()
    drafts = result.data or []

    print(f"✅ Retrieved {len(drafts)} total drafts\n")

    if len(drafts) == 0:
        print("No drafts found in the database.")
        return

    # === OVERALL STATS ===
    print("=" * 80)
    print("OVERALL STATISTICS")
    print("=" * 80)
    print(f"Total drafts: {len(drafts)}")
    print()

    # === USER_APPROVED BREAKDOWN ===
    print("=" * 80)
    print("USER_APPROVED BREAKDOWN")
    print("=" * 80)
    approved_count = len([d for d in drafts if d.get('user_approved') == True])
    not_approved_count = len([d for d in drafts if d.get('user_approved') == False or d.get('user_approved') is None])

    print(f"✅ user_approved = True:  {approved_count} ({approved_count/len(drafts)*100:.1f}%)")
    print(f"❌ user_approved = False: {not_approved_count} ({not_approved_count/len(drafts)*100:.1f}%)")
    print()

    # === DRAFT_STATUS BREAKDOWN ===
    print("=" * 80)
    print("DRAFT_STATUS BREAKDOWN")
    print("=" * 80)
    status_counts = Counter(d.get('draft_status') for d in drafts)
    for status, count in status_counts.most_common():
        print(f"  {status:20s}: {count:4d} ({count/len(drafts)*100:.1f}%)")

    # Show approved status specifically
    approved_status_count = len([d for d in drafts if d.get('draft_status') == 'approved'])
    print(f"\n  📌 APPROVED (ready to send): {approved_status_count}")
    print()

    # === MESSAGE_TYPE BREAKDOWN ===
    print("=" * 80)
    print("MESSAGE_TYPE BREAKDOWN")
    print("=" * 80)
    type_counts = Counter(d.get('message_type') for d in drafts)
    for msg_type, count in type_counts.most_common():
        print(f"  {msg_type:20s}: {count:4d} ({count/len(drafts)*100:.1f}%)")
    print()

    # === SAFE THANK YOU MESSAGES ===
    print("=" * 80)
    print("SAFE THANK YOU MESSAGES (Exact Matches)")
    print("=" * 80)

    SAFE_MESSAGES = {
        "Thank you for confirming.",
        "Thank you for the update.",
        "I'm confirming receipt. Thank you for your response.",
        "I'm confirming receipt. Thank you."
    }

    safe_message_count = 0
    safe_message_details = []

    for draft in drafts:
        message = draft.get('draft_message', '').strip()
        if message in SAFE_MESSAGES:
            safe_message_count += 1
            safe_message_details.append({
                'id': draft.get('id'),
                'message': message,
                'user_approved': draft.get('user_approved'),
                'draft_status': draft.get('draft_status'),
                'created_at': draft.get('created_at', '')[:19]  # Truncate timestamp
            })

    print(f"Found {safe_message_count} drafts with exact safe thank you messages")
    print()

    if safe_message_count > 0:
        print("Details of safe thank you messages:")
        print("-" * 80)
        for detail in safe_message_details[:10]:  # Show first 10
            print(f"  ID: {detail['id']}")
            print(f"  Message: \"{detail['message']}\"")
            print(f"  user_approved: {detail['user_approved']}")
            print(f"  draft_status: {detail['draft_status']}")
            print(f"  created_at: {detail['created_at']}")
            print()

        if len(safe_message_details) > 10:
            print(f"  ... and {len(safe_message_details) - 10} more")
            print()

    # === AUTO_APPROVED IN CHANGE_CONTEXT ===
    print("=" * 80)
    print("AUTO_APPROVED FLAG IN change_context")
    print("=" * 80)

    auto_approved_in_context = 0
    for draft in drafts:
        change_context = draft.get('change_context', {})
        if isinstance(change_context, dict) and change_context.get('auto_approved') == True:
            auto_approved_in_context += 1

    print(f"Drafts with auto_approved=True in change_context: {auto_approved_in_context}")
    print()

    # === RECENT DRAFTS ===
    print("=" * 80)
    print("5 MOST RECENT DRAFTS (Sample)")
    print("=" * 80)

    sorted_drafts = sorted(drafts, key=lambda x: x.get('created_at', ''), reverse=True)
    for i, draft in enumerate(sorted_drafts[:5], 1):
        print(f"{i}. Draft ID: {draft.get('id')}")
        print(f"   Message: \"{draft.get('draft_message', '')[:100]}...\"")
        print(f"   user_approved: {draft.get('user_approved')}")
        print(f"   draft_status: {draft.get('draft_status')}")
        print(f"   created_at: {draft.get('created_at', '')[:19]}")
        print()

    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
