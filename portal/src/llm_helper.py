import base64
import logging
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, SystemMessage
from models import RequestTableAnalysis, RequestDetailAnalysis, MultiRequestSummary
import html2text

logger = logging.getLogger(__name__)

class LLMHelper:
    """LLM helper specifically designed for Phase 3 request analysis"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def analyze_requests_table_page(self, screenshot_base64: str, page_text: str) -> RequestTableAnalysis:
        """Analyze the 'All requests' table page using multimodal LLM"""
        
        analysis_prompt = """
        You are analyzing a screenshot of the "All requests" page from a public records portal.
        
        This page shows a table with multiple public records requests. Your job is to:
        
        1. **Count the requests**: How many requests are visible in the table?
        2. **Extract request numbers**: What are the request IDs/numbers shown?
        3. **Identify status issues**: Which requests appear to need attention (look for warning colors, "action required" status, etc.)?
        4. **Understand table structure**: Can you identify the columns (Request, Status, Description, Department, Contact, etc.)?
        5. **Find navigation elements**: What buttons, links, or actions are available?
        6. **Provide quick insights**: What stands out about these requests?
        
        Look carefully at:
        - Request numbers (usually clickable links like "25-370")
        - Status indicators (open, closed, pending, action required)
        - Any visual cues about urgency (colors, icons, alerts)
        - Available actions (buttons, links, filters)
        - Overall patterns in the requests
        
        Focus on actionable information that would help the user understand their request portfolio.
        """
        
        try:
            structured_llm = self.llm_client.with_structured_output(RequestTableAnalysis)
            
            messages = [
                SystemMessage(content=analysis_prompt),
                HumanMessage(content=[
                    {
                        "type": "text",
                        "text": f"Analyze this requests table page. Here's some page text for context:\n\n{page_text[:1500]}...\n\nPlease provide a comprehensive analysis of what you see."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}"
                        }
                    }
                ])
            ]
            
            result = structured_llm.invoke(messages)
            logger.info(f"Requests table analysis completed. Found {result.total_requests_found} requests")
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze requests table: {str(e)}")
            return RequestTableAnalysis(
                total_requests_found=0,
                request_numbers=[],
                requests_with_issues=[],
                table_structure_understood=False,
                navigation_elements=[],
                quick_insights=[f"Analysis failed: {str(e)}"]
            )
    
    def analyze_request_detail_page(self, screenshot_base64: str, page_text: str, request_number: str = "") -> RequestDetailAnalysis:

        """Analyze individual request detail page using multimodal LLM"""
        
        analysis_prompt = f"""
        <role>
        You are a precise data extraction system for a human-in-the-loop autonomous public records agent. Your job is to extract factual information from request pages and apply consistent business rules to determine when human intervention and agent action are required.
        </role>

        <task>
        Extract structured data from public records request {request_number} using the provided page content. Apply hierarchical flagging rules to ensure consistent attention queue management.
        </task>

        <extraction_principles>
        1. Extract information exactly as it appears in the source
        2. Never paraphrase, summarize, or interpret - use exact text when possible
        3. If information is not explicitly stated, use "Not specified" or "Not found"
        4. Extract ALL timeline events chronologically, don't filter for importance
        5. Use standardized formats for all outputs
        6. Be completely consistent - same input must produce identical output
        7. Apply business rules consistently to determine attention flags
        </extraction_principles>

        <standardized_formats>
        - **Status**: Must be one of: [Open, Closed, Under Review, Additional Information Required, Fee Payment Due, Documents Ready, On Hold, Completed, Denied, Withdrawn]
        - **Dates**: Always MM/DD/YYYY format as found in source
        - **Staff Names**: Extract exactly as shown (e.g., "Law Admin 10", "Emma A. Mekinda")
        - **Timeline Events**: List ALL events chronologically with exact attribution
        </standardized_formats>

        <extraction_framework>
        Extract the following data fields:

        1. **Request Status**: Find the current status indicator and use exact text
        2. **Request Text**: Extract the complete original request text exactly as submitted
        3. **Staff Contact Information**: Extract name and department exactly as shown
        4. **All Timeline Events**: Every dated event found, in chronological order
        5. **Document Information**: List all files, downloads, invoices mentioned
        6. **Payment Information**: Any fees, invoices, payment status mentioned
        7. **Deadline Information**: Any specific dates or timelines mentioned
        8. **Human Action Required**: Apply business rules to determine if human intervention needed
        9. **Agent Attention Needed**: Apply business rules to determine if agent should act
        10. **Attention Priority**: Apply priority framework consistently
        11. **Attention Reason**: Explain specific action needed based on priority level
        </extraction_framework>

        <business_rules_hierarchy>
        **CRITICAL RULE**: In this human-in-the-loop system, agent attention always implies human attention.
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
        DEFAULT BEHAVIOR: When staff sends ANY communication, flag for courtesy response UNLESS:
        1. A thank you/acknowledgment was already sent as the most recent "You:" response in timeline
        2. Staff message explicitly states "no response needed" or "do not reply"
        3. Request is fully completed (all documents uploaded_to_drive)

        **How to check if thank you already sent:**
        - Examine timeline events in chronological order
        - Find the MOST RECENT staff message
        - Check if there is a "You:" response AFTER that staff message
        - If "You:" response exists and appears to be acknowledgment/thank you → do NOT flag again
        - If "You:" response does NOT exist after most recent staff message → FLAG for courtesy response
        - If new staff message came AFTER your last thank you → FLAG for NEW courtesy response

        **When in doubt:** Default to flagging for courtesy response (MEDIUM priority, "Agent should draft thank you response for human review and approval")

        AUTO-FLAGS: agent_attention_needed = TRUE, action_required = TRUE

        **LOW Priority** (Monitoring Only):
        - Pure informational status updates requiring no response
        - Completed requests with no further action needed
        - Routine progress notifications with no acknowledgment expected
        - CRITICAL: All documents with download_status = 'uploaded_to_drive' means request is complete

        AUTO-FLAGS: agent_attention_needed = FALSE, action_required = FALSE
        IMPORTANT: When documents are uploaded_to_drive, you MUST set agent_attention_needed = FALSE
        </business_rules_hierarchy>

        <attention_logic>
        **action_required (Human Intervention Needed)**:
        Set to TRUE when:
        - Any HIGH priority situation occurs
        - Any MEDIUM priority situation occurs (human reviews agent-drafted responses)
        - Human judgment, authorization, or external resources are required
        - Agent attention is needed (hierarchical rule: agent attention → human attention)

        **agent_attention_needed (Agent Should Act)**:
        Set to TRUE when:
        - Any HIGH priority situation occurs
        - Any MEDIUM priority situation occurs (agent drafts responses for human review)
        - The autonomous agent can and should take action (with human oversight)
        - Documents need downloading and organization (NOT yet uploaded_to_drive)
        - Communications need drafting (subject to human approval)

        Set to FALSE when:
        - Request is completed and all documents are uploaded_to_drive
        - No action needed from agent or human

        **attention_priority**:
        - HIGH: Document releases (NOT yet uploaded_to_drive), payments, denials, urgent deadlines, legal decisions
        - MEDIUM: Courtesy responses, acknowledgments, routine clarifications, administrative comms
        - LOW: Pure monitoring, informational updates, completed requests, documents fully uploaded_to_drive

        **attention_reason** (CRITICAL FORMAT REQUIREMENTS):
        - MUST be written from the SYSTEM's perspective TO the agent (not user-facing language)
        - MUST specify what the AGENT should do (not what the user should do)
        - HIGH priority: "Human authorization required for [specific action]" OR "Immediate agent action required: [specific task]"
        - MEDIUM priority: "Agent should draft [type of response] for human review and approval"
          * Examples: "Agent should draft thank you response for staff acknowledgment and monitoring for human review and approval"
          * "Agent should draft acknowledgment of timeline extension for human review and approval"
          * "Agent should draft clarification response for human review and approval"
        - LOW priority: "No action required - monitoring only"
        - NEVER use "your" or "you" when referring to the user - this is an INTERNAL flag for the agent
        - NEVER copy user-facing portal messages directly into attention_reason
        </attention_logic>

        <validation_rules>
        **Flag Consistency Checks**:
        1. If attention_priority = HIGH → agent_attention_needed = TRUE AND action_required = TRUE
        2. If attention_priority = MEDIUM → agent_attention_needed = TRUE AND action_required = TRUE
        3. If attention_priority = LOW → agent_attention_needed = FALSE AND action_required = FALSE
        4. If agent_attention_needed = TRUE → action_required MUST = TRUE (hierarchical rule)
        5. Payment/document scenarios → Always HIGH priority with both flags TRUE (UNLESS documents uploaded_to_drive)
        6. Courtesy response scenarios → Always MEDIUM priority with both flags TRUE
        7. Documents all uploaded_to_drive → agent_attention_needed = FALSE, action_required = FALSE, attention_priority = LOW
        8. attention_reason MUST follow format requirements - agent-facing instructions only, never user-facing language
        </validation_rules>

        <attribution_rules>
        - Use "You:" only for messages clearly from the requester
        - Use exact staff names when provided (e.g., "Thomas W. Milliner:", "Law Admin 10:")
        - Use "Staff:" only when specific name is not available
        - Use "System:" for automated notifications
        - Never guess at attribution - if unclear, use "Unknown sender:"
        </attribution_rules>

        <examples>
        <example_1>
        **Scenario**: Document Release Notification
        **Source Text**: "Staff message from Records Admin 5: Your requested documents are now available for download. Please access them through the following secure link: [https://portal.gov/download/ABC123]. Documents must be downloaded within 30 days or they will be removed from the system."

        **Agent Analysis**:
        - action_required: TRUE (human oversight required for document organization)
        - agent_attention_needed: TRUE (agent should download and organize documents)
        - attention_reason: "Immediate agent action required: download available documents before 30-day expiration"
        - attention_priority: HIGH
        </example_1>

        <example_2>
        **Scenario**: Payment Authorization Required
        **Source Text**: "Invoice #INV-2024-7891 generated for $350.00. Payment is required to process your public records request. Please authorize payment within 10 business days to avoid request closure. Contact billing department at billing@agency.gov with questions."

        **Agent Analysis**:
        - action_required: TRUE (human authorization required for payment)
        - agent_attention_needed: TRUE (agent should prepare payment summary for human review)
        - attention_reason: "Human authorization required for $350.00 payment authorization"
        - attention_priority: HIGH
        </example_2>

        <example_3>
        **Scenario**: Request Denial Requiring Appeal Decision
        **Source Text**: "Legal Counsel determination: Request #REQ-2024-1547 denied under FOIA Exemption 7(A) - ongoing investigation. You have 30 days to submit an administrative appeal if you disagree with this determination. Appeals must be submitted in writing to appeals@agency.gov."

        **Agent Analysis**:
        - action_required: TRUE (human decision required on whether to appeal)
        - agent_attention_needed: TRUE (agent should prepare appeal options analysis)
        - attention_reason: "Human authorization required for appeal decision - 30-day deadline approaching"
        - attention_priority: HIGH
        </example_3>

        <example_4>
        **Scenario**: Thank You Acknowledgment - Status Update
        **Source Text**: "Case Manager Update: We're making good progress on your request. Our team has located the relevant files and we're currently reviewing them for any redactions required. We expect to have documents ready within 2-3 weeks. Thank you for your patience."

        **Agent Analysis**:
        - action_required: TRUE (human review required for courtesy response)
        - agent_attention_needed: TRUE (agent should draft thank you acknowledgment)
        - attention_reason: "Agent should draft thank you response for human review and approval"
        - attention_priority: MEDIUM
        </example_4>

        <example_5>
        **Scenario**: Thank You Acknowledgment - Timeline Extension
        **Source Text**: "Processing Update from FOIA Officer: Due to the volume of records requested, we need to extend our response time by an additional 10 business days as permitted under statute. New estimated completion date is 11/15/2024. We apologize for any inconvenience."

        **Agent Analysis**:
        - action_required: TRUE (human review required for courtesy response)
        - agent_attention_needed: TRUE (agent should draft acknowledgment of timeline extension)
        - attention_reason: "Agent should draft thank you response for timeline extension for human review and approval"
        - attention_priority: MEDIUM
        </example_5>

        <example_6>
        **Scenario**: Staff Clarification Request
        **Source Text**: "Records Specialist inquiry: Could you please clarify the specific date range you're looking for in your request? You mentioned 'recent incidents' but we need exact dates to properly search our database. Please provide start and end dates (MM/DD/YYYY format)."

        **Agent Analysis**:
        - action_required: TRUE (human review required for clarification response)
        - agent_attention_needed: TRUE (agent should draft clarification response)
        - attention_reason: "Agent should draft clarification response with date range for human review and approval"
        - attention_priority: MEDIUM
        </example_6>

        <example_7>
        **Scenario**: Administrative Communication Requiring Polite Response
        **Source Text**: "Public Information Officer: We've received your request and want to confirm we have the correct mailing address for any physical document delivery: 123 Main Street, Suite 200, Oakland, CA 94612. Please confirm this address is current or provide an updated address if needed."

        **Agent Analysis**:
        - action_required: TRUE (human review required for address confirmation response)
        - agent_attention_needed: TRUE (agent should draft address confirmation response)
        - attention_reason: "Agent should draft address confirmation response for human review and approval"
        - attention_priority: MEDIUM
        </example_7>

        <example_8>
        **Scenario**: Monitoring After Clarification Sent - Waiting for Response
        **Source Text**: "System Update: Clarification request sent to agency on 09/01/2024. Awaiting staff response to requester's additional information. Agent should monitor for staff response and provide status updates or further assistance if required."

        **Agent Analysis**:
        - action_required: FALSE (no immediate human decision needed)
        - agent_attention_needed: FALSE (monitoring only, no active drafting required)
        - attention_reason: "No action required - monitoring for staff response"
        - attention_priority: LOW
        </example_8>

        <example_9>
        **Scenario**: Routine Status Update - No Response Required
        **Source Text**: "System notification: Request #REQ-2024-3321 status updated to 'Under Review'. Processing continues normally. No action required from requester at this time. Estimated processing time: 15-20 business days."

        **Agent Analysis**:
        - action_required: FALSE (no human decision needed)
        - agent_attention_needed: FALSE (routine status update, agent monitoring sufficient)
        - attention_reason: "No action required - monitoring only"
        - attention_priority: LOW
        </example_9>

        <example_10>
        **Scenario**: Completed Request - Final Organization
        **Source Text**: "Final Notice: All documents for Request #REQ-2024-2156 have been successfully delivered. Your request is now marked as COMPLETED. If you have any questions about the provided materials, please contact us within 30 days. Thank you for using our public records portal."

        **Agent Analysis**:
        - action_required: FALSE (request completed, no further human action needed)
        - agent_attention_needed: FALSE (completion notification only)
        - attention_reason: "No action required - request completed successfully"
        - attention_priority: LOW
        </example_10>

        <example_11>
        **Scenario**: Complex Multi-Flag Scenario - Payment + Documents + Deadline
        **Source Text**: "URGENT: Multiple items require attention for Request #REQ-2024-8833: (1) Invoice #INV-789 for $125.00 requires payment authorization, (2) Partial document release available for download at [secure-link], (3) Outstanding payment must be resolved within 48 hours or request will be suspended. Please contact Legal Department for payment questions."

        **Agent Analysis**:
        - action_required: TRUE (human payment authorization required)
        - agent_attention_needed: TRUE (agent should download available documents and prepare payment authorization summary)
        - attention_reason: "Human authorization required for $125.00 payment + immediate agent action required: download available documents before 48-hour deadline"
        - attention_priority: HIGH
        </example_11>

        <example_12_incorrect>
        **Scenario**: Request Opened - Initial Acknowledgment Needed
        **Source Text**: "Your public records request (#25-162) is now open. The City must determine within 10 days if it has responsive records. Please monitor your email for updates."

        **WRONG Agent Analysis** ❌:
        - attention_reason: "Your public records request (#25-162) is now open and requires your attention because the City must determine within 10 days if it has responsive records. Please monitor your email for updates."

        **CORRECT Agent Analysis** ✅:
        - action_required: TRUE (human review required for courtesy response)
        - agent_attention_needed: TRUE (agent should draft thank you acknowledgment)
        - attention_reason: "Agent should draft thank you response for staff acknowledgment and monitoring for human review and approval"
        - attention_priority: MEDIUM

        **Why the first is WRONG**:
        - Uses "your" and "you" (user-facing language instead of agent-facing)
        - Copied portal message directly instead of specifying agent action
        - Doesn't specify what the agent should DO
        </example_12_incorrect>

        <example_13_courtesy_response_check>
        **Scenario**: Staff Update - Check if Thank You Already Sent
        **Timeline Events**:
        - 01/15/2025: Staff: "We've received your request and are processing it."
        - 01/15/2025: You: "Thank you for the confirmation. I look forward to hearing from you."
        - 01/20/2025: Staff: "We need an additional 5 days to complete the review."

        **CORRECT Agent Analysis** ✅:
        - Review timeline: Most recent staff message is 01/20 timeline extension
        - Check for response: Last "You:" message was 01/15 thank you (BEFORE the 01/20 staff message)
        - New staff communication AFTER last thank you → FLAG for NEW courtesy response
        - action_required: TRUE
        - agent_attention_needed: TRUE
        - attention_reason: "Agent should draft acknowledgment of timeline extension for human review and approval"
        - attention_priority: MEDIUM

        **WRONG Analysis** ❌:
        - Seeing a thank you in timeline and assuming no new response needed
        - Must check chronological order: new staff message AFTER thank you requires NEW response
        </example_13_courtesy_response_check>

        <example_14_no_duplicate_thank_you>
        **Scenario**: Already Acknowledged - Don't Draft Duplicate
        **Timeline Events**:
        - 01/15/2025: Staff: "We've received your request and are processing it."
        - 01/15/2025: You: "Thank you for the confirmation. I appreciate the update."

        **CORRECT Agent Analysis** ✅:
        - Review timeline: Most recent staff message is 01/15 confirmation
        - Check for response: "You:" thank you exists on 01/15 AFTER the staff message
        - Already acknowledged → do NOT flag for courtesy response
        - action_required: FALSE
        - agent_attention_needed: FALSE
        - attention_reason: "No action required - monitoring only"
        - attention_priority: LOW

        **Why**: Latest staff communication has already been acknowledged. No duplicate needed.
        </example_14_no_duplicate_thank_you>
        </examples>

        <strict_requirements>
        1. Extract ALL timeline events found - do not summarize or combine messages
        2. Use exact dates as they appear in the source material
        3. Quote exact text from staff messages when possible
        4. List all documents, fees, and deadlines mentioned
        5. Apply business rules consistently - same scenario must produce identical flags
        6. Use "Not found" for missing information rather than making assumptions
        7. Maintain chronological order for all timeline events
        8. Extract complete staff names and titles when available
        9. Extract the full original request text without summarization or paraphrasing
        10. Validate flag consistency before finalizing output
        </strict_requirements>

        <output_validation>
        Before submitting your extraction, verify:
        - [ ] All dates are in MM/DD/YYYY format as found in source
        - [ ] All timeline events are listed chronologically with exact attribution
        - [ ] Status uses exact terminology from the standardized list
        - [ ] Priority level correctly determines flag values per business rules
        - [ ] agent_attention_needed=TRUE only when action_required=TRUE (hierarchical rule)
        - [ ] Payment/document scenarios flagged as HIGH priority with both flags TRUE
        - [ ] Courtesy scenarios flagged as MEDIUM priority with both flags TRUE
        - [ ] attention_reason matches the priority level and required action
        - [ ] All timeline events are included, not filtered
        - [ ] Direct quotes are used where possible instead of paraphrasing
        - [ ] No subjective interpretations or inferences made
        - [ ] Flag consistency rules followed without exceptions
        </output_validation>

        Extract the structured data from the provided page content for request {request_number}. Apply the business rules hierarchy consistently to ensure proper attention queue management and human-agent workflow coordination.
        """

        try:
            structured_llm = self.llm_client.with_structured_output(RequestDetailAnalysis)

            print(f"Page text: {page_text}")
            
            messages = [
                SystemMessage(content=analysis_prompt),
                HumanMessage(content=[
                    {
                        "type": "text",
                        "text": f"Analyze this request detail page for request {request_number}. Here's the page text:\n\n{page_text}...\n\nPlease provide a comprehensive analysis focusing on status, actions needed, and key insights."
                    },
                ])
            ]
            
            result = structured_llm.invoke(messages)
            logger.info(f"Request detail analysis completed for {request_number}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze request detail: {str(e)}")
            return RequestDetailAnalysis(
                request_number=request_number,
                current_status="Analysis failed",
                action_required=False,
                action_description="",
                timeline_summary=[],
                correspondence_summary=f"Could not analyze: {str(e)}",
                documents_available=[],
                outstanding_payments=[],
                staff_contact="Unknown",
                estimated_completion="Unknown",
                key_insights=[f"Analysis error: {str(e)}"],
                next_steps="Manually review the request"
            )
    
    def generate_multi_request_summary(self, individual_analyses: List[RequestDetailAnalysis]) -> MultiRequestSummary:
        """Generate overall summary across multiple requests using text LLM"""
        
        if not individual_analyses:
            return MultiRequestSummary(
                total_requests=0,
                urgent_requests=[],
                completed_requests=[],
                waiting_requests=[],
                overall_status="No requests analyzed",
                recommended_actions=[],
                summary="No request data available for analysis"
            )
        
        summary_prompt = f"""
        You are providing an executive summary of multiple public records requests for a user.
        
        Here are the individual request analyses:
        
        {self._format_analyses_for_prompt(individual_analyses)}
        
        Your job is to:
        
        1. **Categorize requests**: Which need urgent attention, which are completed, which are waiting?
        2. **Identify patterns**: Are there common issues or themes across requests?
        3. **Prioritize actions**: What should the user focus on first?
        4. **Assess overall health**: How is the user's request portfolio doing?
        5. **Provide strategic guidance**: What should their next steps be?
        
        Focus on:
        - **URGENT**: Requests needing immediate user action
        - **COMPLETED**: Requests with documents ready or fully closed
        - **WAITING**: Requests in progress waiting for agency response
        - **BLOCKED**: Requests stuck due to payments or other issues
        
        Provide clear, actionable recommendations that help the user manage their public records requests effectively.
        """
        
        try:
            structured_llm = self.llm_client.with_structured_output(MultiRequestSummary)
            
            result = structured_llm.invoke([
                SystemMessage(content=summary_prompt),
                HumanMessage(content="Generate a comprehensive summary of all these public records requests with clear action items.")
            ])
            
            logger.info(f"Multi-request summary generated for {len(individual_analyses)} requests")
            return result
            
        except Exception as e:
            logger.error(f"Failed to generate multi-request summary: {str(e)}")
            return MultiRequestSummary(
                total_requests=len(individual_analyses),
                urgent_requests=[],
                completed_requests=[],
                waiting_requests=[],
                overall_status=f"Summary generation failed: {str(e)}",
                recommended_actions=["Manually review individual requests"],
                summary=f"Could not generate summary due to error: {str(e)}"
            )
    
    def _format_analyses_for_prompt(self, analyses: List[RequestDetailAnalysis]) -> str:
        """Format individual analyses for inclusion in summary prompt"""
        
        formatted = []
        
        for analysis in analyses:
            formatted.append(f"""
