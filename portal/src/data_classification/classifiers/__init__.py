"""
Classifiers submodule

Contains specific classifier implementations:
- PDFClassifier: For OCR'd PDF documents
- TabularClassifier: For CSV/XLSX files with EDA
"""

from data_classification.classifiers.pdf_classifier import PDFClassifier
from data_classification.classifiers.tabular_classifier import TabularClassifier

__all__ = [
    'PDFClassifier',
    'TabularClassifier',
]
