#!/usr/bin/env python3
"""
Portal Agent Unified Entry Point

Consolidates all 7 main_*.py scripts into a single CLI with subcommands.

Available Commands:
    queue submit       - Submit requests from queue (main.py)
    queue analyze      - Bulk analyze portal requests (main_bulk_analysis.py)
    monitor            - Monitor requests for changes (main_monitor.py)
    messages draft     - Draft messages for flagged requests (main_message_draft.py)
    messages send      - Send approved message drafts (main_message_send.py)
    documents download - Download documents from requests (main_document_downloads.py)
    account create     - Create portal accounts (main_new_account.py)

Examples:
    entry.py queue submit --continuous --user-id abc123
    entry.py queue analyze --user-id abc123 --max-jobs 5
    entry.py monitor --mode single
    entry.py monitor --mode continuous --interval 60
    entry.py messages draft --auto-approve
    entry.py messages send --max-batch-size 20
    entry.py documents download --mode single
    entry.py account create --user-id abc123
"""

import sys
import os
import time
import logging
import argparse
import gc
from datetime import datetime
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Import core components
from llm import gpt_4o
from portal_agent import PortalAgent
from email_agent import EmailAgent
from models import LoginCredentials
from message_coordinator import MessageCoordinator
from supabase_integration import SupabaseIntegration
from document_download_coordinator import DocumentDownloadCoordinator
from mcp_gmail_client import MCPGmailClient

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# SHARED UTILITIES (Used by all commands)
# ============================================================================

def validate_environment(require_google: bool = False) -> bool:
    """Validate required environment variables"""
    required_vars = ['SUPABASE_URL', 'SUPABASE_ANON_KEY']

    if require_google:
        required_vars.extend(['GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET'])

    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        print(f"❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"  • {var}")
        print(f"\nPlease add these to your .env file.")
        return False

    return True


def get_credentials_for_user_portal(db: SupabaseIntegration, user_id: str, portal_name: str) -> Optional[Dict[str, Any]]:
    """Get verified credentials for a specific user/portal combination"""
    try:
        # Get credentials for this user
        creds_result = db.supabase.table('user_portal_credentials').select(
            '*'
        ).eq('user_id', user_id).eq('is_active', True).eq('verification_status', 'verified').execute()

        if not creds_result.data:
            return None

        # Get portal info to match portal_name
        portals_result = db.supabase.table('portals').select('*').execute()
        portals = portals_result.data or []
        portal_lookup = {portal['id']: portal for portal in portals}

        # Find credential that matches the portal_name
        for cred in creds_result.data:
            portal_info = portal_lookup.get(cred['portal_id'], {})
            if portal_info.get('portal_url') == portal_name:
                return {
                    'id': cred['id'],
                    'user_id': cred['user_id'],
                    'portal_id': cred['portal_id'],
                    'username': cred['encrypted_username'],
                    'password': cred['encrypted_password'],
                    'agency_name': portal_info.get('agency_name', 'Unknown Agency'),
                    'portal_url': portal_info.get('portal_url', ''),
                    'portal_type': portal_info.get('portal_type', 'unknown'),
                    'requester_name': cred.get('requester_name', ''),
                    'requester_email': cred.get('requester_email', ''),
                    'requester_phone': cred.get('requester_phone', ''),
                    'requester_organization': cred.get('requester_organization', ''),
                }

        return None

    except Exception as e:
        logger.error(f"❌ Error getting credentials for user {user_id}, portal {portal_name}: {str(e)}")
        return None


# ============================================================================
# COMMAND: queue submit
# ============================================================================

def process_email_submission(submission_data: dict) -> dict:
    """
    Process a single email-based submission.

    Args:
        submission_data: Submission queue entry dict

    Returns:
        {
            'success': bool,
            'error': str (if failed),
            'submission_id': str,
            'request_id': str,
            'thread_id': str
        }
    """
    try:
        db = SupabaseIntegration()

        # Get portal data (email address)
        portal_id = submission_data['portal_id']
        portal = db.get_portal(portal_id)

        if not portal:
            error_msg = f"Portal {portal_id} not found"
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'submission_id': submission_data.get('id')
            }

        agency_email = portal.get('contact_email')

        if not agency_email:
            error_msg = f"No contact_email for portal {portal_id}"
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'submission_id': submission_data.get('id')
            }

        # Get user email for sender
        user_id = submission_data['user_id']
        user_email = db.get_user_email(user_id)

        if not user_email:
            error_msg = f"User email not found for {user_id}"
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'submission_id': submission_data.get('id')
            }

        # Get user credentials for requester info
        credentials = db.supabase.table('user_portal_credentials').select(
            'requester_name, requester_email, requester_phone, requester_organization, street_address'
        ).eq('user_id', user_id).eq('portal_id', portal_id).eq('is_active', True).single().execute()

        # Prepare user_info from submission_data and credentials
        user_info = submission_data.get('user_info', {})
        user_info['user_id'] = user_id

        # Merge in credential data if available
        if credentials.data:
            cred = credentials.data
            user_info.setdefault('full_name', cred.get('requester_name', ''))
            user_info.setdefault('email', cred.get('requester_email', user_email))
            user_info.setdefault('phone', cred.get('requester_phone', ''))
            user_info.setdefault('address', cred.get('street_address', ''))

        # Initialize EmailAgent
        logger.info(f"📧 Processing email submission {submission_data['id']} to {agency_email}")
        agent = EmailAgent(gpt_4o, user_email)

        # Get request category from user_notes (if available)
        request_category = submission_data.get('user_notes', '')

        # Submit request
        result = agent.submit_request(
            agency_email=agency_email,
            request_text=submission_data['request_text'],
            user_info=user_info,
            db=db,
            portal_id=portal_id,
            submission_queue_id=submission_data['id'],
            request_category=request_category
        )

        if result['success']:
            logger.info(f"✅ Email submission successful: thread_id={result['thread_id']}, request_id={result['request_id']}")
        else:
            logger.error(f"❌ Email submission failed: {result.get('error')}")

        return {
            'success': result['success'],
            'error': result.get('error'),
            'submission_id': submission_data['id'],
            'request_id': result.get('request_id'),
            'thread_id': result.get('thread_id')
        }

    except Exception as e:
        logger.error(f"❌ Email submission processing failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e),
            'submission_id': submission_data.get('id')
        }


def get_email_submissions_from_queue(db: SupabaseIntegration, test_user_id: str = None, max_requests: int = 10) -> List[Dict[str, Any]]:
    """Get email-based submissions from queue (portal_type='email')"""
    try:
        # Fetch pending email submissions
        query = db.supabase.table('submission_queue').select(
            '*, portals!inner(portal_type, contact_email, agency_name)'
        ).eq('status', 'pending').eq('portals.portal_type', 'email')

        if test_user_id:
            query = query.eq('user_id', test_user_id)

        result = query.order('priority').order('created_at').limit(max_requests).execute()

        if not result.data:
            logger.info("📧 No email-based submissions found in queue")
            return []

        logger.info(f"📧 Found {len(result.data)} email-based submissions in queue")
        logger.debug(f"Email submissions: {result.data}")
        return result.data

    except Exception as e:
        logger.error(f"❌ Failed to get email submissions: {str(e)}")
        return []


def get_submission_sessions_from_queue(db: SupabaseIntegration, test_user_id: str = None, max_requests: int = 10) -> Dict[str, Any]:
    """Get submission sessions grouped by user/portal combination"""
    try:
        # Fetch pending requests from queue
        query = db.supabase.table('submission_queue').select('*').eq('status', 'pending')

        if test_user_id:
            query = query.eq('user_id', test_user_id)

        result = query.order('priority').order('created_at').limit(max_requests).execute()

        if not result.data:
            return {}

        # Group requests by user_id + portal_id
        submission_sessions = {}

        for request in result.data:
            try:
                user_id = request['user_id']
                portal_id = request['portal_id']

                # Get portal info
                portal_result = db.supabase.table('portals').select('*').eq('id', portal_id).single().execute()
                if not portal_result.data:
                    logger.warning(f"Portal not found for request {request['id']}")
                    continue

                # Skip email-based submissions (they are processed separately)
                portal_type = portal_result.data.get('portal_type', 'portal')
                if portal_type == 'email':
                    logger.debug(f"Skipping email submission {request['id']} - processed separately")
                    continue

                # Get credentials
                cred_result = db.supabase.table('user_portal_credentials').select('''
                    *,
                    requester_name,
                    requester_email,
                    requester_phone,
                    requester_organization,
                    street_address,
                    city,
                    state,
                    zip_code,
                    preferred_department
                ''').eq('user_id', user_id).eq('portal_id', portal_id).eq('is_active', True).single().execute()

                if not cred_result.data:
                    logger.warning(f"No credentials found for request {request['id']}")
                    continue

                # Create session key
                session_key = f"{user_id}#{portal_id}"

                # Enrich request data
                enriched_request = {
                    **request,
                    'agency_name': portal_result.data['agency_name'],
                    'portal_url': portal_result.data['portal_url'],
                    'portal_type': portal_result.data['portal_type'],
                    'encrypted_username': cred_result.data['encrypted_username'],
                    'encrypted_password': cred_result.data['encrypted_password'],
                    'contact_info': {
                        'requester_name': cred_result.data.get('requester_name'),
                        'requester_email': cred_result.data.get('requester_email'),
                        'requester_phone': cred_result.data.get('requester_phone'),
                        'requester_organization': cred_result.data.get('requester_organization'),
                        'street_address': cred_result.data.get('street_address'),
                        'city': cred_result.data.get('city'),
                        'state': cred_result.data.get('state'),
                        'zip_code': cred_result.data.get('zip_code'),
                        'preferred_department': cred_result.data.get('preferred_department')
                    }
                }

                # Add to session or create new one
                if session_key not in submission_sessions:
                    submission_sessions[session_key] = {
                        'user_id': user_id,
                        'portal_id': portal_id,
                        'agency_name': portal_result.data['agency_name'],
                        'portal_url': portal_result.data['portal_url'],
                        'portal_type': portal_result.data['portal_type'],
                        'credentials': {
                            'username': cred_result.data['encrypted_username'],
                            'password': cred_result.data['encrypted_password'],
                        },
                        'requests': [],
                        'request_count': 0
                    }

                submission_sessions[session_key]['requests'].append(enriched_request)
                submission_sessions[session_key]['request_count'] += 1

            except Exception as e:
                logger.error(f"Failed to process request {request['id']}: {str(e)}")
                continue

        total_sessions = len(submission_sessions)
        total_requests = sum(session['request_count'] for session in submission_sessions.values())
        logger.info(f"📊 Created {total_sessions} submission sessions for {total_requests} requests")

        return submission_sessions

    except Exception as e:
        logger.error(f"❌ Failed to get submission sessions: {str(e)}")
        return {}


def process_submission_session(session: dict, headless: bool) -> dict:
    """Process all requests for a single portal session with isolated browser"""
    try:
        portal_url = session['portal_url']
        username = session['credentials']['username']
        password = session['credentials']['password']
        requests_to_submit = session['requests']
        agency_name = session.get('agency_name', 'Unknown Agency')

        logger.info(f"📦 Starting session for {agency_name}")
        logger.info(f"   Portal: {portal_url}")
        logger.info(f"   Requests to submit: {len(requests_to_submit)}")

        login_credentials = LoginCredentials(username=username, password=password)

        successful = 0
        failed = 0

        with PortalAgent(gpt_4o, headless=headless) as agent:
            # Access portal and login
            logger.info(f"🌐 Accessing portal: {portal_url}")
            access_result = agent.access_portal_session(portal_url=portal_url, credentials=login_credentials)

            if not access_result.get('navigation', {}).get('success'):
                logger.error(f"❌ Failed to access portal: {portal_url}")
                return {
                    'success': False,
                    'error': 'Failed to access portal',
                    'successful': 0,
                    'failed': len(requests_to_submit)
                }

            logger.info(f"✅ Successfully accessed portal")
            if access_result.get('login', {}).get('success'):
                logger.info(f"✅ Login successful")
            elif access_result.get('login', {}).get('skipped'):
                logger.info(f"ℹ️  Login skipped (already authenticated)")
            else:
                logger.warning(f"⚠️ Login failed or not attempted")

            # Initialize database for status updates
            db = SupabaseIntegration()

            # Process each request in this session
            for i, request_data in enumerate(requests_to_submit, 1):
                try:
                    logger.info(f"🔄 Processing request {i}/{len(requests_to_submit)}: {request_data['id']}")

                    # Update status to processing
                    db.supabase.table('submission_queue').update({
                        'status': 'processing',
                        'started_processing_at': time.strftime('%Y-%m-%dT%H:%M:%SZ')
                    }).eq('id', request_data['id']).execute()

                    # Process the request
                    result = agent._process_single_request(db, request_data)

                    if result['success']:
                        successful += 1
                        logger.info(f"✅ Request {request_data['id']} completed successfully")
                        logger.info(f"   Steps: {', '.join(result.get('steps_completed', []))}")
                        if result.get('submitted_request_number'):
                            logger.info(f"   Request Number: {result['submitted_request_number']}")
                    else:
                        failed += 1
                        logger.error(f"❌ Request {request_data['id']} failed")
                        logger.error(f"   Errors: {'; '.join(result.get('errors', ['Unknown error']))}")
                        logger.error(f"   Steps completed before failure: {', '.join(result.get('steps_completed', []))}")

                    # Add delay between requests
                    if i < len(requests_to_submit):
                        time.sleep(5)

                except Exception as e:
                    logger.error(f"❌ Error processing request {request_data['id']}: {str(e)}")
                    failed += 1

                    # Update status to failed
                    db.supabase.table('submission_queue').update({
                        'status': 'failed',
                        'error_details': str(e),
                        'completed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ')
                    }).eq('id', request_data['id']).execute()

        logger.info(f"📦 Session complete for {agency_name}")
        logger.info(f"   ✅ Successful: {successful}")
        logger.info(f"   ❌ Failed: {failed}")

        # Force garbage collection to free memory
        gc.collect()

        return {
            'success': True,
            'portal': session['agency_name'],
            'successful': successful,
            'failed': failed
        }

    except Exception as e:
        logger.error(f"❌ Session failed for {session.get('agency_name', 'Unknown')}: {str(e)}")

        # Force garbage collection to free memory
        gc.collect()

        return {
            'success': False,
            'error': str(e),
            'portal': session.get('agency_name', 'Unknown'),
            'successful': 0,
            'failed': session.get('request_count', 0)
        }


