import logging
import json
from typing import Dict, Any, Optional, List
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from datetime import datetime
import difflib

logger = logging.getLogger(__name__)


class RequestExtractionResult(BaseModel):
    """Result of extracting request info from email subject"""
    request_number: str = Field(description="Request number (e.g., '25-507')")
    agency_name: str = Field(description="Agency/portal name (e.g., 'City of Hollister')")


class PracticalCompletenessAssessment(BaseModel):
    """Assessment of whether Gmail captures important information for request management"""
    verdict: str = Field(description="PASS or FAIL")
    practical_score: float = Field(description="0.0 to 1.0 - how practically useful is Gmail?")
    summary: str = Field(description="2-3 sentences explaining verdict")
    critical_gaps: List[str] = Field(description="List of critical missing information (empty if PASS)")
    minor_gaps: List[str] = Field(description="List of acceptable missing information (system events)")


class AnalysisComparisonResult(BaseModel):
    """Result of comparing portal analysis vs Gmail analysis"""
    overall_quality_score: float = Field(description="Overall quality score 0.0-1.0 (1.0 = Gmail as good or better)")

    timeline_completeness_score: float = Field(description="0.0-1.0: Does Gmail capture all timeline events from portal?")
    timeline_notes: str = Field(description="Specific findings about timeline comparison")

    status_accuracy_score: float = Field(description="0.0-1.0: Are statuses consistent between analyses?")
    status_notes: str = Field(description="Specific findings about status comparison")

    flags_accuracy_score: float = Field(description="0.0-1.0: Are action_required/needs_attention flags consistent?")
    flags_notes: str = Field(description="Specific findings about flag comparison")

    document_payment_score: float = Field(description="0.0-1.0: Are documents and payments accurately captured?")
    document_payment_notes: str = Field(description="Specific findings about documents/payments")

    verdict: str = Field(description="PASS/FAIL - Whether Gmail analysis is acceptable quality")
    summary: str = Field(description="Overall summary of comparison findings")
    recommendations: str = Field(description="Specific improvements needed if any")


class GmailLLMHelper:
    """LLM helper for Gmail-specific email parsing and analysis"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def extract_request_info(self, email_subject: str) -> Dict[str, str]:
        """
        Extract request number and agency name from email subject using LLM.

        Args:
            email_subject: Email subject line (e.g., "[External Message Added] City of Hollister request #25-507")

        Returns:
            Dict with 'request_number' and 'agency_name' keys

        Example:
            >>> extract_request_info("[External Message Added] City of Hollister request #25-507")
            {'request_number': '25-507', 'agency_name': 'City of Hollister'}
        """

        extraction_prompt = f"""
        Extract structured information from this email subject line.

        Email subject: "{email_subject}"

        Extract:
        1. **request_number**: The request ID in format XX-XXXX (e.g., "25-507", "24-1643")
        2. **agency_name**: The agency or city name (e.g., "City of Hollister", "BART", "City of Manteca")

        Common patterns:
        - "[External Message Added] City of Hollister public records request #25-507"
        - "City of Manteca public records request #25-501"
        - "BART public records request #25-566"

        Return both fields. If request number is not found, return "UNKNOWN".
        If agency name is not found, return "UNKNOWN".
        """

        try:
            structured_llm = self.llm_client.with_structured_output(RequestExtractionResult)

            messages = [
                SystemMessage(content=extraction_prompt),
                HumanMessage(content=f"Extract request info from: {email_subject}")
            ]

            result = structured_llm.invoke(messages)

            logger.info(f"Extracted from '{email_subject}': {result.request_number} / {result.agency_name}")

            return {
                'request_number': result.request_number,
                'agency_name': result.agency_name
            }

        except Exception as e:
            logger.error(f"Failed to extract request info from '{email_subject}': {str(e)}")
            return {
                'request_number': 'UNKNOWN',
                'agency_name': 'UNKNOWN'
            }

    def identify_sender(self, from_address: str, body_text: str = "") -> str:
        """
        Identify if email is from staff or from user.

        Args:
            from_address: Email sender address
            body_text: Optional email body for additional context

        Returns:
            "Staff:" or "You:" for timeline formatting
        """

        # NextRequest emails from staff use: messages@nextrequest.com
        if 'nextrequest.com' in from_address.lower():
            return "Staff:"

        # Could add more sophisticated detection here if needed
        # For now, assume all emails from nextrequest.com are staff
        return "Staff:"

    def parse_email_date(self, email_date: str) -> str:
        """
        Parse email date to MM/DD/YYYY format for timeline consistency.

        Args:
            email_date: Date string from email (various formats)

        Returns:
            Formatted date string "MM/DD/YYYY"
        """

        try:
            # Try parsing common email date formats
            # Example: "Tue, 06 Jan 2026 01:25:56 +0000"

            # Remove timezone info for easier parsing
            date_str = email_date.split('+')[0].split('-')[0].strip()

            # Try multiple date formats
            formats = [
                "%a, %d %b %Y %H:%M:%S",  # "Tue, 06 Jan 2026 01:25:56"
                "%d %b %Y %H:%M:%S",      # "06 Jan 2026 01:25:56"
                "%Y-%m-%d %H:%M:%S",      # "2026-01-06 01:25:56"
                "%Y-%m-%d",               # "2026-01-06"
            ]

            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime("%m/%d/%Y")
                except ValueError:
                    continue

            # If all formats fail, return original
            logger.warning(f"Could not parse date '{email_date}', using as-is")
            return email_date

        except Exception as e:
            logger.error(f"Error parsing date '{email_date}': {str(e)}")
            return email_date

    def compare_practical_completeness(
        self,
        portal_analysis: Dict[str, Any],
        gmail_analysis: Dict[str, Any],
        request_number: str
    ):
        """
        Practical completeness comparison: Does Gmail capture important information?

        Instead of strict field-by-field comparison, asks:
        - Does Gmail have the current status correct?
        - Does Gmail capture important communications and timeline events?
        - Are action flags appropriate for the current state?
        - Are there critical gaps that would prevent action?

        This is more forgiving of missing system events like "Request opened"
        and focuses on practical utility for request management.

        Args:
            portal_analysis: Portal-based analysis (ground truth)
            gmail_analysis: Gmail-based analysis
            request_number: Request identifier

        Returns:
            PracticalCompletenessAssessment with pass/fail and explanation
        """
        from models import PracticalCompletenessAssessment

        prompt = f"""
