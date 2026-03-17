import logging
import json
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

class WorkflowStateHelper:
    """
    Dedicated LLM helper for determining workflow states in the request lifecycle.
    This modular approach keeps state determination logic separate from analysis logic.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def determine_workflow_state(
        self,
        request_data: Dict[str, Any],
        draft_info: Optional[Dict[str, Any]] = None,
        documents_status: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Use LLM to determine the workflow state and pending actions.

        Args:
            request_data: Dict containing request status, analysis, attention info
            draft_info: Optional dict with pending draft information including draft_message
            documents_status: Optional dict with document download/upload status

        Returns:
            Dict with keys:
            - lifecycle_state: One of 'active', 'closed', 'complete'
            - pending_actions: List of action dicts with action_type and metadata
            - state_summary: Human-readable explanation
        """

        result = self._get_state_determination(
            request_data,
            draft_info,
            documents_status
        )

        logger.info(f"Determined lifecycle_state='{result.get('lifecycle_state')}' with {len(result.get('pending_actions', []))} pending actions")

        return result

    def _get_state_determination(
        self,
        request_data: Dict[str, Any],
        draft_info: Optional[Dict[str, Any]],
        documents_status: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Determine lifecycle state, pending actions, and summary using LLM."""

        # Extract key information
        current_status = request_data.get('current_status', 'Unknown')
        attention_reason = request_data.get('agent_attention_reason', '')
        agent_attention_needed = request_data.get('agent_attention_needed', False)
        latest_analysis = request_data.get('latest_analysis', {})

        # Format draft status
        if draft_info and draft_info.get('has_pending_draft'):
            draft_message = draft_info.get('draft_message', '')
            draft_preview = draft_message[:500] + "..." if len(draft_message) > 500 else draft_message
            draft_status_display = f"""Pending draft requiring user approval: YES
Draft created: {draft_info.get('draft_created_at', 'Unknown')}
Draft type: {draft_info.get('draft_message_type', 'Unknown')}
Draft status: {draft_info.get('draft_status', 'Unknown')}
Draft message:
{draft_preview}"""
        else:
            draft_status_display = "No pending draft"

        # Format payment info
        payments = latest_analysis.get('outstanding_payments', [])
        payment_info = "No outstanding payments" if not payments else json.dumps(payments, indent=2)

        # Format timeline events
        timeline_events = latest_analysis.get('all_timeline_events', [])
        if timeline_events:
            timeline_display = "\n".join([f"  {event}" for event in timeline_events])
        else:
            timeline_display = "  No timeline events recorded"

        # Format document status with explicit, unambiguous language
        documents_from_portal = latest_analysis.get('documents_available', [])
        has_documents_in_portal = len(documents_from_portal) > 0

        if has_documents_in_portal:
            # Documents exist in portal
            if documents_status is None:
                # No entries in document_downloads table = not downloaded yet
                docs_info = f"""Documents Released by Government (ready for download): {len(documents_from_portal)}
Files: {json.dumps(documents_from_portal, indent=2)}
Download Status: NOT YET DOWNLOADED
Upload to Google Drive Status: NOT YET UPLOADED
→ ACTION REQUIRED: Agent must download and upload these documents"""
            elif documents_status.get('all_uploaded', False):
                # All documents downloaded and uploaded to Drive
                total = documents_status.get('total_documents', 0)
                docs_info = f"""Documents Released by Government: {total}
Files: {json.dumps(documents_from_portal, indent=2)}
Download Status: DOWNLOADED ✓
Upload to Google Drive Status: UPLOADED ✓
→ All documents processed - no action needed"""
            else:
                # Some documents downloaded but not all uploaded
                total = documents_status.get('total_documents', 0)
                docs_info = f"""Documents Released by Government: {total}
Files: {json.dumps(documents_from_portal, indent=2)}
Download Status: DOWNLOADED ✓
Upload to Google Drive Status: IN PROGRESS (not all uploaded)
→ ACTION REQUIRED: Complete upload to Google Drive"""
        else:
            # No documents mentioned in portal at all
            docs_info = """Documents Released by Government: 0
No documents have been released by the government agency yet.
→ No document action needed"""

        prompt = f"""
<role>
You are an expert at analyzing public records requests to determine their lifecycle state and pending actions.
</role>

<task>
Analyze the request information below and return:
1. The current lifecycle_state (exactly ONE state)
2. All pending_actions (can be multiple or empty array)
3. A state_summary that explains the situation to the user
</task>

<request_information>
Current Status: {current_status}
Agent Attention Needed: {agent_attention_needed}
Attention Reason: {attention_reason}

Outstanding Payments:
{payment_info}

Timeline Events (Chronological):
{timeline_display}

Draft Status:
{draft_status_display}

Document Download/Upload Status:
{docs_info}
</request_information>

<lifecycle_states>
Choose exactly ONE lifecycle state:

- **active**: Request is still being processed by the agency (status is not closed/completed/denied/withdrawn)
  - The agency has not yet reached a final decision
  - Documents may or may not have been released during processing

- **closed**: Request reached terminal status with the agency (status is closed/completed/denied/withdrawn) BUT the agent still has work to do
  - Examples: Documents need to be downloaded/uploaded, complex agency messages need analysis
  - The agent must complete processing before the request is truly done

- **complete**: Request is closed by the agency AND all agent processing is finished
  - All documents (if any) have been downloaded and uploaded to Google Drive
  - No complex agency messages requiring analysis
  - Only user actions may remain (draft approvals, payment submissions, appeal decisions)
  - This is the true end state for agent work
</lifecycle_states>

<action_types>
Identify ALL actions that need to happen. Can be zero, one, or multiple actions.

**User Actions:**
- user_approve_draft: User must review and approve a message draft
  - metadata: {{"draft_type": "notification|response|appeal"}}
- user_make_payment: User must submit payment
  - metadata: {{"amount": "$XX"}}
- user_decide_appeal: User must decide whether to appeal a denial
  - metadata: {{}}
- user_respond_to_agency: User must manually respond (complex case)
  - metadata: {{}}

**Agent Actions:**
- agent_draft_message: Agent should generate a draft response
  - metadata: {{}}
- agent_download_documents: Agent should download and process documents
  - metadata: {{"document_count": X}}
- agent_analyze_new_message: Agent should analyze new agency message
  - metadata: {{}}
</action_types>

<instructions>
1. **Determine lifecycle_state** using this logic:

   a) First check if request status is terminal (Closed/Completed/Denied/Withdrawn):
      - If NO → lifecycle_state = **active**
      - If YES → proceed to step b

   b) Request is closed - does agent still have work to do?
      - Documents not yet downloaded? → lifecycle_state = **closed**
      - Documents downloaded but not all uploaded? → lifecycle_state = **closed**
      - Agent attention needed without a draft (needs analysis)? → lifecycle_state = **closed**
      - All agent work done (documents uploaded, or no documents, and no complex analysis needed)? → lifecycle_state = **complete**

   c) Important: A request can be **complete** even with pending user actions (draft approvals, payments, appeal decisions)
      - "Complete" means the agent has done all it can do
      - User actions don't prevent completion status

