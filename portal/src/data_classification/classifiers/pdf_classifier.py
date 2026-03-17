"""
PDF Classifier - Classifies OCR'd PDF documents against FOIA requests.
"""

import logging
from typing import Dict, Any
from jinja2 import Template

from data_classification.base_classifier import BaseClassifier
from data_classification.pydantic_models import (
    ClassificationResult,
    RequestContext,
    DocumentContext
)
from data_classification.prompts import get_pdf_classification_prompt
from data_classification.llm_models import run_structured_inference

logger = logging.getLogger(__name__)


class PDFClassifier(BaseClassifier):
    """
    Classifier for OCR'd PDF documents.

    Extracts text from OCR data and compares against FOIA request
    using LLM-based analysis.
    """

    def classify(
        self,
        document_data: Dict[str, Any],
        request_context: RequestContext,
        document_context: DocumentContext
    ) -> ClassificationResult:
        """
        Classify if a PDF document matches the FOIA request.

        Args:
            document_data: Dict with 'ocr_data' key containing page_texts
            request_context: Context about the FOIA request
            document_context: Metadata about the document

        Returns:
            ClassificationResult with match decision and explanation

        Raises:
            ValueError: If document_data is missing required keys
            RuntimeError: If classification fails
        """
        logger.info(f"🏷️  Classifying PDF document: {document_context.document_title}")

        # Validate input
        self._validate_document_data(document_data, ['ocr_data'])

        try:
            # Extract OCR text
            ocr_text = self._extract_ocr_text(document_data['ocr_data'])

            if not ocr_text or not ocr_text.strip():
                logger.warning(f"⚠️ No OCR text found for {document_context.document_title}")
                raise ValueError("No OCR text available for classification")

            logger.info(f"📄 Extracted {len(ocr_text)} characters of OCR text")

            # Build timeline summary
            timeline_summary = self._build_timeline_summary(request_context.timeline_events)

            # Build prompt
            prompt = self._build_classification_prompt(
                request_text=request_context.request_text,
                timeline_summary=timeline_summary,
                ocr_text=ocr_text
            )

            logger.info(f"🤖 Sending classification request to LLM")

            # Call LLM with structured inference
            result = run_structured_inference(
                prompt=prompt,
                response_model=ClassificationResult,
                max_tokens=1000,
                temperature=0.1
            )

            logger.info(
                f"✅ Classification complete: Match={result.records_match_request} "
                f"for {document_context.document_title}"
            )

            return result

        except Exception as e:
            logger.error(f"❌ PDF classification failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"PDF classification failed: {str(e)}")

    def _extract_ocr_text(self, ocr_data: Dict[str, Any]) -> str:
        """
        Extract full text from OCR data structure.

        Args:
            ocr_data: OCR data dict with 'page_texts' array

        Returns:
            Combined text from all pages

        Raises:
            ValueError: If OCR data structure is invalid
        """
        if not ocr_data:
            raise ValueError("OCR data is empty")

        page_texts = ocr_data.get('page_texts', [])

        if not page_texts:
            raise ValueError("No page_texts found in OCR data")

        # Combine all pages
        all_text_parts = []

        for page_data in page_texts:
            if isinstance(page_data, dict):
                page_number = page_data.get('page_number', '?')
                text = page_data.get('text', '')

                if text and text.strip():
                    # Add page marker for context
                    all_text_parts.append(f"[Page {page_number}]\n{text}")
            else:
                logger.warning(f"⚠️ Invalid page_data format: {type(page_data)}")

        if not all_text_parts:
            raise ValueError("No text content found in page_texts")

        combined_text = "\n\n".join(all_text_parts)

        logger.debug(f"Extracted text from {len(page_texts)} pages")

        return combined_text

    def _build_classification_prompt(
        self,
        request_text: str,
        timeline_summary: str,
        ocr_text: str
    ) -> str:
        """
        Build the classification prompt for the LLM.

        Args:
            request_text: Original FOIA request
            timeline_summary: Formatted timeline of correspondence
            ocr_text: Combined OCR text from document

        Returns:
            Complete prompt string
        """
        template_str = get_pdf_classification_prompt()
        template = Template(template_str)

        # Truncate OCR text if too long (keep first and last portions)
        max_ocr_chars = 15000  # Limit to avoid token limits
        if len(ocr_text) > max_ocr_chars:
            logger.info(f"⚠️ Truncating OCR text from {len(ocr_text)} to {max_ocr_chars} chars")
            # Keep first 75% and last 25%
            split_point = int(max_ocr_chars * 0.75)
            ocr_text = (
                ocr_text[:split_point] +
                "\n\n[... MIDDLE SECTION TRUNCATED ...]\n\n" +
                ocr_text[-int(max_ocr_chars * 0.25):]
            )

        prompt = template.render(
            request_text=request_text,
            timeline_summary=timeline_summary,
            ocr_text=ocr_text
        )

        return prompt
