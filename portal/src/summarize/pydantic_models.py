from typing import List, Dict, Tuple
from pydantic import BaseModel, Field

class PageValidation(BaseModel):
    """Validation result for a single page in a batch."""
    page_number: int = Field(..., description="Page number analyzed")
    should_be_included: bool = Field(..., description="True if page has explicit evidence")
    relevance_reasoning: str = Field(..., description="Why this page is or isn't relevant")
    supporting_quote: str = Field(..., description="Exact supporting text from page")
    confidence: str = Field(..., description="high|medium|low")
    evidence_strength: str = Field(..., description="explicit|circumstantial|general|unrelated")
    exclusion_reason: str = Field(default="", description="Reason for exclusion if should_be_included is false")


class BatchValidationResult(BaseModel):
    """Result of validating all pages in a batch."""
    validated_pages: List[PageValidation] = Field(..., description="Validation results for each page")
    validator_notes: str = Field(..., description="Overall assessment of the batch")


class BulletpointCitation(BaseModel):
    """Final citation result for a single bulletpoint."""
    bulletpoint_text: str = Field(..., description="Original bulletpoint text")
    cited_pages: List[int] = Field(default=[], description="Page numbers with explicit evidence")
    confidence: str = Field(..., description="HIGH/MEDIUM/LOW - overall confidence")
    has_citation: bool = Field(..., description="True if any pages found")
    citation_count: int = Field(..., description="Number of pages cited")
