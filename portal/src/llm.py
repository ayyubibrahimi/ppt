import base64
from typing import Dict, Any
from models import FormFieldLocation

import logging
from langchain_core.messages import HumanMessage, SystemMessage
from models import ScreenshotAnalysis

from langchain_openai import AzureChatOpenAI

from dotenv import load_dotenv
load_dotenv()


gpt_4o_mini = AzureChatOpenAI(
    api_version="2024-12-01-preview",
    azure_deployment="gpt-4.1-mini" 
)

gpt_4o = AzureChatOpenAI(
    api_version="2024-12-01-preview",
    azure_deployment="gpt-4.1"
)

# gpt_4o_mini = ChatOpenAI(model="gpt-4.1-mini",) 
# gpt_4o = ChatOpenAI(model="gpt-4.1-mini") 


logger = logging.getLogger(__name__)

class LLMAnalyzer:
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def analyze_page(self, screenshot_data: Dict[str, Any], page_text: str) -> ScreenshotAnalysis:
        """Use LLM to analyze the screenshot and page content"""
        
        analysis_prompt = f"""
        You are analyzing a screenshot of the Alameda County NextRequest public records portal to understand the current page state and determine what actions are needed.

        Page Information:
        - URL: {screenshot_data['url']}
        - Title: {screenshot_data['title']}
        - Label: {screenshot_data['label']}
        
        Page Text Content (first 3000 chars):
        {page_text}
        
        CRITICAL: You must provide ALL required fields in your response. Do not omit any fields.
        
        Based on the screenshot and text content, determine:
        
        1. Page Type: What kind of page is this?
           - 'portal_home': Main portal landing page with "Make Request" options
           - 'login_form': Page with login fields
           - 'logged_in_dashboard': User dashboard after successful login
           - 'error': Error page or failed login
           - 'other': Other type of page
        
        2. Login Requirements: Does this page require login to proceed?
        
        3. Login Elements: Which login-related elements are present? YOU MUST PROVIDE ALL FOUR FIELDS:
           - username_field: true/false - Email/username input field present
           - password_field: true/false - Password input field present
           - submit_button: true/false - Login/submit button present
           - sign_in_link: true/false - Link to sign in page present
        
        4. Key Elements: What important elements do you see? (buttons, links, forms, etc.)
        
        5. Next Steps: What should be done next to progress toward accessing the portal?
        
        For NextRequest portals specifically:
        - Look for "Sign in" button in top navigation
        - Look for "Make Request" buttons
        - Identify if we're on the main portal or need to authenticate
        - Note any error messages or authentication requirements
        - Check for "Open Public Records" text and portal description
        
        Expected Output Format (ALL FIELDS REQUIRED):
        page_type: 'portal_home' | 'login_form' | 'logged_in_dashboard' | 'error' | 'other'
        login_required: true | false
        login_elements_found:
          username_field: true | false
          password_field: true | false
          submit_button: true | false
          sign_in_link: true | false
        key_elements: ["element1", "element2", "element3"]
        next_steps: ["step1", "step2", "step3"]
        confidence: 0.0-1.0
        
        Example response:
        {{
          "page_type": "portal_home",
          "login_required": false,
          "login_elements_found": {{
            "username_field": false,
            "password_field": false,
            "submit_button": false,
            "sign_in_link": true
          }},
          "key_elements": ["Make Request button", "Sign in link", "Open Public Records text"],
          "next_steps": ["Click Make Request to start process", "Or click Sign in to authenticate"],
          "confidence": 0.9
        }}
        
        IMPORTANT: Ensure your response includes exactly these fields with the correct data types.
        """
        
        structured_llm = self.llm_client.with_structured_output(ScreenshotAnalysis, method="function_calling")
        result = structured_llm.invoke([
            SystemMessage(content=analysis_prompt),
            HumanMessage(content="Analyze this page and provide detailed assessment with ALL required fields.")
        ])
        
        return result

