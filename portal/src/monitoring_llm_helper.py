import logging
import json
from typing import Dict, List, Any
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

class MonitoringLLMHelper:
    """
    LLM helper specifically designed for monitoring agent change detection.
    Uses the same proven LangChain interface as the working LLMHelper class.
    """
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def detect_changes(self, new_analysis: str, stored_analysis: str) -> bool:
        """Use LLM to determine if meaningful changes occurred."""
        
        change_detection_prompt = f"""
        <role>
        You are an expert at detecting meaningful changes in public records request status.
        </role>

        <task>
        Compare these two analyses of the same public records request and determine if there are ANY meaningful changes that a user should know about.
        </task>

        <previous_analysis>
        {stored_analysis}
        </previous_analysis>

        <new_analysis>
        {new_analysis}
        </new_analysis>

        <meaningful_changes_include>
        - Status changes (any change in request status)
        - New correspondence or messages
        - Document availability changes
        - Payment or fee changes
        - Staff contact changes
        - Timeline or deadline changes
        - Any new information that affects the request
        </meaningful_changes_include>

        <ignore_minor_differences>
        - Small wording variations in the same information
        - Formatting differences
        - Minor timestamp differences if content is same
        - Identical information presented slightly differently
        </ignore_minor_differences>

        <instructions>
        Respond with ONLY one word:
        - "YES" if there are meaningful changes
        - "NO" if there are no meaningful changes

        Think carefully about whether anything substantive changed that the user should know about.
        </instructions>
        """
        
        try:
            response = self.llm_client.invoke([
                SystemMessage(content="You are an expert at detecting meaningful changes in public records request status."),
                HumanMessage(content=change_detection_prompt)
            ])

            print(f"Stored analysis: {stored_analysis}")
            
            print(f"New analysis: {new_analysis}")
            
            result = response.content.strip().upper()
            logger.info(f"🔍 Change detection result: {result}")
            return result == "YES"
            
        except Exception as e:
            logger.error(f"❌ Change detection LLM call failed: {str(e)}")
            # Conservative fallback: assume there are changes to be safe
            return True
    
    def extract_specific_changes(self, new_analysis: str, stored_analysis: str) -> List[Dict]:
        """Use LLM to extract specific changes that occurred."""
        
        changes_prompt = f"""
        <role>
        You are an expert at identifying specific changes in public records request analysis.
        </role>

        <task>
        Compare these two analyses and identify exactly what changed. List each specific change.
        </task>

        <previous_analysis>
        {stored_analysis}
        </previous_analysis>

        <new_analysis>
        {new_analysis}
        </new_analysis>

        <output_format>
        Return a JSON array of changes. Each change should have:
        {{
            "type": "status/correspondence/documents/payments/staff/timeline/other",
            "description": "Clear description of what changed",
            "old_value": "What it was before",
            "new_value": "What it is now"
        }}

        Example:
        [
            {{
                "type": "status",
                "description": "Request status changed from Under Review to Additional Information Required",
                "old_value": "Under Review",
                "new_value": "Additional Information Required"
            }},
            {{
                "type": "correspondence",
                "description": "Staff sent new message requesting clarification",
                "old_value": "No recent correspondence",
                "new_value": "Staff requested additional details about date range"
            }}
        ]
        </output_format>

        <instructions>
        - Only include actual changes, not differences in wording
        - Be specific about what changed
        - Focus on information that affects the user
        - Return empty array [] if no changes found
        </instructions>
        """
        
        try:
            response = self.llm_client.invoke([
                SystemMessage(content="You are an expert at identifying specific changes in public records request analysis."),
                HumanMessage(content=changes_prompt)
            ])
            
            changes = json.loads(response.content)
            
            # Validate the response format
            if isinstance(changes, list):
                return changes
            else:
                logger.warning("❌ LLM returned non-list for changes")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse changes JSON: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"❌ Extract changes LLM call failed: {str(e)}")
            return []
    
    def determine_action_required(self, analysis_text: str) -> bool:
        """Use dedicated LLM call to determine if action is required."""
        
        action_prompt = f"""
        <role>
        You are an expert at analyzing public records request status to determine if the requester needs to take action.
        </role>

        <task>
        Analyze the following request analysis and determine if the USER/REQUESTER needs to take any action.
        </task>

        <analysis>
        {analysis_text}
        </analysis>

        <action_required_criteria>
        Return TRUE if ANY of these apply:
        - Request status indicates user action needed (Additional Information Required, Fee Payment Due, etc.)
        - Government staff has asked for a response or clarification
        - User needs to pay fees or invoices
        - **IMPORTANT: Documents are available for download (released, uploaded, or newly available)**
        - **IMPORTANT: Document release event detected in timeline (even if request is closed)**
        - User needs to pick up documents in person
        - User needs to provide additional information
        - User needs to respond to correspondence
        - User needs to appeal or take further action

        Return FALSE if:
        - Request is being processed by government (Under Review, In Progress, etc.)
        - Waiting for government response
        - Request is completed with NO documents available
        - Just informational updates with no action required
        - Request was already flagged and documents were already downloaded
        </action_required_criteria>

        <instructions>
        Respond with ONLY one word:
        - "TRUE" if the user needs to take action
        - "FALSE" if no user action is required

        CRITICAL: Always return TRUE if documents are available for download - this is the most important action users need to take.
        Document releases should ALWAYS trigger an attention flag, even if the request is marked as "Closed" or "Completed".
        </instructions>
        """
        
        try:
            response = self.llm_client.invoke([
                SystemMessage(content="You are an expert at analyzing public records request status to determine if the requester needs to take action."),
                HumanMessage(content=action_prompt)
            ])
            
            result = response.content.strip().upper()
            logger.info(f"🎯 Action required determination: {result}")
            return result == "TRUE"
            
        except Exception as e:
            logger.error(f"❌ Action required LLM call failed: {str(e)}")
            # Conservative fallback: assume no action required to avoid false alarms
            return False
    
    def classify_severity(self, changes: List[Dict], needs_attention: bool) -> str:
        """Use LLM to classify the severity of detected changes."""
        
        if not changes:
            return 'low'
        
        severity_prompt = f"""
        <role>
        You are an expert at classifying the urgency and importance of changes in public records requests.
        </role>

        <task>
        Classify the severity of these changes for a public records requester.
        </task>

        <changes>
        {json.dumps(changes, indent=2)}
        </changes>

        <user_action_required>
        {needs_attention}
        </user_action_required>

        <severity_levels>
        HIGH:
        - **DOCUMENTS READY FOR DOWNLOAD - HIGHEST PRIORITY**
        - **Document release events (newly available files)**
        - Requires immediate user action (fees due, additional info required)
        - Request denied or rejected
        - Deadlines or time-sensitive requirements

        MEDIUM:
        - Status updates showing progress
        - New correspondence that's informational
        - Timeline changes
        - Staff contact updates

        LOW:
        - Minor administrative updates
        - Small changes that don't affect user experience
        - Routine processing updates
        </severity_levels>

        <instructions>
        Respond with ONLY one word:
        - "high" for high priority changes
        - "medium" for medium priority changes  
        - "low" for low priority changes

        Consider both the type of changes and whether user action is required.
        </instructions>
        """
        
        try:
            response = self.llm_client.invoke([
                SystemMessage(content="You are an expert at classifying the urgency and importance of changes in public records requests."),
                HumanMessage(content=severity_prompt)
            ])
            
            result = response.content.strip().lower()
            if result in ['high', 'medium', 'low']:
                logger.info(f"📊 Change severity classified as: {result}")
                return result
            else:
                logger.warning(f"❌ Invalid severity response: {result}")
                return 'medium'
                
        except Exception as e:
            logger.error(f"❌ Severity classification LLM call failed: {str(e)}")
            return 'medium'  # Safe default
    
    def generate_attention_reason(self, analysis_text: str, changes: List[Dict]) -> str:
        """Generate human-readable reason why this request needs attention."""
        
        reason_prompt = f"""
        <role>
        You are an expert at explaining why a public records request needs the user's attention.
        </role>

        <task>
        Based on the request analysis and detected changes, generate a clear, concise reason why the user should pay attention to this request.
        </task>

        <request_analysis>
        {analysis_text}
        </request_analysis>

        <detected_changes>
        {json.dumps(changes, indent=2)}
        </detected_changes>

        <instructions>
        Generate a clear, actionable reason in 1-2 sentences that explains:
        - What happened that requires attention
        - What the user should do about it (if applicable)

        Examples:
        - "Documents have been released and are ready for immediate download"
        - "New document(s) available: [filename] - download now"
        - "Government staff requested additional information about your date range - you need to respond"
        - "Fee payment of $25 is required to process your request"
        - "Your request was denied - you may want to appeal or submit a revised request"

        IMPORTANT: For document releases, always mention the specific document name if available and emphasize immediate download.
        Keep it concise and actionable.
        </instructions>
        """
        
        try:
            response = self.llm_client.invoke([
                SystemMessage(content="You are an expert at explaining why a public records request needs the user's attention."),
                HumanMessage(content=reason_prompt)
            ])
            
            result = response.content.strip()
            logger.info(f"📝 Generated attention reason: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Attention reason LLM call failed: {str(e)}")
            return "Request status updated - please review"
    
    def generate_change_summary(self, changes: List[Dict]) -> str:
        """Generate brief summary of changes for logging/display."""
        
        if not changes:
            return "No changes detected"
        
        summary_prompt = f"""
        <role>
        You are an expert at creating concise summaries of changes.
        </role>

        <task>
        Create a brief summary (max 10 words) of these changes for logging purposes.
        </task>

        <changes>
        {json.dumps(changes, indent=2)}
        </changes>

        <instructions>
        Generate a very brief summary like:
        - "Status changed to require additional info"
        - "New staff correspondence received"
        - "Documents now available for download"
        - "Multiple updates: status and correspondence"

        Keep it under 10 words and focus on the most important change.
        </instructions>
        """
        
        try:
            response = self.llm_client.invoke([
                SystemMessage(content="You are an expert at creating concise summaries of changes."),
                HumanMessage(content=summary_prompt)
            ])
            
            result = response.content.strip()
            logger.info(f"📄 Generated change summary: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Change summary LLM call failed: {str(e)}")
            # Fallback to simple summary
            if len(changes) == 1:
                return f"{changes[0]['type']} changed"
            else:
                return f"{len(changes)} changes detected"
    
    def analyze_initial_request(self, analysis_text: str) -> Dict[str, Any]:
        """Analyze a request for the first time to determine if it needs attention."""
        
        needs_attention = self.determine_action_required(analysis_text)
        severity = 'high' if needs_attention else 'medium'
        
        attention_reason = None
        if needs_attention:
            attention_reason = self.generate_attention_reason(analysis_text, [])
        
        return {
            'has_changes': True,
            'changes_detected': ['initial_analysis'],
            'needs_attention': needs_attention,
            'attention_reason': attention_reason,
            'change_summary': 'Initial analysis completed for this request',
            'severity': severity,
            'specific_changes': [{'type': 'initial_analysis', 'description': 'First time analyzing this request'}]
        }
    
    def analyze_changes(self, new_analysis_text: str, stored_analysis_summary: str, request_number: str) -> Dict[str, Any]:
        """
        Comprehensive change analysis using multiple LLM calls.
        
        Args:
            new_analysis_text: Fresh analysis from analyze_request_detail_page
            stored_analysis_summary: Previously stored analysis summary from database
            request_number: Request identifier for context
            
        Returns:
            Dict with changes detected, attention needed, and detailed reasoning
        """
        
        if not stored_analysis_summary or stored_analysis_summary.strip() == "":
            # First time analyzing this request
            return self.analyze_initial_request(new_analysis_text)
        
        logger.info(f"🔍 Running comprehensive change analysis for {request_number}")
        
        # Step 1: Determine if there are any meaningful changes
        has_changes = self.detect_changes(new_analysis_text, stored_analysis_summary)
        
        if not has_changes:
            return {
                'has_changes': False,
                'changes_detected': [],
                'needs_attention': False,
                'attention_reason': None,
                'change_summary': 'No meaningful changes detected',
                'severity': 'low',
                'specific_changes': []
            }
        
        # Step 2: Extract what specifically changed
        specific_changes = self.extract_specific_changes(new_analysis_text, stored_analysis_summary)
        
        # Step 3: Determine if action is required from new analysis
        needs_attention = self.determine_action_required(new_analysis_text)
        
        # Step 4: Classify severity of changes
        severity = self.classify_severity(specific_changes, needs_attention)
        
        # Step 5: Generate attention reason if needed
        attention_reason = None
        if needs_attention:
            attention_reason = self.generate_attention_reason(new_analysis_text, specific_changes)
        
        # Step 6: Create summary
        change_summary = self.generate_change_summary(specific_changes)
        
        result = {
            'has_changes': True,
            'changes_detected': [change['type'] for change in specific_changes],
            'needs_attention': needs_attention,
            'attention_reason': attention_reason,
            'change_summary': change_summary,
            'severity': severity,
            'specific_changes': specific_changes
        }
        
        logger.info(f"✅ Change analysis complete for {request_number}: {change_summary}")
        return result
    
    def create_change_records_for_database(self, change_analysis: Dict, request_id: str) -> List[Dict]:
        """Convert LLM change analysis into database change records."""
        
        if not change_analysis.get('has_changes'):
            return []
        
        change_records = []
        
        # Create a general change record
        change_records.append({
            'request_id': request_id,
            'field_changed': 'general',
            'old_value': 'Previous analysis',
            'new_value': change_analysis.get('change_summary', ''),
            'change_severity': change_analysis.get('severity', 'medium'),
            'triggered_attention_flag': change_analysis.get('needs_attention', False),
            'attention_reason': change_analysis.get('attention_reason')
        })
        
        # Create specific change records if available
        for specific_change in change_analysis.get('specific_changes', []):
            change_records.append({
                'request_id': request_id,
                'field_changed': specific_change.get('type', 'unknown'),
                'old_value': str(specific_change.get('old_value', ''))[:1000],  # Truncate
                'new_value': str(specific_change.get('new_value', ''))[:1000],   # Truncate
                'change_severity': change_analysis.get('severity', 'medium'),
                'triggered_attention_flag': change_analysis.get('needs_attention', False),
                'attention_reason': specific_change.get('description', '')[:500]  # Truncate
            })
        
        return change_records