REQUEST {analysis.request_number}:
- Status: {analysis.current_status}
- Action Required: {analysis.action_required}
- Action Description: {analysis.action_description}
- Key Insights: {'; '.join(analysis.key_insights)}
- Next Steps: {analysis.next_steps}
- Documents Available: {len(analysis.documents_available)} documents
- Outstanding Payments: {len(analysis.outstanding_payments)} payments
- Staff Contact: {analysis.staff_contact}
""")
        
        return "\n".join(formatted)
    
    def get_screenshot_from_driver(self, driver) -> str:
        """Helper to get base64 screenshot from selenium driver"""
        try:
            screenshot = driver.get_screenshot_as_png()
            return base64.b64encode(screenshot).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to take screenshot: {str(e)}")
            return ""
    
    def extract_page_text(self, driver) -> str:
        """Convert page HTML to structured Markdown"""
        try:
            html_content = driver.page_source
            
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.ignore_emphasis = False
            h.body_width = 0  # Don't wrap lines
            
            markdown = h.handle(html_content)
            
            # TODO: Add portal-specific cleaning if needed after testing
            return markdown
            
        except Exception as e:
            logger.warning(f"Markdown extraction failed, falling back to text: {str(e)}")
            return driver.find_element("tag name", "body").text
    
    def analyze_correspondence_intelligence(self, timeline_messages: List[str], request_context: str) -> Dict[str, Any]:
        """Deep analysis of correspondence using text LLM"""
        
        correspondence_prompt = f"""
        You are analyzing correspondence for a public records request to identify patterns and provide insights.
        
        REQUEST CONTEXT:
        {request_context}
        
        TIMELINE MESSAGES:
        {chr(10).join([f"- {msg}" for msg in timeline_messages])}
        
        Analyze this correspondence to determine:
        
        1. **Communication patterns**: How responsive is the agency? Are there delays?
        2. **Clarification requests**: What specific information has the agency asked for?
        3. **Roadblocks**: What's preventing progress on this request?
        4. **Agency behavior**: Is the agency being helpful, evasive, or standard?
        5. **Strategic insights**: What should the requester know about how to handle this agency?
        
        Provide tactical advice based on the communication patterns you observe.
        """
        
        try:
            result = self.llm_client.invoke([
                SystemMessage(content=correspondence_prompt),
                HumanMessage(content="Analyze this correspondence and provide strategic insights.")
            ])
            
            return {
                "success": True,
                "insights": result.content,
                "analysis_type": "correspondence_intelligence"
            }
            
        except Exception as e:
            logger.error(f"Failed correspondence intelligence analysis: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "analysis_type": "correspondence_intelligence"
            }
        
    def find_newest_request_number(self, screenshot_base64: str, page_text: str) -> str:
        """
        Use LLM to identify the newest/most recent request number from a requests list page.
        Returns the request number as a string, or "NONE" if no clear newest request found.
        """
        
        prompt = """
        You are analyzing a screenshot of a public records request portal's "All requests" page.
        
        Your task is to identify the NEWEST/MOST RECENT request from the list shown.
        
        Look for:
        1. The request that appears at the top of the list (usually newest)
        2. The request with the most recent date (due date, submission date, etc.)
        3. Request numbers typically follow patterns like "25-14673", "24-15853", etc.
        
        The newest request is usually:
        - At the top of the table
        - Has the most recent year (25-xxxx is newer than 24-xxxx)
        - Has the highest sequence number within the same year
        
        Respond with ONLY the request number of the newest/most recent request.
        Examples of valid responses: "25-14673", "24-15853", "23-9826"
        
        If you cannot clearly identify the newest request, respond with exactly: "NONE"
        """
        
        try:
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=[
                    {
                        "type": "text", 
                        "text": f"Find the newest request number from this page. Page text context:\n\n{page_text[:1000]}..."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}"
                        }
                    }
                ])
            ]
            
            result = self.llm_client.invoke(messages)
            response = result.content.strip()
            
            logger.info(f"LLM newest request analysis: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to find newest request with LLM: {str(e)}")
            return "NONE"