You are evaluating whether a Gmail-based analysis captures the IMPORTANT information
for managing a public records request, compared to a portal-based analysis.

**REQUEST: {request_number}**

**PORTAL ANALYSIS** (Ground Truth - from live portal scraping):
```json
{json.dumps(portal_analysis, indent=2)}
```

**GMAIL ANALYSIS** (From email correspondence):
```json
{json.dumps(gmail_analysis, indent=2)}
```

# Evaluation Criteria

## Focus on PRACTICAL utility, not perfect matching

Ask these questions:

1. **Current Status**: Does Gmail have the current status correct or reasonably close?
   - OK if Gmail is MORE up-to-date than portal (emails arrive faster)
   - NOT OK if Gmail is way out of date

2. **Important Communications**: Does Gmail capture the key communications?
   - System events like "Request opened" are NOT important (no email sent)
   - Staff responses, document notifications, deadlines ARE important
   - Missing 1-2 system events is fine if communications are captured

3. **Action Flags**: Are action_required and agent_attention_needed appropriate?
   - Should match the actual state (closure, documents available, etc.)
   - Small mismatches OK if overall picture is correct

4. **Critical Information**: Any critical gaps?
   - Missing document releases = CRITICAL
   - Missing payment requests = CRITICAL
   - Missing important deadlines = CRITICAL
   - Missing "Request opened" = NOT CRITICAL

## Scoring

- **PASS**: Gmail provides enough information to manage this request effectively
  - May miss some system events (acceptable)
  - Has current status correct (or more up-to-date)
  - Has important communications and documents
  - Action flags are reasonable
  - Has deadlines/dates (even if formatted differently than portal)

- **FAIL**: Gmail is missing critical information
  - Wrong status by more than one step
  - Missing important staff communications with dates/deadlines
  - Missing document release notifications
  - Missing payment requests
  - Action flags completely wrong

## CRITICAL: Deadline Comparison Rules

When comparing deadlines between portal and Gmail:

1. **Check the `stated_deadlines` field in BOTH analyses**
   - Portal: `portal_analysis['stated_deadlines']`
   - Gmail: `gmail_analysis['stated_deadlines']`

2. **Dates can be in different formats but still match:**
   - "DECEMBER 15, 2025" = "12/15/2025" = "December 15, 2025" = SAME DATE
   - "within 10 days" = "10-day response timeline" = SAME DEADLINE
   - Extract actual dates and compare them, not the text format

3. **If Gmail has the date/deadline in stated_deadlines, it's NOT missing:**
   - Don't mark as "Missing deadline" if it appears in gmail_analysis['stated_deadlines']
   - Even if wording is different, if the DATE is present → NOT a critical gap

4. **Only mark as CRITICAL gap if:**
   - Portal has a specific date deadline (e.g., "December 15, 2025")
   - Gmail stated_deadlines is empty OR has a completely different date
   - NOT if it's just formatted differently

