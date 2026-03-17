import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from message_drafter import MessageDrafter
from message_storage import MessageStorage
from message_ui import MessageUI

logger = logging.getLogger(__name__)


class MessageCoordinator:
    """
    Main orchestrator for the automated message drafting and sending workflow.
    Coordinates between change detection results and message generation/sending.
    """
    
    def __init__(self, portal_agent):
        """
        Initialize the message coordinator with portal agent reference.
        
        Args:
            portal_agent: The main PortalAgent instance with navigation and sending capabilities
        """
        self.portal_agent = portal_agent
        self.driver = portal_agent.driver
        self.request_analyzer = portal_agent.request_analyzer
        self.db = portal_agent.request_analyzer.db if portal_agent.request_analyzer else None
        self.user_id = portal_agent.request_analyzer.user_id if portal_agent.request_analyzer else None
        
        # Initialize components
        self.message_drafter = MessageDrafter(
            llm_client=portal_agent.llm_client,
            db=self.db
        )
        self.message_storage = MessageStorage(self.db)
        self.message_ui = MessageUI()
        
        # Session tracking
        self.session_stats = {
            'total_flagged': 0,
            'drafts_generated': 0,
            'messages_sent': 0,
            'user_cancelled': 0,
            'errors': 0,
            'skipped': 0
        }
        
        logger.info("✅ MessageCoordinator initialized")
    
    def process_all_flagged_requests(self, force_regenerate: bool = False) -> Dict[str, Any]:
        """
        Main entry point: Process all requests flagged for attention.
        PRODUCTION MODE: Removes user confirmation prompts.

        Args:
            force_regenerate: If True, regenerate all drafts even if analysis hasn't changed

        Returns:
            Dict containing results summary and session statistics
        """
        try:
            mode_msg = "FORCE REGENERATE MODE" if force_regenerate else "PRODUCTION MODE"
            logger.info(f"🚀 Starting automated message drafting workflow ({mode_msg})")
            
            # Validate prerequisites
            validation_result = self._validate_prerequisites()
            if not validation_result['valid']:
                return {
                    'success': False,
                    'error': validation_result['error'],
                    'session_stats': self.session_stats
                }
            
            # Step 1: Get all flagged requests
            flagged_requests = self._get_flagged_requests()
            if not flagged_requests:
                return {
                    'success': True,
                    'message': 'No requests currently flagged for attention',
                    'total_flagged': 0,
                    'session_stats': self.session_stats
                }
            
            self.session_stats['total_flagged'] = len(flagged_requests)
            logger.info(f"📧 Found {len(flagged_requests)} flagged requests for auto-drafting")
            
            # Step 2: Process each flagged request (NO USER CONFIRMATION)
            results = []
            for i, request_data in enumerate(flagged_requests, 1):
                try:
                    logger.info(f"📧 Processing request {i}/{len(flagged_requests)}: {request_data['request_number']}")

                    result = self.process_single_flagged_request(request_data, i, len(flagged_requests), force_regenerate)
                    results.append(result)

                    # Update session stats
                    if result['success']:
                        if result['action'] == 'draft_saved':
                            self.session_stats['drafts_generated'] += 1
                        elif result['action'] == 'skipped_unchanged':
                            self.session_stats['skipped'] += 1
                    else:
                        self.session_stats['errors'] += 1
                    
                    # Brief pause between requests to avoid overwhelming the system
                    if i < len(flagged_requests):
                        time.sleep(2)
                        
                except Exception as e:
                    logger.error(f"❌ Error processing request {request_data.get('request_number', 'unknown')}: {str(e)}")
                    self.session_stats['errors'] += 1
                    results.append({
                        'success': False,
                        'request_number': request_data.get('request_number', 'unknown'),
                        'error': str(e)
                    })
                    continue
            
            # Step 3: Log summary (NO UI DISPLAY)
            logger.info(
                f"📊 DRAFTING COMPLETE: {self.session_stats['drafts_generated']} drafts generated, "
                f"{self.session_stats['skipped']} skipped (unchanged), "
                f"{self.session_stats['errors']} errors"
            )

            return {
                'success': True,
                'total_processed': len(results),
                'session_stats': self.session_stats,
                'detailed_results': results,
                'message': (
                    f"Generated {self.session_stats['drafts_generated']} drafts for frontend approval, "
                    f"skipped {self.session_stats['skipped']} unchanged requests"
                )
            }
            
        except Exception as e:
            logger.error(f"❌ Message coordination workflow failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'session_stats': self.session_stats
            }
    
    def process_single_flagged_request(self, request_data: Dict[str, Any],
                                     current_index: int = 1, total_count: int = 1,
                                     force_regenerate: bool = False) -> Dict[str, Any]:
        """
        Process a single flagged request through the complete message workflow.
        PRODUCTION MODE: Auto-generates and saves drafts without user interaction.

        Uses data already collected by the monitoring agent from the database,
        avoiding redundant website scraping and LLM vision calls.

        Args:
            request_data: Database record for the flagged request
            current_index: Current request number being processed
            total_count: Total number of requests being processed
            force_regenerate: If True, regenerate draft even if analysis hasn't changed

        Returns:
            Dict containing processing results
        """
        request_number = request_data['request_number']

        try:
            logger.info(f"🔍 Processing flagged request: {request_number}")

            # Step 0: Check if we should create a new draft (deduplication)
            should_create = self.message_storage.should_create_new_draft(request_data['id'], force_regenerate)
            if not should_create:
                logger.info(f"⏭️ Skipping {request_number} - analysis unchanged since last draft")
                return {
                    'success': True,
                    'request_number': request_number,
                    'action': 'skipped_unchanged',
                    'message': 'Request analysis unchanged since last draft - no new draft needed'
                }

            # Step 1: Get analysis from database (uses monitoring agent's data)
            analysis_result = self._get_analysis_from_database(request_data)
            if not analysis_result['success']:
                return {
                    'success': False,
                    'request_number': request_number,
                    'error': f"Could not retrieve analysis from database: {analysis_result['error']}",
                    'stage': 'database_retrieval'
                }

            analysis = analysis_result['analysis']

            # Step 2: Generate contextual message draft
            draft_result = self._generate_message_draft(request_data, analysis)
            if not draft_result['success']:
                return {
                    'success': False,
                    'request_number': request_number,
                    'error': f"Draft generation failed: {draft_result['error']}",
                    'stage': 'drafting'
                }
            
            draft = draft_result['draft']

            # Step 4: Determine draft status based on auto-approval
            # Auto-approved drafts get 'approved' status, others get 'pending_approval'
            auto_approved = draft.get('auto_approved', False)
            draft_status = 'approved' if auto_approved else 'pending_approval'

            # Save draft to database with appropriate status
            draft_id = self._save_draft_to_database(request_data['id'], draft, request_data, status=draft_status)

            if not draft_id:
                return {
                    'success': False,
                    'request_number': request_number,
                    'error': "Failed to save draft to database",
                    'stage': 'saving'
                }
            
            # PRODUCTION MODE: Auto-save and return success
            # Frontend will handle approval workflow for pending drafts
            # Auto-approved drafts will be sent automatically by Messages Send workflow
            status_msg = "AUTO-APPROVED for sending" if auto_approved else "awaiting user approval"
            logger.info(f"✅ Draft {draft_id} saved for request {request_number} - {status_msg}")

            return {
                'success': True,
                'request_number': request_number,
                'action': 'draft_saved',
                'draft_id': draft_id,
                'message': f"Draft saved - {status_msg}",
                'draft_status': draft_status,
                'auto_approved': auto_approved
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing request {request_number}: {str(e)}")
            return {
                'success': False,
                'request_number': request_number,
                'error': str(e),
                'stage': 'unknown'
            }
    
    def _validate_prerequisites(self) -> Dict[str, Any]:
        """Validate that all required components are available"""
        # Note: Login no longer required for drafting - we use database data only
        # Login is only needed when sending approved messages

        if not self.db:
            return {'valid': False, 'error': 'Database connection not available'}

        if not self.user_id:
            return {'valid': False, 'error': 'User ID not available'}

        return {'valid': True}
    
    def _get_flagged_requests(self) -> List[Dict[str, Any]]:
        """Get all requests flagged for attention"""
        try:
            flagged_requests = self.db.get_flagged_requests(self.user_id)
            logger.info(f"📊 Found {len(flagged_requests)} requests flagged for attention")
            return flagged_requests
        except Exception as e:
            logger.error(f"❌ Failed to get flagged requests: {str(e)}")
            return []
    
    def _confirm_processing_start(self, count: int) -> bool:
        """Get user confirmation to start processing"""
        if count == 0:
            return False
        
        print(f"\n🎯 Ready to process {count} flagged request{'s' if count != 1 else ''}")
        print("   This will:")
        print("   • Navigate to each request")
        print("   • Generate contextual message drafts")
        print("   • Present each draft for your review")
        print("   • Send approved messages")
        print("   • Save all drafts to database for audit trail")
        
        while True:
            response = input(f"\nProceed with processing? (y/n): ").strip().lower()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no")
    
    def _navigate_to_request(self, request_number: str) -> Dict[str, Any]:
        """Navigate to a specific request page"""
        try:
            # Step 1: Ensure we're on the requests page first
            nav_result = self.request_analyzer.navigate_to_all_requests()
            if not nav_result['success']:
                return {'success': False, 'error': f"Could not navigate to requests page: {nav_result['error']}"}
            
            # Step 2: Apply requester filter to show only user's requests (THIS WAS MISSING!)
            logger.info("🔍 Applying filters to show only your requests")
            from request_filter_manager import RequestFilterManager
            filter_manager = RequestFilterManager(
                driver=self.driver,
                llm_client=self.portal_agent.llm_client,
                screenshot_manager=self.portal_agent.take_screenshot
            )
            
            # Apply requester filter
            if not filter_manager._apply_requester_filter_only():
                logger.warning("⚠️ Could not apply requester filter, continuing with all requests")
            else:
                logger.info("✅ Filters applied - now showing only your requests")
            
            time.sleep(3)  # Wait for filter to apply
            
            # Step 3: Click on the specific request (now that we're seeing only user's requests)
            click_result = self.request_analyzer.click_request_with_llm(request_number)
            if not click_result['success']:
                return {'success': False, 'error': f"Could not click request: {click_result['error']}"}
            
            logger.info(f"✅ Successfully navigated to request {request_number}")
            return {'success': True, 'url': click_result.get('url', '')}
            
        except Exception as e:
            logger.error(f"❌ Navigation to {request_number} failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _get_analysis_from_database(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reconstruct analysis from database instead of re-scraping the website.
        This uses the data already collected by the monitoring agent.
        """
        try:
            # For email requests, use latest_analysis_gmail; otherwise use latest_analysis
            portal_type = request_data.get('portal_type', 'portal')
            if portal_type == 'email':
                latest_analysis = request_data.get('latest_analysis_gmail', {})
            else:
                latest_analysis = request_data.get('latest_analysis', {})

            # Create a simple object that mimics RequestDetailAnalysis structure
            # but populated from database fields
            class AnalysisFromDatabase:
                def __init__(self, data, latest):
                    self.request_number = data['request_number']
                    self.current_status = data.get('current_status', '')
                    self.request_text = data.get('request_text', '')
                    self.all_timeline_events = latest.get('all_timeline_events', [])
                    self.documents_available = latest.get('documents_available', [])
                    self.outstanding_payments = latest.get('outstanding_payments', [])
                    self.staff_contact = latest.get('staff_contact', '')
                    self.stated_deadlines = latest.get('stated_deadlines', [])
                    self.action_required = data.get('action_required', False)
                    self.needs_attention = data.get('agent_attention_needed', False)
                    self.attention_reason = data.get('agent_attention_reason', '')
                    self.attention_priority = data.get('agent_attention_priority', 'medium')

            analysis = AnalysisFromDatabase(request_data, latest_analysis)

            logger.info(f"✅ Retrieved analysis from database for {request_data['request_number']} (last analyzed: {request_data.get('last_analyzed', 'unknown')})")
            return {'success': True, 'analysis': analysis}

        except Exception as e:
            logger.error(f"❌ Failed to reconstruct analysis from database: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _generate_message_draft(self, request_data: Dict[str, Any],
                              fresh_analysis) -> Dict[str, Any]:
        """Generate contextual message draft"""
        try:
            # For email requests, use latest_analysis_gmail; otherwise use latest_analysis
            portal_type = request_data.get('portal_type', 'portal')
            if portal_type == 'email':
                stored_analysis = request_data.get('latest_analysis_gmail', {})
            else:
                stored_analysis = request_data.get('latest_analysis', {})

            # Extract change context from the flagged request
            change_context = {
                'attention_reason': request_data.get('agent_attention_reason', ''),
                'attention_priority': request_data.get('agent_attention_priority', 'medium'),
                'last_analyzed': request_data.get('last_analyzed', ''),
                'current_status': fresh_analysis.current_status,
                'stored_analysis': stored_analysis
            }
            
            draft = self.message_drafter.draft_message(
                fresh_analysis, change_context
            )
                        
            if draft:
                logger.info(f"✅ Draft generated for {request_data['request_number']}")
                return {'success': True, 'draft': draft}
            else:
                return {'success': False, 'error': 'Draft generation returned empty result'}
                
        except Exception as e:
            logger.error(f"❌ Draft generation failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _save_draft_to_database(self, request_id: str, draft: Dict[str, Any],
                               request_data: Dict[str, Any], status: str = 'pending_approval') -> Optional[str]:
        """Save draft to database for audit trail with specified status"""
        try:
            # Compute hash of current analysis for future deduplication
            # For email requests, use latest_analysis_gmail; otherwise use latest_analysis
            portal_type = request_data.get('portal_type', 'portal')
            if portal_type == 'email':
                latest_analysis = request_data.get('latest_analysis_gmail', {})
            else:
                latest_analysis = request_data.get('latest_analysis', {})
            analysis_hash = self.message_storage.compute_analysis_hash(latest_analysis)

            # Extract auto_approved flag from draft (set by MessageDrafter)
            auto_approved = draft.get('auto_approved', False)

            change_context = {
                'attention_reason': request_data.get('agent_attention_reason', ''),
                'attention_priority': request_data.get('agent_attention_priority', 'medium'),
                'triggered_by_monitoring': True,
                'generation_timestamp': datetime.now().isoformat(),
                'auto_generated': True,  # Flag to indicate this was auto-generated
                'auto_approved': auto_approved,  # Flag to indicate this was auto-approved
                'production_mode': True,
                'analysis_content_hash': analysis_hash  # Store hash for deduplication
            }

            draft_id = self.message_storage.save_message_draft(
                request_id=request_id,
                subject=draft['subject'],
                message=draft['message'],
                message_type=draft.get('template_type', 'contextual'),
                change_context=change_context,
                initial_status=status,  # Set initial status to pending_approval
                user_approved=auto_approved  # Set user_approved based on auto_approved flag
            )

            if draft_id:
                approval_status = "AUTO-APPROVED" if auto_approved else "pending user approval"
                logger.info(f"✅ Draft saved to database with ID: {draft_id}, status: {status}, {approval_status}")
                return draft_id
            else:
                logger.warning("⚠️ Draft save returned no ID")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to save draft: {str(e)}")
            return None
    
    def _send_approved_message(self, draft: Dict[str, Any], request_number: str, 
                         draft_id: Optional[str]) -> Dict[str, Any]:
        """Send an approved message using existing portal functionality"""
        try:
            logger.info(f"📤 Sending approved message for {request_number}")
            
            # Use the new direct sending method instead of interactive workflow
            result = self.request_analyzer.send_pre_drafted_message(
                subject=draft.get('subject', ''),
                message=draft.get('message', '')
            )
            
            # If message was sent successfully, update draft status
            if result['success'] and draft_id:
                self.message_storage.update_draft_status(
                    draft_id, 'sent', sent_at=datetime.now()
                )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Message sending failed: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    def approve_and_send_draft(self, draft_id: str, edited_content: Dict[str, str] = None) -> Dict[str, Any]:
            """
            Approve and send a draft message. Called by frontend.
            """
            try:
                # Get draft from database
                draft_record = self.message_storage.get_draft_by_id(draft_id)
                if not draft_record:
                    return {
                        'success': False,
                        'error': 'Draft not found',
                        'draft_id': draft_id
                    }
                
                # Get associated request
                request_record = self.db.supabase.table('requests').select('*').eq('id', draft_record['request_id']).execute()
                if not request_record.data:
                    return {
                        'success': False,
                        'error': 'Associated request not found',
                        'draft_id': draft_id
                    }
                
                request_data = request_record.data[0]
                request_number = request_data['request_number']
                
                # Use edited content if provided, otherwise use original draft
                if edited_content:
                    draft_content = {
                        'subject': edited_content.get('subject', draft_record['draft_subject']),
                        'message': edited_content.get('message', draft_record['draft_message'])
                    }
                    # Update draft content in database
                    self.message_storage.update_draft_content(draft_id, draft_content)
                else:
                    draft_content = {
                        'subject': draft_record['draft_subject'],
                        'message': draft_record['draft_message']
                    }
                
                # Navigate to request (this may require portal session)
                navigation_result = self._navigate_to_request(request_number)
                if not navigation_result['success']:
                    return {
                        'success': False,
                        'error': f"Navigation failed: {navigation_result['error']}",
                        'draft_id': draft_id,
                        'stage': 'navigation'
                    }
                
                # Send the message
                send_result = self._send_approved_message(draft_content, request_number, draft_id)
                
                if send_result['success']:
                    # Clear the attention flag since we've responded
                    self._clear_attention_flag(request_data['id'])
                    
                    # Update draft status to sent
                    self.message_storage.update_draft_status(draft_id, 'sent', sent_at=datetime.now(), user_approved=True)
                    
                    return {
                        'success': True,
                        'request_number': request_number,
                        'draft_id': draft_id,
                        'message': 'Message sent successfully'
                    }
                else:
                    # Update draft status as failed
                    self.message_storage.update_draft_status(draft_id, 'send_failed')
                    
                    return {
                        'success': False,
                        'error': f"Message sending failed: {send_result['error']}",
                        'draft_id': draft_id,
                        'stage': 'sending'
                    }
                    
            except Exception as e:
                logger.error(f"❌ Error approving/sending draft {draft_id}: {str(e)}")
                return {
                    'success': False,
                    'error': str(e),
                    'draft_id': draft_id,
                    'stage': 'unknown'
                }
    
    def _clear_attention_flag(self, request_id: str) -> bool:
        """Clear the attention flag after successful message sending"""
        try:
            # Update the request to clear attention flag
            update_data = {
                'agent_attention_needed': False,
                'agent_attention_reason': None,
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.db.supabase.table('requests').update(update_data).eq('id', request_id).execute()
            
            if result.data:
                logger.info(f"✅ Attention flag cleared for request")
                return True
            else:
                logger.warning("⚠️ Failed to clear attention flag")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error clearing attention flag: {str(e)}")
            return False
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """Get current session statistics"""
        return self.session_stats.copy()
    
    def reset_session_statistics(self):
        """Reset session statistics for a new workflow run"""
        self.session_stats = {
            'total_flagged': 0,
            'drafts_generated': 0,
            'messages_sent': 0,
            'user_cancelled': 0,
            'errors': 0,
            'skipped': 0
        }