def run_parallel_queue_submit(args) -> int:
    """Run queue submission with parallel workers (isolated browser per worker)"""
    try:
        print(f"\n🚀 RUNNING PARALLEL QUEUE SUBMISSION")
        print(f"-" * 50)
        print(f"👷 Workers: {args.workers}")

        db = SupabaseIntegration()

        # Get both email and portal submissions
        email_submissions = get_email_submissions_from_queue(db, args.user_id, args.max_requests)
        submission_sessions = get_submission_sessions_from_queue(db, args.user_id, args.max_requests)

        total_email = len(email_submissions)
        total_sessions = len(submission_sessions)
        total_portal_requests = sum(session['request_count'] for session in submission_sessions.values())

        if total_email == 0 and total_sessions == 0:
            print(f"\n✅ No pending requests in submission queue")
            return 0

        if total_email > 0:
            print(f"📧 Found {total_email} email-based submissions")
        if total_sessions > 0:
            print(f"🎯 Found {total_sessions} portal sessions with {total_portal_requests} requests to submit")

        # Results aggregation
        results: List[Dict[str, Any]] = []
        email_successful = 0
        email_failed = 0

        # Process email submissions first (they're fast, no browser needed)
        if email_submissions:
            print(f"\n📧 Processing {len(email_submissions)} email submissions...")

            def process_email(submission):
                """Worker function to process a single email submission"""
                # Set workflow context for logging
                try:
                    from daemon_logger import set_workflow_context
                    set_workflow_context('QueueSubmit')
                except ImportError:
                    pass

                return process_email_submission(submission)

            with ThreadPoolExecutor(max_workers=min(args.workers, len(email_submissions))) as executor:
                email_futures = {executor.submit(process_email, sub): sub for sub in email_submissions}

                for future in as_completed(email_futures):
                    result = future.result()
                    if result['success']:
                        email_successful += 1
                        print(f"   ✅ Email sent: {result.get('thread_id', 'unknown')}")
                    else:
                        email_failed += 1
                        print(f"   ❌ Email failed: {result.get('error', 'Unknown error')}")

            print(f"📧 Email submissions complete: {email_successful} successful, {email_failed} failed")

        # Prepare portal session list for parallel processing
        sessions_list = list(submission_sessions.items())

        def process_session(session_data):
            """Worker function to process a single session with isolated browser"""
            # Set workflow context so logs from this worker go to QueueSubmit.log
            try:
                from daemon_logger import set_workflow_context
                set_workflow_context('QueueSubmit')
            except ImportError:
                pass  # Running standalone, not through daemon

            session_key, session = session_data
            try:
                result = process_submission_session(session, args.headless)
                result['session_key'] = session_key
                result['agency_name'] = session['agency_name']
                return result
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'session_key': session_key,
                    'agency_name': session.get('agency_name', 'Unknown'),
                    'successful': 0,
                    'failed': session.get('request_count', 0)
                }

        # Process portal sessions if any exist
        if sessions_list:
            # Execute sessions in parallel with ThreadPoolExecutor
            max_workers = min(args.workers, total_sessions)
            print(f"\n⚡ Starting {max_workers} parallel workers for portal submissions...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all sessions to the executor
                future_to_session = {
                    executor.submit(process_session, session_data): session_data
                    for session_data in sessions_list
                }

                # Process results as they complete
                completed = 0
                for future in as_completed(future_to_session):
                    completed += 1
                    result = future.result()
                    results.append(result)

                    # Print progress
                    if result['success']:
                        print(f"   ✅ [{completed}/{total_sessions}] {result['agency_name']}: "
                              f"{result.get('successful', 0)} successful, "
                              f"{result.get('failed', 0)} failed")
                    else:
                        print(f"   ❌ [{completed}/{total_sessions}] {result['agency_name']}: "
                              f"{result.get('error', 'Unknown error')}")

        # Aggregate results
        portal_successful = sum(r.get('successful', 0) for r in results)
        portal_failed = sum(r.get('failed', 0) for r in results)
        successful_sessions = sum(1 for r in results if r.get('success'))

        print(f"\n📊 PARALLEL QUEUE SUBMISSION COMPLETE:")
        if total_email > 0:
            print(f"  • Email submissions: {email_successful} successful, {email_failed} failed")
        if total_sessions > 0:
            print(f"  • Portal sessions: {successful_sessions}/{total_sessions} processed")
            print(f"  • Portal requests: {portal_successful} successful, {portal_failed} failed")
        print(f"  • TOTAL: {email_successful + portal_successful} successful, {email_failed + portal_failed} failed")

        return 0

    except Exception as e:
        logger.error(f"❌ Parallel queue submission failed: {str(e)}")
        return 1


def run_sequential_queue_submit(args) -> int:
    """Run queue submission sequentially (original behavior)"""
    try:
        # First, process any email submissions (fast, no browser needed)
        db = SupabaseIntegration()
        email_submissions = get_email_submissions_from_queue(db, args.user_id, args.max_requests)

        email_successful = 0
        email_failed = 0

        if email_submissions:
            print(f"\n📧 Processing {len(email_submissions)} email submissions...")
            for submission in email_submissions:
                result = process_email_submission(submission)
                if result['success']:
                    email_successful += 1
                    print(f"   ✅ Email sent: {result.get('thread_id', 'unknown')}")
                else:
                    email_failed += 1
                    print(f"   ❌ Email failed: {result.get('error', 'Unknown error')}")

            print(f"📧 Email submissions complete: {email_successful} successful, {email_failed} failed\n")

        # Now process portal submissions with PortalAgent
        with PortalAgent(gpt_4o, headless=args.headless) as agent:
            print(f"\n🚀 Portal Agent initialized successfully")

            if args.continuous:
                print(f"🔄 Starting continuous queue processing...")
                print(f"💡 Press Ctrl+C to stop gracefully")
                print(f"\n{'='*60}")

                result = agent.run_continuous_queue_processing(
                    test_user_id=args.user_id,
                    check_interval_minutes=args.interval,
                    max_requests_per_batch=args.max_requests
                )
            else:
                print(f"📊 Processing single batch...")
                print(f"\n{'='*60}")

                result = agent.process_submission_queue(
                    test_user_id=args.user_id,
                    max_requests=args.max_requests
                )

            portal_successful = 0
            portal_failed = 0

            if result['success']:
                portal_successful = result.get('successful_submissions', 0)
                portal_failed = result.get('failed_submissions', 0)

            print(f"\n✅ Queue processing completed!")
            print(f"📊 Statistics:")
            if email_successful > 0 or email_failed > 0:
                print(f"  • Email submissions: {email_successful} successful, {email_failed} failed")
            if result.get('processed', 0) > 0:
                print(f"  • Portal submissions: {portal_successful} successful, {portal_failed} failed")
            print(f"  • TOTAL: {email_successful + portal_successful} successful, {email_failed + portal_failed} failed")

            if not result['success']:
                print(f"\n⚠️  Portal processing encountered errors: {result.get('error', 'Unknown error')}")
                if email_successful > 0:
                    print(f"   Note: Email submissions completed successfully")
                return 1

            return 0

    except KeyboardInterrupt:
        print(f"\n🛑 Queue processing stopped by user")
        print(f"✅ Graceful shutdown completed")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        print(f"\n💥 Fatal error occurred: {str(e)}")
        return 1


def cmd_queue_submit(args) -> int:
    """Process request submission queue"""
    print("\n" + "="*80)
    print("🔄 QUEUE PROCESSOR - SUPABASE SUBMISSION HANDLER")
    print("="*80)
    print("Features:")
    print("  ✅ Processes requests from Supabase queue")
    print("  ✅ Dynamic portal access (no pre-login)")
    print("  ✅ Fetches credentials per request")
    if hasattr(args, 'mode') and args.mode == 'parallel':
        print(f"  ✅ Parallel processing with {args.workers} workers")
    elif args.continuous:
        print("  ✅ Continuous monitoring")
    else:
        print("  ℹ️  Single batch mode")
    print("  ✅ Perfect for server deployment")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    print(f"  🔄 Mode: {getattr(args, 'mode', 'single')}")
    print(f"  👤 User ID: {args.user_id or 'Not specified'}")
    print(f"  ⏰ Check Interval: {args.interval} minutes")
    print(f"  📊 Max Requests per Batch: {args.max_requests}")
    print(f"  🖥️  Headless Mode: {args.headless}")
    if hasattr(args, 'workers'):
        print(f"  👷 Workers: {args.workers}")

    try:
        mode = getattr(args, 'mode', 'single')
        if mode == 'parallel':
            return run_parallel_queue_submit(args)
        else:
            return run_sequential_queue_submit(args)

    except KeyboardInterrupt:
        print(f"\n🛑 Queue processing stopped by user")
        print(f"✅ Graceful shutdown completed")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        print(f"\n💥 Fatal error occurred: {str(e)}")
        return 1


# ============================================================================
# COMMAND: queue analyze
# ============================================================================

def get_bulk_analysis_jobs_from_queue(db: SupabaseIntegration, test_user_id: str = None, max_jobs: int = 10) -> List[Dict[str, Any]]:
    """Get bulk analysis jobs from queue with enriched portal and credential information"""
    try:
        logger.info(f"🔍 Fetching bulk analysis jobs for user: {test_user_id}")

        # Get basic job data first - explicitly select all columns including submission_queue_id
        query = db.supabase.table('bulk_analysis_queue').select(
            'id, user_id, portal_id, job_name, analysis_type, priority, created_at, '
            'status, submission_queue_id, job_description, progress_data, resume_info, '
            'final_results, error_details, started_processing_at, completed_at'
        ).eq('status', 'pending')

        if test_user_id:
            query = query.eq('user_id', test_user_id)

        result = query.order('priority').order('created_at').limit(max_jobs).execute()

        logger.info(f"📊 Found {len(result.data) if result.data else 0} pending jobs")

        if not result.data:
            return []

        # Enrich each job with portal, user, and credential data
        enriched_jobs = []
        for job in result.data:
            try:
                # Fetch portal data
                portal_result = db.supabase.table('portals').select('agency_name, portal_url, portal_type').eq('id', job['portal_id']).single().execute()

                if not portal_result.data:
                    logger.warning(f"⚠️ Portal not found for job {job['id']}")
                    continue

                # Fetch user data
                user_result = db.supabase.table('users').select('email, full_name').eq('id', job['user_id']).single().execute()

                if not user_result.data:
                    logger.warning(f"⚠️ User not found for job {job['id']}")
                    continue

                # Fetch credentials
                cred_result = db.supabase.table('user_portal_credentials').select('''
                    encrypted_username,
                    encrypted_password
                ''').eq('user_id', job['user_id']).eq('portal_id', job['portal_id']).eq('is_active', True).single().execute()

                if not cred_result.data:
                    logger.warning(f"⚠️ No credentials found for job {job['id']}")
                    continue

                # Create enriched job data
                enriched_job = {
                    'id': job['id'],
                    'user_id': job['user_id'],
                    'portal_id': job['portal_id'],
                    'job_name': job['job_name'],
                    'analysis_type': job['analysis_type'],
                    'priority': job['priority'],
                    'created_at': job['created_at'],
                    'submission_queue_id': job.get('submission_queue_id'), 
                    'agency_name': portal_result.data['agency_name'],
                    'portal_url': portal_result.data['portal_url'],
                    'portal_type': portal_result.data['portal_type'],
                    'user_email': user_result.data['email'],
                    'user_full_name': user_result.data['full_name'],
                    'encrypted_username': cred_result.data['encrypted_username'],
                    'encrypted_password': cred_result.data['encrypted_password']
                }

                enriched_jobs.append(enriched_job)
                logger.info(f"✅ Successfully enriched job for {enriched_job['agency_name']}")

            except Exception as e:
                logger.error(f"❌ Failed to enrich job {job['id']}: {str(e)}")
                continue

        logger.info(f"📊 Successfully processed {len(enriched_jobs)} bulk analysis jobs")
        return enriched_jobs

    except Exception as e:
        logger.error(f"❌ Failed to fetch pending bulk analysis jobs: {str(e)}")
        return []


def process_single_bulk_analysis_job(job_data: dict, headless: bool) -> dict:
    """Process a single bulk analysis job with isolated browser - uses existing portal_agent method"""
    try:
        job_id = job_data['id']
        agency_name = job_data['agency_name']

        logger.info(f"📦 Starting bulk analysis for {agency_name}")
        logger.info(f"   Job ID: {job_id}")

        db = SupabaseIntegration()

        with PortalAgent(gpt_4o, headless=headless) as agent:
            # Use the existing working method from portal_agent.py
            result = agent._process_single_bulk_analysis_job(db, job_data)

            return {
                'success': result.get('success', False),
                'error': result.get('errors', ['Unknown error'])[0] if result.get('errors') else None,
                'job_id': job_id,
                'agency_name': agency_name,
                'total_requests': result.get('total_requests', 0),
                'successful_analyses': result.get('successful_analyses', 0),
                'skipped_existing': result.get('skipped_existing', 0)
            }

    except Exception as e:
        logger.error(f"❌ Job processing failed for {job_data.get('agency_name', 'Unknown')}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'job_id': job_data.get('id'),
            'agency_name': job_data.get('agency_name', 'Unknown'),
            'total_requests': 0,
            'successful_analyses': 0
        }


def run_parallel_queue_analyze(args) -> int:
    """Run bulk analysis queue with parallel workers (isolated browser per worker)"""
    try:
        print(f"\n🚀 RUNNING PARALLEL BULK ANALYSIS")
        print(f"-" * 50)
        print(f"👷 Workers: {args.workers}")

        db = SupabaseIntegration()
        pending_jobs = get_bulk_analysis_jobs_from_queue(db, args.user_id, args.max_jobs)

        if not pending_jobs:
            print(f"\n✅ No pending bulk analysis jobs in queue")
            return 0

        total_jobs = len(pending_jobs)
        print(f"🎯 Found {total_jobs} bulk analysis jobs to process")

        if total_jobs == 0:
            print(f"\n✅ No jobs to process")
            return 0

        # Results aggregation
        results: List[Dict[str, Any]] = []

        def process_job(job_data):
            """Worker function to process a single job with isolated browser"""
            # Set workflow context so logs from this worker go to QueueAnalyze.log
            try:
                from daemon_logger import set_workflow_context
                set_workflow_context('QueueAnalyze')
            except ImportError:
                pass  # Running standalone, not through daemon

            try:
                result = process_single_bulk_analysis_job(job_data, args.headless)
                return result
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'job_id': job_data.get('id'),
                    'agency_name': job_data.get('agency_name', 'Unknown'),
                    'total_requests': 0,
                    'successful_analyses': 0
                }

        # Execute jobs in parallel with ThreadPoolExecutor
        max_workers = min(args.workers, total_jobs)
        print(f"\n⚡ Starting {max_workers} parallel workers...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs to the executor
            future_to_job = {
                executor.submit(process_job, job_data): job_data
                for job_data in pending_jobs
            }

            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_job):
                completed += 1
                result = future.result()
                results.append(result)

                # Print progress
                if result['success']:
                    print(f"   ✅ [{completed}/{total_jobs}] {result['agency_name']}: "
                          f"{result.get('successful_analyses', 0)} new requests, "
                          f"{result.get('skipped_existing', 0)} skipped")
                else:
                    print(f"   ❌ [{completed}/{total_jobs}] {result['agency_name']}: "
                          f"{result.get('error', 'Unknown error')}")

        # Aggregate results
        total_successful = sum(r.get('successful_analyses', 0) for r in results)
        total_analyzed = sum(r.get('total_requests', 0) for r in results)
        total_skipped = sum(r.get('skipped_existing', 0) for r in results)
        successful_jobs = sum(1 for r in results if r.get('success'))

        print(f"\n📊 PARALLEL BULK ANALYSIS COMPLETE:")
        print(f"  • Jobs processed: {successful_jobs}/{total_jobs}")
        print(f"  • Total requests analyzed: {total_analyzed}")
        print(f"  • New requests added: {total_successful}")
        print(f"  • Existing requests skipped: {total_skipped}")

        return 0

    except Exception as e:
        logger.error(f"❌ Parallel bulk analysis failed: {str(e)}")
        return 1