5. **Check the actual timeline events too:**
   - Deadlines often appear in timeline text
   - If timeline mentions "respond by December 15" → deadline IS captured

## Status Comparison Rules

When comparing status between portal and Gmail:

1. **Gmail can be more up-to-date than portal:**
   - Emails arrive in real-time
   - Portal data may be stale (last scraped hours/days ago)
   - If Gmail shows more recent events → trust Gmail status

2. **Check timeline dates:**
   - Compare most recent portal event date vs most recent Gmail event date
   - If Gmail has events from Dec 31 and portal last event is Dec 25 → Gmail is newer
   - Newer information is more authoritative

3. **"Closed" in Gmail but "Open" in portal:**
   - If Gmail has closure email → Gmail is correct
   - Portal likely not updated yet
   - This is NOT a critical gap, Gmail is MORE accurate

4. **Only mark as status mismatch if:**
   - Gmail contradicts itself (says open but has closure email)
   - Gmail clearly has stale/wrong information
   - NOT when Gmail is simply more recent than portal

## Output

Provide:
1. **verdict**: "PASS" or "FAIL"
2. **practical_score**: 0.0 to 1.0 (how practically useful is Gmail?)
3. **summary**: 2-3 sentences explaining verdict
4. **critical_gaps**: List of important missing information (empty if PASS)
5. **minor_gaps**: List of acceptable missing information (system events, etc.)
"""

        try:
            structured_llm = self.llm_client.with_structured_output(PracticalCompletenessAssessment)

            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=f"Evaluate Gmail analysis for request {request_number}")
            ]

            result = structured_llm.invoke(messages)
            logger.info(f"Practical completeness for {request_number}: {result.verdict} (score: {result.practical_score:.2f})")
            return result

        except Exception as e:
            logger.error(f"Failed to compare analyses: {str(e)}")
            from models import PracticalCompletenessAssessment
            return PracticalCompletenessAssessment(
                verdict="ERROR",
                practical_score=0.0,
                summary=f"Comparison error: {str(e)}",
                critical_gaps=[],
                minor_gaps=[]
            )

    def compare_analyses(
        self,
        portal_analysis: Optional[Dict[str, Any]],
        gmail_analysis: Optional[Dict[str, Any]],
        request_number: str = ""
    ) -> AnalysisComparisonResult:
        """
        Compare portal analysis vs Gmail analysis using LLM to validate Gmail quality.

        This is an evaluation/testing feature to confirm Gmail monitoring produces
        analysis that's at least as good as portal monitoring.

        Args:
            portal_analysis: The latest_analysis from portal monitoring (ground truth)
            gmail_analysis: The latest_analysis_gmail from Gmail monitoring (to validate)
            request_number: Request number for logging

        Returns:
            AnalysisComparisonResult with scores and findings
        """

        # Handle missing analyses
        if not portal_analysis or not gmail_analysis:
            return AnalysisComparisonResult(
                overall_quality_score=0.0,
                timeline_completeness_score=0.0,
                timeline_notes="Missing analysis data",
                status_accuracy_score=0.0,
                status_notes="Missing analysis data",
                flags_accuracy_score=0.0,
                flags_notes="Missing analysis data",
                document_payment_score=0.0,
                document_payment_notes="Missing analysis data",
                verdict="FAIL",
                summary="Cannot compare - one or both analyses missing",
                recommendations="Ensure both portal and Gmail monitoring have run for this request"
            )

        comparison_prompt = f"""
        You are evaluating the quality of a Gmail-based request analysis system by comparing it against portal-based analysis (ground truth).

        **Context**: We have TWO analysis systems for public records requests:
        1. **Portal Analysis** (ground truth): Generated by browser automation scraping the portal
        2. **Gmail Analysis** (being evaluated): Generated by analyzing email correspondence

        Both systems analyze the SAME underlying correspondence/timeline, so they SHOULD produce very similar results.

        **Your Task**: Evaluate if the Gmail analysis is at least as good as the portal analysis.

        **Request Number**: {request_number}

        **PORTAL ANALYSIS (Ground Truth)**:
        ```json
        {portal_analysis}
        ```

        **GMAIL ANALYSIS (Being Evaluated)**:
        ```json
        {gmail_analysis}
        ```

        **Evaluation Criteria**:

        1. **Timeline Completeness** (0.0-1.0):
           - Does Gmail capture ALL timeline events from portal?
           - Are dates and attributions (Staff:/You:) consistent?
           - Note: Gmail might have NEWER events if email arrived after portal check (this is GOOD)
           - Deduct points if Gmail MISSING events that portal has

        2. **Status Accuracy** (0.0-1.0):
           - Is current_status the same or logically consistent?
           - Example: Portal="Open", Gmail="Open" → 1.0 (perfect)
           - Example: Portal="Open", Gmail="Closed" → 0.0 (major inconsistency)

        3. **Flags Accuracy** (0.0-1.0):
           - Are action_required, needs_attention, attention_priority consistent?
           - Do they make sense given the timeline?
           - Example: If portal says HIGH priority for document download, Gmail should too

        4. **Document/Payment Accuracy** (0.0-1.0):
           - Are documents_available and outstanding_payments captured correctly?
           - Gmail should find same docs/payments as portal (or more if newer)

        **Overall Quality Score** (0.0-1.0):
        - Average of the 4 criteria scores
        - 0.9-1.0: Excellent - Gmail as good or better
        - 0.7-0.9: Good - Minor differences acceptable
        - 0.5-0.7: Fair - Some issues but usable
        - Below 0.5: Poor - Significant problems

        **Verdict**:
        - PASS: overall_quality_score >= 0.7 (Gmail analysis is acceptable)
        - FAIL: overall_quality_score < 0.7 (Gmail analysis needs improvement)

        **Important Notes**:
        - Gmail having NEWER events than portal is EXPECTED and GOOD (emails arrive in real-time)
        - Focus on whether Gmail MISSED anything portal caught
        - Both analyses use the same LLM prompt, so they should be structurally similar
        - The goal is to validate that email-based analysis works as well as portal-based
        """

        try:
            structured_llm = self.llm_client.with_structured_output(AnalysisComparisonResult)

            messages = [
                SystemMessage(content=comparison_prompt),
                HumanMessage(content=f"Compare these analyses for request {request_number} and provide detailed evaluation scores.")
            ]

            result = structured_llm.invoke(messages)

            logger.info(
                f"Analysis comparison for {request_number}: "
                f"{result.verdict} (score: {result.overall_quality_score:.2f})"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to compare analyses: {str(e)}")
            return AnalysisComparisonResult(
                overall_quality_score=0.0,
                timeline_completeness_score=0.0,
                timeline_notes=f"Comparison failed: {str(e)}",
                status_accuracy_score=0.0,
                status_notes=f"Comparison failed: {str(e)}",
                flags_accuracy_score=0.0,
                flags_notes=f"Comparison failed: {str(e)}",
                document_payment_score=0.0,
                document_payment_notes=f"Comparison failed: {str(e)}",
                verdict="FAIL",
                summary=f"Comparison error: {str(e)}",
                recommendations="Check logs for details"
            )

    def analyze_gmail_request_thread(
        self,
        request_number: str,
        request_text: str,
        portal_name: str,
        email_thread: list,
        current_status: str
    ):
        """
        Analyze public records request using COMPLETE email thread context.

        This is a Gmail-specific prompt optimized for email thread analysis.
        Unlike portal analysis which scrapes live pages, this receives ALL emails
        with FULL bodies to extract complete timeline without information loss.

        Args:
            request_number: Request identifier (e.g., "25-501")
            request_text: Original FOIA request text
            portal_name: Agency portal name
            email_thread: List of ALL emails in thread, each with:
                - date: Email timestamp
                - from: Sender address
                - subject: Email subject
                - body: FULL email body (not truncated)
            current_status: Current request status from database

        Returns:
            RequestDetailAnalysis: Structured analysis matching portal prompt schema
        """
        from models import RequestDetailAnalysis

        # Build complete email thread text
        thread_text = self._format_email_thread(email_thread)

        # Gmail-specific analysis prompt
        # Architecture: System context → Task → Principles → Business Rules → Examples → Output Schema
        analysis_prompt = f"""