class FormFieldAnalyzer:
    """LLM analyzer specifically for identifying form fields in screenshots"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def analyze_request_description_field(self, screenshot_base64: str, page_html: str = "") -> FormFieldLocation:
        """
        Analyze screenshot to find the main request description textarea where 
        the public records request text should be entered.
        """
        
        analysis_prompt = """
        You are analyzing a screenshot of a public records request form to identify where the main request description should be entered.

        GOAL: Find the PRIMARY textarea field where users should enter their public records request text.

        Context:
        - This is a "REQUEST A PUBLIC RECORD" form
        - The form has multiple fields, but we need the MAIN content area
        - Look for the large text area with placeholder text like "Enter your request - please include all information that could help fulfill this request"
        - This field is typically labeled "Request description" or similar
        - It's usually the largest textarea on the page
        - It's NOT the address field or other contact information fields

        What to look for:
        1. Large textarea elements (not small input fields)
        2. Text that indicates this is for the request content ("Request description", "Enter your request", etc.)
        3. Placeholder text suggesting request details
        4. Position on the form (usually near the top, after the title)
        5. Size - should be substantial for entering detailed requests

        What to AVOID:
        - Small input fields for name, email, phone
        - Address textarea (this is for physical address, not request content)
        - Any field clearly marked for contact information
        - Submit buttons or other non-text elements

        Provide the BEST selector to target this field reliably. Prefer:
        1. CSS selectors using attributes (placeholder, name, id)
        2. XPath if CSS isn't sufficient
        3. Tag-based selectors as last resort

        Return your analysis with:
        - Whether you found the request description field
        - The best selector to use
        - Alternative selectors as backups
        - Confidence level
        - Description of what you observed
        """
        
        try:
            structured_llm = self.llm_client.with_structured_output(FormFieldLocation, method="function_calling")
            
            messages = [
                SystemMessage(content=analysis_prompt),
                HumanMessage(content=[
                    {
                        "type": "text", 
                        "text": "Analyze this form screenshot and identify the main request description textarea field. Focus on finding where the actual public records request text should be entered."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}"
                        }
                    }
                ])
            ]
            
            if page_html:
                messages[1].content[0]["text"] += f"\n\nPage HTML snippet:\n{page_html[:2000]}..."
            
            result = structured_llm.invoke(messages)
            logger.info(f"Form field analysis completed. Found field: {result.field_found}, Confidence: {result.confidence}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze form fields: {str(e)}")
            # Return a fallback result
            return FormFieldLocation(
                field_found=False,
                selector_type="css",
                selector_value="textarea",
                field_description="Analysis failed - using generic selector",
                confidence=0.1,
                alternative_selectors=[],
                context_info=f"LLM analysis failed: {str(e)}"
            )
    
    def analyze_all_form_fields(self, screenshot_base64: str, page_html: str = "") -> Dict[str, FormFieldLocation]:
        """
        Analyze screenshot to identify all major form fields.
        Returns a dictionary with field names as keys.
        """
        
        analysis_prompt = """
        You are analyzing a screenshot of a public records request form to identify ALL major form fields.

        Identify these specific fields if present:
        1. request_description: Main textarea for the public records request content
        2. email: Email input field
        3. name: Full name input field
        4. phone: Phone number input field
        5. street_address: Street address textarea (for contact info, NOT request content)
        6. city: City input field
        7. state: State dropdown/select field
        8. zip: ZIP code input field
        9. company: Company/organization input field

        For each field found, provide the best selector and alternatives.
        If a field is not visible or doesn't exist, mark field_found as false.

        Focus on reliability - choose selectors that are most likely to work consistently.
        """
        
        # This would return a more comprehensive analysis
        # For now, let's focus on the main request field
        return {
            "request_description": self.analyze_request_description_field(screenshot_base64, page_html)
        }
    
    def get_screenshot_from_driver(self, driver) -> str:
        """Helper method to get base64 screenshot from selenium driver"""
        try:
            screenshot = driver.get_screenshot_as_png()
            return base64.b64encode(screenshot).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to take screenshot: {str(e)}")
            return ""
    
    def validate_field_selector(self, driver, selector_type: str, selector_value: str) -> bool:
        """Test if a selector actually finds an element on the page"""
        try:
            if selector_type.lower() == "css":
                elements = driver.find_elements(By.CSS_SELECTOR, selector_value)
            elif selector_type.lower() == "xpath":
                elements = driver.find_elements(By.XPATH, selector_value)
            elif selector_type.lower() == "id":
                elements = driver.find_elements(By.ID, selector_value)
            elif selector_type.lower() == "name":
                elements = driver.find_elements(By.NAME, selector_value)
            else:
                logger.warning(f"Unknown selector type: {selector_type}")
                return False
            
            found_count = len(elements)
            logger.info(f"Selector validation: {selector_type}='{selector_value}' found {found_count} elements")
            
            # We want exactly 1 element for form fields
            return found_count == 1
            
        except Exception as e:
            logger.error(f"Selector validation failed: {str(e)}")
            return False
        
    