def run_sequential_queue_analyze(args) -> int:
    """Run bulk analysis queue sequentially (original behavior)"""
    try:
        with PortalAgent(gpt_4o, headless=args.headless) as agent:
            print(f"\n🚀 Portal Agent initialized successfully")

            if args.continuous:
                print(f"🔬 Starting continuous bulk analysis processing...")
                print(f"💡 Press Ctrl+C to stop gracefully")
                print(f"\n{'='*60}")

                result = agent.run_continuous_bulk_analysis_processing(
                    test_user_id=args.user_id,
                    check_interval_minutes=args.interval,
                    max_jobs_per_batch=args.max_jobs
                )
            else:
                print(f"📊 Processing single batch...")
                print(f"\n{'='*60}")

                result = agent.process_bulk_analysis_queue(
                    test_user_id=args.user_id,
                    max_jobs=args.max_jobs
                )

            if result['success']:
                print(f"\n✅ Bulk analysis processing completed successfully!")
                print(f"📊 Statistics:")
                print(f"  • Total Jobs Processed: {result.get('processed', 0)}")
                print(f"  • Successful: {result.get('successful_jobs', 0)}")
                print(f"  • Failed: {result.get('failed_jobs', 0)}")
                print(f"  • Total Requests Analyzed: {result.get('total_requests_analyzed', 0)}")
                return 0
            else:
                print(f"\n❌ Bulk analysis processing failed: {result.get('error', 'Unknown error')}")
                return 1

    except KeyboardInterrupt:
        print(f"\n🛑 Bulk analysis processing stopped by user")
        print(f"✅ Graceful shutdown completed")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        print(f"\n💥 Fatal error occurred: {str(e)}")
        return 1


def cmd_queue_analyze(args) -> int:
    """Process bulk analysis queue"""
    print("\n" + "="*80)
    print("🔬 BULK ANALYSIS PROCESSOR - DATABASE POPULATION HANDLER")
    print("="*80)
    print("Features:")
    print("  ✅ Processes bulk analysis jobs from Supabase queue")
    print("  ✅ Dynamic portal access (no pre-login)")
    print("  ✅ Fetches credentials per job")
    print("  ✅ Comprehensive request analysis")
    print("  ✅ Real-time progress tracking")
    print("  ✅ Priority-based processing (High → Normal → Low)")
    print("  ✅ Resume functionality for interrupted jobs")
    if hasattr(args, 'mode') and args.mode == 'parallel':
        print(f"  ✅ Parallel processing with {args.workers} workers")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    print(f"  🔄 Mode: {getattr(args, 'mode', 'single')}")
    print(f"  👤 User ID: {args.user_id or 'Not specified'}")
    print(f"  ⏰ Check Interval: {args.interval} minutes")
    print(f"  📊 Max Jobs per Batch: {args.max_jobs}")
    print(f"  🖥️  Headless Mode: {args.headless}")
    if hasattr(args, 'workers'):
        print(f"  👷 Workers: {args.workers}")

    try:
        mode = getattr(args, 'mode', 'single')
        if mode == 'parallel':
            return run_parallel_queue_analyze(args)
        else:
            return run_sequential_queue_analyze(args)

    except KeyboardInterrupt:
        print(f"\n🛑 Bulk analysis processing stopped by user")
        print(f"✅ Graceful shutdown completed")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        print(f"\n💥 Fatal error occurred: {str(e)}")
        return 1


# ============================================================================
# COMMAND: monitor
# ============================================================================

def get_monitoring_sessions_from_requests(db: SupabaseIntegration) -> Dict[str, Any]:
    """Get monitoring sessions based on stale requests"""
    try:
        users_with_requests = db.supabase.table('requests').select(
            'user_id, portal_name'
        ).execute()

        if not users_with_requests.data:
            logger.info("📊 No users with requests found")
            return {}

        unique_users = set(req['user_id'] for req in users_with_requests.data)
        logger.info(f"📊 Found {len(unique_users)} users with requests")

        monitoring_sessions = {}

        for user_id in unique_users:
            try:
                monitoring_queue = db.get_monitoring_queue(user_id)
                requests_to_monitor = monitoring_queue.get('stale_requests', [])

                if not requests_to_monitor:
                    logger.info(f"👤 User {user_id}: No stale requests need monitoring")
                    continue

                logger.info(f"👤 User {user_id}: {len(requests_to_monitor)} stale requests need monitoring")

                requests_by_portal = {}
                for req in requests_to_monitor:
                    portal_name = req['portal_name']
                    if portal_name not in requests_by_portal:
                        requests_by_portal[portal_name] = []
                    requests_by_portal[portal_name].append(req)

                for portal_name, portal_requests in requests_by_portal.items():
                    try:
                        credentials = get_credentials_for_user_portal(db, user_id, portal_name)

                        if credentials:
                            session_key = f"{user_id}#{portal_name}"
                            monitoring_sessions[session_key] = {
                                'user_id': user_id,
                                'portal_name': portal_name,
                                'credentials': credentials,
                                'requests_to_monitor': portal_requests,
                                'request_count': len(portal_requests)
                            }
                            logger.info(f"🌐 {credentials['agency_name']}: {len(portal_requests)} stale requests to monitor")
                        else:
                            logger.warning(f"⚠️ No credentials found for user {user_id} on portal {portal_name}")

                    except Exception as e:
                        logger.error(f"❌ Error processing portal {portal_name} for user {user_id}: {str(e)}")
                        continue

            except Exception as e:
                logger.error(f"❌ Error getting monitoring queue for user {user_id}: {str(e)}")
                continue

        total_sessions = len(monitoring_sessions)
        total_requests = sum(session['request_count'] for session in monitoring_sessions.values())
        logger.info(f"📊 Created {total_sessions} monitoring sessions for {total_requests} stale requests")

        return monitoring_sessions

    except Exception as e:
        logger.error(f"❌ Failed to get monitoring sessions: {str(e)}")
        return {}


def monitor_user_portal(credentials: dict, headless: bool = True) -> dict:
    """Monitor a single user/portal combination"""
    try:
        portal_url = credentials['portal_url']
        username = credentials['username']
        password = credentials['password']
        user_id = credentials['user_id']

        if not username or not password or not portal_url:
            return {'success': False, 'error': f"Missing required fields", 'portal': credentials.get('agency_name', 'Unknown')}

        user_info = {
            'email': credentials.get('requester_email', ''),
            'full_name': credentials.get('requester_name', ''),
            'phone': credentials.get('requester_phone', ''),
            'organization': credentials.get('requester_organization', ''),
        }

        logger.info(f"🔐 Connecting to {credentials['agency_name']} at {portal_url}")

        login_credentials = LoginCredentials(username=username, password=password)

        with PortalAgent(gpt_4o, headless=headless) as agent:
            access_result = agent.access_portal_session(portal_url=portal_url, credentials=login_credentials)

            if not access_result.get('navigation', {}).get('success'):
                return {'success': False, 'error': f"Failed to access portal", 'portal': credentials['agency_name']}

            login_successful = False
            if 'login' in access_result:
                login_successful = access_result['login'].get('skipped') or access_result['login'].get('success', False)

            if not login_successful or not agent.is_logged_in:
                return {'success': False, 'error': 'Portal login failed', 'portal': credentials['agency_name']}

            if hasattr(agent, 'request_analyzer') and hasattr(agent.request_analyzer, 'set_user_info'):
                agent.request_analyzer.set_user_info(
                    email=user_info['email'],
                    full_name=user_info['full_name'],
                    phone=user_info['phone'],
                    organization=user_info['organization'],
                    portal_name=portal_url
                )

            monitoring_result = agent.run_manual_monitoring_cycle(current_portal_url=portal_url)

            if monitoring_result['success']:
                return {
                    'success': True,
                    'portal': credentials['agency_name'],
                    'user_id': user_id,
                    'requests_checked': monitoring_result.get('requests_checked', 0),
                    'failed_checks': monitoring_result.get('failed_checks', 0),
                    'changes_detected': monitoring_result.get('changes_detected', 0),
                    'attention_flags_set': monitoring_result.get('attention_flags_set', 0),
                    'summary': monitoring_result.get('summary', '')
                }
            else:
                return {'success': False, 'error': monitoring_result.get('error', 'Monitoring cycle failed'), 'portal': credentials['agency_name'], 'user_id': user_id}

    except Exception as e:
        logger.error(f"❌ Error monitoring {credentials.get('agency_name', 'unknown')}: {str(e)}")
        return {'success': False, 'error': str(e), 'portal': credentials.get('agency_name', 'unknown')}


def run_single_monitoring_cycle(args) -> int:
    """Run a single monitoring cycle"""
    try:
        print(f"\n🔍 RUNNING STALE-REQUEST MONITORING CYCLE")
        print(f"-" * 50)

        db = SupabaseIntegration()
        monitoring_sessions = get_monitoring_sessions_from_requests(db)

        if not monitoring_sessions:
            print(f"\n✅ No stale requests need monitoring at this time")
            return 0

        if args.target_users != 'all':
            target_user_ids = [uid.strip() for uid in args.target_users.split(',')]
            monitoring_sessions = {
                key: session for key, session in monitoring_sessions.items()
                if session['user_id'] in target_user_ids
            }

        total_sessions = len(monitoring_sessions)
        total_requests_to_monitor = sum(session['request_count'] for session in monitoring_sessions.values())
        print(f"🎯 Found {total_sessions} portal sessions with {total_requests_to_monitor} stale requests to monitor")

        total_requests_checked = 0
        total_failed_checks = 0
        total_changes_detected = 0
        total_attention_flags = 0
        successful_sessions = 0

        for i, (session_key, session) in enumerate(monitoring_sessions.items(), 1):
            try:
                credentials = session['credentials']
                print(f"\n🌐 Session {i}/{total_sessions}: {credentials['agency_name']}")
                print(f"   📊 Stale requests to monitor: {session['request_count']}")

                result = monitor_user_portal(credentials, args.headless)

                if result['success']:
                    total_requests_checked += result.get('requests_checked', 0)
                    total_failed_checks += result.get('failed_checks', 0)
                    total_changes_detected += result.get('changes_detected', 0)
                    total_attention_flags += result.get('attention_flags_set', 0)
                    successful_sessions += 1
                    print(f"   ✅ {result.get('requests_checked', 0)} checked, {result.get('changes_detected', 0)} changes, {result.get('attention_flags_set', 0)} flagged")
                else:
                    print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")

                if i < total_sessions:
                    time.sleep(5)

            except Exception as e:
                logger.error(f"Error processing session: {str(e)}")

        total_attempts = total_requests_checked + total_failed_checks
        print(f"\n📊 MONITORING CYCLE COMPLETE:")
        print(f"  • Requests monitored: {total_requests_checked}/{total_attempts} successful")
        print(f"  • Changes detected: {total_changes_detected}")
        print(f"  • Attention flags set: {total_attention_flags}")

        if total_attention_flags > 0:
            print(f"💡 Use 'entry.py messages draft' to process flagged requests")

        # Return dict with exit code and stats for daemon logging
        return {
            'exit_code': 0,
            'stats': {
                'successful_checks': total_requests_checked,
                'failed_checks': total_failed_checks,
                'changes_detected': total_changes_detected,
                'attention_flags_set': total_attention_flags,
                'sessions_processed': total_sessions,
                'successful_sessions': successful_sessions
            }
        }

    except Exception as e:
        logger.error(f"❌ Monitoring cycle failed: {str(e)}")
        return 1