2. **Identify pending_actions** by checking:
   - Outstanding payments? → user_make_payment
   - Status = "Denied"? → user_decide_appeal
   - Pending draft? → user_approve_draft
   - Documents not downloaded? → agent_download_documents
   - Documents downloaded but not uploaded? → agent_download_documents (to complete the upload)
   - Agent attention needed without draft? → agent_draft_message or agent_analyze_new_message

3. **Write state_summary**:
   - Explain the current lifecycle state clearly
   - Mention what actions are pending and why
   - If there's a draft, briefly describe what it says (e.g., "notification draft thanking the agency" or "response draft requesting clarification")
   - If complete, emphasize that agent work is done
   - Be conversational and informative for the end user
</instructions>

<examples>
**Example 1: Complete with pending draft approval**
Input:
- Status: Closed
- Documents: All uploaded to Google Drive
- Draft: "Thank you for fulfilling this request. We have received the documents."
- Agent attention: No

Output:
{{
  "lifecycle_state": "complete",
  "pending_actions": [
    {{"action_type": "user_approve_draft", "metadata": {{"draft_type": "notification"}}}}
  ],
  "state_summary": "The request is complete - all documents have been uploaded to Google Drive and the agent has finished processing. There is a notification draft pending your approval that thanks the agency for their response."
}}

