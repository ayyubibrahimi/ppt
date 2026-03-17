"""
Base classifier abstract interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
import logging

from data_classification.pydantic_models import (
    ClassificationResult,
    RequestContext,
    DocumentContext
)

logger = logging.getLogger(__name__)


class BaseClassifier(ABC):
    """
    Abstract base class for document classifiers.

    All classifiers (PDFClassifier, TabularClassifier) inherit from this
    and implement the classify() method for their specific document type.
    """

    def __init__(self, llm_client, supabase_db=None):
        """
        Initialize classifier with LLM client.

        Args:
            llm_client: LLM client instance (from llm_models.py)
            supabase_db: Optional SupabaseIntegration instance for database operations
                        (required for TabularClassifier fallback to Google Drive)
        """
        self.llm_client = llm_client
        self.db = supabase_db
        logger.info(f"✅ {self.__class__.__name__} initialized")

    @abstractmethod
    def classify(
        self,
        document_data: Dict[str, Any],
        request_context: RequestContext,
        document_context: DocumentContext
    ) -> ClassificationResult:
        """
        Classify if a document matches the FOIA request.

        This is the main method that each classifier must implement.

        Args:
            document_data: Document-specific data
                - For PDFs: {'ocr_text': str}
                - For CSV/XLSX: {'file_path': str}
            request_context: Context about the FOIA request
            document_context: Metadata about the document

        Returns:
            ClassificationResult with match decision and explanation

        Raises:
            ValueError: If document_data is invalid
            RuntimeError: If classification fails
        """
        pass

    def _build_timeline_summary(self, timeline_events: list) -> str:
        """
        Helper method to build a readable summary from timeline events.

        Args:
            timeline_events: List of timeline event dicts

        Returns:
            Formatted string summarizing the timeline
        """
        if not timeline_events:
            return "No timeline events recorded."

        summary_parts = []
        for i, event in enumerate(timeline_events, 1):
            # Timeline events structure varies, handle gracefully
            if isinstance(event, dict):
                event_str = f"{i}. {event.get('description', str(event))}"
            else:
                event_str = f"{i}. {str(event)}"
            summary_parts.append(event_str)

        return "\n".join(summary_parts)

    def _validate_document_data(self, document_data: Dict[str, Any], required_keys: list):
        """
        Helper method to validate document_data has required keys.

        Args:
            document_data: Document data dict to validate
            required_keys: List of required key names

        Raises:
            ValueError: If required keys are missing
        """
        missing_keys = [key for key in required_keys if key not in document_data]
        if missing_keys:
            raise ValueError(
                f"{self.__class__.__name__} requires document_data keys: {required_keys}. "
                f"Missing: {missing_keys}"
            )
