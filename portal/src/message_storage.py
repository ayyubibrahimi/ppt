import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import hashlib

logger = logging.getLogger(__name__)


class MessageStorage:
    """
    Handle all database operations for message drafts and audit trail.
    Provides clean interface for storing, updating, and retrieving message data.
    """
    
    def __init__(self, db):
        """
        Initialize message storage with database connection.
        
        Args:
            db: SupabaseIntegration instance
        """
        self.db = db
        self.supabase = db.supabase if db else None
        
        if not self.supabase:
            raise ValueError("Database connection is required for MessageStorage")
        
        logger.info("✅ MessageStorage initialized")
    
    def save_message_draft(self, request_id: str, subject: str, message: str,
                      message_type: str = 'contextual',
                      change_context: Dict[str, Any] = None,
                      initial_status: str = 'drafted',
                      user_approved: bool = False) -> Optional[str]:
        """
        Save a message draft to the database.

        If a pending draft already exists for this request, it will be updated
        instead of creating a new draft. This prevents duplicate drafts.

        Args:
            request_id: ID of the request
            subject: Subject line
            message: Message body
            message_type: Type of message (contextual, etc.)
            change_context: Context about what triggered this draft
            initial_status: Initial status for the draft
            user_approved: Whether the draft is auto-approved for sending (default: False)
        """
        try:
            # Check for existing pending draft for this request
            # Look for drafts that are still active (not sent, cancelled, or skipped)
            existing_result = self.supabase.table('message_drafts').select('id').eq(
                'request_id', request_id
            ).in_(
                'draft_status', ['drafted', 'pending_approval', 'edited']
            ).execute()

            existing_draft = existing_result.data[0] if existing_result.data else None

            if existing_draft:
                # Update the existing draft instead of creating a new one
                existing_draft_id = existing_draft['id']
                update_data = {
                    'draft_subject': subject if subject else None,
                    'draft_message': message if message else None,
                    'message_type': message_type,
                    'change_context': change_context or {},
                    'draft_status': initial_status,
                    'user_approved': user_approved,
                    'updated_at': datetime.now().isoformat()
                }

                result = self.supabase.table('message_drafts').update(update_data).eq(
                    'id', existing_draft_id
                ).execute()

                if result.data and len(result.data) > 0:
                    logger.info(f"✅ Existing draft updated with ID: {existing_draft_id}, status: {initial_status}, user_approved: {user_approved}")
                    return existing_draft_id
                else:
                    logger.error(f"❌ Failed to update existing draft {existing_draft_id}")
                    return None
            else:
                # No existing draft found, create a new one
                draft_data = {
                    'request_id': request_id,
                    'draft_subject': subject if subject else None,
                    'draft_message': message if message else None,
                    'message_type': message_type,
                    'change_context': change_context or {},
                    'draft_status': initial_status,
                    'user_approved': user_approved,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }

                result = self.supabase.table('message_drafts').insert(draft_data).execute()

                if result.data and len(result.data) > 0:
                    draft_id = result.data[0]['id']
                    logger.info(f"✅ New message draft saved with ID: {draft_id}, status: {initial_status}, user_approved: {user_approved}")
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
    
    def update_draft_content(self, draft_id: str, updated_draft: Dict[str, str]) -> bool:
        """
        Update the content of a message draft (when user edits).
        
        Args:
            draft_id: ID of the draft to update
            updated_draft: Dict with 'subject' and 'message' keys
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'draft_subject': updated_draft.get('subject', '')[:500],
                'draft_message': updated_draft.get('message', '')[:5000],
                'draft_status': 'edited',
                'user_approved': True,  # User edited means they're engaging with it
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.supabase.table('message_drafts').update(update_data).eq('id', draft_id).execute()
            
            if result.data:
                logger.info(f"✅ Draft {draft_id} content updated")
                return True
            else:
                logger.warning(f"⚠️ No data returned when updating draft content {draft_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to update draft content: {str(e)}")
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
    
    def get_draft_by_id(self, draft_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific message draft by ID.
        
        Args:
            draft_id: ID of the draft
            
        Returns:
            Draft record or None if not found
        """
        try:
            result = self.supabase.table('message_drafts').select('*').eq('id', draft_id).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            else:
                logger.warning(f"⚠️ Draft {draft_id} not found")
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to get draft by ID: {str(e)}")
            return None
    
    def get_recent_drafts(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent message drafts for a user.
        
        Args:
            user_id: ID of the user
            days: How many days back to look
            
        Returns:
            List of recent message drafts with request information
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff_date.isoformat()
            
            # Join with requests table to get user-specific drafts
            result = self.supabase.table('message_drafts').select(
                '*, requests!inner(user_id, request_number, portal_name)'
            ).eq('requests.user_id', user_id).gte('created_at', cutoff_iso).order(
                'created_at', desc=True
            ).execute()
            
            drafts = result.data or []
            logger.info(f"📋 Retrieved {len(drafts)} recent drafts for user")
            return drafts
            
        except Exception as e:
            logger.error(f"❌ Failed to get recent drafts: {str(e)}")
            return []
    
    def get_draft_statistics(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get statistics about message drafting activity.
        
        Args:
            user_id: ID of the user
            days: How many days back to analyze
            
        Returns:
            Dict with drafting statistics
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff_date.isoformat()
            
            # Get all drafts for the user in the time period
            result = self.supabase.table('message_drafts').select(
                '*, requests!inner(user_id, request_number)'
            ).eq('requests.user_id', user_id).gte('created_at', cutoff_iso).execute()
            
            drafts = result.data or []
            
            # Calculate statistics
            total_drafts = len(drafts)
            sent_count = len([d for d in drafts if d['draft_status'] == 'sent'])
            edited_count = len([d for d in drafts if d['draft_status'] == 'edited'])
            cancelled_count = len([d for d in drafts if d['draft_status'] == 'cancelled'])
            skipped_count = len([d for d in drafts if d['draft_status'] == 'skipped'])
            
            # Message type breakdown
            type_counts = {}
            for draft in drafts:
                msg_type = draft.get('message_type', 'unknown')
                type_counts[msg_type] = type_counts.get(msg_type, 0) + 1
            
            # Success rate calculation
            success_rate = (sent_count / total_drafts * 100) if total_drafts > 0 else 0
            
            stats = {
                'period_days': days,
                'total_drafts': total_drafts,
                'sent_count': sent_count,
                'edited_count': edited_count,
                'cancelled_count': cancelled_count,
                'skipped_count': skipped_count,
                'success_rate': round(success_rate, 1),
                'message_type_breakdown': type_counts,
                'most_common_type': max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else None
            }
            
            logger.info(f"📊 Generated draft statistics: {stats['success_rate']}% success rate")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Failed to get draft statistics: {str(e)}")
            return {
                'period_days': days,
                'total_drafts': 0,
                'sent_count': 0,
                'edited_count': 0,
                'cancelled_count': 0,
                'skipped_count': 0,
                'success_rate': 0,
                'message_type_breakdown': {},
                'most_common_type': None
            }
    
    def cleanup_old_drafts(self, days_old: int = 90) -> Dict[str, Any]:
        """
        Clean up old draft records (for maintenance).
        
        Args:
            days_old: Delete drafts older than this many days
            
        Returns:
            Dict with cleanup results
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            cutoff_iso = cutoff_date.isoformat()
            
            # First, count what we're about to delete
            count_result = self.supabase.table('message_drafts').select(
                'id', count='exact'
            ).lt('created_at', cutoff_iso).execute()
            
            old_count = count_result.count or 0
            
            if old_count == 0:
                logger.info("🗑️ No old drafts to clean up")
                return {
                    'success': True,
                    'deleted_count': 0,
                    'message': 'No old drafts found'
                }
            
            # Delete old drafts
            delete_result = self.supabase.table('message_drafts').delete().lt(
                'created_at', cutoff_iso
            ).execute()
            
            deleted_count = len(delete_result.data) if delete_result.data else 0
            
            logger.info(f"🗑️ Cleaned up {deleted_count} old message drafts")
            
            return {
                'success': True,
                'deleted_count': deleted_count,
                'cutoff_date': cutoff_iso,
                'message': f'Deleted {deleted_count} drafts older than {days_old} days'
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old drafts: {str(e)}")
            return {
                'success': False,
                'deleted_count': 0,
                'error': str(e)
            }
    
    def get_pending_drafts(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get drafts that are pending user action (drafted but not sent/cancelled/skipped).
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of pending draft records
        """
        try:
            result = self.supabase.table('message_drafts').select(
                '*, requests!inner(user_id, request_number, portal_name, current_status)'
            ).eq('requests.user_id', user_id).in_(
                'draft_status', ['drafted', 'edited']
            ).order('created_at', desc=True).execute()
            
            pending = result.data or []
            logger.info(f"📋 Found {len(pending)} pending drafts for user")
            return pending
            
        except Exception as e:
            logger.error(f"❌ Failed to get pending drafts: {str(e)}")
            return []
    
    def mark_draft_as_reviewed(self, draft_id: str, user_approved: bool, 
                              notes: str = None) -> bool:
        """
        Mark a draft as reviewed by the user.
        
        Args:
            draft_id: ID of the draft
            user_approved: Whether user approved the draft
            notes: Optional notes about the review
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'user_approved': user_approved,
                'updated_at': datetime.now().isoformat()
            }
            
            if notes:
                # Add notes to change_context
                draft = self.get_draft_by_id(draft_id)
                if draft:
                    change_context = draft.get('change_context', {})
                    change_context['review_notes'] = notes
                    update_data['change_context'] = change_context
            
            result = self.supabase.table('message_drafts').update(update_data).eq('id', draft_id).execute()
            
            if result.data:
                logger.info(f"✅ Draft {draft_id} marked as reviewed (approved: {user_approved})")
                return True
            else:
                logger.warning(f"⚠️ Failed to mark draft {draft_id} as reviewed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to mark draft as reviewed: {str(e)}")
            return False
    
    def get_drafts_by_status(self, user_id: str, status: str) -> List[Dict[str, Any]]:
        """
        Get all drafts with a specific status for a user.
        
        Args:
            user_id: ID of the user
            status: Draft status to filter by
            
        Returns:
            List of draft records with the specified status
        """
        try:
            result = self.supabase.table('message_drafts').select(
                '*, requests!inner(user_id, request_number, portal_name)'
            ).eq('requests.user_id', user_id).eq('draft_status', status).order(
                'created_at', desc=True
            ).execute()
            
            drafts = result.data or []
            logger.info(f"📋 Found {len(drafts)} drafts with status '{status}'")
            return drafts
            
        except Exception as e:
            logger.error(f"❌ Failed to get drafts by status: {str(e)}")
            return []
    
    def get_most_recent_draft(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent draft for a request.

        Args:
            request_id: ID of the request

        Returns:
            Most recent draft record or None if no drafts exist
        """
        try:
            result = self.supabase.table('message_drafts').select('*').eq(
                'request_id', request_id
            ).order('created_at', desc=True).limit(1).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            else:
                return None

        except Exception as e:
            logger.error(f"❌ Failed to get most recent draft: {str(e)}")
            return None

    def compute_analysis_hash(self, latest_analysis: Dict[str, Any]) -> str:
        """
        Compute a stable hash of the latest_analysis JSONB content.

        Args:
            latest_analysis: The latest_analysis JSONB field from requests table

        Returns:
            SHA256 hash of the analysis content
        """
        try:
            # Sort keys to ensure consistent hashing
            analysis_str = json.dumps(latest_analysis, sort_keys=True)
            return hashlib.sha256(analysis_str.encode()).hexdigest()
        except Exception as e:
            logger.error(f"❌ Failed to compute analysis hash: {str(e)}")
            return ""

    def should_create_new_draft(self, request_id: str, force_regenerate: bool = False) -> bool:
        """
        Determine if a new draft should be created based on analysis content changes.

        This prevents duplicate drafts by comparing the hash of the current request's
        latest_analysis against the hash stored in the most recent draft.

        Returns True if:
        - force_regenerate is True (bypass hash check), OR
        - No draft exists for this request, OR
        - Request's latest_analysis has changed since the most recent draft, OR
        - Most recent draft doesn't have a stored analysis hash (backward compatibility)

        Args:
            request_id: ID of the request
            force_regenerate: If True, bypass hash check and always create new draft

        Returns:
            True if a new draft should be created, False otherwise
        """
        try:
            # If force regeneration is enabled, always create new draft
            if force_regenerate:
                logger.info(f"✅ Force regenerate enabled - creating new draft")
                return True

            # Otherwise, proceed with normal hash-based deduplication
            # Get most recent draft
            recent_draft = self.get_most_recent_draft(request_id)

            if not recent_draft:
                logger.info(f"✅ No existing draft - creating new draft")
                return True

            # Get current request's latest_analysis
            request_result = self.supabase.table('requests').select(
                'latest_analysis'
            ).eq('id', request_id).execute()

            if not request_result.data or len(request_result.data) == 0:
                logger.warning(f"⚠️ Request {request_id} not found")
                return False

            # Get the analysis hash from the most recent draft (if stored)
            draft_analysis_hash = recent_draft.get('change_context', {}).get('analysis_content_hash', '')

            # Hash current analysis
            current_analysis = request_result.data[0].get('latest_analysis', {})
            current_hash = self.compute_analysis_hash(current_analysis)

            if not draft_analysis_hash:
                # Old draft without hash - create new draft for backward compatibility
                logger.info(f"✅ Existing draft has no hash - creating new draft")
                return True

            if current_hash != draft_analysis_hash:
                logger.info(f"✅ Analysis content changed since last draft - creating new draft")
                return True
            else:
                logger.info(f"⏭️ Skipping draft - analysis unchanged since last draft")
                return False

        except Exception as e:
            logger.error(f"❌ Failed to check if new draft should be created: {str(e)}")
            # On error, default to creating a draft (safer than skipping)
            return True

    def export_draft_history(self, user_id: str, days: int = 30) -> Optional[str]:
        """
        Export draft history as JSON for backup/analysis.
        
        Args:
            user_id: ID of the user
            days: How many days back to export
            
        Returns:
            JSON string of draft history or None if failed
        """
        try:
            drafts = self.get_recent_drafts(user_id, days)
            
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'user_id': user_id,
                'period_days': days,
                'total_drafts': len(drafts),
                'drafts': drafts
            }
            
            json_export = json.dumps(export_data, indent=2, default=str)
            logger.info(f"📤 Exported {len(drafts)} drafts to JSON")
            return json_export
            
        except Exception as e:
            logger.error(f"❌ Failed to export draft history: {str(e)}")
            return None