**Example 2: Closed but documents need download**
Input:
- Status: Closed
- Documents: 2 files released by agency, NOT downloaded yet
- Draft: None

Output:
{{
  "lifecycle_state": "closed",
  "pending_actions": [
    {{"action_type": "agent_download_documents", "metadata": {{"document_count": 2}}}}
  ],
  "state_summary": "The request is closed, and the agency released 2 documents. However, the agent still needs to download and upload these documents to Google Drive before the request is complete."
}}

**Example 3: Active with payment and draft**
Input:
- Status: In Progress
- Payment: $50 due
- Draft: "We confirm we will pay the $50 fee. Please proceed with our request."

Output:
{{
  "lifecycle_state": "active",
  "pending_actions": [
    {{"action_type": "user_make_payment", "metadata": {{"amount": "$50"}}}},
    {{"action_type": "user_approve_draft", "metadata": {{"draft_type": "response"}}}}
  ],
  "state_summary": "The request is active and requires a $50 payment to proceed. There is a response draft pending your approval that confirms payment will be made."
}}

**Example 4: Closed but needs analysis**
Input:
- Status: Closed
- Documents: None
- Agent attention needed: Yes
- Attention reason: "Complex agency message about exemptions"
- Draft: None

Output:
{{
  "lifecycle_state": "closed",
  "pending_actions": [
    {{"action_type": "agent_analyze_new_message", "metadata": {{}}}}
  ],
  "state_summary": "The request is closed. The agency sent a complex message about exemptions that requires agent analysis before a draft can be generated."
}}

**Example 5: Fully complete, no actions needed**
Input:
- Status: Closed
- Documents: All uploaded to Google Drive
- No pending drafts or payments
- Agent attention: No

Output:
{{
  "lifecycle_state": "complete",
  "pending_actions": [],
  "state_summary": "The request is fully complete. All documents have been processed and uploaded to Google Drive. No further action is required."
}}

**Example 6: Active with documents released mid-process**
Input:
- Status: In Progress
- Documents: 1 file released, already uploaded
- Draft: None

Output:
{{
  "lifecycle_state": "active",
  "pending_actions": [],
  "state_summary": "The request is still active with the agency. They have released 1 document so far, which has been uploaded to Google Drive. Awaiting final agency response."
}}
</examples>

<output_format>
Return a valid JSON object with this exact structure:

{{
  "lifecycle_state": "active|closed|complete",
  "pending_actions": [
    {{"action_type": "...", "metadata": {{...}}}}
  ],
  "state_summary": "Human-readable explanation..."
}}

Return ONLY valid JSON. No markdown, no explanation, just the JSON object.
</output_format>
"""

        try:
            messages = [
                SystemMessage(content="You are an expert at analyzing public records requests."),
                HumanMessage(content=prompt)
            ]

            response = self.llm_client.invoke(messages)
            response_text = response.content.strip()

            # Parse JSON response
            result = json.loads(response_text)

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            logger.error(f"Response was: {response_text}")
            # Return default fallback
            return {
                "lifecycle_state": "active",
                "pending_actions": [],
                "state_summary": f"Error parsing workflow state: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error getting state determination: {e}")
            return {
                "lifecycle_state": "active",
                "pending_actions": [],
                "state_summary": f"Error determining workflow state: {str(e)}"
            }
