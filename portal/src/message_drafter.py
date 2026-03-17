import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from template_examples import previous_correspondence
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class MessageDrafter:
    """
    Intelligent message generation based on request analysis and change context.
    Uses a single comprehensive prompt to generate contextually appropriate responses
    based on proven effective correspondence examples.
    """

    # Define the 4 exact safe thank you responses that will be auto-approved
    SAFE_AUTO_APPROVED_MESSAGES = {
        "Thank you for confirming.",
        "Thank you for the update.",
        "I'm confirming receipt. Thank you for your response.",
        "I'm confirming receipt. Thank you."
    }

    def __init__(self, llm_client, db=None):
        """
        Initialize the message drafter.
        
        Args:
            llm_client: LLM client for generating contextual content
            db: Optional database connection for learning from message history
        """
        self.llm_client = llm_client
        self.db = db
        logger.info("✅ MessageDrafter initialized")
    
    def draft_message(self, request_analysis, change_context: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Generate contextual message draft based on request analysis and optional change context.

        Args:
            request_analysis: Fresh analysis of the request from RequestAnalyzer
            change_context: Optional context about what changed that triggered attention

        Returns:
            Dict with subject, message, and metadata (includes 'auto_approved' flag)
        """
        try:
            logger.info(f"🤖 Generating message draft for {request_analysis.request_number}")

            # Extract context from analysis
            context = self._extract_context(request_analysis, change_context)

            # Generate the response using comprehensive prompt
            template = self._generate_template(context)

            if not template:
                logger.error("❌ Template generation failed")
                return None

            # Check if the message is one of the 4 safe auto-approved thank you responses
            auto_approved = self._is_auto_approved_message(template.get('message', ''))

            # Add metadata for tracking
            template.update({
                'generation_method': 'contextual_ai',
                'change_trigger': change_context.get('attention_reason', '') if change_context else '',
                'priority': change_context.get('attention_priority', 'medium') if change_context else 'medium',
                'generated_at': datetime.now().isoformat(),
                'auto_approved': auto_approved  # Flag for automatic user approval
            })

            if auto_approved:
                logger.info(f"✅ Message auto-approved (safe thank you response): \"{template.get('message')}\"")

            logger.info(f"✅ Message draft generated successfully")
            return template

        except Exception as e:
            logger.error(f"❌ Message drafting failed: {str(e)}")
            return None

    def _is_auto_approved_message(self, message: str) -> bool:
        """
        Check if the generated message is one of the 4 safe auto-approved thank you responses.

        Args:
            message: The message text to check

        Returns:
            True if message exactly matches one of the safe responses, False otherwise
        """
        if not message:
            return False

        # Strip whitespace and check for exact match
        message_stripped = message.strip()

        if message_stripped in self.SAFE_AUTO_APPROVED_MESSAGES:
            logger.debug(f"🎯 Message matched safe auto-approved response: \"{message_stripped}\"")
            return True

        return False

    def _extract_context(self, analysis, change_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extract relevant context from RequestDetailAnalysis object and change context"""
        
        contact_name = self._extract_contact_name(analysis.staff_contact)
        
        context = {
            "request_number": analysis.request_number,
            "status": analysis.current_status,
            "contact_name": contact_name,
            "contact_info": analysis.staff_contact,
            "action_required": "YES" if analysis.action_required else "NO",
            "needs_attention": "YES" if analysis.needs_attention else "NO",
            "attention_reason": analysis.attention_reason,
            "attention_priority": analysis.attention_priority,
            "all_timeline_events": analysis.all_timeline_events,
            "documents_available": analysis.documents_available,
            "outstanding_payments": analysis.outstanding_payments,
            "stated_deadlines": analysis.stated_deadlines,
            "last_timeline_entry": self._get_last_timeline_entry(analysis.all_timeline_events),
            "recent_timeline_entries": self._get_recent_timeline_entries(analysis.all_timeline_events, 3),
        }
        
        # Add change context if provided
        if change_context:
            context.update({
                "change_attention_reason": change_context.get('attention_reason', ''),
                "change_attention_priority": change_context.get('attention_priority', 'medium'),
                "change_triggered": True
            })
        else:
            context.update({
                "change_attention_reason": "",
                "change_attention_priority": "",
                "change_triggered": False
            })
        
        return context

    def _extract_contact_name(self, contact_string: str) -> str:
        """Extract contact name from contact information"""
        if not contact_string:
            return ""
        
        # Handle format like "Law Admin 09, Police Department (NOPD)"
        if "," in contact_string:
            name_part = contact_string.split(",")[0].strip()
            return name_part
        
        # Handle format like "Law Admin 09 (City Attorney's Office)"
        if "(" in contact_string:
            name_part = contact_string.split("(")[0].strip()
            return name_part
        
        return contact_string.strip()

    def _get_last_timeline_entry(self, timeline_events) -> str:
        """Get the most recent timeline entry"""
        if not timeline_events:
            return ""
        
        if isinstance(timeline_events, list) and len(timeline_events) > 0:
            return timeline_events[-1]
        
        return ""

    def _get_recent_timeline_entries(self, timeline_events, count: int = 3) -> List[str]:
        """Get the most recent timeline entries for context"""
        if not timeline_events:
            return []
        
        if isinstance(timeline_events, list):
            return timeline_events[-count:] if len(timeline_events) >= count else timeline_events
        
        return [str(timeline_events)]

    def _generate_template(self, context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Generate template using comprehensive situation-aware prompt"""
        
        prompt = self._build_prompt(context)
        
        try:
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=f"Analyze the situation for request {context['request_number']} and generate the most appropriate response based on the examples provided.")
            ]
            
            response = self.llm_client.invoke(messages)
            
            return self._parse_response(response.content, context)
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _build_prompt(self, context: Dict[str, Any]) -> str:
        """Build comprehensive situation-aware prompt that prioritizes example matching"""
        
        # Format context information for readability
        timeline_text = ""
        if context['all_timeline_events']:
            timeline_text = "\n".join([f"   • {entry}" for entry in context['all_timeline_events']])
        
        recent_timeline_text = ""
        if context['recent_timeline_entries']:
            recent_timeline_text = "\n".join([f"   • {entry}" for entry in context['recent_timeline_entries']])
        
        documents_text = ""
        if context['documents_available']:
            documents_text = "\n".join([f"   • {doc}" for doc in context['documents_available']])
        else:
            documents_text = "   • None currently available"
        
        payments_text = ""
        if context['outstanding_payments']:
            payments_text = "\n".join([f"   • {payment}" for payment in context['outstanding_payments']])
        else:
            payments_text = "   • No outstanding payments"
        
        deadlines_text = ""
        if context['stated_deadlines']:
            deadlines_text = "\n".join([f"   • {deadline}" for deadline in context['stated_deadlines']])
        else:
            deadlines_text = "   • No specific deadlines mentioned"

        # Build change context section
        change_context_text = ""
        if context['change_triggered']:
            change_context_text = f"""
🔄 CHANGE CONTEXT (What triggered this message):
   • Change Reason: {context['change_attention_reason']}
   • Change Priority: {context['change_attention_priority']}
   • This message was triggered by a specific change or alert
"""
        else:
            change_context_text = "\n🔄 CHANGE CONTEXT: No specific change triggered this message (general follow-up)"

        return f"""
You are an expert at public records request follow-up communication. You will be provided with proven effective correspondence examples that show common agency actions and appropriate responses.

IMPORTANT: The examples below show situations where the AGENCY took certain actions and how WE responded. These are reference examples to guide your response when similar situations arise. However, if the current situation does not closely match any example, you should draft an appropriate original message that maintains the same professional tone and legal precision demonstrated in the examples.

⚠️ CRITICAL: AUTOMATIC THANK-YOU RESPONSES ⚠️
================================================================
The following 4 responses will be AUTOMATICALLY SENT without human review if you generate them EXACTLY as written:

1. "Thank you for confirming."
2. "Thank you for the update."
3. "I'm confirming receipt. Thank you for your response."
4. "I'm confirming receipt. Thank you."

IMPORTANT GUIDELINES FOR AUTOMATIC RESPONSES:

✅ DO use these exact phrases when appropriate - they are safe, professional acknowledgments that move the process along efficiently

✅ DO feel free to use these responses in the right situations - they're relatively harmless and prevent the user's review queue from being clogged with simple acknowledgments

✅ DO use these EXACT phrases word-for-word - variations will NOT trigger auto-send and will require human review

❌ DO NOT use these phrases if the situation requires ANY substantive follow-up, legal citation, or clarification

❌ DO NOT create variations of these phrases (e.g., "Thanks for confirming" or "Thank you for the confirmation") - use the exact wording above or draft a full substantive response

WHEN TO USE AUTOMATIC THANK-YOU RESPONSES:

Use one of the 4 auto-send phrases ONLY when ALL of the following are true:

✅ The agency has taken a purely administrative action that requires no follow-up:
   - Confirmed receipt of the request → Use: "Thank you for confirming."
   - Notified us of a routine extension or timeline → Use: "Thank you for the update."
   - Sent final batch of records with clear completion → Use: "I'm confirming receipt. Thank you for your response."
   - Sent partial records with clear indication more are coming → Use: "I'm confirming receipt. Thank you."

❌ DO NOT use auto-send phrases if ANY of the following apply:
   - Records are missing or incomplete (beyond normal staged delivery)
   - The agency failed to meet a deadline without proper extension
   - The agency's response raises legal compliance questions
   - An exemption was claimed without proper justification
   - Fees were mentioned that may be improper
   - The agency attempted to close the request prematurely
   - Redactions appear excessive or improper
   - The agency asked inappropriate questions (e.g., purpose of request)
   - The agency's message contains anything that might require clarification or pushback
   - The timeline shows concerning delays or patterns
   - You're unsure whether follow-up is needed

DECISION TREE:
1. Does the agency's action require ANY substantive response beyond acknowledgment? 
   → YES: Draft a full substantive message
   → NO: Continue to step 2

2. Does the situation match one of the 4 auto-send scenarios exactly?
   → YES: Use the exact auto-send phrase
   → NO: Draft a full substantive message or ask for clarification

WHEN IN DOUBT: Draft a substantive response. It's better to provide a detailed message for human review than to auto-send when follow-up might be needed.

EXAMPLES OF APPROPRIATE AUTO-SEND SITUATIONS:
✅ Agency: "We received your request and assigned it number 2024-123. We will respond within 10 days."
   Response: "Thank you for confirming."

✅ Agency: "We need an additional 14 days to compile the responsive records."
   Response: "Thank you for the update."

✅ Agency: "Attached are the remaining records. This completes our response to request 2024-123."
   Response: "I'm confirming receipt. Thank you for your response."

✅ Agency: "Here is the first batch of 50 pages. We will send the remaining records by March 15th."
   Response: "I'm confirming receipt. Thank you."

EXAMPLES WHERE AUTO-SEND IS INAPPROPRIATE (use full substantive response):
❌ Agency: "We received your request but need 60 days to respond."
   → Draft response citing Gov. Code § 7922.535 requirements

❌ Agency: "Here are all responsive records. Request closed."
   → Draft response verifying all requested items were provided

❌ Agency: "Some records are exempt under attorney-client privilege."
   → Draft response requesting specific exemption justification

❌ Agency: "We cannot locate the records you requested."
   → Draft response citing agency's duty to assist under § 7922.600
================================================================

PROVEN EFFECTIVE CORRESPONDENCE EXAMPLES:
================================================================
The following examples show: [What the Agency Did] → [Our Response]

{previous_correspondence}
================================================================

CURRENT SITUATION ANALYSIS:
================================================================
📊 Request Number: {context['request_number']}
📈 Current Status: {context['status']}
⚡ Action Required: {context['action_required']}
🚨 Needs Attention: {context['needs_attention']}
📋 Attention Reason: {context['attention_reason']}
⏰ Attention Priority: {context['attention_priority']}
👤 Staff Contact: {context['contact_info']}
👤 Contact Name: {context['contact_name']}

📅 COMPLETE TIMELINE:
{timeline_text}

📅 RECENT ACTIVITY (Last 3 Events):
{recent_timeline_text}

📄 DOCUMENTS AVAILABLE:
{documents_text}

💰 OUTSTANDING PAYMENTS:
{payments_text}

⏰ STATED DEADLINES:
{deadlines_text}

📝 MOST RECENT EVENT: {context['last_timeline_entry']}
{change_context_text}
================================================================

TASK INSTRUCTIONS:
1. **Analyze the current situation** based on the timeline, status, attention reason, and any change context
2. **Determine if one of the 4 auto-send phrases is appropriate** (review criteria above carefully)
3. **If auto-send is appropriate**: Use the EXACT phrase from the list above - no variations
4. **If auto-send is not appropriate**: Check if any example scenario closely matches the current situation
5. **IF A CLOSE MATCH EXISTS**: Use that response with appropriate customizations (request number, contact name, specific details)
6. **IF NO CLOSE MATCH EXISTS**: Draft an original, appropriate follow-up message that:
   - Addresses the specific situation at hand
   - Maintains the professional, legally-precise tone demonstrated in the examples
   - Cites relevant statutes when applicable
   - Is clear, direct, and action-oriented
   - Reflects the urgency level indicated by the attention priority

CUSTOMIZATION RULES (when using examples):
- Replace placeholder request numbers with: {context['request_number']}
- Address the contact by name if available: {context['contact_name']}
- Reference specific timeline events only if they add value
- Maintain the exact legal language and citations from examples when applicable
- Keep the professional tone and structure from the examples

DRAFTING GUIDELINES (when creating original messages):
- Use professional, direct language
- Cite relevant California Government Code or Penal Code sections when appropriate
- Be specific about what you're requesting or what action is needed
- Reference specific timeline events or deadlines when relevant
- Match the tone to the urgency level (higher priority = more assertive)
- If acknowledging receipt or updates, keep it brief and professional
- If requesting action, be clear about what's needed and any applicable deadlines

OUTPUT FORMAT:
Return ONLY the subject line and message body in this exact format:
SUBJECT: [subject here]
MESSAGE: [message here]

Remember: 
- Use the 4 exact auto-send phrases freely when appropriate - they're safe and efficient
- Never create variations of the auto-send phrases - use exact wording or draft a full response
- When in doubt about whether auto-send is appropriate, draft a substantive response instead
- Quality and appropriateness matter more than strict adherence to examples
"""

    def _parse_response(self, response: str, context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Parse LLM response into subject and message"""
        try:
            lines = response.strip().split('\n')
            subject = f"Follow-up: Request {context['request_number']}"
            message_lines = []
            
            in_message = False
            
            for line in lines:
                line = line.strip()
                if line.upper().startswith('SUBJECT:'):
                    subject = line.split(':', 1)[1].strip()
                elif line.upper().startswith('MESSAGE:'):
                    in_message = True
                    message_content = line.split(':', 1)[1].strip()
                    if message_content:
                        message_lines.append(message_content)
                elif in_message and line:
                    message_lines.append(line)
            
            message = '\n'.join(message_lines).strip()
            
            # Ensure we have content
            if not message:
                logger.error("❌ No message content parsed from LLM response")
                return None
            
            return {
                "subject": subject,
                "message": message
            }
            
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return None
    