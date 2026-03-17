import logging
from typing import Dict, Any
from message_drafter import MessageDrafter

logger = logging.getLogger(__name__)

def generate_templates(llm_client, analysis: Dict[str, Any], request_number: str) -> Dict[str, Dict[str, str]]:
    """
    Legacy wrapper function for generating templates using the new MessageDrafter.
    Maintains compatibility with existing RequestAnalyzer code.
    
    Args:
        llm_client: LLM client for generating content
        analysis: Request analysis object from RequestAnalyzer
        request_number: The request number string
        
    Returns:
        Dict with numbered keys ("1", "2", etc.) containing template dicts
    """
    try:
        logger.info(f"🔄 Generating templates via MessageDrafter for {request_number}")
        
        # Create MessageDrafter instance
        drafter = MessageDrafter(llm_client)
        
        # Generate single contextual template
        result = drafter.draft_message(analysis)
        
        if result:
            # Return in legacy format expected by RequestAnalyzer
            # Multiple numbered templates for compatibility
            base_template = {
                "subject": result.get("subject", "Follow-up Message"),
                "message": result.get("message", "Hello,\n\nI am following up on my request.\n\nBest regards")
            }
            
            # Generate slight variations for the 4 expected template slots
            return {
                "1": {
                    "subject": base_template["subject"],
                    "message": base_template["message"]
                },
                "2": {
                    "subject": base_template["subject"].replace("Follow-up", "Additional Information -"),
                    "message": base_template["message"]
                },
                "3": {
                    "subject": base_template["subject"].replace("Follow-up", "Clarification -"),
                    "message": base_template["message"]
                },
                "4": {
                    "subject": base_template["subject"].replace("Follow-up", "Thank You -"),
                    "message": base_template["message"]
                }
            }
        else:
            logger.warning(f"⚠️ MessageDrafter returned no result, using fallback templates")
            return _get_fallback_templates(request_number)
            
    except Exception as e:
        logger.error(f"❌ Template generation via MessageDrafter failed: {str(e)}")
        return _get_fallback_templates(request_number)

def _get_fallback_templates(request_number: str) -> Dict[str, Dict[str, str]]:
    """Generate simple fallback templates when MessageDrafter fails"""
    return {
        "1": {
            "subject": f"Status Update Request - {request_number}",
            "message": "Hello,\n\nI am writing to request a status update on my public records request. Could you please provide an update on the progress and expected completion timeline?\n\nThank you for your time and assistance.\n\nBest regards"
        },
        "2": {
            "subject": f"Additional Information - {request_number}",
            "message": "Hello,\n\nI wanted to provide additional information that may help with processing my request:\n\n[Please add your additional details here]\n\nThank you for your assistance.\n\nBest regards"
        },
        "3": {
            "subject": f"Request Clarification - {request_number}",
            "message": "Hello,\n\nI would like to clarify my request to ensure you have all the necessary information:\n\n[Please add your clarification here]\n\nPlease let me know if you need any additional details.\n\nBest regards"
        },
        "4": {
            "subject": f"Thank You - {request_number}",
            "message": "Hello,\n\nThank you for your work on processing my public records request. I appreciate your time and effort.\n\nBest regards"
        }
    }