<role>
You are a precise data extraction system for email-based public records request monitoring.
Your job is to extract factual information from email correspondence and apply consistent
business rules to determine when human intervention and agent action are required.
</role>

<task>
Analyze request {request_number} using the COMPLETE email thread provided below.
Extract ALL timeline events from ALL emails in chronological order.
</task>

<critical_email_context>
**IMPORTANT DIFFERENCES from portal analysis:**

1. **Source Material**: Complete bidirectional conversation (emails + sent messages), not live portal pages
2. **Timeline Strategy**: Extract ALL events from ALL message bodies (full context provided)
3. **Attribution**: Parse email signatures to identify staff names; use "You:" for user messages
4. **Multi-Event Messages**: Single messages often contain multiple timeline events - extract ALL
5. **Chronological Order**: Messages provided oldest-first (natural conversation order), timeline must also be oldest-first
6. **Bidirectional**: You have BOTH agency→user emails AND user→agency messages

**Conversation Thread Format**:
- Messages listed oldest → newest (chronological order)
- Includes BOTH directions: "EMAIL FROM AGENCY TO YOU" and "MESSAGE FROM YOU TO AGENCY"
- ALL message bodies provided in FULL (no truncation)
- Extract EVERY dated event from EVERY message (both directions)
- Do NOT rely on any previous analysis - this is fresh extraction
- **LAST message in thread = most recent communication** (check direction to see who's turn it is)
</critical_email_context>

<extraction_principles>
1. Extract information exactly as it appears in email bodies
2. Never paraphrase, summarize, or interpret - use exact text when possible
3. If information is not explicitly stated, use "Not specified" or "Not found"
4. Extract ALL timeline events from ALL emails chronologically
5. Parse signatures to identify staff names (e.g., "Sincerely, [Name]" → use that name)
6. Use standardized formats for all outputs
7. Be completely consistent - same input must produce identical output
8. Apply business rules consistently to determine attention flags
</extraction_principles>

<standardized_formats>
- **Status**: Must be one of: [Open, Closed, Under Review, Additional Information Required, Fee Payment Due, Documents Ready, On Hold, Completed, Denied, Withdrawn]
- **Staff Names**: Extract from signatures exactly (e.g., "Thomas W. Milliner:", "Emma Rodriguez:")
- **Timeline Events**: List ALL messages sequentially WITHOUT dates, just attribution and content (e.g., "You: [message]", "Staff: [message]")
  - Format: "[Attribution]: [message content]"
  - NO dates - messages are already in chronological order
  - The LAST event in the list = most recent message
  - Position in array determines chronology
</standardized_formats>

<extraction_framework>
Extract the following data fields:

1. **Request Status**: Find current status from most recent email
2. **Request Text**: Use the original request text provided in context
3. **Staff Contact Information**: Extract name from email signatures
4. **All Timeline Events**: ONE event per message, in sequential order WITHOUT dates (format: "Attribution: content")
5. **Document Information**: Any files, downloads, links mentioned in emails
6. **Payment Information**: Any fees, invoices, payment status mentioned
7. **Deadline Information**: Any specific dates or timelines mentioned
8. **Human Action Required**: Apply business rules consistently
9. **Agent Attention Needed**: Apply business rules consistently
10. **Attention Priority**: HIGH/MEDIUM/LOW based on priority framework
11. **Attention Reason**: Agent-facing instruction (not user-facing language)
</extraction_framework>

<business_rules_hierarchy>
**CRITICAL RULE**: Agent attention always implies human attention.
If agent_attention_needed = TRUE, then action_required MUST also be TRUE.

**Priority Framework with Automatic Flagging:**

**HIGH Priority** (Immediate Action Required):
- Document releases available for download
- Payment authorization required (any fees/invoices)
- Request denials requiring appeal decisions
- Legal/scope change decisions needed
- Same-day deadlines or urgent time constraints
- Complex policy interpretations requiring expertise
- System errors or portal access issues

AUTO-FLAGS: agent_attention_needed = TRUE, action_required = TRUE

**MEDIUM Priority** (Collaborative Human-Agent Processing):
- Courtesy responses needed ("thank you" acknowledgments)
- Status update acknowledgments
- Staff requests for routine clarification
- Administrative communications requiring polite response
- Timeline change notifications requiring acknowledgment
- Routine follow-ups on request progress

**COURTESY RESPONSE POLICY (CRITICAL)**:

**STEP 1: Check who sent the LAST timeline event:**
- Timeline events are in chronological order (oldest → newest)
- Look at the VERY LAST event in the all_timeline_events array
- Check if it starts with "You:"

**If LAST timeline event starts with "You:":**
- Ball is in agency's court, waiting for their response
- agent_attention_needed = FALSE
- action_required = FALSE
- attention_priority = LOW
- attention_reason = "No action required - waiting for agency response"
- STOP - do not evaluate further

**If LAST timeline event starts with anything else (staff name, agency name):**
- Agency just communicated, evaluate if response needed
- Continue to STEP 2

**STEP 2: Determine response type needed (only if last message was from agency):**
1. Asks specific question → Draft specific answer (MEDIUM priority)
2. Status update/notification → Draft acknowledgment/thank you (MEDIUM priority)
3. States "no response needed" → No action (LOW priority)
4. Request fully completed (all documents uploaded_to_drive) → No action (LOW priority)

AUTO-FLAGS: agent_attention_needed = TRUE, action_required = TRUE

**LOW Priority** (Monitoring Only):
- Pure informational status updates requiring no response
- Completed requests with no further action needed
- Routine progress notifications with no acknowledgment expected
- All documents with download_status = 'uploaded_to_drive'

AUTO-FLAGS: agent_attention_needed = FALSE, action_required = FALSE
</business_rules_hierarchy>

<attention_logic>
**action_required (Human Intervention Needed)**:
Set to TRUE when:
- Any HIGH priority situation occurs
- Any MEDIUM priority situation occurs
- Human judgment, authorization, or external resources required
- Agent attention is needed (hierarchical rule)

**agent_attention_needed (Agent Should Act)**:
Set to TRUE when:
- Any HIGH priority situation occurs
- Any MEDIUM priority situation occurs
- Autonomous agent can and should act (with human oversight)
- Documents need downloading (NOT yet uploaded_to_drive)
- Communications need drafting (subject to human approval)

Set to FALSE when:
- Request completed and all documents uploaded_to_drive
- No action needed from agent or human

**attention_priority**:
- HIGH: Document releases (NOT uploaded_to_drive), payments, denials, urgent deadlines
- MEDIUM: Courtesy responses, acknowledgments, routine clarifications
- LOW: Monitoring only, completed requests, documents fully uploaded_to_drive

**attention_reason** (CRITICAL FORMAT):
- MUST be written from SYSTEM's perspective TO the agent
- MUST specify what AGENT should do
- HIGH: "Human authorization required for [action]" OR "Immediate agent action required: [task]"
- MEDIUM: "Agent should draft [response type] for human review and approval"
- LOW: "No action required - monitoring only"
- NEVER use "your" or "you" referring to user
- NEVER copy user-facing portal messages
</attention_logic>

<validation_rules>
**Flag Consistency Checks**:
1. If attention_priority = HIGH → agent_attention_needed = TRUE AND action_required = TRUE
2. If attention_priority = MEDIUM → agent_attention_needed = TRUE AND action_required = TRUE
3. If attention_priority = LOW → agent_attention_needed = FALSE AND action_required = FALSE
4. If agent_attention_needed = TRUE → action_required MUST = TRUE
5. Payment/document scenarios → Always HIGH unless uploaded_to_drive
6. Courtesy responses → Always MEDIUM with both flags TRUE
7. Documents uploaded_to_drive → Both flags FALSE, priority LOW
8. attention_reason MUST be agent-facing instructions
</validation_rules>

<email_attribution_rules>
**Email Signature Parsing**:
- Look for signatures: "Sincerely, [Name]", "[Name], [Title]", "Best regards, [Name]"
- Use EXACT name from signature for attribution (e.g., "Thomas W. Milliner:")
- If from:messages@nextrequest.com but no signature → "Staff:"
- If email clearly from requester → "You:"
- System notifications → "System:"
- Unknown → "Unknown sender:"

**Multi-Event Email Extraction**:
Many emails contain multiple dated events in body:
- "12/20: Request opened"
- "12/22: Legal review completed"
- "12/28: Documents prepared"

Extract EACH as separate timeline event with same attribution.
</email_attribution_rules>

<email_specific_examples>
<example_1_email_timeline_extraction>
**Scenario**: Three emails in thread about document release

**Email 1** (Oldest - Jan 5):
From: messages@nextrequest.com
Subject: Request #25-501 Opened
Body: "Your request has been received and is under review.
Sincerely, Records Admin Team"

**Email 2** (Jan 10):
From: messages@nextrequest.com
Subject: Request #25-501 Status Update
Body: "We are processing your request. Estimated completion: Jan 15.
Thomas W. Milliner, Senior Records Specialist"

**Email 3** (Newest - Jan 15):
From: messages@nextrequest.com
Subject: Documents Ready - Request #25-501
Body: "Your documents are ready for download at: [link]
Thomas W. Milliner, Senior Records Specialist"

**CORRECT Analysis** ✅:
all_timeline_events: [
  "You: [original FOIA request]",
  "Records Admin Team: Your request has been received and is under review",
  "Thomas W. Milliner: We are processing your request. Estimated completion: Jan 15",
  "Thomas W. Milliner: Your documents are ready for download"
]
agent_attention_needed: TRUE
action_required: TRUE
attention_priority: HIGH
attention_reason: "Immediate agent action required: download available documents before expiration"

**WRONG** ❌:
- Including dates (NO dates allowed - use position for chronology)
- Only extracting from latest email (must include ALL messages)
- Truncating older emails to 200 chars
- Using "Staff:" when "Thomas W. Milliner" in signature
</example_1_email_timeline_extraction>

<example_2_multi_event_single_email>
**Scenario**: Single email contains multiple timeline events

Email Body:
"Update on request #25-676:
- 12/20: Request opened and assigned to legal team
- 12/22: Legal review completed, no exemptions apply
- 12/28: Documents prepared for release
- 01/02: Documents now available for download

Please access documents at: [link]
Emma Rodriguez, FOIA Officer"

**CORRECT Analysis** ✅:
all_timeline_events: [
  "12/20/2024: Emma Rodriguez: Request opened and assigned to legal team",
  "12/22/2024: Emma Rodriguez: Legal review completed, no exemptions apply",
  "12/28/2024: Emma Rodriguez: Documents prepared for release",
  "01/02/2025: Emma Rodriguez: Documents now available for download"
]
documents_available: ["Documents available at link"]
agent_attention_needed: TRUE
action_required: TRUE
attention_priority: HIGH
attention_reason: "Immediate agent action required: download available documents"
</example_2_multi_event_single_email>

<example_3_courtesy_response_needed>
**Scenario**: Staff update requiring acknowledgment

Email Body:
"We've received your request and are processing it. Estimated completion: 15 business days.
Thank you for your patience.
Sarah Johnson, Records Coordinator"

**CORRECT Analysis** ✅:
all_timeline_events: [
  "You: [original FOIA request]",
  "Sarah Johnson: We've received your request and are processing it. Estimated completion: 15 business days"
]
# LAST message is from Staff → need response
agent_attention_needed: TRUE
action_required: TRUE
attention_priority: MEDIUM
attention_reason: "Agent should draft thank you response for human review and approval"
</example_3_courtesy_response_needed>

<example_4_courtesy_already_sent>
**Scenario**: Staff update already acknowledged

**CORRECT Analysis** ✅:
all_timeline_events: [
  "You: [original FOIA request]",
  "Staff: Processing your request",
  "You: Thank you for the update"
]
# LAST message is from "You:" → ball in their court
agent_attention_needed: FALSE
action_required: FALSE
attention_priority: LOW
attention_reason: "No action required - waiting for agency response"

**Why**: Latest staff communication already acknowledged.
</example_4_courtesy_already_sent>
</email_specific_examples>

<strict_requirements>
1. Extract ONE timeline event per message - no multiple events, no summarization
2. DO NOT include dates in timeline events - messages are already in chronological order
3. Quote key text from email bodies when possible
4. List all documents, fees, deadlines mentioned in their respective fields
5. Apply business rules consistently - identical scenarios produce identical flags
6. Use "Not found" for missing information
7. Timeline order = message order (oldest → newest, pre-sorted for you)
8. Extract complete staff names from signatures
9. Extract full original request text without modification
10. Validate flag consistency before output
11. Parse email signatures for attribution
12. Check LAST timeline event to see who sent most recent message
13. Do NOT rely on previous analysis - extract fresh from provided emails
</strict_requirements>

<output_validation>
Before submitting extraction, verify:
- [ ] Timeline events have NO dates - just "Attribution: content"
- [ ] Timeline has ONE event per message in sequential order
- [ ] LAST timeline event = most recent message (check direction to determine who's turn it is)
- [ ] Status uses exact terminology from standardized list
- [ ] Priority level correctly determines flag values
- [ ] agent_attention_needed=TRUE only when action_required=TRUE
- [ ] Payment/document scenarios flagged HIGH (unless uploaded_to_drive)
- [ ] Courtesy scenarios: check if LAST message is from "You:" (if yes, no action needed)
- [ ] attention_reason is agent-facing instruction
- [ ] Timeline includes ALL messages provided (one per message)
- [ ] Staff names extracted from signatures when available
- [ ] No timeline events truncated or summarized
</output_validation>

---

**REQUEST CONTEXT**:
Request Number: {request_number}
Portal/Agency: {portal_name}
Current Status (from DB): {current_status}

Original Request Text:
{request_text}

---

**COMPLETE EMAIL THREAD** (oldest first - chronological conversation order):

{thread_text}

---

Extract structured data from the email thread above, applying business rules consistently.
Build COMPLETE timeline from ALL emails provided. Parse signatures for staff attribution.
"""

        try:
            from models import RequestDetailAnalysis

            structured_llm = self.llm_client.with_structured_output(RequestDetailAnalysis)

            messages = [
                SystemMessage(content=analysis_prompt),
                HumanMessage(content=[{
                    "type": "text",
                    "text": f"Analyze request {request_number} using the complete email thread. Extract ALL timeline events from ALL emails chronologically."
                }])
            ]

            result = structured_llm.invoke(messages)
            logger.info(f"Gmail thread analysis completed for {request_number}")
            return result

        except Exception as e:
            logger.error(f"Failed to analyze Gmail thread: {str(e)}")
            # Import here to avoid circular dependency
            from models import RequestDetailAnalysis
            return RequestDetailAnalysis(
                request_number=request_number,
                current_status="Analysis failed",
                request_text=request_text,
                all_timeline_events=[],
                documents_available=[],
                outstanding_payments=[],
                staff_contact="Unknown",
                stated_deadlines=[],
                action_required=False,
                needs_attention=False,
                attention_reason=f"Analysis error: {str(e)}",
                attention_priority="low"
            )

    def _format_email_thread(self, emails: list) -> str:
        """
        Format complete conversation thread for LLM analysis.

        Provides ALL communications with FULL bodies (no truncation):
        - Emails from agency → user (incoming)
        - Messages from user → agency (outgoing)

        Sorted chronologically to enable complete timeline extraction.

        Args:
            emails: List of message dicts with date, from, subject, body, direction

        Returns:
            Formatted string with complete conversation
        """
        if not emails:
            return "No messages in conversation"

        thread_parts = []

        for i, message in enumerate(emails, 1):
            # Determine message type and direction indicator
            direction = message.get('direction', 'incoming')
            msg_type = message.get('type', 'email')

            if direction == 'outgoing':
                direction_label = "MESSAGE FROM YOU TO AGENCY"
            else:
                direction_label = "EMAIL FROM AGENCY TO YOU"

            message_section = f"""
=== MESSAGE {i} ({direction_label}) ===
Date: {message.get('date', 'Unknown')}
From: {message.get('from', 'Unknown')}
Subject: {message.get('subject', 'No subject')}

Body:
{message.get('body', 'No body')}

---
"""
            thread_parts.append(message_section)

        return "\n".join(thread_parts)


def fuzzy_match_portal(agency_name: str, candidate_requests: list) -> Optional[Dict[str, Any]]:
    """
    Fuzzy match agency name against portal URLs in candidate requests.

    Args:
        agency_name: Extracted agency name (e.g., "City of Hollister")
        candidate_requests: List of request dicts with 'portal_name' field

    Returns:
        Best matching request dict, or None if no good match found

    Example:
        >>> candidates = [
        ...     {'portal_name': 'https://cityofhollister-ca.nextrequest.com/', 'id': '123'},
        ...     {'portal_name': 'https://cityofmanteca.nextrequest.com/', 'id': '456'}
        ... ]
        >>> fuzzy_match_portal('City of Hollister', candidates)
        {'portal_name': 'https://cityofhollister-ca.nextrequest.com/', 'id': '123'}
    """

    if not candidate_requests:
        return None

    # Fast path: if only one candidate, return it
    if len(candidate_requests) == 1:
        return candidate_requests[0]

    # Normalize agency name for matching
    normalized_agency = _normalize_string(agency_name)

    best_match = None
    best_score = 0.0
    threshold = 0.8  # Minimum similarity score

    for request in candidate_requests:
        portal_name = request.get('portal_name', '')

        # Extract domain part for matching
        # "https://cityofhollister-ca.nextrequest.com/" -> "cityofhollister"
        normalized_portal = _normalize_string(portal_name)

        # Calculate similarity score
        score = difflib.SequenceMatcher(None, normalized_agency, normalized_portal).ratio()

        logger.debug(f"Matching '{normalized_agency}' vs '{normalized_portal}': {score:.2f}")

        if score > best_score:
            best_score = score
            best_match = request

    # Return best match if above threshold
    if best_score >= threshold:
        logger.info(f"Matched '{agency_name}' to '{best_match['portal_name']}' (score: {best_score:.2f})")
        return best_match
    else:
        logger.warning(f"No good match for '{agency_name}' (best score: {best_score:.2f})")
        return None


def _normalize_string(s: str) -> str:
    """
    Normalize string for fuzzy matching.

    Removes: spaces, hyphens, punctuation, protocol, domains
    Converts to lowercase

    Example:
        >>> _normalize_string("City of Hollister")
        'cityofhollister'
        >>> _normalize_string("https://cityofhollister-ca.nextrequest.com/")
        'cityofhollister'
    """

    # Remove protocol
    s = s.replace('https://', '').replace('http://', '')

    # Remove common domain parts
    s = s.replace('.nextrequest.com', '')
    s = s.replace('.com', '')
    s = s.replace('.gov', '')

    # Remove punctuation and spaces
    s = s.lower()
    s = s.replace(' ', '')
    s = s.replace('-', '')
    s = s.replace('_', '')
    s = s.replace('/', '')
    s = s.replace('.', '')

    return s
