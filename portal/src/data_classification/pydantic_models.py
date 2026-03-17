"""
Pydantic models for data classification responses.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class SheetClassification(BaseModel):
    """
    Classification result for a single sheet in a multi-sheet Excel file.

    Used for hierarchical classification where each sheet is analyzed
    separately before orchestrating a final decision.

    Distinguishes between:
    - Contains relevant data: Is this sheet about the right topic?
    - Matches request: Does it have ALL the fundamental fields requested?
    """
    sheet_name: str = Field(
        ...,
        description="Name of the sheet being classified"
    )

    contains_relevant_data: bool = Field(
        ...,
        description="TRUE if this sheet contains data on the right topic/subject matter (e.g., use of force incidents), FALSE if completely unrelated"
    )

    matches_request_requirements: bool = Field(
        ...,
        description="TRUE if this sheet has ALL fundamental fields requested (e.g., officer names, dates, force type). FALSE if missing critical required fields, even if the data is related to the topic."
    )

    summary: str = Field(
        ...,
        description="Brief summary of what this sheet contains (structure, columns, data type)"
    )

    confidence: Optional[float] = Field(
        default=None,
        description="Confidence level (0.0-1.0) in this classification. Higher is more confident."
    )

    key_columns: List[str] = Field(
        default_factory=list,
        description="List of key column names found in this sheet"
    )

    missing_required_fields: List[str] = Field(
        default_factory=list,
        description="List of fundamental fields that were requested but are MISSING from this sheet (e.g., 'officer names', 'badge numbers')"
    )

    reasoning: Optional[str] = Field(
        default=None,
        description="Brief reasoning for the classification decision"
    )


class ClassificationResult(BaseModel):
    """
    Result of classifying a document against a FOIA request.

    This is the structured response from the LLM after analyzing
    whether a released document matches what was requested.
    """
    records_match_request: bool = Field(
        ...,
        description="TRUE if document matches the FOIA request, FALSE otherwise"
    )

    explanation: str = Field(
        ...,
        description="Detailed explanation of the classification decision, including what was matched or missing"
    )

    matched_requirements: List[str] = Field(
        default_factory=list,
        description="List of request requirements that were found in the document"
    )

    missing_requirements: List[str] = Field(
        default_factory=list,
        description="List of request requirements that were NOT found in the document"
    )

    additional_notes: Optional[str] = Field(
        default=None,
        description="Any additional observations or context about the classification"
    )


class RequestContext(BaseModel):
    """
    Context about the FOIA request for classification.

    Includes the original request text and full timeline of correspondence
    (which may include amendments to the original request).
    """
    request_id: str = Field(..., description="Request ID from database")
    request_number: str = Field(..., description="Request number (e.g., '25-704')")
    request_text: str = Field(..., description="Original FOIA request text")
    timeline_events: List[str] = Field(
        default_factory=list,
        description="Full timeline of correspondence in 'MM/DD/YYYY: Sender: Message' format"
    )
    current_status: str = Field(..., description="Current request status")


class DocumentContext(BaseModel):
    """
    Context about the document being classified.
    """
    download_id: str = Field(..., description="Document download ID from database")
    document_title: str = Field(..., description="Document title/filename")
    file_extension: str = Field(..., description="File extension (.pdf, .csv, .xlsx)")
    num_pages: Optional[int] = Field(None, description="Number of pages (for PDFs)")
