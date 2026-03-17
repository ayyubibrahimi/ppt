import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MessageUI:
    """
    Terminal-based user interface components for message review and interaction.
    Provides clean, intuitive interfaces for reviewing drafts and managing the workflow.
    """
    
    def __init__(self):
        """Initialize the Message UI component."""
        logger.info("✅ MessageUI initialized")
    
    def display_flagged_requests_summary(self, flagged_requests: List[Dict[str, Any]]) -> None:
        """
        Display overview of all requests flagged for attention.
        
        Args:
            flagged_requests: List of request records flagged for attention
        """
        try:
            print("\n" + "="*80)
            print("📧 AUTOMATED MESSAGE DRAFTING - FLAGGED REQUESTS")
            print("="*80)
            
            if not flagged_requests:
                print("✅ No requests currently flagged for attention!")
                print("   All your requests are up to date.")
                print("="*80)
                return
            
            print(f"Found {len(flagged_requests)} request{'s' if len(flagged_requests) != 1 else ''} needing attention:")
            print()
            
            # Group by priority for better organization
            high_priority = [r for r in flagged_requests if r.get('agent_attention_priority') == 'high']
            medium_priority = [r for r in flagged_requests if r.get('agent_attention_priority') == 'medium']
            low_priority = [r for r in flagged_requests if r.get('agent_attention_priority') == 'low']
            
            # Display high priority first
            if high_priority:
                print("🚨 HIGH PRIORITY:")
                for req in high_priority:
                    self._display_single_request_summary(req, "🚨")
                print()
            
            # Display medium priority
            if medium_priority:
                print("⚠️  MEDIUM PRIORITY:")
                for req in medium_priority:
                    self._display_single_request_summary(req, "⚠️")
                print()
            
            # Display low priority
            if low_priority:
                print("📄 LOW PRIORITY:")
                for req in low_priority:
                    self._display_single_request_summary(req, "📄")
                print()
            
            # Summary stats
            print("📊 SUMMARY:")
            print(f"   High Priority: {len(high_priority)}")
            print(f"   Medium Priority: {len(medium_priority)}")
            print(f"   Low Priority: {len(low_priority)}")
            print(f"   Total: {len(flagged_requests)}")
            print("="*80)
            
        except Exception as e:
            logger.error(f"❌ Failed to display flagged requests summary: {str(e)}")
            print(f"❌ Error displaying summary: {str(e)}")
    
    def _display_single_request_summary(self, request: Dict[str, Any], priority_emoji: str) -> None:
        """Display a single request in the summary list."""
        try:
            request_number = request.get('request_number', 'Unknown')
            status = request.get('current_status', 'Unknown')
            reason = request.get('agent_attention_reason', 'No reason specified')
            last_analyzed = request.get('last_analyzed', '')
            
            # Format the last analyzed time
            time_str = ""
            if last_analyzed:
                try:
                    analyzed_dt = datetime.fromisoformat(last_analyzed.replace('Z', '+00:00'))
                    time_str = f" (last checked: {analyzed_dt.strftime('%m/%d %H:%M')})"
                except:
                    time_str = f" (last checked: {last_analyzed[:10]})"
            
            print(f"   {priority_emoji} Request {request_number} - {status}{time_str}")
            print(f"      Reason: {reason}")
            
        except Exception as e:
            logger.error(f"❌ Error displaying request summary: {str(e)}")
            print(f"   ❌ Error displaying request details")
    
    def review_drafted_message(self, draft: Dict[str, Any], request_analysis, 
                             request_data: Dict[str, Any], current_index: int = 1, 
                             total_count: int = 1) -> Dict[str, Any]:
        """
        Present a drafted message to the user for review and approval.
        
        Args:
            draft: Generated message draft
            request_analysis: Fresh analysis of the request
            request_data: Original request database record
            current_index: Current request number being processed
            total_count: Total number of requests being processed
            
        Returns:
            Dict with user's decision and any edited content
        """
        try:
            request_number = request_data.get('request_number', 'Unknown')
            
            # Header
            print("\n" + "="*80)
            print(f"📧 MESSAGE REVIEW ({current_index}/{total_count})")
            print("="*80)
            
            # Request context
            print(f"🎯 REQUEST: {request_number}")
            print(f"📈 Current Status: {request_analysis.current_status}")
            print(f"👤 Contact: {request_analysis.staff_contact}")
            print(f"🚨 Flagged Because: {request_data.get('agent_attention_reason', 'Unknown')}")
            print(f"⏰ Priority: {request_data.get('agent_attention_priority', 'medium').upper()}")
            
            # Recent timeline context
            if hasattr(request_analysis, 'all_timeline_events') and request_analysis.all_timeline_events:
                recent_events = request_analysis.all_timeline_events[-2:]
                print(f"\n📅 RECENT ACTIVITY:")
                for event in recent_events:
                    print(f"   • {event}")
            
            # Draft preview
            print(f"\n📝 AI-GENERATED DRAFT:")
            print("-" * 60)
            print(f"📌 Subject: {draft.get('subject', 'No subject')}")
            print(f"📄 Message:")
            print()
            
            # Display message with proper formatting
            message_lines = draft.get('message', '').split('\n')
            for line in message_lines:
                print(f"   {line}")
            
            print("-" * 60)
            
            # Draft metadata
            template_type = draft.get('template_type', 'unknown')
            generation_method = draft.get('generation_method', 'unknown')
            print(f"🤖 Generated using: {template_type} template ({generation_method})")
            
            # Options
            print(f"\n🎯 YOUR OPTIONS:")
            print(f"   [A]pprove & Send    - Send this message as-is")
            print(f"   [E]dit & Send       - Make changes before sending")
            print(f"   [S]kip             - Skip this request for now")
            print(f"   [C]ancel           - Cancel entire workflow")
            print(f"   [P]review Again    - Show the message again")
            
            if current_index < total_count:
                print(f"   [N]ext Only        - Skip this and continue to next request")
            
            print("="*80)
            
            # Get user decision
            while True:
                try:
                    choice = input(f"\nYour choice: ").strip().upper()
                    
                    if choice in ['A', 'APPROVE']:
                        return {'action': 'approve', 'draft': draft}
                    
                    elif choice in ['E', 'EDIT']:
                        edited_draft = self._handle_message_editing(draft)
                        if edited_draft:
                            return {'action': 'send_edited', 'edited_draft': edited_draft}
                        else:
                            print("❌ Editing cancelled. Choose another option.")
                            continue
                    
                    elif choice in ['S', 'SKIP']:
                        reason = input("Reason for skipping (optional): ").strip()
                        return {'action': 'skip', 'reason': reason or 'User chose to skip'}
                    
                    elif choice in ['C', 'CANCEL']:
                        confirm = input("Cancel entire workflow? (y/n): ").strip().lower()
                        if confirm in ['y', 'yes']:
                            return {'action': 'cancel'}
                        else:
                            continue
                    
                    elif choice in ['P', 'PREVIEW']:
                        # Redisplay the draft
                        print(f"\n📝 DRAFT PREVIEW:")
                        print("-" * 40)
                        print(f"Subject: {draft.get('subject', '')}")
                        print(f"Message:")
                        for line in draft.get('message', '').split('\n'):
                            print(f"   {line}")
                        print("-" * 40)
                        continue
                    
                    elif choice in ['N', 'NEXT'] and current_index < total_count:
                        return {'action': 'skip', 'reason': 'User chose to move to next request'}
                    
                    else:
                        valid_options = ['A', 'E', 'S', 'C', 'P']
                        if current_index < total_count:
                            valid_options.append('N')
                        print(f"Please enter one of: {', '.join(valid_options)}")
                        continue
                        
                except KeyboardInterrupt:
                    print(f"\n\n❌ Workflow cancelled by user.")
                    return {'action': 'cancel'}
                except Exception as e:
                    logger.error(f"❌ Error getting user input: {str(e)}")
                    print(f"❌ Input error. Please try again.")
                    continue
            
        except Exception as e:
            logger.error(f"❌ Failed to review drafted message: {str(e)}")
            return {'action': 'cancel', 'error': str(e)}
    
    def _handle_message_editing(self, draft: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle the message editing workflow.
        
        Args:
            draft: Original draft to edit
            
        Returns:
            Edited draft or None if cancelled
        """
        try:
            print(f"\n📝 MESSAGE EDITING")
            print("="*50)
            
            current_subject = draft.get('subject', '')
            current_message = draft.get('message', '')
            
            print(f"1. Edit subject line")
            print(f"2. Edit message body")
            print(f"3. Replace entire message")
            print(f"4. Cancel editing")
            
            while True:
                choice = input(f"\nWhat would you like to edit? (1-4): ").strip()
                
                if choice == "1":
                    # Edit subject
                    print(f"\nCurrent subject: {current_subject}")
                    new_subject = input(f"New subject (or press Enter to keep current): ").strip()
                    if new_subject:
                        current_subject = new_subject
                        print(f"✅ Subject updated")
                    
                elif choice == "2":
                    # Edit message body
                    new_message = self._edit_message_body(current_message)
                    if new_message is not None:
                        current_message = new_message
                        print(f"✅ Message updated")
                    
                elif choice == "3":
                    # Replace entire message
                    new_message = self._write_new_message()
                    if new_message:
                        current_message = new_message
                        print(f"✅ Message replaced")
                    
                elif choice == "4":
                    return None
                
                else:
                    print(f"Please enter 1, 2, 3, or 4")
                    continue
                
                # Show preview and ask if done
                print(f"\n📋 UPDATED PREVIEW:")
                print("-" * 40)
                print(f"Subject: {current_subject}")
                print(f"Message:")
                for line in current_message.split('\n'):
                    print(f"   {line}")
                print("-" * 40)
                
                while True:
                    action = input(f"\nContinue editing (e), use this version (u), or cancel (c)? ").strip().lower()
                    if action in ['e', 'edit']:
                        break  # Continue editing loop
                    elif action in ['u', 'use']:
                        return {
                            'subject': current_subject,
                            'message': current_message,
                            **{k: v for k, v in draft.items() if k not in ['subject', 'message']}
                        }
                    elif action in ['c', 'cancel']:
                        return None
                    else:
                        print(f"Please enter 'e' for edit, 'u' for use, or 'c' for cancel")
            
        except Exception as e:
            logger.error(f"❌ Message editing failed: {str(e)}")
            print(f"❌ Editing error: {str(e)}")
            return None
    
    def _edit_message_body(self, current_message: str) -> Optional[str]:
        """Edit the message body with line-by-line interface."""
        try:
            print(f"\n📄 CURRENT MESSAGE:")
            lines = current_message.split('\n')
            for i, line in enumerate(lines, 1):
                print(f"   {i:2d}: {line}")
            
            print(f"\nEditing options:")
            print(f"a. Add lines to the end")
            print(f"b. Replace entire message") 
            print(f"c. Cancel")
            
            choice = input(f"Choose option (a/b/c): ").strip().lower()
            
            if choice == 'a':
                print(f"\nAdd lines (type 'DONE' when finished):")
                additional_lines = []
                while True:
                    line = input(f"   + ")
                    if line.upper() == "DONE":
                        break
                    additional_lines.append(line)
                
                if additional_lines:
                    return current_message + "\n" + "\n".join(additional_lines)
                else:
                    return current_message
            
            elif choice == 'b':
                return self._write_new_message()
            
            else:
                return None
                
        except Exception as e:
            logger.error(f"❌ Message body editing failed: {str(e)}")
            return None
    
    def _write_new_message(self) -> Optional[str]:
        """Interface for writing a completely new message."""
        try:
            print(f"\n✍️  WRITE NEW MESSAGE:")
            print(f"   Enter your message line by line")
            print(f"   Type 'DONE' on a new line when finished")
            print(f"   Type 'CANCEL' to cancel")
            print(f"   " + "-"*40)
            
            message_lines = []
            
            while True:
                line = input(f"   ")
                
                if line.upper() == "DONE":
                    if message_lines:
                        return "\n".join(message_lines)
                    else:
                        print(f"   ⚠️  Message cannot be empty. Add content or type CANCEL.")
                        continue
                
                elif line.upper() == "CANCEL":
                    return None
                
                else:
                    message_lines.append(line)
            
        except Exception as e:
            logger.error(f"❌ New message writing failed: {str(e)}")
            return None
    
    def confirm_message_sending(self, final_message: Dict[str, Any], 
                              request_number: str) -> bool:
        """
        Final confirmation before sending a message.
        
        Args:
            final_message: Final message to be sent
            request_number: Request number for context
            
        Returns:
            True if user confirms sending, False otherwise
        """
        try:
            print(f"\n" + "="*60)
            print(f"📤 FINAL CONFIRMATION")
            print("="*60)
            print(f"🎯 Request: {request_number}")
            print(f"📌 Subject: {final_message.get('subject', '')}")
            print(f"📄 Message Preview:")
            print("-" * 40)
            
            for line in final_message.get('message', '').split('\n'):
                print(f"   {line}")
            
            print("-" * 40)
            print(f"📊 Character count: {len(final_message.get('message', ''))}")
            print(f"📊 Word count: {len(final_message.get('message', '').split())}")
            print("="*60)
            
            while True:
                confirm = input(f"\n📤 Send this message? (y/n): ").strip().lower()
                
                if confirm in ['y', 'yes']:
                    return True
                elif confirm in ['n', 'no']:
                    return False
                else:
                    print(f"Please enter 'y' for yes or 'n' for no")
            
        except Exception as e:
            logger.error(f"❌ Confirmation dialog failed: {str(e)}")
            return False
    
    def display_session_summary(self, session_stats: Dict[str, Any], 
                              detailed_results: List[Dict[str, Any]] = None) -> None:
        """
        Display summary of the entire message drafting session.
        
        Args:
            session_stats: Statistics about the session
            detailed_results: Optional detailed results for each request
        """
        try:
            print(f"\n" + "="*80)
            print(f"📊 MESSAGE DRAFTING SESSION SUMMARY")
            print("="*80)
            
            # Main statistics
            total_flagged = session_stats.get('total_flagged', 0)
            messages_sent = session_stats.get('messages_sent', 0)
            drafts_generated = session_stats.get('drafts_generated', 0)
            skipped = session_stats.get('skipped', 0)
            errors = session_stats.get('errors', 0)
            
            print(f"📈 RESULTS:")
            print(f"   Total requests flagged: {total_flagged}")
            print(f"   ✅ Messages sent: {messages_sent}")
            print(f"   📝 Drafts generated: {drafts_generated}")
            print(f"   ⏭️  Requests skipped: {skipped}")
            print(f"   ❌ Errors encountered: {errors}")
            
            # Success rate
            if total_flagged > 0:
                success_rate = (messages_sent / total_flagged) * 100
                print(f"   📊 Success rate: {success_rate:.1f}%")
            
            # Detailed breakdown if available
            if detailed_results:
                print(f"\n📋 DETAILED RESULTS:")
                
                sent_requests = [r for r in detailed_results if r.get('action') == 'sent']
                skipped_requests = [r for r in detailed_results if r.get('action') == 'skipped']
                failed_requests = [r for r in detailed_results if not r.get('success', True)]
                
                if sent_requests:
                    print(f"   ✅ SENT ({len(sent_requests)}):")
                    for req in sent_requests:
                        edited_note = " (edited)" if req.get('was_edited') else ""
                        print(f"      • {req.get('request_number', 'Unknown')}{edited_note}")
                
                if skipped_requests:
                    print(f"   ⏭️  SKIPPED ({len(skipped_requests)}):")
                    for req in skipped_requests:
                        reason = req.get('reason', 'No reason given')
                        print(f"      • {req.get('request_number', 'Unknown')}: {reason}")
                
                if failed_requests:
                    print(f"   ❌ FAILED ({len(failed_requests)}):")
                    for req in failed_requests:
                        error = req.get('error', 'Unknown error')
                        stage = req.get('stage', 'unknown')
                        print(f"      • {req.get('request_number', 'Unknown')}: {error} (at {stage})")
            
            # Next steps
            print(f"\n💡 NEXT STEPS:")
            if messages_sent > 0:
                print(f"   • {messages_sent} message{'s' if messages_sent != 1 else ''} sent - responses may arrive in your requests")
                print(f"   • Check your request dashboard for updates")
            
            if skipped > 0:
                print(f"   • {skipped} request{'s' if skipped != 1 else ''} still need{'s' if skipped == 1 else ''} attention")
                print(f"   • Run this workflow again later to address them")
            
            if errors > 0:
                print(f"   • {errors} error{'s' if errors != 1 else ''} occurred - check logs for details")
                print(f"   • Try running the workflow again for failed requests")
            
            if total_flagged == 0:
                print(f"   • All requests are up to date!")
                print(f"   • Continue monitoring for new changes")
            
            # Database records
            print(f"\n💾 AUDIT TRAIL:")
            print(f"   • All drafts and actions saved to database")
            print(f"   • Message history available for each request")
            print(f"   • Use monitoring statistics to track patterns")
            
            print("="*80)
            
        except Exception as e:
            logger.error(f"❌ Failed to display session summary: {str(e)}")
            print(f"❌ Error displaying summary: {str(e)}")
    
    def display_error_message(self, error: str, context: str = None) -> None:
        """
        Display a formatted error message to the user.
        
        Args:
            error: Error message to display
            context: Optional context about when the error occurred
        """
        print(f"\n❌ ERROR")
        if context:
            print(f"   Context: {context}")
        print(f"   Message: {error}")
        print(f"   Please try again or contact support if the issue persists.")
    
    def display_progress_indicator(self, current: int, total: int, 
                                 current_item: str = None) -> None:
        """
        Display progress indicator for multi-request processing.
        
        Args:
            current: Current item number
            total: Total number of items
            current_item: Optional description of current item
        """
        try:
            percentage = (current / total) * 100 if total > 0 else 0
            progress_bar = "█" * int(percentage // 5) + "░" * (20 - int(percentage // 5))
            
            item_text = f" - {current_item}" if current_item else ""
            print(f"\n📊 Progress: [{progress_bar}] {percentage:.1f}% ({current}/{total}){item_text}")
            
        except Exception as e:
            logger.error(f"❌ Progress indicator error: {str(e)}")
            print(f"\n📊 Processing {current}/{total}...")