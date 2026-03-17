import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any

from ocr.src import DocClient, getcreds
from summarize.src import (
    create_memory_log,
    process_file,
    combine_and_finalize_summaries,
    get_template_strings
)
from supabase_integration import SupabaseIntegration

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Handles complete document processing pipeline for downloaded PDFs:
    - OCR processing (extract text from PDFs)
    - Summarization (generate summaries from OCR text)

    Intelligently processes documents through both stages, with checkpointing
    after each stage to avoid losing work if processing fails.
    """

    def __init__(self, supabase_integration: SupabaseIntegration):
        """
        Initialize document processor.

        Args:
            supabase_integration: Supabase client for database operations
        """
        self.db = supabase_integration
        self.ocr_client = None
        self.template_strings = None
        logger.info("✅ DocumentProcessor initialized")

    def _get_ocr_client(self) -> DocClient:
        """
        Lazy-load OCR client (expensive to initialize).
        """
        if self.ocr_client is None:
            try:
                endpoint, key = getcreds()
                self.ocr_client = DocClient(endpoint, key)
                logger.info("✅ OCR client initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize OCR client: {str(e)}")
                raise

        return self.ocr_client

    def _get_template_strings(self) -> Dict[str, str]:
        """
        Lazy-load summarization template strings.
        """
        if self.template_strings is None:
            try:
                self.template_strings = get_template_strings()
                logger.info("✅ Summarization templates loaded")
            except Exception as e:
                logger.error(f"❌ Failed to load summarization templates: {str(e)}")
                raise

        return self.template_strings

    def ocr_document(
        self,
        download_id: str,
        pdf_path: str,
        local_file_path: str = None,
        _ocr_client: DocClient = None
    ) -> bool:
        """
        OCR a document and save results to Supabase.

        Args:
            download_id: Document download record ID in Supabase
            pdf_path: Path to PDF file to process
            local_file_path: Optional path to store for reference

        Returns:
            True if OCR successful and saved, False otherwise
        """
        try:
            # Validate file exists
            if not os.path.exists(pdf_path):
                logger.error(f"❌ PDF file not found: {pdf_path}")
                self.db.set_ocr_status(download_id, 'failed', f"File not found: {pdf_path}")
                return False

            # Set status to processing
            logger.info(f"🔍 Starting OCR for document {download_id}: {os.path.basename(pdf_path)}")
            self.db.set_ocr_status(download_id, 'processing')

            # Get OCR client (use provided client if given, e.g. from parallel worker)
            ocr_client = _ocr_client if _ocr_client is not None else self._get_ocr_client()

            # Run OCR
            ocr_result = ocr_client.process_pdf_to_data(pdf_path)

            # Extract data from result
            ocr_data = ocr_result['ocr_data']
            num_pages = ocr_result['num_pages']
            file_size_bytes = ocr_result['file_size_bytes']
            ocr_method = ocr_data['ocr_method']

            # Save to Supabase
            success = self.db.update_document_ocr_data(
                download_id=download_id,
                ocr_data=ocr_data,
                ocr_method=ocr_method,
                num_pages=num_pages,
                file_size_bytes=file_size_bytes,
                local_file_path=local_file_path or pdf_path
            )

            if success:
                logger.info(f"✅ OCR completed and saved for document {download_id} ({num_pages} pages, {ocr_method})")

                # CHECKPOINT: OCR succeeded, now mark as ready for summarization
                self.db.set_summary_status(download_id, 'pending')
                logger.info(f"📝 Document {download_id} marked as ready for summarization")

                return True
            else:
                logger.error(f"❌ Failed to save OCR data to database for document {download_id}")
                self.db.set_ocr_status(download_id, 'failed', 'Database save failed')
                return False

        except Exception as e:
            logger.error(f"❌ OCR processing failed for document {download_id}: {str(e)}", exc_info=True)
            self.db.set_ocr_status(download_id, 'failed', str(e))
            return False

    def summarize_document(self, download_id: str) -> bool:
        """
        Summarize a document using its OCR data from Supabase.

        Args:
            download_id: Document download record ID in Supabase

        Returns:
            True if summarization successful and saved, False otherwise
        """
        try:
            # Set status to processing
            logger.info(f"📝 Starting summarization for document {download_id}")
            self.db.set_summary_status(download_id, 'processing')

            # Fetch document with OCR data
            doc = self.db.get_document_with_data(download_id)

            if not doc:
                logger.error(f"❌ Document {download_id} not found in database")
                self.db.set_summary_status(download_id, 'failed', 'Document not found')
                return False

            # Verify OCR data exists
            document_data = doc.get('document_data', {})
            ocr_data = document_data.get('ocr_data')

            if not ocr_data or not ocr_data.get('page_texts'):
                logger.error(f"❌ No OCR data found for document {download_id}")
                self.db.set_summary_status(download_id, 'failed', 'No OCR data available')
                return False

            # Transform OCR data to summarization format
            page_texts = ocr_data.get('page_texts', [])
            pages = []
            for page_data in page_texts:
                pages.append({
                    'page_number': page_data['page_number'],
                    'page_content': page_data['text'],
                    'sha1': download_id  # Use download_id as identifier
                })

            if not pages:
                logger.error(f"❌ No pages to summarize for document {download_id}")
                self.db.set_summary_status(download_id, 'failed', 'No page content')
                return False

            logger.info(f"📄 Loaded {len(pages)} pages for summarization")

            # Get template strings
            template_strings = self._get_template_strings()

            # Create memory log
            logger.info(f"🧠 Creating memory log for document {download_id}")
            memory_log = create_memory_log(pages, template_strings)

            # Process file into interval summaries
            logger.info(f"⚙️ Processing {len(pages)} pages into interval summaries")
            interval_summaries, _ = process_file(
                pages=pages,
                sha1=download_id,
                output_directory=None,  # Not saving to file
                template_strings=template_strings
            )

            if not interval_summaries:
                logger.error(f"❌ No interval summaries generated for document {download_id}")
                self.db.set_summary_status(download_id, 'failed', 'No summaries generated')
                return False

            # Combine, improve, and organize summaries
            logger.info(f"🔄 Combining and finalizing summaries for document {download_id}")
            final_summary = combine_and_finalize_summaries(
                interval_summaries=interval_summaries,
                memory_log=memory_log,
                template_strings=template_strings
            )

            if not final_summary:
                logger.error(f"❌ Failed to generate final summary for document {download_id}")
                self.db.set_summary_status(download_id, 'failed', 'Summary generation failed')
                return False

            # Prepare summary data
            summary_data = {
                'summary_text': final_summary,
                'summary_timestamp': None,  # Will be set by database method
                'num_pages': len(pages),
                'num_intervals': len(interval_summaries)
            }

            # Save to Supabase
            success = self.db.update_document_summary(
                download_id=download_id,
                summary=summary_data,
                summary_method='azure_gpt4'  # Using Azure OpenAI from llm_models.py
            )

            if success:
                logger.info(f"✅ Summarization completed and saved for document {download_id} ({len(pages)} pages)")
                return True
            else:
                logger.error(f"❌ Failed to save summary to database for document {download_id}")
                self.db.set_summary_status(download_id, 'failed', 'Database save failed')
                return False

        except Exception as e:
            logger.error(f"❌ Summarization failed for document {download_id}: {str(e)}", exc_info=True)
            self.db.set_summary_status(download_id, 'failed', str(e))
            return False

    def process_pending_documents(self, user_id: str = None, max_documents: int = None) -> Dict[str, Any]:
        """
        Process all documents pending OCR and/or summarization.

        This method intelligently processes documents through both stages:
        1. OCR documents that need text extraction
        2. Summarize documents that have completed OCR

        Args:
            user_id: Optional user ID to filter by
            max_documents: Maximum number of documents to process per stage.
                          If None (default), processes all pending documents.

        Returns:
            Dict with processing statistics for both OCR and summarization
        """
        logger.info("🔍 Checking for documents pending processing...")

        # Stage 1: Process documents pending OCR
        ocr_stats = self.process_pending_ocr(user_id, max_documents)

        # Stage 2: Process documents pending summarization
        summary_stats = self.process_pending_summaries(user_id, max_documents)

        # Combined statistics
        combined_stats = {
            'ocr': ocr_stats,
            'summarization': summary_stats,
            'total_processed': ocr_stats['processed'] + summary_stats['processed'],
            'total_successful': ocr_stats['successful'] + summary_stats['successful'],
            'total_failed': ocr_stats['failed'] + summary_stats['failed']
        }

        logger.info(f"✅ Document processing complete:")
        logger.info(f"   OCR: {ocr_stats['successful']}/{ocr_stats['processed']} successful")
        logger.info(f"   Summarization: {summary_stats['successful']}/{summary_stats['processed']} successful")

        return combined_stats

    def process_pending_ocr(self, user_id: str = None, max_documents: int = None, max_workers: int = 3) -> Dict[str, Any]:
        """Process documents pending OCR in parallel across documents."""
        logger.info("📄 Checking for documents pending OCR...")

        limit = max_documents if max_documents is not None else 10000
        pending_docs = self.db.get_documents_pending_ocr(user_id=user_id, limit=limit)

        if not pending_docs:
            logger.info("✅ No documents pending OCR")
            return {
                'total_pending': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'documents': []
            }

        logger.info(f"📋 Found {len(pending_docs)} documents pending OCR, processing with {max_workers} workers")

        stats = {
            'total_pending': len(pending_docs),
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'documents': []
        }

        def _process_doc(doc):
            download_id = doc['id']
            local_path = doc.get('local_file_path')

            if not local_path:
                logger.warning(f"⚠️ Document {download_id} has no local_file_path, skipping")
                self.db.set_ocr_status(download_id, 'failed', 'No local file path')
                return {'download_id': download_id, 'status': 'failed', 'reason': 'No local file path'}

            if not os.path.exists(local_path):
                logger.warning(f"⚠️ File not found for document {download_id}: {local_path}")
                self.db.set_ocr_status(download_id, 'failed', f"File not found: {local_path}")
                return {'download_id': download_id, 'status': 'failed', 'reason': 'File not found'}

            try:
                # Each worker gets its own DocClient to avoid sharing EasyOCR reader across threads
                endpoint, key = getcreds()
                with DocClient(endpoint, key) as ocr_client:
                    success = self.ocr_document(download_id, local_path, _ocr_client=ocr_client)
            except Exception as e:
                logger.error(f"❌ OCR worker failed for {download_id}: {e}")
                self.db.set_ocr_status(download_id, 'failed', str(e))
                return {'download_id': download_id, 'status': 'failed', 'reason': str(e)}

            return {
                'download_id': download_id,
                'status': 'success' if success else 'failed',
                'reason': None if success else 'OCR processing error'
            }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_doc, doc): doc['id'] for doc in pending_docs}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    stats['processed'] += 1
                    if result['status'] == 'success':
                        stats['successful'] += 1
                    else:
                        stats['failed'] += 1
                    stats['documents'].append(result)
                except Exception as exc:
                    logger.error(f'Document OCR worker raised exception: {exc}')
                    stats['failed'] += 1

        return stats

    def process_pending_summaries(self, user_id: str = None, max_documents: int = None) -> Dict[str, Any]:
        """Process documents pending summarization."""
        logger.info("📝 Checking for documents pending summarization...")

        # If max_documents is None, use a very large limit to get all documents
        limit = max_documents if max_documents is not None else 10000
        pending_docs = self.db.get_documents_pending_summary(user_id=user_id, limit=limit)

        if not pending_docs:
            logger.info("✅ No documents pending summarization")
            return {
                'total_pending': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'documents': []
            }

        logger.info(f"📋 Found {len(pending_docs)} documents pending summarization")

        stats = {
            'total_pending': len(pending_docs),
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'documents': []
        }

        for doc in pending_docs:
            download_id = doc['id']

            # Process document (summarization)
            success = self.summarize_document(download_id)

            stats['processed'] += 1
            if success:
                stats['successful'] += 1
                stats['documents'].append({
                    'download_id': download_id,
                    'status': 'success'
                })
            else:
                stats['failed'] += 1
                stats['documents'].append({
                    'download_id': download_id,
                    'status': 'failed',
                    'reason': 'Summarization processing error'
                })

        return stats

    # Keep old method name for backward compatibility
    def process_pending_ocr_documents(self, user_id: str = None, max_documents: int = None) -> Dict[str, Any]:
        """
        DEPRECATED: Use process_pending_documents() instead.
        This method only processes OCR for backward compatibility.

        Args:
            user_id: Optional user ID to filter by
            max_documents: Maximum number of documents to process.
                          If None (default), processes all pending documents.
        """
        logger.warning("⚠️ process_pending_ocr_documents() is deprecated, use process_pending_documents() instead")
        return self.process_pending_ocr(user_id, max_documents)

    # ============================================================================
    # DATA CLASSIFICATION METHODS
    # ============================================================================

    def classify_document(self, download_id: str) -> bool:
        """
        Classify a single document against its FOIA request.

        Determines if the document contains the information requested
        by analyzing OCR text (for PDFs) or table structure (for CSV/XLSX).

        Args:
            download_id: Document download record ID

        Returns:
            True if classification successful, False otherwise
        """
        try:
            from data_classification.src import DocumentClassificationProcessor

            processor = DocumentClassificationProcessor(self.db)
            return processor.classify_document(download_id)

        except Exception as e:
            logger.error(f"❌ Classification failed for document {download_id}: {str(e)}", exc_info=True)
            return False

    def process_pending_classifications(
        self,
        user_id: str = None,
        max_documents: int = None
    ) -> Dict[str, Any]:
        """
        Process all documents pending classification.

        Classifies documents against their FOIA requests to determine
        if released records match what was requested.

        Args:
            user_id: Optional user ID to filter by
            max_documents: Maximum number of documents to process.
                          If None (default), processes all pending documents.

        Returns:
            Dict with processing statistics
        """
        try:
            from data_classification.src import DocumentClassificationProcessor

            processor = DocumentClassificationProcessor(self.db)
            return processor.process_pending_classifications(user_id, max_documents)

        except Exception as e:
            logger.error(f"❌ Failed to process pending classifications: {str(e)}", exc_info=True)
            return {
                'total_pending': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'error': str(e)
            }

    def cleanup(self):
        """Clean up resources (close OCR client)."""
        if self.ocr_client:
            try:
                self.ocr_client.close()
                logger.info("✅ OCR client closed")
            except Exception as e:
                logger.warning(f"⚠️ Error closing OCR client: {str(e)}")
