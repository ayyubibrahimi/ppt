"""
document_download_coordinator.py

Main orchestrator for automated document downloads and Google Drive uploads.
SIMPLIFIED: Downloads ALL documents for a request when classifier says ready.
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import tempfile
import shutil
from datetime import datetime

from document_classifier import DocumentClassifier
from google_drive_manager import GoogleDriveManager
from nextrequest_scraper import NextRequest
from supabase_integration import SupabaseIntegration
from document_processor import DocumentProcessor

logger = logging.getLogger(__name__)


class DocumentDownloadCoordinator:
    """
    Coordinates automated document downloads and uploads to Google Drive.
    """
    
    def __init__(self, llm_client, supabase_db: SupabaseIntegration):
        """
        Initialize coordinator with dependencies.

        Args:
            llm_client: LLM client (gpt_4o from llm.py)
            supabase_db: SupabaseIntegration instance
        """
        self.llm_client = llm_client
        self.db = supabase_db
        self.classifier = DocumentClassifier(llm_client)
        self.drive_manager = GoogleDriveManager(supabase_db)
        self.doc_processor = DocumentProcessor(supabase_db)
    
    def process_flagged_requests(self, user_id: str = None) -> Dict[str, Any]:
        """
        Main entry point: Process all flagged requests for document downloads.
        
        Args:
            user_id: Optional specific user ID to process, otherwise processes all eligible users
            
        Returns:
            Dict with processing results and statistics
        """
        try:
            logger.info("🚀 Starting document download coordinator")
            
            # Get flagged requests where user has Google Drive enabled
            eligible_requests = self.db.get_requests_needing_document_check(user_id)
            
            if not eligible_requests:
                logger.info("📭 No eligible requests found for document download")
                return {
                    'success': True,
                    'message': 'No eligible requests to process',
                    'processed': 0,
                    'documents_downloaded': 0,
                    'documents_uploaded': 0
                }
            
            logger.info(f"📊 Found {len(eligible_requests)} eligible requests to check")
            
            # Classify which requests have documents ready
            classifications = self._classify_requests(eligible_requests)
            
            # Filter to only requests with documents ready
            ready_requests = [
                (req, classification) 
                for req, classification in zip(eligible_requests, classifications)
                if classification.documents_ready
            ]
            
            if not ready_requests:
                logger.info("📭 No requests have documents ready for download")
                return {
                    'success': True,
                    'message': 'No documents ready for download',
                    'requests_checked': len(eligible_requests),
                    'requests_with_documents_ready': 0,
                    'processed': 0,
                    'documents_downloaded': 0,
                    'documents_uploaded': 0
                }
            
            logger.info(f"📄 {len(ready_requests)} requests have documents ready")
            
            # Process each request with documents ready
            results = []
            total_downloaded = 0
            total_uploaded = 0
            
            for request_data, classification in ready_requests:
                result = self._process_single_request(request_data, classification)
                results.append(result)
                
                if result['success']:
                    total_downloaded += result.get('documents_downloaded', 0)
                    total_uploaded += result.get('documents_uploaded', 0)
            
            # Summary
            successful = sum(1 for r in results if r['success'])
            failed = len(results) - successful
            
            logger.info(f"✅ Document download coordinator complete:")
            logger.info(f"   Requests checked: {len(eligible_requests)}")
            logger.info(f"   Requests with documents ready: {len(ready_requests)}")
            logger.info(f"   Requests processed: {successful}/{len(ready_requests)}")
            logger.info(f"   Total documents downloaded: {total_downloaded}")
            logger.info(f"   Total documents uploaded to Drive: {total_uploaded}")

            # Post-processing: OCR cleanup, summarization, and classification
            logger.info("")
            logger.info("🔄 Starting post-processing (OCR cleanup + summarization + classification)...")

            # Step 1: Catch any documents that need OCR (shouldn't be many since we OCR inline)
            ocr_stats = self.doc_processor.process_pending_ocr(user_id=user_id)
            if ocr_stats['processed'] > 0:
                logger.info(f"   📄 OCR cleanup: {ocr_stats['successful']}/{ocr_stats['processed']} successful")

            # Step 2: Summarize documents that have completed OCR
            summary_stats = self.doc_processor.process_pending_summaries(user_id=user_id)
            if summary_stats['processed'] > 0:
                logger.info(f"   📝 Summarization: {summary_stats['successful']}/{summary_stats['processed']} successful")

            # Step 3: Classify documents against FOIA requests
            classification_stats = self.doc_processor.process_pending_classifications(user_id=user_id)
            if classification_stats['processed'] > 0:
                logger.info(f"   🏷️  Classification: {classification_stats['successful']}/{classification_stats['processed']} successful")

            logger.info("✅ Post-processing complete")

            return {
                'success': True,
                'requests_checked': len(eligible_requests),
                'requests_with_documents_ready': len(ready_requests),
                'requests_processed': successful,
                'requests_failed': failed,
                'documents_downloaded': total_downloaded,
                'documents_uploaded': total_uploaded,
                'ocr_stats': ocr_stats,
                'summarization_stats': summary_stats,
                'classification_stats': classification_stats,
                'details': results
            }
            
        except Exception as e:
            logger.error(f"❌ Document download coordinator failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'processed': 0
            }
    
    def _classify_requests(self, requests: List[Dict[str, Any]]) -> List:
        """
        Classify all requests to determine which have documents ready.
        
        Args:
            requests: List of request records
            
        Returns:
            List of DocumentClassification results
        """
        logger.info(f"🔍 Classifying {len(requests)} requests")
        
        classifications = self.classifier.classify_batch(requests)
        
        ready_count = sum(1 for c in classifications if c.documents_ready)
        logger.info(f"📊 Classification complete: {ready_count}/{len(requests)} have documents ready")
        
        return classifications
    
    def _process_single_request(
        self,
        request_data: Dict[str, Any],
        classification: Any
    ) -> Dict[str, Any]:
        """
        Process a single request: download ALL documents and upload to Drive.

        Args:
            request_data: Request record from database
            classification: DocumentClassification result (not currently used, kept for future enhancement)

        Returns:
            Dict with processing results
        """
        request_id = request_data['id']
        request_number = request_data['request_number']
        user_id = request_data['user_id']
        portal_name = request_data['portal_name']
        portal_type = request_data.get('portal_type', 'portal')

        logger.info(f"🔄 Processing request {request_number} (type: {portal_type})")

        result = {
            'request_id': request_id,
            'request_number': request_number,
            'success': False,
            'documents_downloaded': 0,
            'documents_uploaded': 0,
            'errors': []
        }

        try:
            # Initialize Google Drive for user
            if not self.drive_manager.initialize_for_user(user_id):
                error_msg = "Failed to initialize Google Drive"
                logger.error(f"❌ {error_msg} for request {request_number}")
                result['errors'].append(error_msg)
                return result

            # Get user's Google account email for file permissions
            user_google_email = self._get_user_google_email(user_id)
            if not user_google_email:
                error_msg = "No Google account email found for user"
                logger.error(f"❌ {error_msg} for request {request_number}")
                result['errors'].append(error_msg)
                return result

            # ====================================================================
            # ROUTE BASED ON PORTAL TYPE: Email vs Portal
            # ====================================================================
            if portal_type == 'email':
                # Email-based request: Download attachments from Gmail thread
                return self._process_email_attachments(
                    request_data=request_data,
                    user_google_email=user_google_email,
                    result=result
                )

            # ====================================================================
            # PORTAL-BASED REQUEST: Continue with existing logic
            # ====================================================================

            # Get portal credentials to login
            credentials = self._get_portal_credentials(user_id, portal_name)

            if not credentials:
                error_msg = "No portal credentials found"
                logger.error(f"❌ {error_msg} for request {request_number}")
                result['errors'].append(error_msg)
                return result

            # ====================================================================
            # STEP 1: CHECK WHAT ALREADY EXISTS - Granular approach
            # ====================================================================
            existing_docs = self.db.get_downloads_for_request(request_id)
            already_in_drive = {
                doc['document_title']: doc
                for doc in existing_docs
                if doc.get('google_drive_file_id')
            }

            if already_in_drive:
                logger.info(f"📁 {len(already_in_drive)} documents already in Google Drive, will skip downloading those")
            else:
                logger.info(f"📥 No documents in Drive yet, will download from portal")

            # Initialize download_results to None (will be populated if download happens)
            download_results = None

            # Download only if needed
            if len(already_in_drive) == 0:
                # Download ALL documents from portal
                download_results = self._download_all_documents(
                    portal_name=portal_name,
                    request_number=request_number,
                    username=credentials.get('username'),
                    password=credentials.get('password')
                )

                if not download_results['success']:
                    error_msg = f"Download failed: {download_results.get('error', 'Unknown error')}"
                    logger.error(f"❌ {error_msg}")
                    result['errors'].append(error_msg)
                    return result

                downloaded_files = download_results['downloaded_files']
                result['documents_downloaded'] = len(downloaded_files)
            else:
                # All docs already in Drive, skip download
                logger.info(f"⏭️ All documents already in Drive, skipping portal download")
                downloaded_files = []
                result['documents_downloaded'] = 0
                result['skipped_download'] = len(already_in_drive)

            # Save download records to database FIRST (needed for OCR)
            for file_info in downloaded_files:
                download_record_id = self.db.save_document_download_record(
                    request_id=request_id,
                    user_id=user_id,
                    portal_name=portal_name,
                    document_metadata={
                        'title': file_info['filename'],
                        'document_id': 'bulk_download',
                    }
                )

                if download_record_id:
                    # Mark as downloaded and save local path
                    self.db.update_document_download_status(
                        download_record_id,
                        'completed'
                    )
                    # Update with local file path for OCR
                    self.db.supabase.table('document_downloads').update({
                        'local_file_path': file_info['local_path'],
                        'file_size_bytes': file_info['size_bytes']
                    }).eq('id', download_record_id).execute()

                    # Add download_record_id to file_info for OCR processing
                    file_info['download_record_id'] = download_record_id

            # ====================================================================
            # STEP 2: OCR PROCESSING - Check if already completed
            # ====================================================================
            logger.info(f"🔍 Starting OCR processing for {len(downloaded_files)} documents")
            ocr_processed = 0
            ocr_skipped = 0
            ocr_already_done = 0

            for file_info in downloaded_files:
                if not file_info.get('download_record_id'):
                    logger.warning(f"⚠️ No download_record_id for {file_info['filename']}, skipping OCR")
                    continue

                # Only OCR PDFs
                if file_info['filename'].lower().endswith('.pdf'):
                    download_id = file_info['download_record_id']

                    # GRANULAR CHECK: Is OCR already completed?
                    doc_record = self.db.get_document_with_data(download_id)
                    if doc_record and doc_record.get('ocr_status') == 'completed':
                        logger.info(f"⏭️ OCR already completed for {file_info['filename']}, skipping")
                        ocr_already_done += 1
                        continue

                    # OCR needed (either not done or failed)
                    success = self.doc_processor.ocr_document(
                        download_id=download_id,
                        pdf_path=file_info['local_path']
                    )
                    if success:
                        ocr_processed += 1
                    else:
                        logger.warning(f"⚠️ OCR failed for {file_info['filename']}")
                else:
                    ocr_skipped += 1
                    logger.debug(f"⏭️ Skipping OCR for non-PDF: {file_info['filename']}")

            logger.info(f"✅ OCR complete: {ocr_processed} processed, {ocr_already_done} already done, {ocr_skipped} skipped (non-PDF)")

            # Check database for already uploaded documents to avoid duplicates
            existing_uploads = self.db.get_downloads_for_request(request_id)
            existing_filenames = set(
                upload.get('document_title') for upload in existing_uploads 
                if upload.get('download_status') == 'uploaded_to_drive'
            )
            
            # Filter out already uploaded files
            files_to_upload = [
                f for f in downloaded_files 
                if f['filename'] not in existing_filenames
            ]
            
            if not files_to_upload:
                logger.info(f"✅ All {len(downloaded_files)} documents already uploaded for {request_number}")
                result['success'] = True
                result['documents_uploaded'] = 0

                # Cleanup temp files (if download happened)
                if download_results:
                    self._cleanup_temp_files(download_results.get('temp_dir'))
                return result
            
            logger.info(f"📤 Uploading {len(files_to_upload)} new documents (skipping {len(existing_filenames)} already uploaded)")

            # Upload new files to Google Drive
            upload_results = self._upload_to_drive(request_number, files_to_upload, user_google_email)
            
            if not upload_results['success']:
                error_msg = f"Upload failed: {upload_results.get('error', 'Unknown error')}"
                logger.warning(f"⚠️ {error_msg}")
                result['errors'].append(error_msg)
            else:
                result['documents_uploaded'] = upload_results['success_count']

                # Update existing records with Google Drive info (records already created during download)
                for uploaded_file in upload_results['successful_uploads']:
                    # Find the matching download record
                    recent_downloads = self.db.get_downloads_for_request(request_id)
                    matching_download = next(
                        (d for d in recent_downloads if d.get('document_title') == uploaded_file['filename']),
                        None
                    )

                    if matching_download:
                        self.db.update_document_download_status(
                            matching_download['id'],
                            'uploaded_to_drive',
                            google_drive_file_id=uploaded_file['file_id'],
                            google_drive_folder_id=upload_results['folder_id'],
                            google_drive_web_link=uploaded_file.get('web_link')
                        )

                        # Set classification status to pending now that file is in Google Drive
                        # For PDFs: OCR already completed inline, ready for classification
                        # For CSV/XLSX: No OCR needed, ready for classification
                        self.db.set_classification_status(matching_download['id'], 'pending')
                        logger.info(f"🏷️  Document {matching_download['id']} marked as ready for classification")

            # Cleanup temporary files (if download happened)
            if download_results:
                self._cleanup_temp_files(download_results.get('temp_dir'))

            # Mark as successful if we downloaded anything
            result['success'] = result['documents_downloaded'] > 0
            
            logger.info(f"✅ Processed request {request_number}: "
                       f"{result['documents_downloaded']} downloaded, "
                       f"{result['documents_uploaded']} uploaded")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to process request {request_number}: {str(e)}")
            result['errors'].append(str(e))
            return result
    
    def _get_user_google_email(self, user_id: str) -> Optional[str]:
        """
        Get user's Google account email from database.

        Args:
            user_id: User ID

        Returns:
            Google account email if found, None otherwise
        """
        try:
            user_result = self.db.supabase.table('users').select('google_account_email').eq(
                'id', user_id
            ).execute()

            if not user_result.data:
                logger.warning(f"⚠️ No user found with ID: {user_id}")
                return None

            google_email = user_result.data[0].get('google_account_email')

            if not google_email:
                logger.warning(f"⚠️ User {user_id} has no Google account email stored")
                return None

            logger.info(f"✅ Found Google email for user {user_id}")
            return google_email

        except Exception as e:
            logger.error(f"❌ Failed to get user Google email: {str(e)}")
            return None

    def _get_portal_credentials(self, user_id: str, portal_name: str) -> Optional[Dict[str, str]]:
        """
        Get portal credentials for a user.
        """
        try:
            logger.info(f"🔍 Looking for credentials: user_id={user_id}, portal={portal_name}")
            
            # Step 1: Find the portal_id that matches this portal URL
            portal_result = self.db.supabase.table('portals').select('id').eq(
                'portal_url', portal_name
            ).execute()
            
            if not portal_result.data:
                logger.warning(f"⚠️ No portal found with URL: {portal_name}")
                return None
            
            portal_id = portal_result.data[0]['id']
            logger.info(f"✅ Found portal_id: {portal_id}")
            
            # Step 2: Get credentials for this user + portal combination
            creds_result = self.db.supabase.table('user_portal_credentials').select(
                'encrypted_username, encrypted_password'
            ).eq('user_id', user_id).eq('portal_id', portal_id).eq('is_active', True).execute()
            
            if not creds_result.data:
                logger.warning(f"⚠️ No active credentials found for user {user_id} on portal {portal_id}")
                return None
            
            cred = creds_result.data[0]
            logger.info(f"✅ Found credentials for user {user_id}")
            
            return {
                'username': cred['encrypted_username'],
                'password': cred['encrypted_password']
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get portal credentials: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def _download_all_documents(
        self,
        portal_name: str,
        request_number: str,
        username: str,
        password: str
    ) -> Dict[str, Any]:
        """
        Download ALL documents for a request from NextRequest portal.
        
        Args:
            portal_name: Portal URL
            request_number: Request number (e.g., "25-704")
            username: Portal username
            password: Portal password
            
        Returns:
            Dict with download results
        """
        try:
            logger.info(f"📥 Downloading ALL documents for request {request_number}")
            
            # Create temporary directory for downloads
            temp_dir = tempfile.mkdtemp(prefix='foia_downloads_')
            logger.info(f"📁 Using temp directory: {temp_dir}")
            
            # Initialize NextRequest scraper with authentication
            scraper = NextRequest(
                url=portal_name,
                request_id=request_number,
                outputdir=temp_dir,
                username=username,
                password=password
            )
            
            # Download ALL documents for this request
            scraper.download_all_documents()
            
            # Collect all downloaded files
            downloaded_files = []
            temp_path = Path(temp_dir)
            
            for file_path in temp_path.rglob('*'):
                if file_path.is_file():
                    downloaded_files.append({
                        'local_path': str(file_path),
                        'filename': file_path.name,
                        'size_bytes': file_path.stat().st_size
                    })
            
            if not downloaded_files:
                return {
                    'success': False,
                    'error': 'No documents were downloaded'
                }
            
            logger.info(f"✅ Downloaded {len(downloaded_files)} documents")
            
            return {
                'success': True,
                'downloaded_files': downloaded_files,
                'temp_dir': temp_dir,
                'total_downloaded': len(downloaded_files)
            }
            
        except Exception as e:
            logger.error(f"❌ Document download failed: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e)
            }

    def _process_email_attachments(
        self,
        request_data: Dict[str, Any],
        user_google_email: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process email attachments for an email-based request.
        Downloads attachments from Gmail thread, processes through OCR/classification,
        and uploads to Google Drive.

        Args:
            request_data: Request record from database
            user_google_email: User's Google account email for Drive permissions
            result: Result dict to populate

        Returns:
            Dict with processing results
        """
        from mcp_gmail_client import MCPGmailClient
        import tempfile
        import shutil

        request_id = request_data['id']
        request_number = request_data['request_number']
        gmail_thread_id = request_data.get('gmail_thread_id')

        if not gmail_thread_id:
            error_msg = "No gmail_thread_id found for email request"
            logger.error(f"❌ {error_msg}")
            result['errors'].append(error_msg)
            return result

        try:
            logger.info(f"📧 Processing email attachments for thread {gmail_thread_id}")

            # Create temporary directory for downloads
            temp_dir = tempfile.mkdtemp(prefix='email_attachments_')
            logger.info(f"📁 Using temp directory: {temp_dir}")

            # Get all messages in thread using subject search (same as monitoring)
            # NOTE: search_thread() doesn't work reliably, use search by subject instead
            email_subject = request_data.get('email_subject')
            if not email_subject:
                error_msg = "No email_subject found for email request"
                logger.error(f"❌ {error_msg}")
                result['errors'].append(error_msg)
                shutil.rmtree(temp_dir)
                return result

            with MCPGmailClient() as mcp:
                # Search by subject
                logger.info(f"🔍 Searching by subject: {email_subject}")
                search_results = mcp.search_emails(f'subject:"{email_subject}"', max_results=50)
                logger.info(f"📧 Found {len(search_results)} emails from search")

                # Read each email to get full details including thread_id
                messages = []
                for email_summary in search_results:
                    try:
                        email_id = email_summary.get('id')
                        full_email = mcp.read_email(email_id)

                        if full_email and full_email.get('thread_id') == gmail_thread_id:
                            full_email['id'] = email_id  # Ensure ID is present
                            messages.append(full_email)
                    except Exception as e:
                        logger.warning(f"Could not read email {email_id}: {e}")
                        continue

                logger.info(f"📨 Found {len(messages)} messages in thread {gmail_thread_id} (from {len(search_results)} search results)")

                downloaded_files = []

                for message in messages:
                    message_id = message['id']

                    # Check if message already processed
                    if self._is_message_processed(request_id, message_id):
                        logger.debug(f"⏭️ Message {message_id} already processed, skipping")
                        continue

                    # Download attachments from this message
                    logger.info(f"📎 Checking message {message_id} for attachments")
                    attachments = mcp.get_attachments(message_id, save_path=temp_dir)

                    if not attachments:
                        # No attachments in this message, mark as processed
                        self._mark_message_processed(request_id, message_id)
                        logger.debug(f"No attachments in message {message_id}")
                        continue

                    logger.info(f"📥 Downloaded {len(attachments)} attachment(s) from message {message_id}")

                    # Add attachments to downloaded_files list
                    for attachment in attachments:
                        downloaded_files.append({
                            'local_path': attachment['filepath'],
                            'filename': attachment['filename'],
                            'size_bytes': attachment['size'],
                            'mime_type': attachment.get('mime_type', 'application/octet-stream')
                        })

                    # Mark message as processed
                    self._mark_message_processed(request_id, message_id)

            if not downloaded_files:
                logger.info(f"📭 No new attachments found in thread {gmail_thread_id}")
                result['success'] = True
                result['documents_downloaded'] = 0
                shutil.rmtree(temp_dir)
                return result

            logger.info(f"✅ Downloaded {len(downloaded_files)} attachment(s) total")
            result['documents_downloaded'] = len(downloaded_files)

            # ====================================================================
            # SAVE TO DATABASE AND PROCESS
            # ====================================================================

            # Save download records to database
            for file_info in downloaded_files:
                download_record_id = self.db.save_document_download_record(
                    request_id=request_id,
                    user_id=request_data['user_id'],
                    portal_name=request_data['portal_name'],
                    document_metadata={
                        'title': file_info['filename'],
                        'document_id': 'email_attachment',
                    }
                )

                if download_record_id:
                    # Mark as downloaded and save local path
                    self.db.update_document_download_status(
                        download_record_id,
                        'completed'
                    )
                    self.db.supabase.table('document_downloads').update({
                        'local_file_path': file_info['local_path'],
                        'file_size_bytes': file_info['size_bytes']
                    }).eq('id', download_record_id).execute()

                    # Add download_record_id for OCR processing
                    file_info['download_record_id'] = download_record_id

            # ====================================================================
            # OCR PROCESSING (PDFs only)
            # ====================================================================
            logger.info(f"🔍 Starting OCR processing for {len(downloaded_files)} documents")
            ocr_processed = 0
            ocr_skipped = 0

            for file_info in downloaded_files:
                if not file_info.get('download_record_id'):
                    logger.warning(f"⚠️ No download_record_id for {file_info['filename']}, skipping OCR")
                    continue

                # Only OCR PDFs
                if file_info['filename'].lower().endswith('.pdf'):
                    download_id = file_info['download_record_id']

                    # Check if OCR already completed
                    doc_record = self.db.get_document_with_data(download_id)
                    if doc_record and doc_record.get('ocr_status') == 'completed':
                        logger.info(f"⏭️ OCR already completed for {file_info['filename']}, skipping")
                        continue

                    # OCR needed
                    success = self.doc_processor.ocr_document(
                        download_id=download_id,
                        pdf_path=file_info['local_path']
                    )
                    if success:
                        ocr_processed += 1
                    else:
                        logger.warning(f"⚠️ OCR failed for {file_info['filename']}")
                else:
                    ocr_skipped += 1
                    logger.debug(f"⏭️ Skipping OCR for non-PDF: {file_info['filename']}")

            logger.info(f"✅ OCR complete: {ocr_processed} processed, {ocr_skipped} skipped (non-PDF)")

            # ====================================================================
            # UPLOAD TO GOOGLE DRIVE
            # ====================================================================

            # Check what's already uploaded
            existing_uploads = self.db.get_downloads_for_request(request_id)
            existing_filenames = set(
                upload.get('document_title') for upload in existing_uploads
                if upload.get('download_status') == 'uploaded_to_drive'
            )

            # Filter out already uploaded files
            files_to_upload = [
                f for f in downloaded_files
                if f['filename'] not in existing_filenames
            ]

            if not files_to_upload:
                logger.info(f"✅ All {len(downloaded_files)} documents already uploaded")
                result['success'] = True
                result['documents_uploaded'] = 0
                shutil.rmtree(temp_dir)
                return result

            logger.info(f"📤 Uploading {len(files_to_upload)} new documents (skipping {len(existing_filenames)} already uploaded)")

            # Upload to Drive
            upload_results = self._upload_to_drive(request_number, files_to_upload, user_google_email)

            if not upload_results['success']:
                error_msg = f"Upload failed: {upload_results.get('error', 'Unknown error')}"
                logger.warning(f"⚠️ {error_msg}")
                result['errors'].append(error_msg)
            else:
                result['documents_uploaded'] = upload_results['success_count']

                # Update database records with Google Drive info
                for uploaded_file in upload_results['successful_uploads']:
                    recent_downloads = self.db.get_downloads_for_request(request_id)
                    matching_download = next(
                        (d for d in recent_downloads if d.get('document_title') == uploaded_file['filename']),
                        None
                    )

                    if matching_download:
                        self.db.update_document_download_status(
                            matching_download['id'],
                            'uploaded_to_drive',
                            google_drive_file_id=uploaded_file['file_id'],
                            google_drive_folder_id=upload_results['folder_id'],
                            google_drive_web_link=uploaded_file.get('web_link')
                        )

                        # Set classification status to pending
                        # For PDFs: OCR already completed, ready for classification
                        # For CSV/XLSX: No OCR needed, ready for classification
                        self.db.set_classification_status(matching_download['id'], 'pending')
                        logger.info(f"🏷️  Document {matching_download['id']} marked as ready for classification")

            # Cleanup temp directory
            shutil.rmtree(temp_dir)
            logger.info(f"🗑️ Cleaned up temp directory: {temp_dir}")

            # Mark as successful if we processed anything
            result['success'] = result['documents_downloaded'] > 0

            logger.info(f"✅ Processed email request {request_number}: "
                       f"{result['documents_downloaded']} downloaded, "
                       f"{result['documents_uploaded']} uploaded")

            return result

        except Exception as e:
            logger.error(f"❌ Failed to process email attachments for {request_number}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            result['errors'].append(str(e))
            return result

    def _is_message_processed(self, request_id: str, message_id: str) -> bool:
        """
        Check if a Gmail message has already been processed for downloads.

        Args:
            request_id: Request ID
            message_id: Gmail message ID

        Returns:
            True if message already processed, False otherwise
        """
        try:
            result = self.db.supabase.table('requests').select('processed_gmail_ids').eq(
                'id', request_id
            ).execute()

            if result.data and len(result.data) > 0:
                processed_ids = result.data[0].get('processed_gmail_ids') or []
                return message_id in processed_ids

            return False

        except Exception as e:
            logger.error(f"Error checking if message processed: {str(e)}")
            return False

    def _mark_message_processed(self, request_id: str, message_id: str):
        """
        Mark a Gmail message as processed for downloads.

        Args:
            request_id: Request ID
            message_id: Gmail message ID
        """
        try:
            # Get current processed_gmail_ids
            result = self.db.supabase.table('requests').select('processed_gmail_ids').eq(
                'id', request_id
            ).execute()

            processed_ids = []
            if result.data and len(result.data) > 0:
                processed_ids = result.data[0].get('processed_gmail_ids') or []

            # Add new message_id if not already present
            if message_id not in processed_ids:
                processed_ids.append(message_id)

                # Update database
                self.db.supabase.table('requests').update({
                    'processed_gmail_ids': processed_ids
                }).eq('id', request_id).execute()

                logger.debug(f"✅ Marked message {message_id} as processed")

        except Exception as e:
            logger.error(f"Error marking message as processed: {str(e)}")

    def _upload_to_drive(
        self,
        request_number: str,
        downloaded_files: List[Dict[str, str]],
        user_email: str
    ) -> Dict[str, Any]:
        """
        Upload downloaded files to Google Drive.

        Args:
            request_number: Request number for folder organization
            downloaded_files: List of file info dicts
            user_email: User's Google account email for file permissions

        Returns:
            Dict with upload results
        """
        try:
            logger.info(f"📤 Uploading {len(downloaded_files)} files to Google Drive")

            # Prepare file list for Drive manager
            files_to_upload = [
                {
                    'local_path': f['local_path'],
                    'filename': f['filename']
                }
                for f in downloaded_files
            ]

            # Upload files
            upload_results = self.drive_manager.upload_multiple_files(
                files=files_to_upload,
                request_number=request_number,
                user_email=user_email
            )
            
            if upload_results['success']:
                logger.info(f"✅ Uploaded {upload_results['success_count']} files to Drive")
            else:
                logger.error(f"❌ Upload failed: {upload_results.get('error')}")
            
            return upload_results
            
        except Exception as e:
            logger.error(f"❌ Drive upload failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _cleanup_temp_files(self, temp_dir: str):
        """
        Clean up temporary download directory.
        
        Args:
            temp_dir: Path to temporary directory
        """
        try:
            if temp_dir and Path(temp_dir).exists():
                shutil.rmtree(temp_dir)
                logger.info(f"🗑️ Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to cleanup temp directory: {str(e)}")


def process_document_downloads(llm_client, user_id: str = None) -> Dict[str, Any]:
    """
    Convenience function to process document downloads.
    """
    db = SupabaseIntegration()
    coordinator = DocumentDownloadCoordinator(llm_client, db)
    return coordinator.process_flagged_requests(user_id)