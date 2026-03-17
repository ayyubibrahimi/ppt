import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
from monitoring_llm_helper import MonitoringLLMHelper
from workflow_state_helper import WorkflowStateHelper

logger = logging.getLogger(__name__)


class MonitoringAgent:
    def __init__(self, portal_agent, db, check_interval_minutes: int = 60, current_portal_url: str = None):
        self.portal_agent = portal_agent
        self.db = db
        self.check_interval_minutes = check_interval_minutes
        self.current_portal_url = current_portal_url

        self.llm_helper = MonitoringLLMHelper(portal_agent.llm_client)
        self.workflow_state_helper = WorkflowStateHelper(portal_agent.llm_client)

        self.is_running = False
        self.monitoring_thread = None
        self.user_id = None

        self.last_run_time = None
        self.total_runs = 0
        self.successful_runs = 0
    
    def start_monitoring(self, user_id: str) -> bool:
        """Start the monitoring agent in a background thread."""
        if self.is_running:
            logger.warning("Monitoring agent is already running")
            return False
        
        self.user_id = user_id
        self.is_running = True
        
        # Start monitoring in background thread
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True  # Dies when main program exits
        )
        self.monitoring_thread.start()
        
        logger.info(f"🔄 Robust LLM monitoring agent started (checking every {self.check_interval_minutes} minutes)")
        return True
    
    def stop_monitoring(self):
        """Stop the monitoring agent."""
        self.is_running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=10)
        logger.info("🛑 Monitoring agent stopped")
    
    def run_single_monitoring_cycle(self, user_id: str = None) -> Dict[str, Any]:
        """Run a single monitoring cycle manually (for testing or on-demand checks)."""
        if not user_id:
            user_id = self.user_id
        
        if not user_id:
            return {'success': False, 'error': 'No user ID provided'}
        
        return self._execute_monitoring_cycle(user_id)
    
    def _monitoring_loop(self):
        """Main monitoring loop that runs in background thread."""
        logger.info(f"🔄 Robust LLM monitoring loop started for user: {self.user_id}")
        
        while self.is_running:
            try:
                # Execute monitoring cycle
                result = self._execute_monitoring_cycle(self.user_id)
                
                if result['success']:
                    self.successful_runs += 1
                    logger.info(f"✅ Monitoring cycle completed: {result['summary']}")
                else:
                    logger.error(f"❌ Monitoring cycle failed: {result.get('error', 'Unknown error')}")
                
                self.total_runs += 1
                self.last_run_time = datetime.now()
                
                # Wait for next cycle
                if self.is_running:  # Check if still running before sleeping
                    time.sleep(self.check_interval_minutes * 60)
                    
            except Exception as e:
                logger.error(f"❌ Monitoring loop error: {str(e)}")
                # Wait before retrying
                if self.is_running:
                    time.sleep(60)  # Wait 1 minute before retry
    
    def _execute_monitoring_cycle(self, user_id: str) -> Dict[str, Any]:
        """
        Execute a complete monitoring cycle using LLM-based analysis.
        """
        run_id = None
        requests_checked = 0
        failed_checks = 0
        changes_detected = 0
        attention_flags_set = 0
        errors = []
        
        try:
            logger.info(f"🔄 Starting LLM-based monitoring cycle for user: {user_id}")
            if self.current_portal_url:
                logger.info(f"🌐 Filtering to requests from portal: {self.current_portal_url}")
            
            # Start tracking this monitoring run
            run_id = self.db.start_monitoring_run(user_id, 'automated')
            
            # Get open requests that need monitoring
            monitoring_queue = self.db.get_monitoring_queue(user_id)
            all_open_requests = monitoring_queue['all_open_requests']
            
            # NEW: Filter requests to only include current portal
            if self.current_portal_url:
                open_requests = [
                    req for req in all_open_requests 
                    if req.get('portal_name') == self.current_portal_url
                ]
                
                if len(all_open_requests) != len(open_requests):
                    logger.info(f"📊 Filtered {len(all_open_requests)} total requests to {len(open_requests)} requests from current portal")
            else:
                logger.warning("⚠️ No current portal URL specified, processing all requests")
                open_requests = all_open_requests
            
            if not open_requests:
                logger.info("📄 No open requests found for current portal")
                if run_id:
                    self.db.complete_monitoring_run(run_id, 0, 0, 0)
                return {
                    'success': True,
                    'summary': f'No open requests to monitor for portal {self.current_portal_url}',
                    'requests_checked': 0,
                    'failed_checks': 0,
                    'changes_detected': 0,
                    'attention_flags_set': 0
                }
            
            logger.info(f"📊 Found {len(open_requests)} open requests for current portal")
            
            # Navigate to portal requests page
            nav_result = self._navigate_to_requests_page()
            if not nav_result['success']:
                error_msg = f"Failed to navigate to requests page: {nav_result['error']}"
                logger.error(error_msg)
                if run_id:
                    self.db.complete_monitoring_run(run_id, 0, 0, 0, error_msg)
                return {'success': False, 'error': error_msg}
            
            # Process each open request
            for i, request in enumerate(open_requests):
                check_start_time = time.time()
                check_changes_detected = False
                check_attention_set = False
                check_error = None

                try:
                    request_number = request['request_number']
                    logger.info(f"🔍 Monitoring request {i+1}/{len(open_requests)}: {request_number}")
                    
                    # Get stored analysis FIRST (using the portal_name from the request record)
                    stored_analysis = self.db.get_stored_analysis(
                        request_number, user_id, request['portal_name']
                    )
                    
                    stored_analysis_data = stored_analysis.get('latest_analysis', {}) if stored_analysis else {}
                    stored_analysis_text = self._format_stored_analysis_for_comparison(stored_analysis_data)
                    
                    # Re-analyze this request WITHOUT auto-saving
                    analysis_result = self._re_analyze_request_with_llm(request_number)
                    
                    if analysis_result['success']:
                        new_analysis_text = analysis_result['analysis_text']

                        # Use LLM helper to detect changes
                        change_analysis = self.llm_helper.analyze_changes(
                            new_analysis_text, stored_analysis_text, request_number
                        )

                        if change_analysis['has_changes']:
                            logger.info(f"🔍 Detected changes in {request_number}: {change_analysis['change_summary']}")
                            changes_detected += 1

                            # Save the new analysis since changes were detected (without workflow_state)
                            try:
                                saved = self.db.save_request_analysis(
                                    user_id, request['portal_name'], analysis_result['analysis_object']
                                )
                                if saved:
                                    logger.info(f"💾 Updated analysis saved for {request_number}")
                            except Exception as e:
                                logger.error(f"❌ Failed to save updated analysis for {request_number}: {str(e)}")

                            # Create change records for database
                            change_records = self.llm_helper.create_change_records_for_database(
                                change_analysis, request['id']
                            )

                            # Save each change record
                            for change_record in change_records:
                                change_record['monitoring_run_id'] = run_id
                                self.db.track_request_change(**change_record)

                            # Update request in database if attention is needed
                            if change_analysis['needs_attention']:
                                attention_flags_set += 1
                                check_attention_set = True
                                self._update_request_attention_status(
                                    request['id'],
                                    change_analysis['attention_reason'],
                                    new_analysis_text
                                )
                                logger.info(f"🚨 Request {request_number} flagged for attention: {change_analysis['attention_reason']}")

                            # Update last_portal_check
                            self._update_last_portal_check(request['id'])
                            check_changes_detected = True

                        else:
                            # No changes detected, just update last_portal_check timestamp
                            self._update_last_portal_check(request['id'])
                            logger.info(f"✅ No changes detected for {request_number}")
                        
                        requests_checked += 1
                        
                    else:
                        check_error = f"Failed to re-analyze {request_number}: {analysis_result['error']}"
                        logger.error(check_error)
                        errors.append(check_error)
                        failed_checks += 1

                    # Log the check
                    check_duration = time.time() - check_start_time
                    self.db.log_monitoring_check(
                        monitoring_run_id=run_id,
                        request_id=request['id'],
                        user_id=user_id,
                        portal_name=request['portal_name'],
                        request_number=request_number,
                        check_status='success' if not check_error else 'failed',
                        changes_detected=check_changes_detected,
                        attention_flag_set=check_attention_set,
                        error_message=check_error,
                        check_duration_seconds=check_duration
                    )

                    # Rate limiting to avoid overwhelming the portal
                    time.sleep(2)

                except Exception as e:
                    error_msg = f"Error processing request {request.get('request_number', 'unknown')}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    failed_checks += 1

                    # Log failed check
                    check_duration = time.time() - check_start_time
                    self.db.log_monitoring_check(
                        monitoring_run_id=run_id,
                        request_id=request.get('id'),
                        user_id=user_id,
                        portal_name=request.get('portal_name', ''),
                        request_number=request.get('request_number', 'unknown'),
                        check_status='failed',
                        changes_detected=False,
                        attention_flag_set=False,
                        error_message=error_msg,
                        check_duration_seconds=check_duration
                    )
            
            # Complete monitoring run
            if run_id:
                error_details = "; ".join(errors[:3]) if errors else None  # First 3 errors
                self.db.complete_monitoring_run(
                    run_id, requests_checked, changes_detected, attention_flags_set, error_details
                )

            # STEP 2: Update workflow states for all monitored requests (after monitoring completes)
            logger.info(f"🔄 Updating workflow states for {len(open_requests)} requests")
            workflow_states_updated = self._update_workflow_states_for_requests(open_requests, user_id)
            logger.info(f"✅ Updated workflow states for {workflow_states_updated} requests")

            total_attempts = requests_checked + failed_checks
            summary = f"{requests_checked}/{total_attempts} successful, {changes_detected} changes, {attention_flags_set} flagged for portal {self.current_portal_url}"

            return {
                'success': True,
                'summary': summary,
                'requests_checked': requests_checked,
                'failed_checks': failed_checks,
                'changes_detected': changes_detected,
                'attention_flags_set': attention_flags_set,
                'workflow_states_updated': workflow_states_updated,
                'errors': errors
            }
            
        except Exception as e:
            error_msg = f"Monitoring cycle failed: {str(e)}"
            logger.error(error_msg)
            
            if run_id:
                self.db.complete_monitoring_run(run_id, requests_checked, changes_detected, attention_flags_set, error_msg)
            
            return {'success': False, 'error': error_msg}

    def _re_analyze_request_with_llm(self, request_number: str) -> Dict[str, Any]:
        """
        Re-analyze a specific request by finding it across pages and clicking it.
        """
        try:
            # First, search for the request across all pages
            found_page = self._find_request_across_pages(request_number)
            
            if not found_page:
                return {'success': False, 'error': f"Request {request_number} not found on any page"}
            
            # Verify the request is visible on current page before clicking
            extraction = self.portal_agent.request_analyzer.extract_requests_with_llm()
            current_requests = [req.request_number for req in extraction.clickable_requests]
            
            if request_number not in current_requests:
                return {'success': False, 'error': f"Request {request_number} not visible on current page after navigation"}
            
            logger.info(f"✅ Request {request_number} confirmed visible, proceeding to click")
            
            # Now click the request using existing logic
            click_result = self.portal_agent.request_analyzer.click_request_with_llm(request_number)
            
            if not click_result['success']:
                return {'success': False, 'error': click_result['error']}
            
            # Use the working analyze_request_detail_with_llm method
            analysis_result = self.portal_agent.request_analyzer.analyze_request_detail_with_llm(
            request_number, auto_save=False  )
        
            
            # Navigate back to requests list
            self.portal_agent.driver.back()
            time.sleep(2)  # Wait for page load
            
            if analysis_result['success']:
                analysis_text = self._format_analysis_for_comparison(analysis_result['analysis'])
                
                return {
                    'success': True,
                    'analysis_object': analysis_result['analysis'],
                    'analysis_text': analysis_text
                }
            else:
                return {'success': False, 'error': analysis_result['error']}
                
        except Exception as e:
            # Try to get back to requests list
            try:
                self.portal_agent.driver.back()
                time.sleep(2)
            except:
                pass
            
            return {'success': False, 'error': str(e)}

    def _find_request_across_pages(self, request_number: str) -> bool:
        """Search using the same pagination pattern as analyze_all_requests()"""
        try:
            logger.info(f"🔍 Searching for request {request_number} across pages...")
            
            # Go to first page like analyze_all_requests does
            self.portal_agent._navigate_to_first_page()
            time.sleep(2)
            
            current_page = 1
            max_pages = 10
            
            while current_page <= max_pages:
                logger.info(f"📄 Checking page {current_page} for request {request_number}")
                
                # Check current page for request
                extraction = self.portal_agent.request_analyzer.extract_requests_with_llm()
                
                if extraction.extraction_successful:
                    request_numbers = [req.request_number for req in extraction.clickable_requests]
                    
                    if request_number in request_numbers:
                        logger.info(f"✅ Found request {request_number} on page {current_page}")
                        time.sleep(1)  # Let page fully load
                        return True
                    
                    logger.info(f"   Request not found on page {current_page}, trying next page...")
                    
                    # Try next page using the working method
                    if self.portal_agent._navigate_to_page_number(current_page + 1):
                        current_page += 1
                        time.sleep(2)
                    else:
                        logger.info(f"📄 No more pages to check")
                        break
                else:
                    logger.error(f"❌ Failed to extract requests from page {current_page}")
                    break
            
            logger.error(f"❌ Request {request_number} not found after checking {current_page} pages")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error searching for request across pages: {str(e)}")
            return False

    def _navigate_to_requests_page(self) -> Dict[str, Any]:
        """Navigate to the requests page and apply filters."""
        try:
            # Use existing RequestAnalyzer navigation
            nav_result = self.portal_agent.request_analyzer.navigate_to_all_requests()
            
            if not nav_result['success']:
                return nav_result
            
            # Apply user-specific filters
            from request_filter_manager import RequestFilterManager
            filter_manager = RequestFilterManager(
                driver=self.portal_agent.driver,
                llm_client=self.portal_agent.llm_client,
                screenshot_manager=self.portal_agent.take_screenshot
            )
            
            # Apply requester filter to show only user's requests
            if filter_manager._apply_requester_filter_only():
                logger.info("✅ Applied requester filter for monitoring")
                time.sleep(3)  # Wait for filter to apply
                return {'success': True}
            else:
                logger.warning("⚠️ Could not apply requester filter, continuing with all requests")
                return {'success': True}  # Continue anyway
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _navigate_to_next_page(self) -> bool:
        """Navigate to next page using portal_agent's working logic."""
        return self.portal_agent._navigate_to_next_page()

    def _navigate_to_first_page(self) -> bool:
        """Navigate back to first page using portal_agent's working logic."""
        return self.portal_agent._navigate_to_first_page()
    
    def _format_analysis_for_comparison(self, analysis) -> str:
        """Convert RequestDetailAnalysis object to structured XML for LLM comparison."""
        try:
            xml_parts = [
                "<request_analysis>",
                f"  <request_number>{getattr(analysis, 'request_number', 'Unknown')}</request_number>",
                f"  <current_status>{getattr(analysis, 'current_status', 'Unknown')}</current_status>",
                f"  <action_required>{getattr(analysis, 'action_required', False)}</action_required>",
                
                "  <timeline_events>"
            ]
            
            # Format timeline events clearly
            timeline_events = getattr(analysis, 'all_timeline_events', [])
            for i, event in enumerate(timeline_events):
                xml_parts.append(f"    <event_{i+1}>")
                xml_parts.append(f"      <![CDATA[{event}]]>")
                xml_parts.append(f"    </event_{i+1}>")
            
            xml_parts.extend([
                "  </timeline_events>",
                
                "  <documents_available>"
            ])
            
            # Format documents
            documents = getattr(analysis, 'documents_available', [])
            for i, doc in enumerate(documents):
                xml_parts.append(f"    <document_{i+1}>{doc}</document_{i+1}>")
            
            xml_parts.extend([
                "  </documents_available>",
                
                "  <outstanding_payments>"
            ])
            
            # Format payments
            payments = getattr(analysis, 'outstanding_payments', [])
            for i, payment in enumerate(payments):
                xml_parts.append(f"    <payment_{i+1}>{payment}</payment_{i+1}>")
            
            xml_parts.extend([
                "  </outstanding_payments>",
                
                f"  <staff_contact>{getattr(analysis, 'staff_contact', 'None')}</staff_contact>",
                
                "  <stated_deadlines>"
            ])
            
            # Format deadlines
            deadlines = getattr(analysis, 'stated_deadlines', [])
            for i, deadline in enumerate(deadlines):
                xml_parts.append(f"    <deadline_{i+1}>{deadline}</deadline_{i+1}>")
            
            xml_parts.extend([
                "  </stated_deadlines>",
                "</request_analysis>"
            ])
            
            return "\n".join(xml_parts)
            
        except Exception as e:
            logger.error(f"❌ Failed to format analysis for comparison: {str(e)}")
            return f"<request_analysis><error>{str(e)}</error></request_analysis>"

    def _format_stored_analysis_for_comparison(self, stored_analysis_data: dict) -> str:
        """Format stored latest_analysis data to structured XML matching new analysis format."""
        
        xml_parts = [
            "<request_analysis>",
            f"  <current_status>{stored_analysis_data.get('current_status', 'Unknown')}</current_status>",
            f"  <action_required>{stored_analysis_data.get('action_required', False)}</action_required>",
            
            "  <timeline_events>"
        ]
        
        # Format timeline events clearly
        timeline_events = stored_analysis_data.get('all_timeline_events', [])
        for i, event in enumerate(timeline_events):
            xml_parts.append(f"    <event_{i+1}>")
            xml_parts.append(f"      <![CDATA[{event}]]>")
            xml_parts.append(f"    </event_{i+1}>")
        
        xml_parts.extend([
            "  </timeline_events>",
            
            "  <documents_available>"
        ])
        
        # Format documents
        documents = stored_analysis_data.get('documents_available', [])
        for i, doc in enumerate(documents):
            xml_parts.append(f"    <document_{i+1}>{doc}</document_{i+1}>")
        
        xml_parts.extend([
            "  </documents_available>",
            
            "  <outstanding_payments>"
        ])
        
        # Format payments
        payments = stored_analysis_data.get('outstanding_payments', [])
        for i, payment in enumerate(payments):
            xml_parts.append(f"    <payment_{i+1}>{payment}</payment_{i+1}>")
        
        xml_parts.extend([
            "  </outstanding_payments>",
            
            f"  <staff_contact>{stored_analysis_data.get('staff_contact', 'None')}</staff_contact>",
            
            "  <stated_deadlines>"
        ])
        
        # Format deadlines
        deadlines = stored_analysis_data.get('stated_deadlines', [])
        for i, deadline in enumerate(deadlines):
            xml_parts.append(f"    <deadline_{i+1}>{deadline}</deadline_{i+1}>")
        
        xml_parts.extend([
            "  </stated_deadlines>",
            "</request_analysis>"
        ])
        
        return "\n".join(xml_parts)
        
    def _update_request_attention_status(self, request_id: str, attention_reason: str, new_analysis_text: str):
        """Update request to require attention with reason."""
        try:
            update_data = {
                'agent_attention_needed': True,
                'agent_attention_reason': attention_reason,
                'last_portal_check': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            self.db.supabase.table('requests').update(update_data).eq('id', request_id).execute()
            
        except Exception as e:
            logger.error(f"❌ Failed to update attention status for request {request_id}: {str(e)}")
    
    def _update_last_portal_check(self, request_id: str):
        """Update just the last_portal_check timestamp."""
        try:
            update_data = {
                'last_portal_check': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

            self.db.supabase.table('requests').update(update_data).eq('id', request_id).execute()

        except Exception as e:
            logger.error(f"❌ Failed to update last portal check for request {request_id}: {str(e)}")

    def _update_workflow_states_for_requests(self, requests: List[Dict], user_id: str) -> int:
        """
        Update workflow states for all requests based on current database state.
        This runs AFTER monitoring completes so it sees the final state.

        Args:
            requests: List of request records from monitoring
            user_id: User ID for logging

        Returns:
            Number of workflow states successfully updated
        """
        updated_count = 0

        for request in requests:
            try:
                request_id = request['id']
                request_number = request.get('request_number', 'unknown')

                # Fetch CURRENT database state (post-monitoring)
                fresh_request = self.db.supabase.table('requests').select('*').eq('id', request_id).execute()

                if not fresh_request.data or len(fresh_request.data) == 0:
                    logger.warning(f"⚠️ Could not fetch request {request_number} from database")
                    continue

                request_data = fresh_request.data[0]

                # Build request_data dict from DATABASE state
                request_info = {
                    'id': request_data['id'],
                    'current_status': request_data.get('current_status', 'Unknown'),
                    'agent_attention_needed': request_data.get('agent_attention_needed', False),
                    'agent_attention_reason': request_data.get('agent_attention_reason', ''),
                    'agent_attention_priority': request_data.get('agent_attention_priority', 'low'),
                    'latest_analysis': request_data.get('latest_analysis', {})
                }

                # Check for pending drafts
                draft_info = None
                try:
                    drafts_result = self.db.supabase.table('message_drafts').select('*').eq(
                        'request_id', request_id
                    ).in_('draft_status', ['drafted', 'edited', 'pending_approval']).eq(
                        'user_approved', False
                    ).execute()

                    if drafts_result.data and len(drafts_result.data) > 0:
                        latest_draft = drafts_result.data[-1]
                        draft_info = {
                            'has_pending_draft': True,
                            'draft_status': latest_draft['draft_status'],
                            'draft_created_at': latest_draft['created_at'],
                            'draft_message_type': latest_draft['message_type'],
                            'user_approved': latest_draft['user_approved'],
                            'draft_message': latest_draft.get('draft_message', '')
                        }
                except Exception as e:
                    logger.warning(f"⚠️ Failed to check drafts for {request_number}: {e}")

                # Get documents status
                documents_status = None
                try:
                    docs = self.db.supabase.table('document_downloads').select('*').eq(
                        'request_id', request_id
                    ).execute()
                    if docs.data:
                        documents_status = {
                            'total_documents': len(docs.data),
                            'all_uploaded': all(d['download_status'] == 'uploaded_to_drive' for d in docs.data),
                            'any_pending': any(d['download_status'] in ['pending', 'completed'] for d in docs.data)
                        }
                except Exception as e:
                    logger.warning(f"⚠️ Failed to check documents for {request_number}: {e}")

                # Determine workflow state based on COMPLETE database state
                workflow_state = self.workflow_state_helper.determine_workflow_state(
                    request_data=request_info,
                    draft_info=draft_info,
                    documents_status=documents_status
                )

                # Update workflow state in database
                success = self.db.update_workflow_state_only(request_id, workflow_state)
                if success:
                    updated_count += 1
                    logger.info(f"🔄 Updated workflow_state to '{workflow_state}' for {request_number}")

            except Exception as e:
                logger.error(f"❌ Failed to update workflow state for request {request.get('request_number', 'unknown')}: {str(e)}")

        return updated_count

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring agent status and statistics."""
        return {
            'is_running': self.is_running,
            'check_interval_minutes': self.check_interval_minutes,
            'user_id': self.user_id,
            'last_run_time': self.last_run_time.isoformat() if self.last_run_time else None,
            'total_runs': self.total_runs,
            'successful_runs': self.successful_runs,
            'success_rate': (self.successful_runs / self.total_runs * 100) if self.total_runs > 0 else 0
        }
    
    def set_check_interval(self, minutes: int):
        """Update the check interval (takes effect on next cycle)."""
        self.check_interval_minutes = minutes
        logger.info(f"🔄 Monitoring interval updated to {minutes} minutes")