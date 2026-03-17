"""
Data Classification Module

Classifies whether released government documents match the original FOIA request.
Supports PDFs (OCR'd text) and tabular data (CSV/XLSX).
"""

from data_classification.pydantic_models import ClassificationResult
from data_classification.base_classifier import BaseClassifier

__all__ = [
    'ClassificationResult',
    'BaseClassifier',
]
