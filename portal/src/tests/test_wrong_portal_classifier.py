#!/usr/bin/env python3
"""
Wrong Portal Classifier: Identifies emails indicating request was sent to wrong agency.

Reads all emails from Gmail inbox and classifies whether they indicate that:
1. The request was submitted to the wrong portal/agency
2. The request was forwarded or redirected to another agency
3. Extracts the correct agency name when mentioned

Outputs results to a text file for review.
"""

import logging
from typing import List, Dict, Any
from mcp_gmail_client import MCPGmailClient
from wrong_portal_llm_helper import WrongPortalLLMHelper
from llm import gpt_4o
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def test_wrong_portal_classification():
    """
    Main function to classify all emails for wrong portal submissions.
    """
    print("=" * 80)
    print("🔍 WRONG PORTAL CLASSIFIER: Analyzing All Emails")
    print("=" * 80)

    # Initialize
    gmail_helper = WrongPortalLLMHelper(llm_client=gpt_4o)

    # Fetch all emails from inbox
    print("\n📧 Fetching all emails from inbox...")

    try:
        with MCPGmailClient() as mcp:
            # Search for all NextRequest emails
            query = "from:messages@nextrequest.com in:inbox"
            emails = mcp.search_emails(query, max_results=500)

            print(f"✅ Found {len(emails)} emails to analyze")
    except Exception as e:
        print(f"❌ Failed to fetch emails: {e}")
        return

    if not emails:
        print("❌ No emails found")
        return

    # Track statistics
    wrong_portal_count = 0
    forwarded_count = 0
    correct_portal_count = 0
    error_count = 0

    wrong_portal_results = []

    # Analyze each email
    for i, email in enumerate(emails, 1):
        email_id = email.get('id', 'unknown')
        subject = email.get('subject', 'No subject')

        print(f"\n{'=' * 80}")
        print(f"Email #{i}/{len(emails)}: {subject[:60]}")
        print('=' * 80)

        try:
            # Read full email body
            with MCPGmailClient() as mcp:
                full_email = mcp.read_email(email_id)

            if not full_email or not full_email.get('body'):
                print("⚠️  No email body found, skipping")
                error_count += 1
                continue

            email_body = full_email.get('body', '')
            email_from = full_email.get('from', '')
            email_date = full_email.get('date', '')

            # Classify email
            classification = gmail_helper.classify_wrong_portal(
                subject=subject,
                body=email_body,
                from_address=email_from
            )

            # Display results
            if classification.is_wrong_portal:
                wrong_portal_count += 1
                status_emoji = "❌"

                print(f"\n{status_emoji} Wrong Portal Detected!")
                print(f"📝 Reason: {classification.reason}")
                print(f"🏢 Correct Agency: {classification.correct_agency_name}")
                print(f"🔄 Forwarded: {classification.forwarded}")

                # Store for output file
                wrong_portal_results.append({
                    'email_id': email_id,
                    'subject': subject,
                    'date': email_date,
                    'from': email_from,
                    'correct_agency': classification.correct_agency_name,
                    'reason': classification.reason,
                    'forwarded': classification.forwarded,
                    'excerpt': classification.relevant_excerpt[:200] if classification.relevant_excerpt else "N/A"
                })

                if classification.forwarded:
                    forwarded_count += 1
            else:
                correct_portal_count += 1
                print(f"\n✅ Correct Portal")

        except Exception as e:
            logger.error(f"❌ Error analyzing email {email_id}: {e}")
            error_count += 1
            continue

    # Output statistics
    print("\n" + "=" * 80)
    print("📊 CLASSIFICATION STATISTICS")
    print("=" * 80)

    total = len(emails)
    print(f"\n📧 Total Emails Analyzed: {total}")
    print(f"❌ Wrong Portal: {wrong_portal_count}")
    print(f"🔄 Forwarded to Correct Agency: {forwarded_count}")
    print(f"✅ Correct Portal: {correct_portal_count}")
    print(f"⚠️  Errors: {error_count}")

    if wrong_portal_count > 0:
        print(f"\n📈 Wrong Portal Rate: {(wrong_portal_count / total * 100):.1f}%")

    # Write results to file
    output_file = f"wrong_portal_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    try:
        with open(output_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("WRONG PORTAL CLASSIFICATION RESULTS\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Emails Analyzed: {total}\n")
            f.write(f"Wrong Portal Detected: {wrong_portal_count}\n")
            f.write(f"Forwarded to Correct Agency: {forwarded_count}\n")
            f.write(f"Correct Portal: {correct_portal_count}\n")
            f.write(f"Errors: {error_count}\n\n")

            f.write("=" * 80 + "\n")
            f.write("WRONG PORTAL SUBMISSIONS\n")
            f.write("=" * 80 + "\n\n")

            if wrong_portal_results:
                for idx, result in enumerate(wrong_portal_results, 1):
                    f.write(f"--- Entry #{idx} ---\n")
                    f.write(f"Date: {result['date']}\n")
                    f.write(f"Subject: {result['subject']}\n")
                    f.write(f"Correct Agency: {result['correct_agency']}\n")
                    f.write(f"Forwarded: {result['forwarded']}\n")
                    f.write(f"Reason: {result['reason']}\n")
                    f.write(f"Excerpt: {result['excerpt']}\n")
                    f.write(f"Email ID: {result['email_id']}\n")
                    f.write("\n")
            else:
                f.write("No wrong portal submissions detected.\n")

        print(f"\n✅ Results written to: {output_file}")

    except Exception as e:
        logger.error(f"❌ Failed to write output file: {e}")

    print("\n" + "=" * 80)
    print("✅ CLASSIFICATION COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    test_wrong_portal_classification()
