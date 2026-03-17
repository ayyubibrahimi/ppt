"""
Data Classification Main Module
"""

import logging
import re
from typing import Dict, Any, Optional

from data_classification.classifiers import PDFClassifier, TabularClassifier
from data_classification.pydantic_models import (
    ClassificationResult,
    RequestContext,
    DocumentContext
)
from data_classification.llm_models import llm
from supabase_integration import SupabaseIntegration

logger = logging.getLogger(__name__)


def extract_file_extension(filename: str) -> str:
    """
    Extract file extension from filename.

    Handles cases where file_extension column is NULL in database
    by parsing it from the document_title/filename.

    Args:
        filename: Filename or path

    Returns:
        File extension with leading dot (e.g., '.pdf', '.csv')
        Returns empty string if no extension found

    Examples:
        'document.pdf' -> '.pdf'
        'data_file.csv' -> '.csv'
        'report.2024.xlsx' -> '.xlsx'
        'noextension' -> ''
    """
    if not filename:
        return ''

    # Match extension at end of string: . followed by alphanumeric characters
    match = re.search(r'\.([a-zA-Z0-9]+)$', filename)

    if match:
        ext = match.group(1).lower()
        return f'.{ext}'

    return ''


class DocumentClassificationProcessor:
    """
    Main processor for document classification.

    Orchestrates classification of documents by routing to appropriate
    classifiers (PDF or Tabular) and managing database operations.
    """

    def __init__(self, supabase_integration: SupabaseIntegration):
        """
        Initialize classification processor.

        Args:
            supabase_integration: Supabase client for database operations
        """
        self.db = supabase_integration

        # Initialize classifiers
        # PDFClassifier doesn't need db (works with in-memory OCR data)
        self.pdf_classifier = PDFClassifier(llm)
        # TabularClassifier needs db for fallback Google Drive downloads
        self.tabular_classifier = TabularClassifier(llm, supabase_db=self.db)

        logger.info("✅ DocumentClassificationProcessor initialized")

    def classify_document(self, download_id: str) -> bool:
        """
        Classify a single document.

        Workflow:
        1. Get document with data from database
        2. Get request context (request text + timeline)
        3. Route to appropriate classifier (PDF vs Tabular)
        4. Store classification results

        Args:
            download_id: Document download record ID

        Returns:
            True if classification successful, False otherwise
        """
        try:
            logger.info(f"🏷️  Starting classification for document {download_id}")

            # Set status to processing
            self.db.set_classification_status(download_id, 'processing')

            # Get document with full data
            doc = self.db.get_document_with_data(download_id)

            if not doc:
                logger.error(f"❌ Document {download_id} not found in database")
                self.db.set_classification_status(
                    download_id, 'failed', 'Document not found'
                )
                return False

            # Get request context
            request_id = doc.get('request_id')
            if not request_id:
                logger.error(f"❌ Document {download_id} has no request_id")
                self.db.set_classification_status(
                    download_id, 'failed', 'No request_id'
                )
                return False

            request_context_dict = self.db.get_request_context(request_id)

            if not request_context_dict:
                logger.error(f"❌ Request context not found for request {request_id}")
                self.db.set_classification_status(
                    download_id, 'failed', 'Request context not found'
                )
                return False

            # Build RequestContext object
            request_context = RequestContext(
                request_id=request_context_dict['request_id'],
                request_number=request_context_dict['request_number'],
                request_text=request_context_dict['request_text'],
                timeline_events=request_context_dict['timeline_events'],
                current_status=request_context_dict['current_status']
            )

            # Get file extension - extract from title if NULL in database
            file_extension = doc.get('file_extension')
            document_title = doc.get('document_title', 'Unknown')

            if not file_extension:
                logger.info(f"⚠️ file_extension is NULL, extracting from document_title: {document_title}")
                file_extension = extract_file_extension(document_title)
                logger.info(f"✅ Extracted file_extension: {file_extension}")

            # Normalize to lowercase
            file_extension = file_extension.lower() if file_extension else ''

            # Build DocumentContext object
            document_context = DocumentContext(
                download_id=download_id,
                document_title=document_title,
                file_extension=file_extension,
                num_pages=doc.get('num_pages')
            )

            # Route to appropriate classifier based on file type
            if file_extension == '.pdf':
                result = self._classify_pdf(doc, request_context, document_context)
            elif file_extension in ['.csv', '.xlsx', '.xls']:
                result = self._classify_tabular(doc, request_context, document_context)
            else:
                logger.warning(f"⚠️ Unsupported file type: {file_extension}")
                self.db.set_classification_status(
                    download_id, 'failed', f'Unsupported file type: {file_extension}'
                )
                return False

            # Store classification results
            success = self.db.update_document_classification(
                download_id=download_id,
                matches_request=result.records_match_request,
                explanation=self._build_full_explanation(result)
            )

            if success:
                logger.info(
                    f"✅ Classification complete for document {download_id}: "
                    f"Match={result.records_match_request}"
                )
                return True
            else:
                logger.error(f"❌ Failed to save classification results for {download_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Classification failed for document {download_id}: {str(e)}", exc_info=True)
            self.db.set_classification_status(download_id, 'failed', str(e))
            return False

    def _classify_pdf(
        self,
        doc: Dict[str, Any],
        request_context: RequestContext,
        document_context: DocumentContext
    ) -> ClassificationResult:
        """
        Classify a PDF document.

        Args:
            doc: Document record from database
            request_context: Request context
            document_context: Document context

        Returns:
            ClassificationResult

        Raises:
            ValueError: If OCR data is missing or invalid
        """
        logger.info(f"📄 Routing to PDF classifier")

        # Extract OCR data
        document_data_jsonb = doc.get('document_data', {})
        ocr_data = document_data_jsonb.get('ocr_data')

        if not ocr_data:
            raise ValueError("No OCR data available for PDF classification")

        document_data = {'ocr_data': ocr_data}

        # Classify
        result = self.pdf_classifier.classify(
            document_data=document_data,
            request_context=request_context,
            document_context=document_context
        )

        return result

    def _classify_tabular(
        self,
        doc: Dict[str, Any],
        request_context: RequestContext,
        document_context: DocumentContext
    ) -> ClassificationResult:
        """
        Classify a tabular data file (CSV/XLSX).

        Args:
            doc: Document record from database
            request_context: Request context
            document_context: Document context

        Returns:
            ClassificationResult

        Raises:
            ValueError: If file path is missing
        """
        logger.info(f"📊 Routing to tabular classifier")

        # Get file path
        local_file_path = doc.get('local_file_path')

        if not local_file_path:
            raise ValueError("No local_file_path available for tabular classification")

        # Include Google Drive info for fallback download if local file missing
        document_data = {
            'file_path': local_file_path,
            'google_drive_file_id': doc.get('google_drive_file_id'),
            'download_id': doc.get('id')
        }

        # Classify
        result = self.tabular_classifier.classify(
            document_data=document_data,
            request_context=request_context,
            document_context=document_context
        )

        return result

    def _build_full_explanation(self, result: ClassificationResult) -> str:
        """
        Build comprehensive explanation from ClassificationResult.

        Args:
            result: Classification result from LLM

        Returns:
            Formatted explanation string
        """
        explanation_parts = [result.explanation]

        if result.matched_requirements:
            explanation_parts.append(
                f"\n\nMatched requirements: {', '.join(result.matched_requirements)}"
            )

        if result.missing_requirements:
            explanation_parts.append(
                f"\n\nMissing requirements: {', '.join(result.missing_requirements)}"
            )

        if result.additional_notes:
            explanation_parts.append(f"\n\nAdditional notes: {result.additional_notes}")

        return "".join(explanation_parts)

    def process_pending_classifications(
        self,
        user_id: Optional[str] = None,
        max_documents: int = None
    ) -> Dict[str, Any]:
        """
        Process all documents pending classification.

        Args:
            user_id: Optional user ID to filter by
            max_documents: Maximum number of documents to process.
                          If None (default), processes all pending documents.

        Returns:
            Dict with processing statistics
        """
        logger.info("🏷️  Checking for documents pending classification...")

        # Get pending documents
        limit = max_documents if max_documents is not None else 10000
        pending_docs = self.db.get_documents_pending_classification(
            user_id=user_id,
            limit=limit
        )

        if not pending_docs:
            logger.info("✅ No documents pending classification")
            return {
                'total_pending': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'documents': []
            }

        logger.info(f"📋 Found {len(pending_docs)} documents pending classification")

        stats = {
            'total_pending': len(pending_docs),
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'documents': []
        }

        for doc in pending_docs:
            download_id = doc['id']

            # Classify document
            success = self.classify_document(download_id)

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
                    'status': 'failed'
                })

        logger.info(f"✅ Classification processing complete:")
        logger.info(f"   Processed: {stats['successful']}/{stats['processed']} successful")

        return stats


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def classify_document(download_id: str, db: SupabaseIntegration = None) -> bool:
    """
    Convenience function to classify a single document.

    Args:
        download_id: Document download ID
        db: Optional SupabaseIntegration instance (creates new if not provided)

    Returns:
        True if successful, False otherwise
    """
    if db is None:
        db = SupabaseIntegration()

    processor = DocumentClassificationProcessor(db)
    return processor.classify_document(download_id)


def process_pending_classifications(
    user_id: Optional[str] = None,
    max_documents: int = None,
    db: SupabaseIntegration = None
) -> Dict[str, Any]:
    """
    Convenience function to process all pending classifications.

    Args:
        user_id: Optional user ID to filter by
        max_documents: Maximum number to process
        db: Optional SupabaseIntegration instance

    Returns:
        Processing statistics dict
    """
    if db is None:
        db = SupabaseIntegration()

    processor = DocumentClassificationProcessor(db)
    return processor.process_pending_classifications(user_id, max_documents)