def run_parallel_monitoring_cycle(args) -> int:
    """Run a monitoring cycle with parallel workers (isolated browser per worker)"""
    try:
        print(f"\n🚀 RUNNING PARALLEL MONITORING CYCLE")
        print(f"-" * 50)
        print(f"👷 Workers: {args.workers}")

        db = SupabaseIntegration()
        monitoring_sessions = get_monitoring_sessions_from_requests(db)

        if not monitoring_sessions:
            print(f"\n✅ No requests need monitoring at this time")
            return 0

        if args.target_users != 'all':
            target_user_ids = [uid.strip() for uid in args.target_users.split(',')]
            monitoring_sessions = {
                key: session for key, session in monitoring_sessions.items()
                if session['user_id'] in target_user_ids
            }

        total_sessions = len(monitoring_sessions)
        total_requests_to_monitor = sum(session['request_count'] for session in monitoring_sessions.values())
        print(f"🎯 Found {total_sessions} portal sessions with {total_requests_to_monitor} requests to monitor")

        if total_sessions == 0:
            print(f"\n✅ No sessions to process after filtering")
            return 0

        # Prepare session list for parallel processing
        sessions_list = list(monitoring_sessions.items())

        # Results aggregation
        results: List[Dict[str, Any]] = []

        def process_session(session_data):
            """Worker function to process a single session with isolated browser"""
            # Set workflow context so logs from this worker go to Monitor.log
            try:
                from daemon_logger import set_workflow_context
                set_workflow_context('Monitor')
            except ImportError:
                pass  # Running standalone, not through daemon

            session_key, session = session_data
            credentials = session['credentials']
            try:
                result = monitor_user_portal(credentials, args.headless)
                result['session_key'] = session_key
                result['agency_name'] = credentials['agency_name']
                return result
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'session_key': session_key,
                    'agency_name': credentials.get('agency_name', 'Unknown'),
                    'requests_checked': 0,
                    'changes_detected': 0,
                    'attention_flags_set': 0
                }

        # Execute sessions in parallel with ThreadPoolExecutor
        max_workers = min(args.workers, total_sessions)
        print(f"\n⚡ Starting {max_workers} parallel workers...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all sessions to the executor
            future_to_session = {
                executor.submit(process_session, session_data): session_data
                for session_data in sessions_list
            }

            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_session):
                completed += 1
                result = future.result()
                results.append(result)

                # Print progress
                if result['success']:
                    print(f"   ✅ [{completed}/{total_sessions}] {result['agency_name']}: "
                          f"{result.get('requests_checked', 0)} checked, "
                          f"{result.get('changes_detected', 0)} changes, "
                          f"{result.get('attention_flags_set', 0)} flagged")
                else:
                    print(f"   ❌ [{completed}/{total_sessions}] {result['agency_name']}: "
                          f"{result.get('error', 'Unknown error')}")

        # Aggregate results
        total_requests_checked = sum(r.get('requests_checked', 0) for r in results)
        total_failed_checks = sum(r.get('failed_checks', 0) for r in results)
        total_changes_detected = sum(r.get('changes_detected', 0) for r in results)
        total_attention_flags = sum(r.get('attention_flags_set', 0) for r in results)
        successful_sessions = sum(1 for r in results if r.get('success'))

        total_attempts = total_requests_checked + total_failed_checks

        print(f"\n📊 PARALLEL MONITORING CYCLE COMPLETE:")
        print(f"  • Sessions processed: {successful_sessions}/{total_sessions}")
        print(f"  • Requests monitored: {total_requests_checked}/{total_attempts} successful")
        print(f"  • Changes detected: {total_changes_detected}")
        print(f"  • Attention flags set: {total_attention_flags}")

        if total_attention_flags > 0:
            print(f"💡 Use 'entry.py messages draft' to process flagged requests")

        # Return dict with exit code and stats for daemon logging
        return {
            'exit_code': 0,
            'stats': {
                'successful_checks': total_requests_checked,
                'failed_checks': total_failed_checks,
                'changes_detected': total_changes_detected,
                'attention_flags_set': total_attention_flags,
                'sessions_processed': total_sessions,
                'successful_sessions': successful_sessions
            }
        }

    except Exception as e:
        logger.error(f"❌ Parallel monitoring cycle failed: {str(e)}")
        return 1


