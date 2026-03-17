import os
from supabase import create_client, Client
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SupabaseIntegration:
    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY")
        
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment")
        
        self.supabase: Client = create_client(url, key)
        logger.info("✅ Supabase client initialized")
    
    def save_user(self, email: str, full_name: str, phone: str = None, organization: str = None) -> str:
        try:
            # Check if user exists
            result = self.supabase.table('users').select('id').eq('email', email).execute()
            
            if result.data:
                return result.data[0]['id']
            
            # Create new user
            user_data = {
                'email': email,
                'full_name': full_name,
                'phone': phone,
                'organization': organization,
                'is_active': True,
                'last_login': datetime.now().isoformat()
            }
            
            result = self.supabase.table('users').insert(user_data).execute()
            return result.data[0]['id']
            
        except Exception as e:
            logger.error(f"❌ Failed to save user: {str(e)}")
            raise
    
    def save_request_analysis(self, user_id: str, portal_name: str, analysis, submission_queue_id: str = None, workflow_state: str = 'monitoring') -> bool:
        """Save initial request analysis with updated model structure

        Args:
            user_id: User ID
            portal_name: Portal name
            analysis: Request analysis object
            submission_queue_id: Optional submission_queue ID to link this request back to its origin
            workflow_state: Workflow state for the request (default: 'monitoring')
        """
        try:
            request_data = {
                'user_id': user_id,
                'request_number': analysis.request_number,
                'portal_name': portal_name,
                'request_text': analysis.request_text,
                'current_status': analysis.current_status,
                'action_required': analysis.action_required,
                'agent_attention_needed': analysis.needs_attention,
                'agent_attention_reason': analysis.attention_reason,
                'agent_attention_priority': analysis.attention_priority,
                'latest_analysis': {
                    'current_status': analysis.current_status,
                    'action_required': analysis.action_required,
                    'all_timeline_events': analysis.all_timeline_events,
                    'documents_available': analysis.documents_available,
                    'outstanding_payments': analysis.outstanding_payments,
                    'staff_contact': analysis.staff_contact,
                    'stated_deadlines': analysis.stated_deadlines
                },
                # More structured analysis summary
                'analysis_summary': f"Status: {analysis.current_status}. Contact: {analysis.staff_contact}. Action Required: {'Yes' if analysis.action_required else 'No'}. Timeline Events: {len(analysis.all_timeline_events)}. Correspondence Count: {len(analysis.all_timeline_events)}.",
                'last_analyzed': datetime.now().isoformat(),
                'last_portal_check': datetime.now().isoformat(),
                'workflow_state': workflow_state
            }

            # Add submission_queue_id if provided (links request back to original submission)
            if submission_queue_id:
                request_data['submission_queue_id'] = submission_queue_id

                # Fetch and propagate user_notes from submission_queue
                try:
                    queue_result = self.supabase.table('submission_queue').select('user_notes').eq(
                        'id', submission_queue_id
                    ).single().execute()

                    if queue_result.data and queue_result.data.get('user_notes'):
                        request_data['user_notes'] = queue_result.data['user_notes']
                        logger.info(f"✅ Propagated user_notes from submission_queue {submission_queue_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not fetch user_notes from submission_queue: {str(e)}")
            
            # Upsert (update or insert)
            existing = self.supabase.table('requests').select('id').eq('user_id', user_id).eq('request_number', analysis.request_number).eq('portal_name', portal_name).execute()
            
            if existing.data:
                request_data['updated_at'] = datetime.now().isoformat()
                self.supabase.table('requests').update(request_data).eq('id', existing.data[0]['id']).execute()
            else:
                request_data['created_at'] = datetime.now().isoformat()
                self.supabase.table('requests').insert(request_data).execute()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save request analysis: {str(e)}")
            return False

    def update_workflow_state_only(self, request_id: str, workflow_state: str) -> bool:
        """Update only the workflow_state field for a request.

        Used when there are no portal changes but workflow state needs updating
        (e.g., draft created, documents uploaded, etc.)

        Args:
            request_id: ID of the request to update
            workflow_state: New workflow state value

        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'workflow_state': workflow_state,
                'updated_at': datetime.now().isoformat()
            }

            self.supabase.table('requests').update(update_data).eq('id', request_id).execute()
            logger.info(f"✅ Updated workflow_state to '{workflow_state}' for request {request_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update workflow_state for request {request_id}: {str(e)}")
            return False

    # ============================================================================
    # SUBMISSION QUEUE METHODS
    # ============================================================================

    def add_portal_to_bulk_analysis_queue(self, user_id: str, portal_id: str,
                                          portal_name: str, submission_queue_id: str = None) -> Optional[str]:
        """
        Add portal to bulk_analysis_queue to extract all requests.
        Used when a new account is created during submission.

        Args:
            user_id: ID of the user
            portal_id: ID of the portal
            portal_name: Portal name for logging/display
            submission_queue_id: Optional ID of the submission_queue entry that triggered this

        Returns:
            Queue job ID if successful, None if failed
        """
        try:
            # Each submission should create its own bulk analysis job for proper tracking
            # This allows 1:1 linking between submission_queue and requests table
            logger.info(f"Creating new bulk analysis job for {portal_name}")

            # Create new queue job
            queue_data = {
                'user_id': user_id,
                'portal_id': portal_id,
                'job_name': f"Bulk analysis for {portal_name}",
                'analysis_type': 'full_portal_scan',
                'priority': 3,  # Integer priority (1=low, 2=normal, 3=high)
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'progress_data': {
                    'created_reason': 'account_creation',
                    'initial_status': 'queued'
                }
            }

            # Add submission_queue_id if provided (for linking back after analysis)
            if submission_queue_id:
                queue_data['submission_queue_id'] = submission_queue_id
                queue_data['progress_data']['triggered_by_submission'] = submission_queue_id

            result = self.supabase.table('bulk_analysis_queue').insert(queue_data).execute()

            if result.data and len(result.data) > 0:
                queue_id = result.data[0]['id']
                logger.info(f"✅ Added to bulk_analysis_queue: {queue_id}")
                return queue_id
            else:
                logger.error("❌ Failed to add to bulk_analysis_queue - no data returned")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to add to bulk_analysis_queue: {str(e)}")
            return None

    def get_failed_submissions(self, user_id: str = None) -> List[Dict]:
        """
        Get submissions that submitted to portal but failed to queue for analysis.
        These submissions succeeded at the portal level but failed downstream processing.
        Useful for manual intervention or retry.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            List of submission records that need attention
        """
        try:
            query = self.supabase.table('submission_queue').select('*').eq(
                'queued_for_analysis', False
            ).eq('status', 'partial_failure')

            if user_id:
                query = query.eq('user_id', user_id)

            result = query.order('created_at', desc=True).execute()

            failed = result.data or []
            logger.info(f"🚨 Found {len(failed)} submissions that failed to queue for analysis")

            return failed

        except Exception as e:
            logger.error(f"❌ Failed to get failed submissions: {str(e)}")
            return []

    # ============================================================================
    # MONITORING ANALYTICS AND REPORTING
    # ============================================================================

    def get_open_requests_for_monitoring(self, user_id: str) -> List[Dict]:
        """
        Get all requests that need periodic monitoring for changes.
        Returns ALL requests regardless of status.
        """
        try:
            # Get all requests for the user
            result = self.supabase.table('requests').select('*').eq('user_id', user_id).execute()

            requests_to_monitor = result.data or []

            logger.info(f"📊 Found {len(requests_to_monitor)} requests for monitoring (user: {user_id})")
            return requests_to_monitor

        except Exception as e:
            logger.error(f"❌ Failed to get requests for monitoring: {str(e)}")
            return []

    def get_stale_requests(self, user_id: str, hours_threshold: int = 24) -> List[Dict]:
        """
        Get requests that haven't been checked within the specified threshold.
        These requests might have portal updates we haven't detected yet.
        Returns ALL stale requests regardless of status.
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_threshold)
            cutoff_iso = cutoff_time.isoformat()

            result = self.supabase.table('requests').select('*').eq(
                'user_id', user_id
            ).lt('last_portal_check', cutoff_iso).execute()

            stale_requests = result.data or []

            logger.info(f"📊 Found {len(stale_requests)} stale requests (>{hours_threshold}h old)")
            return stale_requests

        except Exception as e:
            logger.error(f"❌ Failed to get stale requests: {str(e)}")
            return []

    def get_stored_analysis(self, request_number: str, user_id: str, portal_name: str) -> Optional[Dict]:
        """
        Retrieve the last known analysis for a specific request.
        Used for comparison to detect changes.
        """
        try:
            result = self.supabase.table('requests').select('*').eq(
                'user_id', user_id
            ).eq('request_number', request_number).eq('portal_name', portal_name).execute()
            
            if result.data:
                return result.data[0]
            else:
                logger.debug(f"No stored analysis found for request {request_number}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to get stored analysis for {request_number}: {str(e)}")
            return None

    def get_monitoring_queue(self, user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive monitoring queue including both flagged and stale requests.
        Returns organized data for monitoring agent to process.
        """
        try:
            # Get requests that need immediate attention
            urgent_requests = self.supabase.table('requests').select('*').eq(
                'user_id', user_id
            ).eq('agent_attention_needed', True).execute()
            
            # Get stale requests (haven't been checked in 30 minutes)
            stale_requests = self.get_stale_requests(user_id, .24)
            
            # Get all open requests for context
            open_requests = self.get_open_requests_for_monitoring(user_id)
            
            return {
                'urgent_requests': urgent_requests.data,
                'stale_requests': stale_requests,
                'all_open_requests': open_requests,
                'total_monitoring_queue': len(urgent_requests.data) + len(stale_requests),
                'summary': {
                    'urgent_count': len(urgent_requests.data),
                    'stale_count': len(stale_requests),
                    'total_open_count': len(open_requests)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get monitoring queue: {str(e)}")
            return {
                'urgent_requests': [], 'stale_requests': [], 'all_open_requests': [],
                'total_monitoring_queue': 0, 'summary': {'urgent_count': 0, 'stale_count': 0, 'total_open_count': 0}
            }

    def update_request_with_changes(self, request_id: str, new_analysis, changes_detected: List[Dict],
                            monitoring_run_id: str = None, workflow_state: str = None) -> bool:
        """
        Update request with new analysis and track what changed.
        This is the core method for synchronizing portal changes with database.

        Args:
            request_id: ID of the request to update
            new_analysis: New analysis data
            changes_detected: List of changes detected
            monitoring_run_id: Optional monitoring run ID
            workflow_state: Optional workflow state to set (if None, not updated)
        """
        try:
            # Prepare update data with new model structure
            update_data = {
                'current_status': new_analysis.current_status,
                'action_required': new_analysis.action_required,
                'agent_attention_needed': new_analysis.needs_attention,
                'attention_priority': new_analysis.attention_priority,
                'agent_attention_reason': new_analysis.attention_reason, 
                'latest_analysis': {
                    'current_status': new_analysis.current_status,
                    'request_text': new_analysis.request_text, 
                    'action_required': new_analysis.action_required,
                    'all_timeline_events': new_analysis.all_timeline_events,
                    'documents_available': new_analysis.documents_available,
                    'outstanding_payments': new_analysis.outstanding_payments,
                    'staff_contact': new_analysis.staff_contact,
                    'stated_deadlines': new_analysis.stated_deadlines
                },
                # Updated analysis summary to be more deterministic
                'analysis_summary': f"Status: {new_analysis.current_status}. Contact: {new_analysis.staff_contact}. Action Required: {'Yes' if new_analysis.action_required else 'No'}. Timeline Events: {len(new_analysis.all_timeline_events)}. Correspondence Count: {len(new_analysis.all_timeline_events)}.",
                'last_analyzed': datetime.now().isoformat(),
                'last_portal_check': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

            # Add workflow_state if provided
            if workflow_state is not None:
                update_data['workflow_state'] = workflow_state

            # Update the request
            self.supabase.table('requests').update(update_data).eq('id', request_id).execute()
            
            # Track individual changes for audit trail
            for change in changes_detected:
                self.track_request_change(
                    request_id=request_id,
                    field_changed=change['field'],
                    old_value=change.get('old_value', ''),
                    new_value=change.get('new_value', ''),
                    change_severity=change.get('severity', 'medium'),
                    triggered_attention=new_analysis.needs_attention,  
                    attention_reason=change.get('details', ''),
                    monitoring_run_id=monitoring_run_id
                )
            
            logger.info(f"✅ Updated request {request_id} with {len(changes_detected)} changes")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update request with changes: {str(e)}")
            return False

    def track_request_change(self, request_id: str, field_changed: str, old_value: str, 
                       new_value: str, change_severity: str = 'medium', 
                       triggered_attention_flag: bool = False,  # ← Match column name
                       attention_reason: str = None, monitoring_run_id: str = None) -> bool:
        """Track individual changes for audit trail and learning."""
        try:
            change_data = {
                'request_id': request_id,
                'field_changed': field_changed,
                'old_value': old_value[:1000] if old_value else None,
                'new_value': new_value[:1000] if new_value else None,
                'change_severity': change_severity,
                'triggered_attention_flag': triggered_attention_flag,  # ← Now matches
                'attention_reason': attention_reason[:500] if attention_reason else None,
                'monitoring_run_id': monitoring_run_id
            }
            
            self.supabase.table('request_changes').insert(change_data).execute()
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to track request change: {str(e)}")
            return False

    def start_monitoring_run(self, user_id: str, run_type: str = 'scheduled') -> str:
        """
        Start tracking a monitoring run for performance analysis.
        Returns run_id for associating changes with this monitoring cycle.
        """
        try:
            run_data = {
                'user_id': user_id,
                'run_type': run_type,  # 'scheduled', 'manual', 'triggered'
                'started_at': datetime.now().isoformat(),
                'status': 'running',
                'requests_checked': 0,
                'changes_detected': 0,
                'attention_flags_set': 0
            }
            
            result = self.supabase.table('monitoring_runs').insert(run_data).execute()
            run_id = result.data[0]['id']
            
            logger.info(f"🔄 Started monitoring run: {run_id} (type: {run_type})")
            return run_id
            
        except Exception as e:
            logger.error(f"❌ Failed to start monitoring run: {str(e)}")
            return None

    def complete_monitoring_run(self, run_id: str, requests_checked: int, changes_detected: int, 
                              attention_flags_set: int, error_details: str = None) -> bool:
        """
        Complete monitoring run with results summary.
        """
        try:
            duration_seconds = None
            
            # Get start time to calculate duration
            run_info = self.supabase.table('monitoring_runs').select('started_at').eq('id', run_id).execute()
            if run_info.data:
                started_at = datetime.fromisoformat(run_info.data[0]['started_at'].replace('Z', '+00:00'))
                duration_seconds = int((datetime.now() - started_at.replace(tzinfo=None)).total_seconds())
            
            update_data = {
                'completed_at': datetime.now().isoformat(),
                'status': 'failed' if error_details else 'completed',
                'requests_checked': requests_checked,
                'changes_detected': changes_detected,
                'attention_flags_set': attention_flags_set,
                'duration_seconds': duration_seconds,
                'error_details': error_details
            }
            
            self.supabase.table('monitoring_runs').update(update_data).eq('id', run_id).execute()
            
            status = "completed" if not error_details else "failed"
            logger.info(f"✅ Monitoring run {run_id} {status}: {requests_checked} checked, {changes_detected} changes, {attention_flags_set} flagged")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to complete monitoring run: {str(e)}")
            return False

    def log_monitoring_check(
        self,
        monitoring_run_id: str,
        request_id: str,
        user_id: str,
        portal_name: str,
        request_number: str,
        check_status: str,
        changes_detected: bool = False,
        attention_flag_set: bool = False,
        error_message: str = None,
        check_duration_seconds: float = None
    ) -> Optional[str]:
        """
        Log an individual request check within a monitoring run.

        Args:
            monitoring_run_id: ID of the parent monitoring run
            request_id: ID of the request being checked
            user_id: ID of the user
            portal_name: Portal URL/name
            request_number: Request number for easy reference
            check_status: 'success', 'failed', or 'skipped'
            changes_detected: Whether changes were detected
            attention_flag_set: Whether attention flag was set
            error_message: Error details if check failed
            check_duration_seconds: How long the check took

        Returns:
            Log entry ID if successful, None otherwise
        """
        try:
            log_data = {
                'monitoring_run_id': monitoring_run_id,
                'request_id': request_id,
                'user_id': user_id,
                'portal_name': portal_name,
                'request_number': request_number,
                'check_status': check_status,
                'changes_detected': changes_detected,
                'attention_flag_set': attention_flag_set
            }

            if error_message:
                log_data['error_message'] = error_message[:1000]  # Limit length

            if check_duration_seconds is not None:
                log_data['check_duration_seconds'] = round(check_duration_seconds, 2)

            result = self.supabase.table('monitoring_check_logs').insert(log_data).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]['id']

            return None

        except Exception as e:
            logger.error(f"❌ Failed to log monitoring check for {request_number}: {str(e)}")
            return None

    def get_monitoring_statistics(self, user_id: str, days_back: int = 7) -> Dict[str, Any]:
        """
        Get monitoring performance statistics for the user.
        Useful for understanding monitoring effectiveness and tuning.
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            cutoff_iso = cutoff_date.isoformat()
            
            # Get recent monitoring runs
            runs = self.supabase.table('monitoring_runs').select('*').eq(
                'user_id', user_id
            ).gte('started_at', cutoff_iso).execute()
            
            # Get recent changes
            changes = self.supabase.table('request_changes').select(
                '*, requests!inner(user_id)'
            ).eq('requests.user_id', user_id).gte('created_at', cutoff_iso).execute()
            
            # Calculate statistics
            total_runs = len(runs.data)
            successful_runs = len([r for r in runs.data if r.get('status') == 'completed'])
            total_requests_checked = sum(r.get('requests_checked', 0) for r in runs.data)
            total_changes_detected = len(changes.data)
            high_severity_changes = len([c for c in changes.data if c.get('change_severity') == 'high'])
            attention_flags_set = sum(r.get('attention_flags_set', 0) for r in runs.data)
            
            avg_run_duration = None
            if runs.data:
                durations = [r.get('duration_seconds', 0) for r in runs.data if r.get('duration_seconds')]
                if durations:
                    avg_run_duration = sum(durations) / len(durations)
            
            return {
                'period_days': days_back,
                'monitoring_runs': {
                    'total': total_runs,
                    'successful': successful_runs,
                    'success_rate': (successful_runs / total_runs * 100) if total_runs > 0 else 0,
                    'avg_duration_seconds': avg_run_duration
                },
                'change_detection': {
                    'total_requests_checked': total_requests_checked,
                    'total_changes_detected': total_changes_detected,
                    'high_severity_changes': high_severity_changes,
                    'attention_flags_set': attention_flags_set,
                    'change_rate': (total_changes_detected / total_requests_checked * 100) if total_requests_checked > 0 else 0
                },
                'recent_changes': changes.data[:10]  # Most recent 10 changes
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get monitoring statistics: {str(e)}")
            return {
                'period_days': days_back,
                'monitoring_runs': {'total': 0, 'successful': 0, 'success_rate': 0},
                'change_detection': {'total_requests_checked': 0, 'total_changes_detected': 0, 'high_severity_changes': 0, 'attention_flags_set': 0, 'change_rate': 0},
                'recent_changes': []
            }
        
    # ============================================================================
    # MESSAGE DRAFTING AND AUDIT METHODS
    # ============================================================================

    def get_flagged_requests(self, user_id: str) -> List[Dict]:
        """
        Get all requests flagged for attention (agent_attention_needed = True).
        Used by MessageCoordinator to find requests needing automated messages.
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of request records flagged for attention
        """
        try:
            result = self.supabase.table('requests').select('*').eq(
                'user_id', user_id
            ).eq('agent_attention_needed', True).execute()
            
            flagged_requests = result.data or []
            logger.info(f"📧 Found {len(flagged_requests)} requests flagged for attention (user: {user_id})")
            
            return flagged_requests
            
        except Exception as e:
            logger.error(f"❌ Failed to get flagged requests: {str(e)}")
            return []

    def save_message_draft(self, request_id: str, subject: str, message: str,
                          message_type: str = 'contextual', 
                          change_context: Dict[str, Any] = None) -> Optional[str]:
        """
        Save a message draft to the database for audit trail.
        
        Args:
            request_id: ID of the request this message is for
            subject: Subject line of the message
            message: Body of the message
            message_type: Type of template used (status_update, additional_info, etc.)
            change_context: Context about what triggered this draft
            
        Returns:
            Draft ID if successful, None if failed
        """
        try:
            draft_data = {
                'request_id': request_id,
                'draft_subject': subject[:500] if subject else None,  # Limit length
                'draft_message': message[:5000] if message else None,  # Limit length
                'message_type': message_type,
                'change_context': change_context or {},
                'draft_status': 'drafted',
                'user_approved': False,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.supabase.table('message_drafts').insert(draft_data).execute()
            
            if result.data and len(result.data) > 0:
                draft_id = result.data[0]['id']
                logger.info(f"✅ Message draft saved with ID: {draft_id}")
                return draft_id
            else:
                logger.error("❌ Draft save returned no data")
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to save message draft: {str(e)}")
            return None

    def update_draft_status(self, draft_id: str, status: str, 
                           sent_at: datetime = None, user_approved: bool = None) -> bool:
        """
        Update the status of a message draft.
        
        Args:
            draft_id: ID of the draft to update
            status: New status (drafted, edited, sent, cancelled, skipped, send_failed)
            sent_at: Timestamp when message was sent (for 'sent' status)
            user_approved: Whether user approved the message
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'draft_status': status,
                'updated_at': datetime.now().isoformat()
            }
            
            if sent_at:
                update_data['sent_at'] = sent_at.isoformat()
            
            if user_approved is not None:
                update_data['user_approved'] = user_approved
            
            result = self.supabase.table('message_drafts').update(update_data).eq('id', draft_id).execute()
            
            if result.data:
                logger.info(f"✅ Draft {draft_id} status updated to: {status}")
                return True
            else:
                logger.warning(f"⚠️ No data returned when updating draft {draft_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to update draft status: {str(e)}")
            return False

    def get_message_history(self, request_id: str) -> List[Dict[str, Any]]:
        """
        Get all message drafts for a specific request (for audit trail).
        
        Args:
            request_id: ID of the request
            
        Returns:
            List of message draft records, ordered by creation date
        """
        try:
            result = self.supabase.table('message_drafts').select('*').eq(
                'request_id', request_id
            ).order('created_at', desc=False).execute()
            
            messages = result.data or []
            logger.info(f"📋 Retrieved {len(messages)} message records for request")
            return messages
            
        except Exception as e:
            logger.error(f"❌ Failed to get message history: {str(e)}")
            return []

    def get_message_drafting_statistics(self, user_id: str, days_back: int = 30) -> Dict[str, Any]:
        """
        Get statistics about message drafting activity for analytics.
        
        Args:
            user_id: ID of the user
            days_back: How many days back to analyze
            
        Returns:
            Dict with comprehensive drafting statistics
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            cutoff_iso = cutoff_date.isoformat()
            
            # Get all drafts for the user in the time period
            result = self.supabase.table('message_drafts').select(
                '*, requests!inner(user_id, request_number)'
            ).eq('requests.user_id', user_id).gte('created_at', cutoff_iso).execute()
            
            drafts = result.data or []
            
            # Calculate comprehensive statistics
            total_drafts = len(drafts)
            sent_count = len([d for d in drafts if d['draft_status'] == 'sent'])
            edited_count = len([d for d in drafts if d['draft_status'] == 'edited'])
            cancelled_count = len([d for d in drafts if d['draft_status'] == 'cancelled'])
            skipped_count = len([d for d in drafts if d['draft_status'] == 'skipped'])
            failed_count = len([d for d in drafts if d['draft_status'] == 'send_failed'])
            
            # Message type breakdown
            type_counts = {}
            for draft in drafts:
                msg_type = draft.get('message_type', 'unknown')
                type_counts[msg_type] = type_counts.get(msg_type, 0) + 1
            
            # Success metrics
            success_rate = (sent_count / total_drafts * 100) if total_drafts > 0 else 0
            approval_rate = (len([d for d in drafts if d.get('user_approved', False)]) / total_drafts * 100) if total_drafts > 0 else 0
            
            # Change context analysis
            change_reasons = {}
            for draft in drafts:
                context = draft.get('change_context', {})
                reason = context.get('attention_reason', 'unknown')
                change_reasons[reason] = change_reasons.get(reason, 0) + 1
            
            return {
                'period_days': days_back,
                'total_drafts': total_drafts,
                'sent_count': sent_count,
                'edited_count': edited_count,
                'cancelled_count': cancelled_count,
                'skipped_count': skipped_count,
                'failed_count': failed_count,
                'success_rate': round(success_rate, 1),
                'approval_rate': round(approval_rate, 1),
                'message_type_breakdown': type_counts,
                'change_reason_breakdown': change_reasons,
                'most_common_type': max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else None,
                'most_common_change_reason': max(change_reasons.items(), key=lambda x: x[1])[0] if change_reasons else None
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get message drafting statistics: {str(e)}")
            return {
                'period_days': days_back,
                'total_drafts': 0,
                'sent_count': 0,
                'edited_count': 0,
                'cancelled_count': 0,
                'skipped_count': 0,
                'failed_count': 0,
                'success_rate': 0,
                'approval_rate': 0,
                'message_type_breakdown': {},
                'change_reason_breakdown': {},
                'most_common_type': None,
                'most_common_change_reason': None
            }

    def clear_attention_flags_batch(self, request_ids: List[str]) -> int:
        """
        Clear attention flags for multiple requests (batch operation).
        Used after successful message sending to clear flags efficiently.
        
        Args:
            request_ids: List of request IDs to clear flags for
            
        Returns:
            Number of requests successfully updated
        """
        try:
            if not request_ids:
                return 0
            
            update_data = {
                'agent_attention_needed': False,
                'agent_attention_reason': None,
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.supabase.table('requests').update(update_data).in_('id', request_ids).execute()
            
            updated_count = len(result.data) if result.data else 0
            logger.info(f"✅ Cleared attention flags for {updated_count} requests")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"❌ Failed to clear attention flags in batch: {str(e)}")
            return 0

    def get_pending_message_drafts(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get message drafts that are pending user action.
        Used for recovery/resume functionality.
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of pending draft records with request context
        """
        try:
            result = self.supabase.table('message_drafts').select(
                '*, requests!inner(user_id, request_number, portal_name, current_status)'
            ).eq('requests.user_id', user_id).in_(
                'draft_status', ['drafted', 'edited']
            ).order('created_at', desc=True).execute()
            
            pending = result.data or []
            logger.info(f"📋 Found {len(pending)} pending message drafts for user")
            return pending
            
        except Exception as e:
            logger.error(f"❌ Failed to get pending message drafts: {str(e)}")
            return []

    def archive_old_message_drafts(self, days_old: int = 90) -> Dict[str, Any]:
        """
        Archive or clean up old message draft records for maintenance.
        
        Args:
            days_old: Archive drafts older than this many days
            
        Returns:
            Dict with cleanup results
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            cutoff_iso = cutoff_date.isoformat()
            
            # Count drafts to be archived
            count_result = self.supabase.table('message_drafts').select(
                'id', count='exact'
            ).lt('created_at', cutoff_iso).execute()
            
            old_count = count_result.count or 0
            
            if old_count == 0:
                logger.info("🗑️ No old message drafts to archive")
                return {
                    'success': True,
                    'archived_count': 0,
                    'message': 'No old drafts found'
                }
            
            # In a production system, you might move to an archive table instead of deleting
            # For now, we'll delete old drafts (keeping the audit trail for recent activity)
            delete_result = self.supabase.table('message_drafts').delete().lt(
                'created_at', cutoff_iso
            ).execute()
            
            archived_count = len(delete_result.data) if delete_result.data else 0
            
            logger.info(f"🗑️ Archived {archived_count} old message drafts")
            
            return {
                'success': True,
                'archived_count': archived_count,
                'cutoff_date': cutoff_iso,
                'message': f'Archived {archived_count} drafts older than {days_old} days'
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to archive old message drafts: {str(e)}")
            return {
                'success': False,
                'archived_count': 0,
                'error': str(e)
            }

    def get_message_effectiveness_metrics(self, user_id: str, days_back: int = 60) -> Dict[str, Any]:
        """
        Analyze message effectiveness by correlating sent messages with subsequent request changes.
        Advanced analytics for understanding message impact.
        
        Args:
            user_id: ID of the user
            days_back: How many days back to analyze
            
        Returns:
            Dict with effectiveness metrics
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            cutoff_iso = cutoff_date.isoformat()
            
            # Get sent messages with their request context
            sent_messages = self.supabase.table('message_drafts').select(
                '*, requests!inner(user_id, request_number, id as request_id)'
            ).eq('requests.user_id', user_id).eq('draft_status', 'sent').gte(
                'sent_at', cutoff_iso
            ).execute()
            
            messages = sent_messages.data or []
            
            if not messages:
                return {
                    'period_days': days_back,
                    'total_sent_messages': 0,
                    'effectiveness_metrics': {}
                }
            
            # Analyze follow-up activity for each sent message
            effectiveness_data = []
            
            for message in messages:
                request_id = message['requests']['request_id']
                sent_at = datetime.fromisoformat(message['sent_at'].replace('Z', '+00:00'))
                
                # Look for monitoring changes after the message was sent
                changes_after = self.supabase.table('request_changes').select('*').eq(
                    'request_id', request_id
                ).gte('created_at', sent_at.isoformat()).execute()
                
                subsequent_changes = len(changes_after.data) if changes_after.data else 0
                
                effectiveness_data.append({
                    'message_type': message.get('message_type', 'unknown'),
                    'subsequent_changes': subsequent_changes,
                    'days_since_sent': (datetime.now() - sent_at.replace(tzinfo=None)).days
                })
            
            # Calculate metrics
            total_messages = len(messages)
            messages_with_response = len([m for m in effectiveness_data if m['subsequent_changes'] > 0])
            response_rate = (messages_with_response / total_messages * 100) if total_messages > 0 else 0
            
            # Type effectiveness
            type_effectiveness = {}
            for msg_type in set(m['message_type'] for m in effectiveness_data):
                type_messages = [m for m in effectiveness_data if m['message_type'] == msg_type]
                type_responses = len([m for m in type_messages if m['subsequent_changes'] > 0])
                type_effectiveness[msg_type] = {
                    'sent_count': len(type_messages),
                    'response_count': type_responses,
                    'response_rate': (type_responses / len(type_messages) * 100) if type_messages else 0
                }
            
            return {
                'period_days': days_back,
                'total_sent_messages': total_messages,
                'messages_with_subsequent_activity': messages_with_response,
                'overall_response_rate': round(response_rate, 1),
                'type_effectiveness': type_effectiveness,
                'avg_days_to_response': sum(m['days_since_sent'] for m in effectiveness_data if m['subsequent_changes'] > 0) / messages_with_response if messages_with_response > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get message effectiveness metrics: {str(e)}")
            return {
                'period_days': days_back,
                'total_sent_messages': 0,
                'effectiveness_metrics': {},
                'error': str(e)
            }
        

    # ============================================================================
    # DOCUMENT DOWNLOAD AND GOOGLE DRIVE METHODS
    # ============================================================================

    def get_requests_needing_document_check(self, user_id: str = None) -> List[Dict]:
        """
        Get flagged requests for users who have Google Drive enabled.
        These are candidates for automatic document download.
        
        Args:
            user_id: Optional specific user ID, otherwise gets all eligible requests
            
        Returns:
            List of request records with user's Google Drive status
        """
        try:
            # Query requests that need attention and have Google Drive enabled
            query = self.supabase.table('requests').select(
                '*, users!inner(id, google_drive_enabled, google_drive_access_token)'
            ).eq('agent_attention_needed', True).eq('users.google_drive_enabled', True)
            
            # Filter to specific user if provided
            if user_id:
                query = query.eq('user_id', user_id)
            
            result = query.execute()
            
            eligible_requests = result.data or []
            
            logger.info(f"📥 Found {len(eligible_requests)} flagged requests with Google Drive enabled")
            
            return eligible_requests
            
        except Exception as e:
            logger.error(f"❌ Failed to get requests needing document check: {str(e)}")
            return []

    def get_google_drive_tokens(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve user's Google Drive OAuth tokens.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dict with tokens and expiry, or None if not available
        """
        try:
            result = self.supabase.table('users').select(
                'google_drive_enabled, '
                'google_drive_access_token, '
                'google_drive_refresh_token, '
                'google_drive_token_expiry'
            ).eq('id', user_id).single().execute()
            
            if not result.data:
                logger.warning(f"User {user_id} not found")
                return None
            
            user_data = result.data
            
            # Check if Google Drive is enabled
            if not user_data.get('google_drive_enabled'):
                logger.info(f"Google Drive not enabled for user {user_id}")
                return None
            
            # Check if tokens exist
            if not user_data.get('google_drive_access_token') or not user_data.get('google_drive_refresh_token'):
                logger.warning(f"Google Drive tokens missing for user {user_id}")
                return None
            
            tokens = {
                'access_token': user_data['google_drive_access_token'],
                'refresh_token': user_data['google_drive_refresh_token'],
                'token_expiry': user_data['google_drive_token_expiry']
            }
            
            logger.info(f"✅ Retrieved Google Drive tokens for user {user_id}")
            return tokens
            
        except Exception as e:
            logger.error(f"❌ Failed to get Google Drive tokens for user {user_id}: {str(e)}")
            return None

    def update_google_drive_tokens(self, user_id: str, access_token: str, 
                                token_expiry: str) -> bool:
        """
        Update user's Google Drive access token after refresh.
        
        Args:
            user_id: ID of the user
            access_token: New access token
            token_expiry: New token expiry timestamp (ISO format)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'google_drive_access_token': access_token,
                'google_drive_token_expiry': token_expiry,
                'updated_at': datetime.now().isoformat()
            }
            
            self.supabase.table('users').update(update_data).eq('id', user_id).execute()
            
            logger.info(f"✅ Updated Google Drive tokens for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update Google Drive tokens: {str(e)}")
            return False

    def save_document_download_record(
        self,
        request_id: str,
        user_id: str,
        portal_name: str,
        document_metadata: Dict[str, Any]
    ) -> Optional[str]:
        """
        Create a record to track document download.
        Checks for existing record first to avoid duplicates.

        Args:
            request_id: ID of the request
            user_id: ID of the user
            portal_name: Portal URL/name
            document_metadata: Document details (id, title, extension, etc.)

        Returns:
            Download record ID if successful, None otherwise
        """
        try:
            import os

            document_title = document_metadata.get('title')

            # Check if a record already exists for this document
            existing = self.supabase.table('document_downloads').select('id').eq(
                'request_id', request_id
            ).eq(
                'document_title', document_title
            ).execute()

            # If record exists, return its ID instead of creating a duplicate
            if existing.data and len(existing.data) > 0:
                record_id = existing.data[0]['id']
                logger.info(f"📌 Found existing download record {record_id} for document {document_title}")
                return record_id

            # Extract file extension from document_title if not provided
            file_extension = document_metadata.get('file_extension')
            if not file_extension and document_title:
                # Use os.path.splitext to parse the extension
                _, ext = os.path.splitext(document_title)
                # Keep the leading dot (e.g., ".pdf")
                file_extension = ext.lower() if ext else None

            # Determine OCR and summary status based on file type
            # Only PDFs need OCR; Excel/CSV files are processed directly for classification
            if file_extension and file_extension.lower() == '.pdf':
                ocr_status = 'pending'
                summary_status = 'pending'  # PDFs need summarization after OCR
            elif file_extension and file_extension.lower() in ['.csv', '.xlsx', '.xls']:
                ocr_status = 'not_applicable'  # Excel/CSV don't need OCR
                summary_status = 'not_applicable'  # Excel/CSV don't need summarization
            else:
                # Unknown file types - mark as pending to be safe
                ocr_status = 'pending'
                summary_status = 'pending'

            # No existing record, create a new one
            download_data = {
                'request_id': request_id,
                'user_id': user_id,
                'portal_name': portal_name,
                'document_id': document_metadata.get('document_id'),
                'document_title': document_title,
                'file_extension': file_extension,
                'download_status': 'pending',
                'ocr_status': ocr_status,
                'summary_status': summary_status,
                'portal_document_id': str(document_metadata.get('id', document_metadata.get('document_id'))),
                'created_at': datetime.now().isoformat()
            }

            result = self.supabase.table('document_downloads').insert(download_data).execute()

            if result.data and len(result.data) > 0:
                record_id = result.data[0]['id']
                logger.info(f"✅ Created download record {record_id} for document {document_title}")
                return record_id
            else:
                logger.error("❌ Failed to create download record - no data returned")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to save document download record: {str(e)}")
            return None

    def update_document_download_status(
    self,
    download_id: str,
    status: str,
    error_message: str = None,
    google_drive_file_id: str = None,
    google_drive_folder_id: str = None,
    google_drive_web_link: str = None
) -> bool:
        """Update status of a document download record"""
        try:
            from datetime import datetime

            update_data = {
                'download_status': status,
            }

            # Set appropriate timestamp based on status
            if status == 'completed':
                update_data['downloaded_at'] = datetime.now().isoformat()
            elif status == 'uploaded_to_drive':
                update_data['uploaded_to_drive_at'] = datetime.now().isoformat()

            if error_message:
                update_data['error_details'] = error_message  # Note: column is 'error_details' not 'error_message'
            if google_drive_file_id:
                update_data['google_drive_file_id'] = google_drive_file_id
            if google_drive_folder_id:
                update_data['google_drive_folder_id'] = google_drive_folder_id
            if google_drive_web_link:
                update_data['google_drive_web_link'] = google_drive_web_link
            
            result = self.supabase.table('document_downloads').update(
                update_data
            ).eq('id', download_id).execute()
            
            logger.info(f"✅ Updated download status to '{status}' for record {download_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update download status: {str(e)}")
            return False

    def get_pending_document_downloads(self, user_id: str = None) -> List[Dict]:
        """
        Get document downloads that are pending or failed (for retry).
        
        Args:
            user_id: Optional user ID to filter by
            
        Returns:
            List of pending/failed download records
        """
        try:
            query = self.supabase.table('document_downloads').select('*').in_(
                'download_status', ['pending', 'failed']
            )
            
            if user_id:
                query = query.eq('user_id', user_id)
            
            result = query.order('created_at', desc=False).execute()
            
            pending = result.data or []
            logger.info(f"📋 Found {len(pending)} pending/failed downloads")
            
            return pending
            
        except Exception as e:
            logger.error(f"❌ Failed to get pending downloads: {str(e)}")
            return []

    def get_downloads_for_request(self, request_id: str) -> List[Dict]:
        """
        Get all document downloads associated with a request.
        
        Args:
            request_id: ID of the request
            
        Returns:
            List of download records for this request
        """
        try:
            result = self.supabase.table('document_downloads').select('*').eq(
                'request_id', request_id
            ).order('created_at', desc=False).execute()
            
            downloads = result.data or []
            logger.info(f"📋 Found {len(downloads)} downloads for request {request_id}")
            
            return downloads
            
        except Exception as e:
            logger.error(f"❌ Failed to get downloads for request: {str(e)}")
            return []

    def mark_documents_downloaded(self, download_ids: List[str]) -> int:
        """
        Batch update multiple download records to 'completed' status.
        
        Args:
            download_ids: List of download record IDs
            
        Returns:
            Number of records successfully updated
        """
        try:
            if not download_ids:
                return 0
            
            update_data = {
                'download_status': 'completed',
                'downloaded_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.supabase.table('document_downloads').update(update_data).in_(
                'id', download_ids
            ).execute()
            
            updated_count = len(result.data) if result.data else 0
            logger.info(f"✅ Marked {updated_count} documents as downloaded")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"❌ Failed to mark documents as downloaded: {str(e)}")
            return 0

    def get_document_download_statistics(self, user_id: str, days_back: int = 30) -> Dict[str, Any]:
        """
        Get statistics about document downloads for analytics.

        Args:
            user_id: ID of the user
            days_back: How many days back to analyze

        Returns:
            Dict with download statistics
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            cutoff_iso = cutoff_date.isoformat()

            result = self.supabase.table('document_downloads').select('*').eq(
                'user_id', user_id
            ).gte('created_at', cutoff_iso).execute()

            downloads = result.data or []

            # Calculate statistics
            total = len(downloads)
            completed = len([d for d in downloads if d['download_status'] == 'completed'])
            uploaded = len([d for d in downloads if d['download_status'] == 'uploaded_to_drive'])
            failed = len([d for d in downloads if d['download_status'] == 'failed'])
            pending = len([d for d in downloads if d['download_status'] == 'pending'])

            # Calculate total file size
            total_bytes = sum(d.get('file_size_bytes', 0) for d in downloads if d.get('file_size_bytes'))

            return {
                'period_days': days_back,
                'total_downloads': total,
                'completed': completed,
                'uploaded_to_drive': uploaded,
                'failed': failed,
                'pending': pending,
                'success_rate': (completed / total * 100) if total > 0 else 0,
                'upload_rate': (uploaded / total * 100) if total > 0 else 0,
                'total_size_mb': round(total_bytes / (1024 * 1024), 2)
            }

        except Exception as e:
            logger.error(f"❌ Failed to get download statistics: {str(e)}")
            return {
                'period_days': days_back,
                'total_downloads': 0,
                'error': str(e)
            }

    # ============================================================================
    # OCR AND SUMMARIZATION METHODS
    # ============================================================================

    def update_document_ocr_data(
        self,
        download_id: str,
        ocr_data: Dict[str, Any],
        ocr_method: str,
        num_pages: int,
        file_size_bytes: int = None,
        local_file_path: str = None
    ) -> bool:
        """
        Update document with OCR data after processing.

        Args:
            download_id: Document download record ID
            ocr_data: OCR data dict with page_texts structure
            ocr_method: OCR engine used (azure_cv, easyocr)
            num_pages: Number of pages in document
            file_size_bytes: File size in bytes
            local_file_path: Path where file was downloaded

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get existing document_data or create new
            existing = self.supabase.table('document_downloads').select('document_data').eq('id', download_id).execute()

            document_data = {}
            if existing.data and existing.data[0].get('document_data'):
                document_data = existing.data[0]['document_data']

            # Update with OCR data
            document_data['ocr_data'] = ocr_data

            update_data = {
                'document_data': document_data,
                'ocr_status': 'completed',
                'ocr_completed_at': datetime.now().isoformat(),
                'ocr_method': ocr_method,
                'num_pages': num_pages
            }

            if file_size_bytes:
                update_data['file_size_bytes'] = file_size_bytes

            if local_file_path:
                update_data['local_file_path'] = local_file_path

            result = self.supabase.table('document_downloads').update(update_data).eq('id', download_id).execute()

            logger.info(f"✅ Updated OCR data for document {download_id} ({num_pages} pages, method: {ocr_method})")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update OCR data: {str(e)}")
            return False

    def update_document_summary(
        self,
        download_id: str,
        summary: Dict[str, Any],
        summary_method: str
    ) -> bool:
        """
        Update document with summary after processing.

        Args:
            download_id: Document download record ID
            summary: Summary data dict with summary_text, timestamp, etc.
            summary_method: LLM model used for summarization

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get existing document_data
            existing = self.supabase.table('document_downloads').select('document_data').eq('id', download_id).execute()

            if not existing.data or not existing.data[0].get('document_data'):
                logger.error(f"❌ Cannot add summary - no document_data found for {download_id}")
                return False

            document_data = existing.data[0]['document_data']

            # Add summary to document_data
            document_data['summary'] = summary

            update_data = {
                'document_data': document_data,
                'summary_status': 'completed',
                'summary_completed_at': datetime.now().isoformat(),
                'summary_method': summary_method
            }

            result = self.supabase.table('document_downloads').update(update_data).eq('id', download_id).execute()

            logger.info(f"✅ Updated summary for document {download_id} (method: {summary_method})")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update summary: {str(e)}")
            return False

    def set_ocr_status(self, download_id: str, status: str, error_message: str = None) -> bool:
        """
        Update OCR processing status.

        Args:
            download_id: Document download record ID
            status: Status (pending, processing, completed, failed)
            error_message: Error details if failed

        Returns:
            True if successful
        """
        try:
            update_data = {'ocr_status': status}

            if status == 'completed':
                update_data['ocr_completed_at'] = datetime.now().isoformat()
            elif status == 'failed' and error_message:
                update_data['error_details'] = f"OCR Error: {error_message}"

            self.supabase.table('document_downloads').update(update_data).eq('id', download_id).execute()
            logger.info(f"✅ Set OCR status to '{status}' for document {download_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to set OCR status: {str(e)}")
            return False

    def set_summary_status(self, download_id: str, status: str, error_message: str = None) -> bool:
        """
        Update summary processing status.

        Args:
            download_id: Document download record ID
            status: Status (pending, processing, completed, failed)
            error_message: Error details if failed

        Returns:
            True if successful
        """
        try:
            update_data = {'summary_status': status}

            if status == 'completed':
                update_data['summary_completed_at'] = datetime.now().isoformat()
            elif status == 'failed' and error_message:
                update_data['error_details'] = f"Summary Error: {error_message}"

            self.supabase.table('document_downloads').update(update_data).eq('id', download_id).execute()
            logger.info(f"✅ Set summary status to '{status}' for document {download_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to set summary status: {str(e)}")
            return False

    def get_documents_pending_ocr(self, user_id: str = None, limit: int = 10) -> List[Dict]:
        """
        Get documents that need OCR processing.

        Args:
            user_id: Optional user ID to filter by
            limit: Maximum number of records to return

        Returns:
            List of document records pending OCR
        """
        try:
            query = self.supabase.table('document_downloads').select('*').eq('ocr_status', 'pending')

            if user_id:
                query = query.eq('user_id', user_id)

            result = query.limit(limit).order('created_at', desc=False).execute()

            pending = result.data or []
            logger.info(f"📋 Found {len(pending)} documents pending OCR")

            return pending

        except Exception as e:
            logger.error(f"❌ Failed to get documents pending OCR: {str(e)}")
            return []

    def get_documents_pending_summary(self, user_id: str = None, limit: int = 10) -> List[Dict]:
        """
        Get documents that have OCR completed but need summarization.

        Args:
            user_id: Optional user ID to filter by
            limit: Maximum number of records to return

        Returns:
            List of document records pending summarization
        """
        try:
            query = self.supabase.table('document_downloads').select('*').eq(
                'ocr_status', 'completed'
            ).eq(
                'summary_status', 'pending'
            )

            if user_id:
                query = query.eq('user_id', user_id)

            result = query.limit(limit).order('created_at', desc=False).execute()

            pending = result.data or []
            logger.info(f"📋 Found {len(pending)} documents pending summarization")

            return pending

        except Exception as e:
            logger.error(f"❌ Failed to get documents pending summary: {str(e)}")
            return []

    def get_document_with_data(self, download_id: str) -> Optional[Dict]:
        """
        Get complete document record including document_data JSONB.

        Args:
            download_id: Document download record ID

        Returns:
            Complete document record with all data
        """
        try:
            result = self.supabase.table('document_downloads').select('*').eq('id', download_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]

            logger.warning(f"⚠️ Document {download_id} not found")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get document: {str(e)}")
            return None

    # ============================================================================
    # DATA CLASSIFICATION METHODS
    # ============================================================================

    def get_documents_pending_classification(self, user_id: str = None, limit: int = 10) -> List[Dict]:
        """
        Get documents that need classification.

        Returns documents where:
        - For PDFs: ocr_status='completed' AND classification_status='pending'
        - For CSV/XLSX: google_drive_file_id IS NOT NULL AND classification_status='pending'
          (these files don't need OCR)

        Args:
            user_id: Optional user ID to filter by
            limit: Maximum number of records to return

        Returns:
            List of document records pending classification
        """
        try:
            all_docs = []

            # Query 1: Documents with completed OCR (PDFs)
            query_pdf = self.supabase.table('document_downloads').select('*').eq(
                'classification_status', 'pending'
            ).eq(
                'ocr_status', 'completed'
            )

            if user_id:
                query_pdf = query_pdf.eq('user_id', user_id)

            pdf_docs = query_pdf.limit(limit).order('created_at', desc=False).execute().data or []
            all_docs.extend(pdf_docs)

            # Query 2: Documents in Google Drive without OCR (CSV/XLSX)
            # These have google_drive_file_id but ocr_status != 'completed'
            remaining_limit = limit - len(all_docs)
            tabular_docs = []

            if remaining_limit > 0:
                query_tabular = self.supabase.table('document_downloads').select('*').eq(
                    'classification_status', 'pending'
                ).neq(
                    'ocr_status', 'completed'
                ).not_.is_(
                    'google_drive_file_id', 'null'
                )

                if user_id:
                    query_tabular = query_tabular.eq('user_id', user_id)

                tabular_docs = query_tabular.limit(remaining_limit).order('created_at', desc=False).execute().data or []
                all_docs.extend(tabular_docs)

            logger.info(
                f"🏷️  Found {len(all_docs)} documents pending classification "
                f"({len(pdf_docs)} PDFs with OCR, {len(tabular_docs)} tabular files)"
            )

            return all_docs

        except Exception as e:
            logger.error(f"❌ Failed to get documents pending classification: {str(e)}")
            return []

    def update_document_classification(
        self,
        download_id: str,
        matches_request: bool,
        explanation: str
    ) -> bool:
        """
        Update document with classification results.

        Args:
            download_id: Document download record ID
            matches_request: TRUE if document matches request, FALSE otherwise
            explanation: Detailed explanation of classification decision

        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'records_match_request': matches_request,
                'classification_explanation': explanation,
                'classification_status': 'completed',
                'classification_completed_at': datetime.now().isoformat()
            }

            result = self.supabase.table('document_downloads').update(update_data).eq('id', download_id).execute()

            logger.info(f"✅ Updated classification for document {download_id}: Match={matches_request}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update classification: {str(e)}")
            return False

    def set_classification_status(self, download_id: str, status: str, error_message: str = None) -> bool:
        """
        Update classification processing status.

        Args:
            download_id: Document download record ID
            status: Status (pending, processing, completed, failed)
            error_message: Error details if failed

        Returns:
            True if successful
        """
        try:
            update_data = {'classification_status': status}

            if status == 'completed':
                update_data['classification_completed_at'] = datetime.now().isoformat()
            elif status == 'failed' and error_message:
                update_data['classification_explanation'] = f"Classification Error: {error_message}"

            self.supabase.table('document_downloads').update(update_data).eq('id', download_id).execute()
            logger.info(f"✅ Set classification status to '{status}' for document {download_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to set classification status: {str(e)}")
            return False

    def get_request_context(self, request_id: str) -> Optional[Dict]:
        """
        Get request text and timeline for classification.

        Args:
            request_id: Request ID

        Returns:
            Dict with request_text, timeline_events, and other context
        """
        try:
            result = self.supabase.table('requests').select('*').eq('id', request_id).execute()

            if not result.data or len(result.data) == 0:
                logger.warning(f"⚠️ Request {request_id} not found")
                return None

            request = result.data[0]

            # Extract timeline from latest_analysis (use correct field based on portal_type)
            portal_type = request.get('portal_type', 'portal')
            if portal_type == 'email':
                latest_analysis = request.get('latest_analysis_gmail', {})
            else:
                latest_analysis = request.get('latest_analysis', {})

            timeline_events = latest_analysis.get('all_timeline_events', []) if latest_analysis else []

            context = {
                'request_id': request_id,
                'request_number': request.get('request_number', ''),
                'request_text': request.get('request_text', ''),
                'timeline_events': timeline_events,
                'current_status': request.get('current_status', ''),
                'portal_name': request.get('portal_name', '')
            }

            logger.info(f"✅ Retrieved request context for {request.get('request_number')}")
            return context

        except Exception as e:
            logger.error(f"❌ Failed to get request context: {str(e)}")
            return None

    # ============================================================================
    # CREDENTIAL MANAGEMENT - For Claude SDK Account Creation
    # ============================================================================

    def save_verified_credentials(self, user_id: str, portal_id: str, email: str, password: str) -> bool:
        """
        Save or update verified working credentials after successful account creation.

        This is called after Claude SDK successfully creates an account to store
        the credentials so future submissions don't need to recreate the account.

        Args:
            user_id: User ID
            portal_id: Portal ID
            email: Verified working email/username
            password: Verified working password (will be stored as encrypted in production)

        Returns:
            bool: True if saved successfully
        """
        try:
            logger.info(f"💾 Saving verified credentials for user {user_id} on portal {portal_id}")

            # Check if credentials already exist
            existing = self.supabase.table('user_portal_credentials').select('id').eq(
                'user_id', user_id
            ).eq('portal_id', portal_id).execute()

            credential_data = {
                'user_id': user_id,
                'portal_id': portal_id,
                'encrypted_username': email,  # TODO: Encrypt in production
                'encrypted_password': password,  # TODO: Encrypt in production
                'is_active': True,
                'is_verified': True,
                'last_verified_at': datetime.now().isoformat(),
                'created_reason': 'claude_sdk_account_creation',
                'updated_at': datetime.now().isoformat()
            }

            if existing.data:
                # Update existing credentials
                logger.info(f"   Updating existing credential record {existing.data[0]['id']}")
                self.supabase.table('user_portal_credentials').update(credential_data).eq(
                    'id', existing.data[0]['id']
                ).execute()
            else:
                # Create new credential record
                logger.info(f"   Creating new credential record")
                credential_data['created_at'] = datetime.now().isoformat()
                self.supabase.table('user_portal_credentials').insert(credential_data).execute()

            logger.info("✅ Credentials saved successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to save verified credentials: {str(e)}")
            return False

    # ============================================================================
    # GMAIL MONITORING METHODS
    # ============================================================================

    def update_gmail_analysis(self, request_id: str, analysis, email_id: str) -> bool:
        """
        Update request with new Gmail-based analysis and mark email as processed.

        Args:
            request_id: Database ID of request
            analysis: RequestDetailAnalysis object from LLM
            email_id: Gmail message ID to mark as processed

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build update data
            update_data = {
                'latest_analysis_gmail': {
                    'current_status': analysis.current_status,
                    'action_required': analysis.action_required,
                    'agent_attention_needed': analysis.needs_attention,
                    'attention_priority': analysis.attention_priority,
                    'attention_reason': analysis.attention_reason,
                    'all_timeline_events': analysis.all_timeline_events,
                    'documents_available': analysis.documents_available,
                    'outstanding_payments': analysis.outstanding_payments,
                    'staff_contact': analysis.staff_contact,
                    'stated_deadlines': analysis.stated_deadlines
                },
                'last_gmail_check': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

            # Also update attention flags if needed
            if analysis.needs_attention:
                update_data['agent_attention_needed'] = True
                update_data['agent_attention_reason'] = analysis.attention_reason
                update_data['agent_attention_priority'] = analysis.attention_priority

            # Update request
            self.supabase.table('requests').update(update_data).eq('id', request_id).execute()

            # Add email ID to processed list
            self._mark_email_processed(request_id, email_id)

            logger.info(f"✅ Updated Gmail analysis for request {request_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update Gmail analysis: {str(e)}")
            return False

    def _mark_email_processed(self, request_id: str, email_id: str) -> bool:
        """
        Add email ID to processed_gmail_ids array.

        Args:
            request_id: Request ID
            email_id: Gmail message ID to mark as processed

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current processed IDs
            result = self.supabase.table('requests').select('processed_gmail_ids').eq(
                'id', request_id
            ).single().execute()

            current_ids = result.data.get('processed_gmail_ids', []) or []

            # Add new ID if not already present
            if email_id not in current_ids:
                current_ids.append(email_id)

                # Update array
                self.supabase.table('requests').update({
                    'processed_gmail_ids': current_ids
                }).eq('id', request_id).execute()

                logger.debug(f"Marked email {email_id} as processed for request {request_id}")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to mark email as processed: {str(e)}")
            return False

    def get_user_email(self, user_id: str) -> Optional[str]:
        """
        Get user's email address for Gmail filtering.

        Args:
            user_id: User ID

        Returns:
            User's email address, or None if not found
        """
        try:
            result = self.supabase.table('users').select('email').eq('id', user_id).single().execute()

            if result.data:
                return result.data.get('email')

            return None

        except Exception as e:
            logger.error(f"❌ Failed to get user email: {str(e)}")
            return None

    # ========== Thread Resolution Methods (for InboxClassifier) ==========

    def update_thread_resolution(
        self,
        request_id: str,
        status: str,
        new_thread_id: str = None
    ) -> bool:
        """
        Update thread_resolution_status for an email-based request.
        Optionally overwrites gmail_thread_id when classifier finds a better thread.

        Args:
            request_id: Request ID
            status: One of 'auto', 'classifier', 'needs_review'
            new_thread_id: New gmail_thread_id (only for status='classifier')

        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'thread_resolution_status': status,
                'updated_at': datetime.now().isoformat()
            }

            if new_thread_id and status == 'classifier':
                update_data['gmail_thread_id'] = new_thread_id

            self.supabase.table('requests').update(update_data).eq('id', request_id).execute()
            logger.info(f"✅ Set thread_resolution_status='{status}' for request {request_id}"
                        + (f" (new thread: {new_thread_id})" if new_thread_id else ""))
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update thread resolution for {request_id}: {str(e)}")
            return False

    def get_requests_pending_thread_resolution(self, user_id: str) -> List[Dict]:
        """
        Fetch email-based requests that need inbox classification.

        Returns portal_type='email' requests where thread_resolution_status
        is 'pending' or 'needs_review', enriched with portal contact_email
        and agency_name under a 'portals' key.

        Args:
            user_id: User ID

        Returns:
            List of request dicts with portal data attached as req['portals']
        """
        try:
            result = self.supabase.table('requests').select('*').eq(
                'user_id', user_id
            ).eq('portal_type', 'email').in_(
                'thread_resolution_status', ['pending', 'needs_review']
            ).execute()

            requests = self._enrich_with_portal_data(result.data or [])
            logger.info(f"Found {len(requests)} email request(s) pending thread resolution for user {user_id}")
            return requests

        except Exception as e:
            logger.error(f"❌ Failed to fetch pending thread resolution requests: {str(e)}")
            return []

    def _enrich_with_portal_data(self, requests: List[Dict]) -> List[Dict]:
        """
        Attach portal contact_email and agency_name to each request as req['portals'].
        Fetches all needed portals in a single query.

        Args:
            requests: List of request dicts that have a 'portal_id' field

        Returns:
            Same list with req['portals'] = {'contact_email': ..., 'agency_name': ...}
        """
        portal_ids = list({r['portal_id'] for r in requests if r.get('portal_id')})
        if not portal_ids:
            for req in requests:
                req['portals'] = {}
            return requests

        try:
            portals_result = self.supabase.table('portals').select(
                'id, contact_email, agency_name'
            ).in_('id', portal_ids).execute()

            portal_map = {p['id']: p for p in (portals_result.data or [])}
        except Exception as e:
            logger.warning(f"Could not fetch portal data for enrichment: {e}")
            portal_map = {}

        for req in requests:
            req['portals'] = portal_map.get(req.get('portal_id'), {})

        return requests

    def get_all_email_request_thread_ids(self, user_id: str) -> set:
        """
        Return the set of all known gmail_thread_ids for a user's email requests.
        Used by InboxClassifier to exclude already-claimed threads from inbox scan.

        Args:
            user_id: User ID

        Returns:
            Set of gmail_thread_id strings (excludes None values)
        """
        try:
            result = self.supabase.table('requests').select(
                'gmail_thread_id'
            ).eq('user_id', user_id).eq('portal_type', 'email').execute()

            thread_ids = {
                r['gmail_thread_id']
                for r in (result.data or [])
                if r.get('gmail_thread_id')
            }
            logger.debug(f"Found {len(thread_ids)} known thread IDs for user {user_id}")
            return thread_ids

        except Exception as e:
            logger.error(f"❌ Failed to fetch known thread IDs: {str(e)}")
            return set()

    # ========== Portal Helper Methods (for Email-Based Request System) ==========

    def get_portal_type(self, portal_id: str) -> str:
        """
        Get portal type for a portal.

        Args:
            portal_id: Portal ID

        Returns:
            Portal type ('portal' or 'email'), defaults to 'portal' if not found
        """
        try:
            result = self.supabase.table('portals').select('portal_type').eq(
                'id', portal_id
            ).single().execute()

            if result.data:
                return result.data.get('portal_type', 'portal')

            logger.warning(f"⚠️ Portal {portal_id} not found, defaulting to type 'portal'")
            return 'portal'

        except Exception as e:
            logger.error(f"❌ Failed to get portal type for {portal_id}: {str(e)}")
            return 'portal'

    def get_portal(self, portal_id: str) -> Dict[str, Any]:
        """
        Get complete portal information including contact_email.

        Args:
            portal_id: Portal ID

        Returns:
            Portal data dictionary, or empty dict if not found
        """
        try:
            result = self.supabase.table('portals').select('*').eq(
                'id', portal_id
            ).single().execute()

            if result.data:
                return result.data

            logger.warning(f"⚠️ Portal {portal_id} not found")
            return {}

        except Exception as e:
            logger.error(f"❌ Failed to get portal {portal_id}: {str(e)}")
            return {}

    def get_portal_contact_email(self, portal_id: str) -> Optional[str]:
        """
        Get contact email for a portal (for email-based submissions).

        Args:
            portal_id: Portal ID

        Returns:
            Contact email address, or None if not found
        """
        try:
            result = self.supabase.table('portals').select('contact_email').eq(
                'id', portal_id
            ).single().execute()

            if result.data:
                return result.data.get('contact_email')

            logger.warning(f"⚠️ Portal {portal_id} not found")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get contact email for portal {portal_id}: {str(e)}")
            return None