def run_continuous_monitoring(args) -> int:
    """Run continuous monitoring cycles"""
    try:
        print(f"\n⚡ STARTING CONTINUOUS REQUEST-DRIVEN MONITORING")
        print(f"⏰ Check interval: {args.interval} minutes")
        print(f"💡 Press Ctrl+C to stop gracefully\n")

        cycle_count = 0

        while True:
            cycle_count += 1
            print(f"\n🔄 MONITORING CYCLE #{cycle_count} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            result = run_single_monitoring_cycle(args)

            if result == 0:
                print(f"✅ Cycle #{cycle_count} completed")
            else:
                print(f"❌ Cycle #{cycle_count} failed")

            print(f"\n💤 Waiting {args.interval} minutes until next cycle...")
            time.sleep(args.interval * 60)

    except KeyboardInterrupt:
        print(f"\n🛑 Continuous monitoring stopped by user")
        return 0


def cmd_monitor(args) -> int:
    """Monitor requests for changes"""
    print("\n" + "="*80)
    print("🎯 REQUEST-DRIVEN MONITORING SYSTEM - INTELLIGENT CHANGE DETECTION")
    print("="*80)
    print("Features:")
    print("  ✅ Monitors all requests (not just open)")
    print("  ✅ Fetches user credentials dynamically from Supabase")
    print("  ✅ AI-powered change detection")
    print("  ✅ Automatic attention flagging")
    if hasattr(args, 'workers') and args.workers > 1:
        print(f"  ✅ Parallel processing with {args.workers} workers")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    print(f"  🔄 Mode: {args.mode}")
    print(f"  ⏰ Check Interval: {args.interval} minutes")
    print(f"  👥 Target Users: {args.target_users}")
    print(f"  🖥️  Headless Mode: {args.headless}")
    if hasattr(args, 'workers'):
        print(f"  👷 Workers: {args.workers}")

    try:
        if args.mode == 'single':
            return run_single_monitoring_cycle(args)
        elif args.mode == 'parallel':
            return run_parallel_monitoring_cycle(args)
        elif args.mode == 'continuous':
            return run_continuous_monitoring(args)
        else:
            print(f"❌ Invalid mode: {args.mode}")
            return 1

    except KeyboardInterrupt:
        print(f"\n🛑 Monitoring stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        return 1


# ============================================================================
# COMMAND: inbox classify
# ============================================================================

def cmd_inbox_classify(args) -> int:
    """Run InboxClassifier to link unmatched agency reply threads to FOIA requests."""
    import os
    from inbox_classifier import InboxClassifierAgent

    dry_run = getattr(args, 'dry_run', False)
    retroactive = getattr(args, 'retroactive', False)
    user_id = getattr(args, 'user_id', None)

    # Always write a log file alongside terminal output
    os.makedirs('logs', exist_ok=True)
    mode_tag = 'dry_run' if dry_run else 'live'
    retro_tag = '_retroactive' if retroactive else ''
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = f"logs/inbox_classifier_{mode_tag}{retro_tag}_{timestamp}.log"

    def emit(line='', file=None):
        """Write to both terminal and log file."""
        print(line, file=file)
        log_file.write(line + '\n')
        log_file.flush()

    with open(log_path, 'w') as log_file:
        emit("=" * 80)
        emit(f"INBOX CLASSIFIER LOG")
        emit(f"Timestamp : {timestamp}")
        emit(f"Mode      : {'DRY RUN (no DB writes)' if dry_run else 'LIVE'}")
        emit(f"Retroactive: {retroactive}")
        emit("=" * 80)

        db = SupabaseIntegration()

        if user_id:
            users = [{'id': user_id}]
        else:
            result = db.supabase.table('users').select('id, email').eq('is_active', True).execute()
            users = result.data or []

        if not users:
            emit("❌ No users found")
            emit(f"\nLog written to: {log_path}")
            return 1

        emit(f"Users: {len(users)}\n")

        totals = {'auto': 0, 'classifier': 0, 'needs_review': 0, 'no_match': 0, 'errors': 0}

        for user in users:
            uid = user['id']
            emit("=" * 80)
            emit(f"USER: {uid}")
            emit("=" * 80)

            classifier = InboxClassifierAgent(db=db, llm_client=gpt_4o)
            result = classifier.run_classification_cycle(
                uid, retroactive=retroactive, dry_run=dry_run
            )

            if not result.get('success'):
                emit(f"❌ Failed: {result.get('error', 'unknown error')}")
                totals['errors'] += 1
                continue

            _write_classifier_report(result.get('decisions', []), emit, dry_run)

            totals['auto'] += result['auto_resolved']
            totals['classifier'] += result['classifier_resolved']
            totals['needs_review'] += result['needs_review_flagged']
            totals['no_match'] += sum(
                1 for d in result.get('decisions', []) if d['action'] == 'no_match'
            )
            totals['errors'] += result['errors']

        emit("\n" + "=" * 80)
        emit(
            f"TOTAL — auto: {totals['auto']}  classifier: {totals['classifier']}  "
            f"needs_review: {totals['needs_review']}  no_match: {totals['no_match']}  "
            f"errors: {totals['errors']}"
        )
        if dry_run:
            emit("⚠️  DRY RUN — nothing was written to the database")
        emit("=" * 80)

    print(f"\nLog written to: {log_path}")
    return 0


def _write_classifier_report(decisions: list, emit, dry_run: bool) -> None:
    """Write a structured per-decision audit block to terminal + log file via emit()."""
    ACTION_LABELS = {
        'auto':         '[auto]        ',
        'classifier':   '[classifier]  ',
        'needs_review': '[needs_review]',
        'no_match':     '[no_match]    ',
        'skipped':      '[skipped]     ',
    }

    if not decisions:
        emit("  (no decisions — no email requests found or all already resolved)")
        return

    emit()
    for d in decisions:
        label   = ACTION_LABELS.get(d['action'], f"[{d['action']}]     ")
        req_num = d.get('request_number') or d.get('request_id', '?')
        agency  = d.get('agency') or '(unknown agency)'
        orig    = d.get('original_thread_id') or '(no thread)'

        emit(f"{label}  {agency} | #{req_num}")
        emit(f"              Thread          : {orig}")

        if d['action'] == 'classifier':
            emit(f"              New thread      : {d.get('new_thread_id')}")
            emit(f"  --- ORIGINAL REQUEST ---")
            for line in (d.get('request_text') or '(none)').splitlines():
                emit(f"  {line}")
            emit(f"  --- MATCHED EMAIL ---")
            emit(f"  From    : {d.get('email_from')}")
            emit(f"  Date    : {d.get('email_date')}")
            emit(f"  Subject : {d.get('email_subject')}")
            emit(f"  Body:")
            for line in (d.get('email_body') or '(empty)').splitlines():
                emit(f"    {line}")
            emit(f"  ---")
            if dry_run:
                emit(f"              ACTION (dry)    : would set gmail_thread_id → {d.get('new_thread_id')}, status=classifier")
            else:
                emit(f"              ACTION          : gmail_thread_id updated, status=classifier")

        elif d['action'] == 'auto':
            emit(f"  --- ORIGINAL REQUEST ---")
            for line in (d.get('request_text') or '(none)').splitlines():
                emit(f"  {line}")
            emit(f"  ---")
            emit(f"              Agency replied  : {d.get('auto_sender') or d.get('email_from')}")
            if dry_run:
                emit(f"              ACTION (dry)    : would set status=auto (gmail_thread_id unchanged)")
            else:
                emit(f"              ACTION          : status=auto (gmail_thread_id unchanged)")

        elif d['action'] in ('needs_review', 'no_match'):
            emit(f"  --- ORIGINAL REQUEST ---")
            for line in (d.get('request_text') or '(none)').splitlines():
                emit(f"  {line}")
            emit(f"  ---")
            emit(f"              Reason          : {d.get('reason', '')}")
            if d['action'] == 'needs_review':
                if dry_run:
                    emit(f"              ACTION (dry)    : would set status=needs_review")
                else:
                    emit(f"              ACTION          : status=needs_review")
            else:
                emit(f"              ACTION          : no action this cycle (will retry)")

        else:
            emit(f"              Reason          : {d.get('reason', '')}")

        emit()

    counts = {}
    for d in decisions:
        counts[d['action']] = counts.get(d['action'], 0) + 1
    summary = '  '.join(f"{k}: {v}" for k, v in sorted(counts.items()))
    emit(f"  SUMMARY  {summary}")
    emit()


# COMMAND: gmail monitor
# ============================================================================

def cmd_gmail_monitor(args) -> int:
    """Monitor Gmail for agency email responses"""
    print("\n" + "="*80)
    print("📧 GMAIL MONITORING SYSTEM - REAL-TIME EMAIL PROCESSING")
    print("="*80)
    print("Features:")
    print("  ✅ Real-time email monitoring (1-5 min intervals)")
    print("  ✅ AI-powered email analysis")
    print("  ✅ Parallel to portal monitoring")
    print("  ✅ No browser automation required")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    print(f"  🔄 Mode: {args.mode}")
    print(f"  👥 Target Users: {args.target_users}")
    print(f"  📊 Portal Type Filter: {getattr(args, 'portal_type', 'all')}")
    if hasattr(args, 'workers'):
        print(f"  👷 Workers: {args.workers}")

    try:
        if args.mode == 'single':
            return run_single_gmail_monitoring_cycle(args)
        elif args.mode == 'parallel':
            return run_parallel_gmail_monitoring_cycle(args)
        else:
            print(f"❌ Invalid mode: {args.mode}")
            return 1

    except KeyboardInterrupt:
        print(f"\n🛑 Gmail monitoring stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        return 1


def run_single_gmail_monitoring_cycle(args) -> int:
    """Run a single Gmail monitoring cycle"""
    from gmail_monitoring_agent import GmailMonitoringAgent

    db = SupabaseIntegration()

    # Get users to monitor
    if args.target_users == 'all':
        users_result = db.supabase.table('users').select('id, email').eq('is_active', True).execute()
        users = users_result.data or []
    else:
        users = [{'id': args.target_users}]

    if not users:
        print("❌ No users found to monitor")
        return 1

    print(f"\n📧 Starting Gmail monitoring for {len(users)} user(s)")

    total_emails = 0
    total_errors = 0

    for user in users:
        try:
            user_id = user['id']
            print(f"\n{'='*80}")
            print(f"👤 Processing user: {user_id}")
            print(f"{'='*80}")

            # Step 1: Run InboxClassifier to correct gmail_thread_id before monitoring
            portal_type_filter = getattr(args, 'portal_type', 'all')
            if portal_type_filter in ('all', 'email'):
                from inbox_classifier import InboxClassifierAgent
                classifier = InboxClassifierAgent(db=db, llm_client=gpt_4o)
                classifier.run_classification_cycle(user_id)

            # Step 2: Create Gmail monitoring agent
            agent = GmailMonitoringAgent(
                db=db,
                llm_client=gpt_4o,
                check_interval_minutes=5
            )

            # Run monitoring cycle with portal_type filter
            result = agent.run_monitoring_cycle(user_id, portal_type_filter=portal_type_filter)

            if result['success']:
                total_emails += result['emails_processed']
                total_errors += len(result.get('errors', []))

                print(f"\n✅ User {user_id}: {result['summary']}")

                if result.get('errors'):
                    print(f"⚠️  Errors encountered:")
                    for error in result['errors'][:3]:  # Show first 3 errors
                        print(f"   - {error}")
            else:
                print(f"❌ User {user_id}: {result.get('error', 'Unknown error')}")
                total_errors += 1

        except Exception as e:
            logger.error(f"❌ Error monitoring Gmail for user {user.get('id', 'unknown')}: {str(e)}")
            total_errors += 1

    print(f"\n{'='*80}")
    print(f"📊 GMAIL MONITORING SUMMARY")
    print(f"{'='*80}")
    print(f"  📧 Total emails processed: {total_emails}")
    print(f"  ❌ Total errors: {total_errors}")
    print(f"  ✅ Success rate: {((len(users) - total_errors) / len(users) * 100):.1f}%")

    return 0 if total_errors == 0 else 1


def run_parallel_gmail_monitoring_cycle(args) -> int:
    """Run Gmail monitoring in parallel for multiple users"""
    from gmail_monitoring_agent import GmailMonitoringAgent
    from concurrent.futures import ThreadPoolExecutor, as_completed

    db = SupabaseIntegration()

    # Get users to monitor
    if args.target_users == 'all':
        users_result = db.supabase.table('users').select('id, email').eq('is_active', True).execute()
        users = users_result.data or []
    else:
        users = [{'id': args.target_users}]

    if not users:
        print("❌ No users found to monitor")
        return 1

    print(f"\n📧 Starting parallel Gmail monitoring for {len(users)} user(s)")
    print(f"   Workers: {args.workers}")

    def process_user_gmail(user):
        """Process Gmail monitoring for one user"""
        try:
            user_id = user['id']
            agent = GmailMonitoringAgent(
                db=SupabaseIntegration(),  # Each worker gets own db connection
                llm_client=gpt_4o,
                check_interval_minutes=5
            )

            result = agent.run_monitoring_cycle(user_id)

            return {
                'user_id': user_id,
                'success': result['success'],
                'emails_processed': result.get('emails_processed', 0),
                'errors': result.get('errors', []),
                'summary': result.get('summary', '')
            }

        except Exception as e:
            logger.error(f"❌ Worker error for user {user.get('id')}: {str(e)}")
            return {
                'user_id': user.get('id', 'unknown'),
                'success': False,
                'emails_processed': 0,
                'errors': [str(e)],
                'summary': f'Worker error: {str(e)}'
            }

    # Process users in parallel
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_user_gmail, user): user for user in users}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            # Log progress
            status_icon = "✅" if result['success'] else "❌"
            print(f"{status_icon} {result['user_id']}: {result['summary']}")

    # Calculate summary statistics
    total_emails = sum(r['emails_processed'] for r in results)
    total_errors = sum(len(r['errors']) for r in results)
    successful_users = sum(1 for r in results if r['success'])

    print(f"\n{'='*80}")
    print(f"📊 PARALLEL GMAIL MONITORING SUMMARY")
    print(f"{'='*80}")
    print(f"  👥 Users processed: {len(results)}")
    print(f"  ✅ Successful: {successful_users}")
    print(f"  📧 Total emails processed: {total_emails}")
    print(f"  ❌ Total errors: {total_errors}")

    return 0 if total_errors == 0 else 1


# ============================================================================
# COMMAND: messages draft
# ============================================================================

def get_flagged_message_sessions(db: SupabaseIntegration) -> Dict[str, Any]:
    """Get message drafting sessions based on requests flagged for attention"""
    try:
        flagged_requests_result = db.supabase.table('requests').select(
            'user_id, portal_name'
        ).eq('agent_attention_needed', True).execute()

        if not flagged_requests_result.data:
            return {}

        unique_users = set(req['user_id'] for req in flagged_requests_result.data)
        message_sessions = {}

        for user_id in unique_users:
            try:
                flagged_requests = db.get_flagged_requests(user_id)
                if not flagged_requests:
                    continue

                requests_by_portal = {}
                for req in flagged_requests:
                    portal_name = req['portal_name']
                    if portal_name not in requests_by_portal:
                        requests_by_portal[portal_name] = []
                    requests_by_portal[portal_name].append(req)

                for portal_name, portal_requests in requests_by_portal.items():
                    credentials = get_credentials_for_user_portal(db, user_id, portal_name)
                    if credentials:
                        session_key = f"{user_id}#{portal_name}"
                        message_sessions[session_key] = {
                            'user_id': user_id,
                            'portal_name': portal_name,
                            'credentials': credentials,
                            'flagged_requests': portal_requests,
                            'request_count': len(portal_requests)
                        }

            except Exception as e:
                logger.error(f"❌ Error getting flagged requests for user {user_id}: {str(e)}")
                continue

        return message_sessions

    except Exception as e:
        logger.error(f"❌ Failed to get flagged message sessions: {str(e)}")
        return {}


def process_flagged_requests(user_id: str, flagged_requests: List[Dict[str, Any]], force_regenerate: bool = False) -> dict:
    """
    Process flagged requests for message drafting using database data.
    No browser or portal login required - uses data from monitoring agent.

    Args:
        user_id: User ID to process requests for
        flagged_requests: List of flagged request records
        force_regenerate: If True, regenerate all drafts even if analysis unchanged
    """
    try:
        from message_coordinator import MessageCoordinator
        from supabase_integration import SupabaseIntegration

        # Lightweight agent for drafting only (no browser/portal required)
        class DraftAgent:
            def __init__(self, user_id):
                self.is_logged_in = False  # Not needed for drafting
                self.db = SupabaseIntegration()
                self.user_id = user_id
                self.llm_client = gpt_4o
                # Minimal request_analyzer stub for MessageCoordinator init
                self.request_analyzer = type('obj', (object,), {
                    'db': self.db,
                    'user_id': user_id
                })()
                self.driver = None

        agent = DraftAgent(user_id)
        coordinator = MessageCoordinator(agent)

        drafts_generated = 0
        errors = 0

        mode_msg = " (FORCE REGENERATE MODE)" if force_regenerate else ""
        logger.info(f"📧 Processing {len(flagged_requests)} flagged requests{mode_msg}")

        for i, request_data in enumerate(flagged_requests, 1):
            try:
                result = coordinator.process_single_flagged_request(
                    request_data, i, len(flagged_requests), force_regenerate
                )

                if result['success']:
                    drafts_generated += 1
                    logger.info(f"✅ [{i}/{len(flagged_requests)}] Draft saved for {request_data['request_number']}")
                else:
                    errors += 1
                    logger.error(f"❌ [{i}/{len(flagged_requests)}] Failed: {request_data['request_number']} - {result.get('error', 'Unknown')}")

                # Small pause between drafts
                if i < len(flagged_requests):
                    time.sleep(0.5)

            except Exception as e:
                logger.error(f"❌ Error processing {request_data.get('request_number', 'unknown')}: {str(e)}")
                errors += 1

        return {
            'success': True,
            'drafts_generated': drafts_generated,
            'errors': errors,
            'total_processed': len(flagged_requests)
        }

    except Exception as e:
        logger.error(f"❌ Processing failed: {str(e)}")
        return {'success': False, 'error': str(e)}


def process_flagged_requests_for_portal(session: dict, headless: bool) -> dict:
    """Process flagged requests for a specific portal"""
    try:
        credentials = session['credentials']
        flagged_requests = session['flagged_requests']

        login_credentials = LoginCredentials(username=credentials['username'], password=credentials['password'])

        with PortalAgent(gpt_4o, headless=headless) as agent:
            access_result = agent.access_portal_session(portal_url=credentials['portal_url'], credentials=login_credentials)

            if not access_result.get('navigation', {}).get('success'):
                return {'success': False, 'error': f"Failed to access portal"}

            login_successful = False
            if 'login' in access_result:
                login_successful = access_result['login'].get('skipped') or access_result['login'].get('success', False)

            if not login_successful or not agent.is_logged_in:
                return {'success': False, 'error': 'Portal login failed'}

            message_coordinator = MessageCoordinator(agent)
            drafts_generated = 0
            messages_sent = 0
            skipped = 0

            for i, request_data in enumerate(flagged_requests, 1):
                try:
                    result = message_coordinator.process_single_flagged_request(request_data, i, len(flagged_requests))
                    if result['success']:
                        drafts_generated += 1
                        if result.get('message_sent'):
                            messages_sent += 1
                        elif result.get('action') == 'skipped':
                            skipped += 1
                    else:
                        skipped += 1

                    if i < len(flagged_requests):
                        time.sleep(2)

                except Exception as e:
                    logger.error(f"❌ Error processing request: {str(e)}")
                    skipped += 1
                    continue

            return {
                'success': True,
                'portal': credentials['agency_name'],
                'drafts_generated': drafts_generated,
                'messages_sent': messages_sent,
                'skipped': skipped
            }

    except Exception as e:
        return {'success': False, 'error': str(e)}


def run_parallel_message_drafting(args) -> int:
    """Run message drafting with parallel workers (database-only, no browser needed)"""
    try:
        print(f"\n🚀 RUNNING PARALLEL MESSAGE DRAFTING (Database-Only Mode)")
        print(f"-" * 50)
        print(f"👷 Workers: {args.workers}")
        print(f"⚡ Optimized: No browser/portal login required")

        db = SupabaseIntegration()

        # Get all flagged requests grouped by user
        flagged_requests_result = db.supabase.table('requests').select(
            '*'
        ).eq('agent_attention_needed', True).execute()

        if not flagged_requests_result.data:
            print(f"\n✅ No requests currently flagged for attention")
            return 0

        # Group requests by user_id
        requests_by_user = {}
        for req in flagged_requests_result.data:
            user_id = req['user_id']
            if user_id not in requests_by_user:
                requests_by_user[user_id] = []
            requests_by_user[user_id].append(req)

        # Filter by target users if specified
        if args.target_users != 'all':
            target_user_ids = [uid.strip() for uid in args.target_users.split(',')]
            requests_by_user = {
                uid: reqs for uid, reqs in requests_by_user.items()
                if uid in target_user_ids
            }

        total_users = len(requests_by_user)
        total_flagged_requests = sum(len(reqs) for reqs in requests_by_user.values())

        print(f"🎯 Found {total_flagged_requests} flagged requests across {total_users} users")

        if total_users == 0:
            print(f"\n✅ No requests to process after filtering")
            return 0

        # Results aggregation
        results: List[Dict[str, Any]] = []

        def process_user_requests(user_data):
            """Worker function to process all requests for a single user"""
            # Set workflow context so logs from this worker go to MessagesDraft.log
            try:
                from daemon_logger import set_workflow_context
                set_workflow_context('MessagesDraft')
            except ImportError:
                pass  # Running standalone, not through daemon

            user_id, user_requests = user_data
            try:
                result = process_flagged_requests(user_id, user_requests, args.force_regenerate)
                result['user_id'] = user_id
                result['request_count'] = len(user_requests)
                return result
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'user_id': user_id,
                    'request_count': len(user_requests),
                    'drafts_generated': 0,
                    'errors': 0
                }

        # Execute in parallel with ThreadPoolExecutor
        max_workers = min(args.workers, total_users)
        print(f"\n⚡ Starting {max_workers} parallel workers...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all user batches to the executor
            future_to_user = {
                executor.submit(process_user_requests, user_data): user_data
                for user_data in requests_by_user.items()
            }

            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_user):
                completed += 1
                result = future.result()
                results.append(result)

                # Print progress
                if result['success']:
                    print(f"   ✅ [{completed}/{total_users}] User {result['user_id'][:8]}...: "
                          f"{result.get('drafts_generated', 0)}/{result.get('request_count', 0)} drafts generated")
                else:
                    print(f"   ❌ [{completed}/{total_users}] User {result['user_id'][:8]}...: "
                          f"{result.get('error', 'Unknown error')}")

        # Aggregate results
        total_drafts_generated = sum(r.get('drafts_generated', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)
        successful_users = sum(1 for r in results if r.get('success'))

        print(f"\n📊 PARALLEL MESSAGE DRAFTING COMPLETE:")
        print(f"  • Users processed: {successful_users}/{total_users}")
        print(f"  • Drafts generated: {total_drafts_generated}/{total_flagged_requests}")
        print(f"  • Errors: {total_errors}")
        print(f"\n💡 Drafts are awaiting approval in the frontend")

        return 0

    except Exception as e:
        logger.error(f"❌ Parallel message drafting failed: {str(e)}")
        return 1


def run_sequential_message_drafting(args) -> int:
    """Run message drafting sequentially (database-only, no browser needed)"""
    try:
        print(f"\n🚀 RUNNING SEQUENTIAL MESSAGE DRAFTING (Database-Only Mode)")
        print(f"⚡ Optimized: No browser/portal login required")

        db = SupabaseIntegration()

        # Get all flagged requests grouped by user
        flagged_requests_result = db.supabase.table('requests').select(
            '*'
        ).eq('agent_attention_needed', True).execute()

        if not flagged_requests_result.data:
            print(f"\n✅ No requests currently flagged for attention")
            print(f"💡 Run 'entry.py monitor' to check for new changes")
            return 0

        # Group requests by user_id
        requests_by_user = {}
        for req in flagged_requests_result.data:
            user_id = req['user_id']
            if user_id not in requests_by_user:
                requests_by_user[user_id] = []
            requests_by_user[user_id].append(req)

        # Filter by target users if specified
        if args.target_users != 'all':
            target_user_ids = [uid.strip() for uid in args.target_users.split(',')]
            requests_by_user = {
                uid: reqs for uid, reqs in requests_by_user.items()
                if uid in target_user_ids
            }

        total_users = len(requests_by_user)
        total_flagged_requests = sum(len(reqs) for reqs in requests_by_user.values())

        print(f"\n🎯 Found {total_flagged_requests} flagged requests across {total_users} users")

        total_drafts_generated = 0
        total_errors = 0

        for i, (user_id, user_requests) in enumerate(requests_by_user.items(), 1):
            print(f"\n📧 User {i}/{total_users}: {user_id[:8]}... ({len(user_requests)} requests)")

            result = process_flagged_requests(user_id, user_requests, args.force_regenerate)

            if result['success']:
                total_drafts_generated += result.get('drafts_generated', 0)
                total_errors += result.get('errors', 0)
                print(f"   ✅ {result.get('drafts_generated', 0)}/{len(user_requests)} drafts generated")
            else:
                total_errors += len(user_requests)
                print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")

            if i < total_users:
                time.sleep(1)

        print(f"\n📊 MESSAGE DRAFTING COMPLETE:")
        print(f"  • Drafts generated: {total_drafts_generated}/{total_flagged_requests}")
        print(f"  • Errors: {total_errors}")
        print(f"\n💡 Drafts are awaiting approval in the frontend")
        return 0

    except Exception as e:
        logger.error(f"❌ Sequential message drafting failed: {str(e)}")
        return 1


def cmd_messages_draft(args) -> int:
    """Draft messages for flagged requests"""
    print("\n" + "="*80)
    print("📧 INTELLIGENT MESSAGE DRAFTING SYSTEM")
    print("="*80)
    print("Features:")
    print("  ✅ AI-powered contextual message generation")
    print("  ✅ Drafts saved for frontend approval")
    if hasattr(args, 'mode') and args.mode == 'parallel':
        print(f"  ✅ Parallel processing with {args.workers} workers")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    print(f"  🔄 Mode: {getattr(args, 'mode', 'single')}")
    print(f"  👥 Target Users: {args.target_users}")
    print(f"  🖥️  Headless Mode: {args.headless}")
    if hasattr(args, 'workers'):
        print(f"  👷 Workers: {args.workers}")
    if getattr(args, 'force_regenerate', False):
        print(f"  🔁 Force Regenerate: ENABLED (will regenerate all drafts)")

    try:
        mode = getattr(args, 'mode', 'single')
        if mode == 'parallel':
            return run_parallel_message_drafting(args)
        else:
            return run_sequential_message_drafting(args)

    except KeyboardInterrupt:
        print(f"\n🛑 Message drafting stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        return 1


# ============================================================================
# COMMAND: messages send
# ============================================================================

def send_via_gmail(draft: Dict[str, Any], request: Dict[str, Any]) -> bool:
    """
    Send message draft via Gmail as reply in thread.

    Args:
        draft: Message draft dict from database
        request: Request dict from database

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"📧 Sending email for request {request['request_number']}")

        # Validate required fields
        thread_id = request.get('gmail_thread_id')
        if not thread_id:
            logger.error("❌ No thread_id for email request")
            return False

        agency_email = request.get('portal_name')  # Email address stored here
        if not agency_email:
            logger.error("❌ No portal_name (email address) for request")
            return False

        # For email replies, use the original subject with "Re:" prefix
        # Combined with In-Reply-To header (via in_reply_to param), this ensures proper threading
        reply_subject = request.get('email_subject')
        if not reply_subject:
            logger.warning(f"⚠️  email_subject is missing for request {request.get('request_number')}! Using fallback subject.")
            reply_subject = 'Public Records Request'

        # Add "Re:" prefix if not already present
        if not reply_subject.startswith('Re: '):
            reply_subject = f"Re: {reply_subject}"

        logger.info(f"📧 Reply subject: '{reply_subject}'")

        # CRITICAL: Get the RFC 2822 Message-ID header for proper threading
        # This fixes the recipient-side threading issue (messages appearing in separate conversations)
        in_reply_to_message_id = None
        reply_to_email = agency_email  # Default to stored address; overridden below if we find actual sender

        try:
            # Use MCP to search for emails and find the latest agency message
            with MCPGmailClient() as mcp:
                # Search for emails with the original subject (without Re:)
                original_subject = request.get('email_subject')
                if not original_subject:
                    original_subject = 'Public Records Request'
                search_query = f'subject:"{original_subject}"'
                emails = mcp.search_emails(search_query, max_results=20)

                # Find the most recent email from the agency (not from us)
                db = SupabaseIntegration()
                user_email = db.get_user_email(request['user_id'])

                latest_agency_email = None
                for email_summary in emails:
                    full_email = mcp.read_email(email_summary['id'])
                    if full_email and full_email.get('thread_id') == thread_id:
                        # Check if this email is from the agency (not from us)
                        from_email = full_email.get('from', '')
                        if user_email and user_email.lower() not in from_email.lower():
                            # This is from the agency
                            if not latest_agency_email or full_email.get('date', '') > latest_agency_email.get('date', ''):
                                latest_agency_email = full_email

                if latest_agency_email:
                    gmail_msg_id = latest_agency_email['id']
                    logger.info(f"📧 Found latest agency email: {gmail_msg_id}")

                    # Use the actual sender's address as reply target instead of stored contact_email.
                    # This avoids multi-address issues and ensures we reply to whoever wrote us.
                    raw_from = latest_agency_email.get('from', '')
                    import re as _re
                    addr_match = _re.search(r'<([^>]+)>', raw_from)
                    reply_to_email = addr_match.group(1).strip() if addr_match else raw_from.strip() or agency_email
                    logger.info(f"📧 Replying to actual sender: {reply_to_email}")

                    # Use Gmail API directly to extract Message-ID header (MCP doesn't provide it)
                    from gmail_api_direct import GmailAPIClient
                    gmail_client = GmailAPIClient()
                    in_reply_to_message_id = gmail_client.get_message_id_header(gmail_msg_id)

                    if in_reply_to_message_id:
                        logger.info(f"✅ Found Message-ID header for In-Reply-To: {in_reply_to_message_id}")
                    else:
                        logger.warning(f"⚠️  Could not extract Message-ID header from {gmail_msg_id}")
                else:
                    logger.warning(f"⚠️  Could not find agency message in thread {thread_id}")

        except Exception as e:
            logger.warning(f"⚠️  Could not get In-Reply-To message ID: {e}")
            import traceback
            traceback.print_exc()

        # Send email via Gmail API directly (NOT MCP) for proper threading
        # This fixes the recipient-side threading issue where replies appeared as separate conversations
        logger.info(f"📧 Sending email via Gmail API with RFC 2822 threading headers...")
        from gmail_api_direct import GmailAPIClient

        gmail_client = GmailAPIClient()
        result = gmail_client.send_threaded_email(
            to=reply_to_email,
            subject=reply_subject,
            body=draft['draft_message'],
            thread_id=thread_id,  # Sender-side threading
            in_reply_to=in_reply_to_message_id,  # Recipient-side threading (RFC 2822)
            references=in_reply_to_message_id  # RFC 2822 References header
        )

        if result['success']:
            # Update draft status
            db = SupabaseIntegration()
            db.supabase.table('message_drafts').update({
                'draft_status': 'sent',
                'sent_at': datetime.now().isoformat()
            }).eq('id', draft['id']).execute()

            logger.info(f"✅ Email sent successfully (message_id: {result.get('message_id')})")
            return True

        else:
            logger.error(f"❌ Email send failed: {result.get('error')}")
            return False

    except Exception as e:
        logger.error(f"❌ Email send error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def get_email_drafts_to_send(db: SupabaseIntegration) -> List[Dict[str, Any]]:
    """Get email-based approved drafts (portal_type='email')"""
    try:
        approved_drafts_result = db.supabase.table('message_drafts').select(
            '*, requests!inner(user_id, portal_name, request_number, portal_type, gmail_thread_id, email_subject)'
        ).in_('draft_status', ['approved', 'edited']).eq('user_approved', True).eq(
            'requests.portal_type', 'email'
        ).execute()

        if not approved_drafts_result.data:
            return []

        logger.info(f"📧 Found {len(approved_drafts_result.data)} email-based drafts to send")
        return approved_drafts_result.data

    except Exception as e:
        logger.error(f"❌ Failed to get email drafts: {str(e)}")
        return []


def get_approved_draft_sessions(db: SupabaseIntegration) -> Dict[str, Any]:
    """Get message sending sessions based on approved drafts (portal-type only)"""
    try:
        approved_drafts_result = db.supabase.table('message_drafts').select(
            '*, requests!inner(user_id, portal_name, request_number, portal_type)'
        ).in_('draft_status', ['approved', 'edited']).eq('user_approved', True).execute()

        if not approved_drafts_result.data:
            return {}

        # Filter out email-based drafts (they're processed separately)
        portal_drafts = [
            draft for draft in approved_drafts_result.data
            if draft['requests'].get('portal_type', 'portal') != 'email'
        ]

        if not portal_drafts:
            return {}

        unique_users = set(draft['requests']['user_id'] for draft in portal_drafts)
        approved_sessions = {}

        for user_id in unique_users:
            user_drafts = [draft for draft in portal_drafts if draft['requests']['user_id'] == user_id]

            drafts_by_portal = {}
            for draft in user_drafts:
                portal_name = draft['requests']['portal_name']
                if portal_name not in drafts_by_portal:
                    drafts_by_portal[portal_name] = []
                drafts_by_portal[portal_name].append(draft)

            for portal_name, portal_portal_drafts in drafts_by_portal.items():
                credentials = get_credentials_for_user_portal(db, user_id, portal_name)
                if credentials:
                    session_key = f"{user_id}#{portal_name}"
                    approved_sessions[session_key] = {
                        'user_id': user_id,
                        'credentials': credentials,
                        'approved_drafts': portal_portal_drafts,
                        'draft_count': len(portal_portal_drafts)
                    }

        return approved_sessions

    except Exception as e:
        logger.error(f"❌ Failed to get approved draft sessions: {str(e)}")
        return {}


def process_approved_drafts_for_portal(session: dict, headless: bool, max_batch_size: int) -> dict:
    """Process approved drafts for a specific portal with isolated browser"""
    try:
        credentials = session['credentials']
        approved_drafts = session['approved_drafts'][:max_batch_size]
        agency_name = credentials.get('agency_name', 'Unknown Agency')

        logger.info(f"📦 Starting message sending for {agency_name}")
        logger.info(f"   Portal: {credentials['portal_url']}")
        logger.info(f"   Approved drafts to send: {len(approved_drafts)}")

        login_credentials = LoginCredentials(username=credentials['username'], password=credentials['password'])

        with PortalAgent(gpt_4o, headless=headless) as agent:
            access_result = agent.access_portal_session(portal_url=credentials['portal_url'], credentials=login_credentials)

            if not access_result.get('navigation', {}).get('success'):
                logger.error(f"❌ Failed to access portal: {credentials['portal_url']}")
                return {
                    'success': False,
                    'error': 'Failed to access portal',
                    'portal': agency_name,
                    'messages_sent': 0,
                    'failures': len(approved_drafts)
                }

            login_successful = False
            if 'login' in access_result:
                login_successful = access_result['login'].get('skipped') or access_result['login'].get('success', False)

            if not login_successful or not agent.is_logged_in:
                logger.error(f"❌ Portal login failed for {agency_name}")
                return {
                    'success': False,
                    'error': 'Portal login failed',
                    'portal': agency_name,
                    'messages_sent': 0,
                    'failures': len(approved_drafts)
                }

            logger.info(f"✅ Successfully logged in to {agency_name}")

            message_coordinator = MessageCoordinator(agent)
            messages_sent = 0
            failures = 0

            for i, draft in enumerate(approved_drafts, 1):
                try:
                    logger.info(f"🔄 Processing draft {i}/{len(approved_drafts)}: {draft['id']}")
                    result = message_coordinator.approve_and_send_draft(draft['id'], None)

                    if result['success']:
                        messages_sent += 1
                        logger.info(f"✅ Draft {draft['id']} sent successfully")
                    else:
                        failures += 1
                        logger.error(f"❌ Draft {draft['id']} failed to send")

                    if i < len(approved_drafts):
                        time.sleep(2)

                except Exception as e:
                    logger.error(f"❌ Error processing draft {draft['id']}: {str(e)}")
                    failures += 1
                    continue

            logger.info(f"📦 Session complete for {agency_name}")
            logger.info(f"   ✅ Messages sent: {messages_sent}")
            logger.info(f"   ❌ Failures: {failures}")

            return {
                'success': True,
                'portal': agency_name,
                'messages_sent': messages_sent,
                'failures': failures
            }

    except Exception as e:
        logger.error(f"❌ Session failed for {session.get('credentials', {}).get('agency_name', 'Unknown')}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'portal': session.get('credentials', {}).get('agency_name', 'Unknown'),
            'messages_sent': 0,
            'failures': len(session.get('approved_drafts', []))
        }


def run_parallel_message_sending(args) -> int:
    """Run message sending with parallel workers (isolated browser per worker)"""
    try:
        print(f"\n🚀 RUNNING PARALLEL MESSAGE SENDING")
        print(f"-" * 50)
        print(f"👷 Workers: {args.workers}")

        db = SupabaseIntegration()

        # Get both email and portal drafts
        email_drafts = get_email_drafts_to_send(db)
        approved_sessions = get_approved_draft_sessions(db)

        # Filter by target_users if specified
        if args.target_users != 'all':
            target_user_ids = [uid.strip() for uid in args.target_users.split(',')]
            email_drafts = [d for d in email_drafts if d['requests']['user_id'] in target_user_ids]
            approved_sessions = {
                key: session for key, session in approved_sessions.items()
                if session['user_id'] in target_user_ids
            }

        total_email = len(email_drafts)
        total_sessions = len(approved_sessions)
        total_approved_drafts = sum(session['draft_count'] for session in approved_sessions.values())

        if total_email == 0 and total_sessions == 0:
            print(f"\n✅ No approved drafts currently awaiting send")
            return 0

        if total_email > 0:
            print(f"📧 Found {total_email} email-based drafts")
        if total_sessions > 0:
            print(f"🎯 Found {total_sessions} portal sessions with {total_approved_drafts} approved drafts")

        # Results aggregation
        results: List[Dict[str, Any]] = []
        email_sent = 0
        email_failed = 0

        # Process email drafts first (fast, no browser needed)
        if email_drafts:
            print(f"\n📧 Processing {len(email_drafts)} email drafts...")

            def process_email_draft(draft):
                """Worker function to send a single email draft"""
                try:
                    from daemon_logger import set_workflow_context
                    set_workflow_context('MessagesSend')
                except ImportError:
                    pass

                request = draft['requests']
                return {
                    'success': send_via_gmail(draft, request),
                    'draft_id': draft['id'],
                    'portal_name': request['portal_name']
                }

            with ThreadPoolExecutor(max_workers=min(args.workers, len(email_drafts))) as executor:
                email_futures = {executor.submit(process_email_draft, draft): draft for draft in email_drafts}

                for future in as_completed(email_futures):
                    result = future.result()
                    if result['success']:
                        email_sent += 1
                        print(f"   ✅ Sent to {result['portal_name']}")
                    else:
                        email_failed += 1
                        print(f"   ❌ Failed to {result['portal_name']}")

            print(f"📧 Email drafts complete: {email_sent} sent, {email_failed} failed")

        # Prepare portal session list for parallel processing
        sessions_list = list(approved_sessions.items())

        def process_session(session_data):
            """Worker function to process a single session with isolated browser"""
            # Set workflow context so logs from this worker go to MessagesSend.log
            try:
                from daemon_logger import set_workflow_context
                set_workflow_context('MessagesSend')
            except ImportError:
                pass  # Running standalone, not through daemon

            session_key, session = session_data
            try:
                result = process_approved_drafts_for_portal(session, args.headless, args.max_batch_size)
                result['session_key'] = session_key
                result['agency_name'] = session['credentials']['agency_name']
                return result
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'session_key': session_key,
                    'agency_name': session['credentials'].get('agency_name', 'Unknown'),
                    'messages_sent': 0,
                    'failures': session.get('draft_count', 0)
                }

        # Process portal sessions if any exist
        if sessions_list:
            # Execute sessions in parallel with ThreadPoolExecutor
            max_workers = min(args.workers, total_sessions)
            print(f"\n⚡ Starting {max_workers} parallel workers for portal drafts...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all sessions to the executor
                future_to_session = {
                    executor.submit(process_session, session_data): session_data
                    for session_data in sessions_list
                }

                # Process results as they complete
                completed = 0
                for future in as_completed(future_to_session):
                    completed += 1
                    result = future.result()
                    results.append(result)

                # Print progress
                if result['success']:
                    print(f"   ✅ [{completed}/{total_sessions}] {result['agency_name']}: "
                          f"{result.get('messages_sent', 0)} sent, "
                          f"{result.get('failures', 0)} failed")
                else:
                    print(f"   ❌ [{completed}/{total_sessions}] {result['agency_name']}: "
                          f"{result.get('error', 'Unknown error')}")

        # Aggregate results
        portal_messages_sent = sum(r.get('messages_sent', 0) for r in results)
        portal_failures = sum(r.get('failures', 0) for r in results)
        successful_sessions = sum(1 for r in results if r.get('success'))

        print(f"\n📊 PARALLEL MESSAGE SENDING COMPLETE:")
        if total_email > 0:
            print(f"  • Email messages: {email_sent} sent, {email_failed} failed")
        if total_sessions > 0:
            print(f"  • Portal sessions: {successful_sessions}/{total_sessions} processed")
            print(f"  • Portal messages: {portal_messages_sent} sent, {portal_failures} failed")
        print(f"  • TOTAL: {email_sent + portal_messages_sent} sent, {email_failed + portal_failures} failed")

        return 0

    except Exception as e:
        logger.error(f"❌ Parallel message sending failed: {str(e)}")
        return 1


def run_sequential_message_sending(args) -> int:
    """Run message sending sequentially (original behavior)"""
    try:
        db = SupabaseIntegration()

        # Process email drafts first (no browser needed)
        email_drafts = get_email_drafts_to_send(db)
        email_sent = 0
        email_failed = 0

        if email_drafts:
            # Filter by target_users if specified
            if args.target_users != 'all':
                target_user_ids = [uid.strip() for uid in args.target_users.split(',')]
                email_drafts = [d for d in email_drafts if d['requests']['user_id'] in target_user_ids]

            if email_drafts:
                print(f"\n📧 Processing {len(email_drafts)} email-based drafts...")
                for draft in email_drafts:
                    request = draft['requests']
                    if send_via_gmail(draft, request):
                        email_sent += 1
                        print(f"   ✅ Sent to {request['portal_name']}")
                    else:
                        email_failed += 1
                        print(f"   ❌ Failed to send to {request['portal_name']}")

                print(f"📧 Email drafts complete: {email_sent} sent, {email_failed} failed\n")

        # Now process portal-based drafts
        approved_sessions = get_approved_draft_sessions(db)

        if not approved_sessions and email_sent == 0:
            print(f"\n✅ No approved drafts currently awaiting send")
            return 0

        if args.target_users != 'all':
            target_user_ids = [uid.strip() for uid in args.target_users.split(',')]
            approved_sessions = {key: session for key, session in approved_sessions.items() if session['user_id'] in target_user_ids}

        total_sessions = len(approved_sessions)
        total_approved_drafts = sum(session['draft_count'] for session in approved_sessions.values())

        if total_sessions > 0:
            print(f"\n🎯 Found {total_sessions} portal sessions with {total_approved_drafts} approved drafts")

        total_messages_sent = 0
        total_failures = 0

        for i, (session_key, session) in enumerate(approved_sessions.items(), 1):
            credentials = session['credentials']
            print(f"\n📤 Session {i}/{total_sessions}: {credentials['agency_name']}")

            result = process_approved_drafts_for_portal(session, args.headless, args.max_batch_size)

            if result['success']:
                total_messages_sent += result.get('messages_sent', 0)
                total_failures += result.get('failures', 0)
                print(f"   ✅ {result.get('messages_sent', 0)} sent, {result.get('failures', 0)} failed")

            if i < total_sessions:
                time.sleep(3)

        print(f"\n📊 MESSAGE SENDING COMPLETE:")
        if email_sent > 0 or email_failed > 0:
            print(f"  • Email messages: {email_sent} sent, {email_failed} failed")
        if total_messages_sent > 0 or total_failures > 0:
            print(f"  • Portal messages: {total_messages_sent} sent, {total_failures} failed")
        print(f"  • TOTAL: {email_sent + total_messages_sent} sent, {email_failed + total_failures} failed")
        return 0

    except Exception as e:
        logger.error(f"❌ Sequential message sending failed: {str(e)}")
        return 1


def cmd_messages_send(args) -> int:
    """Send approved message drafts"""
    print("\n" + "="*80)
    print("📤 INTELLIGENT MESSAGE SENDING SYSTEM")
    print("="*80)
    print("Features:")
    print("  ✅ Sends user-approved message drafts")
    print("  ✅ Batch processing per portal session")
    if hasattr(args, 'mode') and args.mode == 'parallel':
        print(f"  ✅ Parallel processing with {args.workers} workers")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    print(f"  🔄 Mode: {getattr(args, 'mode', 'single')}")
    print(f"  👥 Target Users: {args.target_users}")
    print(f"  📊 Max Batch Size: {args.max_batch_size}")
    print(f"  🖥️  Headless Mode: {args.headless}")
    if hasattr(args, 'workers'):
        print(f"  👷 Workers: {args.workers}")

    try:
        mode = getattr(args, 'mode', 'single')
        if mode == 'parallel':
            return run_parallel_message_sending(args)
        else:
            return run_sequential_message_sending(args)

    except KeyboardInterrupt:
        print(f"\n🛑 Message sending stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        return 1


# ============================================================================
# COMMAND: documents download
# ============================================================================

def cmd_documents_download(args) -> int:
    """Download documents from flagged requests"""
    print("\n" + "="*80)
    print("📥 AUTOMATED DOCUMENT DOWNLOAD SYSTEM")
    print("="*80)
    print("Features:")
    print("  ✅ AI-powered document classification")
    print("  ✅ Automatic downloads from NextRequest portals")
    print("  ✅ Google Drive integration for storage")
    print("  ✅ Comprehensive download tracking")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    print(f"  🔄 Mode: {args.mode}")
    print(f"  ⏰ Check Interval: {args.interval} minutes")
    print(f"  👥 Target Users: {args.target_users}")

    try:
        if args.mode == 'single':
            return run_single_download_cycle(args)
        elif args.mode == 'continuous':
            return run_continuous_downloads(args)
        else:
            print(f"❌ Invalid mode: {args.mode}")
            return 1

    except KeyboardInterrupt:
        print(f"\n🛑 Document downloads stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        return 1


def run_single_download_cycle(args) -> int:
    """Run a single document download cycle"""
    try:
        print(f"\n📥 RUNNING DOCUMENT DOWNLOAD CYCLE")

        db = SupabaseIntegration()
        coordinator = DocumentDownloadCoordinator(gpt_4o, db)

        user_id = None
        if args.target_users != 'all':
            target_user_ids = [uid.strip() for uid in args.target_users.split(',')]
            if len(target_user_ids) == 1:
                user_id = target_user_ids[0]

        result = coordinator.process_flagged_requests(user_id)

        if not result['success']:
            print(f"❌ Download cycle failed: {result.get('error')}")
            return 1

        print(f"\n📊 DOCUMENT DOWNLOAD CYCLE COMPLETE:")
        print(f"  • Flagged requests checked: {result.get('requests_checked', 0)}")
        print(f"  • Documents downloaded: {result.get('documents_downloaded', 0)}")
        print(f"  • Documents uploaded to Drive: {result.get('documents_uploaded', 0)}")
        return 0

    except Exception as e:
        logger.error(f"❌ Download cycle failed: {str(e)}")
        return 1


def run_continuous_downloads(args) -> int:
    """Run continuous document download cycles"""
    try:
        print(f"\n⚡ STARTING CONTINUOUS DOCUMENT DOWNLOAD PROCESSING")
        print(f"⏰ Check interval: {args.interval} minutes")
        print(f"💡 Press Ctrl+C to stop gracefully\n")

        cycle_count = 0

        while True:
            cycle_count += 1
            print(f"\n🔄 DOWNLOAD CYCLE #{cycle_count} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            result = run_single_download_cycle(args)

            if result == 0:
                print(f"✅ Cycle #{cycle_count} completed")
            else:
                print(f"❌ Cycle #{cycle_count} failed")

            print(f"\n💤 Waiting {args.interval} minutes until next cycle...")
            time.sleep(args.interval * 60)

    except KeyboardInterrupt:
        print(f"\n🛑 Continuous downloads stopped by user")
        return 0


# ============================================================================
# COMMAND: documents ocr
# ============================================================================

def cmd_documents_ocr(args) -> int:
    """Process pending OCR and summarization for downloaded documents"""
    print("\n" + "="*80)
    print("🔍 DOCUMENT PROCESSING SYSTEM")
    print("="*80)
    print("Features:")
    print("  ✅ Azure Computer Vision OCR with EasyOCR fallback")
    print("  ✅ AI-powered document summarization")
    print("  ✅ Parallel page processing for speed")
    print("  ✅ Automatic storage in Supabase")
    print("  ✅ Skips already processed documents")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    if args.max_documents:
        print(f"  📄 Max Documents per Stage: {args.max_documents}")
    else:
        print(f"  📄 Max Documents per Stage: All pending documents")
    if args.user_id:
        print(f"  👤 User ID: {args.user_id}")
    else:
        print(f"  👥 Processing: All users")

    try:
        from supabase_integration import SupabaseIntegration
        from document_processor import DocumentProcessor

        print(f"\n🔍 Checking for documents pending processing...")

        db = SupabaseIntegration()
        processor = DocumentProcessor(db)

        # Process pending documents (OCR + Summarization)
        stats = processor.process_pending_documents(
            user_id=args.user_id,
            max_documents=args.max_documents
        )

        print(f"\n📊 DOCUMENT PROCESSING RESULTS:")
        print(f"\n  📄 OCR Processing:")
        print(f"    📋 Total Pending: {stats['ocr']['total_pending']}")
        print(f"    ✅ Successful: {stats['ocr']['successful']}")
        print(f"    ❌ Failed: {stats['ocr']['failed']}")
        if stats['ocr']['processed'] > 0:
            print(f"    📈 Success Rate: {(stats['ocr']['successful']/stats['ocr']['processed']*100):.1f}%")

        print(f"\n  📝 Summarization Processing:")
        print(f"    📋 Total Pending: {stats['summarization']['total_pending']}")
        print(f"    ✅ Successful: {stats['summarization']['successful']}")
        print(f"    ❌ Failed: {stats['summarization']['failed']}")
        if stats['summarization']['processed'] > 0:
            print(f"    📈 Success Rate: {(stats['summarization']['successful']/stats['summarization']['processed']*100):.1f}%")

        print(f"\n  🎯 Overall:")
        print(f"    📋 Total Processed: {stats['total_processed']}")
        print(f"    ✅ Total Successful: {stats['total_successful']}")
        print(f"    ❌ Total Failed: {stats['total_failed']}")

        # Cleanup
        processor.cleanup()

        if stats['total_failed'] > 0:
            print(f"\n⚠️ Some documents failed processing")
            return 1

        print(f"\n✅ Document processing complete")
        return 0

    except KeyboardInterrupt:
        print(f"\n🛑 Document processing stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}", exc_info=True)
        return 1


# ============================================================================
# COMMAND: documents classify
# ============================================================================

def cmd_documents_classify(args) -> int:
    """Classify documents against FOIA requests"""
    print("\n" + "="*80)
    print("🏷️  DOCUMENT CLASSIFICATION SYSTEM")
    print("="*80)
    print("Features:")
    print("  ✅ Classifies PDFs using OCR text analysis")
    print("  ✅ Classifies CSV/XLSX using EDA + table structure")
    print("  ✅ Compares against full FOIA request timeline")
    print("  ✅ Detects if released records match request")
    print("  ✅ Stores results with detailed explanations")
    print("="*80)

    print(f"\n📋 CONFIGURATION:")
    if args.max_documents:
        print(f"  📄 Max Documents: {args.max_documents}")
    else:
        print(f"  📄 Max Documents: All pending documents")
    if args.user_id:
        print(f"  👤 User ID: {args.user_id}")
    else:
        print(f"  👥 Processing: All users")

    try:
        from supabase_integration import SupabaseIntegration
        from document_processor import DocumentProcessor

        print(f"\n🏷️  Checking for documents pending classification...")

        db = SupabaseIntegration()
        processor = DocumentProcessor(db)

        # Process pending classifications
        stats = processor.process_pending_classifications(
            user_id=args.user_id,
            max_documents=args.max_documents
        )

        print(f"\n📊 CLASSIFICATION RESULTS:")
        print(f"\n  📋 Total Pending: {stats['total_pending']}")
        print(f"  ✅ Successful: {stats['successful']}")
        print(f"  ❌ Failed: {stats['failed']}")

        if stats['processed'] > 0:
            success_rate = (stats['successful'] / stats['processed'] * 100)
            print(f"  📈 Success Rate: {success_rate:.1f}%")

            # Count matches
            successful_docs = stats.get('documents', [])
            if successful_docs:
                print(f"\n  🎯 Classification Summary:")
                print(f"    Total Classified: {stats['successful']}")

        if stats['failed'] > 0:
            print(f"\n⚠️ {stats['failed']} documents failed classification")
            return 1

        print(f"\n✅ Document classification complete")
        return 0

    except KeyboardInterrupt:
        print(f"\n🛑 Classification stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}", exc_info=True)
        return 1


# ============================================================================
# COMMAND: account create
# ============================================================================

def cmd_account_create(args) -> int:
    """Create portal accounts (same as queue submit but for new accounts)"""
    print("\n" + "="*80)
    print("🎯 SMART REQUEST SUBMISSION - USES STORED CREDENTIALS")
    print("="*80)
    print("Features:")
    print("  ✅ Handles both existing AND new accounts automatically")
    print("  ✅ Tries login first, continues if fails")
    print("  ✅ Creates account during submission if needed")
    print("="*80)

    # This is the same as queue submit - the logic handles account creation automatically
    return cmd_queue_submit(args)


# ============================================================================
# MAIN CLI ENTRY POINT
# ============================================================================

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Portal Agent - Unified CLI for portal automation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s queue submit --continuous --user-id abc123
  %(prog)s queue analyze --user-id abc123 --max-jobs 5
  %(prog)s monitor --mode single
  %(prog)s monitor --mode continuous --interval 60
  %(prog)s messages draft
  %(prog)s messages send
  %(prog)s documents download --mode single
        """
    )

    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # ========== queue command ==========
    queue_parser = subparsers.add_parser('queue', help='Queue processing commands')
    queue_subparsers = queue_parser.add_subparsers(dest='queue_command')

    submit_parser = queue_subparsers.add_parser('submit', help='Process request submission queue')
    submit_parser.add_argument('--mode', choices=['single', 'parallel'], default='parallel', help='Execution mode (default: parallel)')
    submit_parser.add_argument('--continuous', action='store_true', help='Run in continuous mode (only for single mode)')
    submit_parser.add_argument('--user-id', type=str)
    submit_parser.add_argument('--interval', type=int, default=30)
    submit_parser.add_argument('--max-requests', type=int, default=10)
    submit_parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers (default: 5)')

    analyze_parser = queue_subparsers.add_parser('analyze', help='Process bulk analysis queue')
    analyze_parser.add_argument('--mode', choices=['single', 'parallel'], default='parallel', help='Execution mode (default: parallel)')
    analyze_parser.add_argument('--continuous', action='store_true', help='Run in continuous mode (only for single mode)')
    analyze_parser.add_argument('--user-id', type=str)
    analyze_parser.add_argument('--interval', type=int, default=60)
    analyze_parser.add_argument('--max-jobs', type=int, default=10)
    analyze_parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers (default: 5)')

    # ========== monitor command ==========
    monitor_parser = subparsers.add_parser('monitor', help='Monitor requests for changes')
    monitor_parser.add_argument('--mode', choices=['single', 'parallel', 'continuous'], default='parallel')
    monitor_parser.add_argument('--interval', type=int, default=60)
    monitor_parser.add_argument('--target-users', type=str, default='all')
    monitor_parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers (default: 5)')

    # ========== gmail-monitor command ==========
    gmail_monitor_parser = subparsers.add_parser('gmail-monitor', help='Monitor Gmail for agency email responses')
    gmail_monitor_parser.add_argument('--mode', choices=['single', 'parallel'], default='single')
    gmail_monitor_parser.add_argument('--target-users', type=str, default='all', help='User ID or "all" (default: all)')
    gmail_monitor_parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers (default: 5)')
    gmail_monitor_parser.add_argument('--portal-type', choices=['all', 'email', 'portal'], default='all', help='Filter by portal type (default: all)')

    # ========== inbox-classify command ==========
    inbox_classify_parser = subparsers.add_parser('inbox-classify', help='Classify unmatched inbox emails to FOIA request threads')
    inbox_classify_parser.add_argument('--user-id', type=str, default=None, help='Target a specific user (default: all active users)')
    inbox_classify_parser.add_argument('--retroactive', action='store_true', help='Scan full inbox history and process ALL email requests regardless of status')
    inbox_classify_parser.add_argument('--dry-run', action='store_true', help='Run full pipeline but write nothing to DB — prints audit report instead')

    # ========== messages command ==========
    messages_parser = subparsers.add_parser('messages', help='Message drafting and sending')
    messages_subparsers = messages_parser.add_subparsers(dest='messages_command')

    draft_parser = messages_subparsers.add_parser('draft', help='Draft messages')
    draft_parser.add_argument('--mode', choices=['single', 'parallel'], default='parallel', help='Execution mode (default: parallel)')
    draft_parser.add_argument('--target-users', type=str, default='all')
    draft_parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers (default: 5)')
    draft_parser.add_argument('--force-regenerate', action='store_true', help='Regenerate all drafts even if analysis unchanged (one-time full update)')

    send_parser = messages_subparsers.add_parser('send', help='Send approved drafts')
    send_parser.add_argument('--mode', choices=['single', 'parallel'], default='parallel', help='Execution mode (default: parallel)')
    send_parser.add_argument('--target-users', type=str, default='all')
    send_parser.add_argument('--max-batch-size', type=int, default=10)
    send_parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers (default: 5)')

    # ========== documents command ==========
    documents_parser = subparsers.add_parser('documents', help='Document management')
    documents_subparsers = documents_parser.add_subparsers(dest='documents_command')

    download_parser = documents_subparsers.add_parser('download', help='Download documents')
    download_parser.add_argument('--mode', choices=['single', 'continuous'], default='single')
    download_parser.add_argument('--interval', type=int, default=360)
    download_parser.add_argument('--target-users', type=str, default='all')

    ocr_parser = documents_subparsers.add_parser('ocr', help='Process documents (OCR + Summarization)')
    ocr_parser.add_argument('--user-id', type=str, default=None, help='Process documents for specific user')
    ocr_parser.add_argument('--max-documents', type=int, default=None, help='Maximum documents to process per stage (default: all pending)')

    classify_parser = documents_subparsers.add_parser('classify', help='Classify documents against FOIA requests')
    classify_parser.add_argument('--user-id', type=str, default=None, help='Classify documents for specific user')
    classify_parser.add_argument('--max-documents', type=int, default=None, help='Maximum documents to classify (default: all pending)')

    # ========== account command ==========
    account_parser = subparsers.add_parser('account', help='Account management')
    account_subparsers = account_parser.add_subparsers(dest='account_command')

    create_parser = account_subparsers.add_parser('create', help='Create portal accounts')
    create_parser.add_argument('--user-id', type=str)
    create_parser.add_argument('--interval', type=int, default=30)
    create_parser.add_argument('--max-requests', type=int, default=10)

    # Parse arguments
    args = parser.parse_args()

    # Validate environment (with Google for documents command)
    require_google = (args.command == 'documents' and args.documents_command == 'download')
    if not validate_environment(require_google):
        return 1

    # Route to appropriate command
    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == 'queue':
            if args.queue_command == 'submit':
                return cmd_queue_submit(args)
            elif args.queue_command == 'analyze':
                return cmd_queue_analyze(args)
            else:
                queue_parser.print_help()
                return 1

        elif args.command == 'monitor':
            return cmd_monitor(args)

        elif args.command == 'gmail-monitor':
            return cmd_gmail_monitor(args)

        elif args.command == 'inbox-classify':
            return cmd_inbox_classify(args)

        elif args.command == 'messages':
            if args.messages_command == 'draft':
                return cmd_messages_draft(args)
            elif args.messages_command == 'send':
                return cmd_messages_send(args)
            else:
                messages_parser.print_help()
                return 1

        elif args.command == 'documents':
            if args.documents_command == 'download':
                return cmd_documents_download(args)
            elif args.documents_command == 'ocr':
                return cmd_documents_ocr(args)
            elif args.documents_command == 'classify':
                return cmd_documents_classify(args)
            else:
                documents_parser.print_help()
                return 1

        elif args.command == 'account':
            if args.account_command == 'create':
                return cmd_account_create(args)
            else:
                account_parser.print_help()
                return 1

        else:
            parser.print_help()
            return 1

    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        print(f"\n💥 Fatal error occurred: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
