from typing import Dict, List, Optional
from pydantic import BaseModel, Field


######## PORTAL AGENT #########
class PaginationAnalysis(BaseModel):
    """Model for analyzing pagination controls"""
    has_multiple_pages: bool = Field(description="Whether there are multiple pages available")
    last_page_number: int = Field(description="The highest page number visible")
    current_page: int = Field(description="The current page number")
    navigation_method: str = Field(description="How to navigate (click_number, click_last_button, etc)")
    navigation_instructions: str = Field(description="Specific instructions for navigation")
    confidence: float = Field(description="Confidence in the analysis (0.0 to 1.0)")
######## PORTAL AGENT #########

#### LOGIN HANDLER ######
class ScreenshotAnalysis(BaseModel):
    page_type: str = Field(description="Type of page: 'portal_home', 'login_form', 'logged_in_dashboard', 'error', 'other'")
    login_required: bool = Field(description="Whether login is required to proceed")
    login_elements_found: Dict[str, bool] = Field(
        default={
            "username_field": False,
            "password_field": False, 
            "submit_button": False,
            "sign_in_link": False
        },
        description="Login elements present: username_field, password_field, submit_button, sign_in_link"
    )
    key_elements: List[str] = Field(description="Important elements visible on the page")
    next_steps: List[str] = Field(description="Recommended actions to take next")
    confidence: float = Field(description="Confidence in analysis (0-1)")

class LoginCredentials(BaseModel):
    username: str
    password: str
#### LOGIN HANDLER ######

#### LLM HELPER ######
class RequestTableAnalysis(BaseModel):
    """Model for analyzing the requests table page"""
    total_requests_found: int = Field(description="Number of requests visible in table")
    request_numbers: List[str] = Field(description="List of request numbers found")
    requests_with_issues: List[str] = Field(description="Request numbers that appear to need attention")
    table_structure_understood: bool = Field(description="Whether the table structure was properly identified")
    navigation_elements: List[str] = Field(description="Available navigation or action elements")
    quick_insights: List[str] = Field(description="Quick insights about the requests visible")

class RequestDetailAnalysis(BaseModel):
    """Model for extracting structured data from request detail pages"""
    request_number: str = Field(description="Request number being analyzed")
    current_status: str = Field(description="Exact status as shown in source")
    request_text: str = Field(description="Full text of the original request as submitted")


    all_timeline_events: List[str] = Field(description="ALL dated events in MM/DD/YYYY: Sender: Message format")

    documents_available: List[str] = Field(description="Exact document names/links found")
    outstanding_payments: List[str] = Field(description="Exact fees/invoices with amounts if stated")
    staff_contact: str = Field(description="Exact staff name and department as shown")
    stated_deadlines: List[str] = Field(description="Any specific deadlines mentioned")

    action_required: bool = Field(description="TRUE only if explicit action needed")
    
    needs_attention: bool = Field(description="TRUE if user should review this request")
    attention_reason: str = Field(description="Specific reason why attention is needed, or 'No action required'")
    attention_priority: str = Field(description="low/medium/high based on urgency")

class MultiRequestSummary(BaseModel):
    """Model for summarizing multiple requests"""
    total_requests: int = Field(description="Total number of requests analyzed")
    urgent_requests: List[str] = Field(description="Requests needing immediate attention")
    completed_requests: List[str] = Field(description="Requests that are completed")
    waiting_requests: List[str] = Field(description="Requests waiting for agency response")
    overall_status: str = Field(description="Overall status of all requests")
    recommended_actions: List[str] = Field(description="Recommended actions for the user")
    summary: str = Field(description="Executive summary of all request activity")
#### LLM HELPER ######

###### LLM #######
class FormFieldLocation(BaseModel):
    """Model for form field identification results"""
    field_found: bool = Field(description="Whether the target field was found")
    selector_type: str = Field(description="Best selector type to use (css, xpath, id, name, etc.)")
    selector_value: str = Field(description="The actual selector string to use")
    field_description: str = Field(description="Description of what this field is for")
    confidence: float = Field(description="Confidence level 0.0-1.0")
    alternative_selectors: List[Dict[str, str]] = Field(default=[], description="Backup selectors if primary fails")
    context_info: str = Field(description="Additional context about the field location and purpose")
###### LLM #######


######### MESSAGE HELPERS ########
class MessageInterfaceAnalysis(BaseModel):
    """Model for LLM analysis of message composition interface"""
    message_field_found: bool = Field(description="Whether the message text area was found")
    message_field_selector: str = Field(description="CSS selector or XPath for the message field")
    message_field_method: str = Field(description="'css_selector', 'xpath', 'id', or 'name'")
    
    send_button_found: bool = Field(description="Whether the send button was found")
    send_button_selector: str = Field(description="CSS selector or XPath for the send button")
    send_button_method: str = Field(description="'css_selector', 'xpath', 'id', or 'text'")
    
    subject_field_found: bool = Field(description="Whether a subject field exists")
    subject_field_selector: Optional[str] = Field(description="Selector for subject field if it exists", default=None)
    
    interface_type: str = Field(description="Type of interface: 'simple', 'rich_text', 'modal', etc.")
    additional_notes: str = Field(description="Any special notes about the interface")
    confidence: float = Field(description="Confidence level 0-1 in the analysis")
######### MESSAGE HELPERS ########

######## REQUEST ANALYZER ##############
class ClickableRequest(BaseModel):
    """Model for a clickable request in the table"""
    request_number: str = Field(description="The request number/ID")
    status: str = Field(description="Current status of the request")
    description: str = Field(description="Brief description of the request")
    urgency_level: str = Field(description="Low/Medium/High based on visual cues")
    clickable_element_description: str = Field(description="Description of where to click")

class RequestTableExtraction(BaseModel):
    """Model for extracting requests from the table"""
    total_requests_visible: int = Field(description="Number of requests found in table")
    clickable_requests: List[ClickableRequest] = Field(description="List of all clickable requests")
    extraction_successful: bool = Field(description="Whether extraction worked properly")
    table_analysis: str = Field(description="Description of what the LLM sees in the table")

class ClickInstruction(BaseModel):
    """Model for LLM to provide click instructions"""
    element_to_click: str = Field(description="CSS selector or description of element to click")
    click_coordinates: Optional[tuple] = Field(description="X,Y coordinates if needed", default=None)
    click_method: str = Field(description="'link_text', 'css_selector', 'coordinates'")
    confidence: float = Field(description="Confidence level 0-1")
    reasoning: str = Field(description="Why this element should be clicked")

class MessageComposerAnalysis(BaseModel):
    """Model for analyzing the message composition interface"""
    message_box_found: bool = Field(description="Whether the message composition interface is visible")
    subject_field_available: bool = Field(description="Whether there's a subject field")
    message_field_available: bool = Field(description="Whether there's a message body field")
    send_button_location: str = Field(description="Description of where the send button is located")
    interface_description: str = Field(description="Description of the messaging interface")
######## REQUEST ANALYZER ##############



######## REQUEST FILTER MANAGER ###########
class CheckboxSelector(BaseModel):
    """Model for a single checkbox selector and metadata"""
    found: bool = Field(description="Whether the checkbox was found in the HTML")
    selector_type: str = Field(description="Type of selector: 'css' or 'xpath'")
    selector: str = Field(description="The actual selector string")
    current_state: bool = Field(description="Current checked state of the checkbox")
    confidence: float = Field(description="Confidence level 0-1 for this selector")
    reasoning: str = Field(description="Brief explanation of why this selector was chosen")

class FilterAnalysis(BaseModel):
    """Enhanced model for LLM analysis of the filter interface"""
    requester_checkbox: CheckboxSelector = Field(description="Selector info for the Requester checkbox")
    open_checkbox: CheckboxSelector = Field(description="Selector info for the Open status checkbox")
    closed_checkbox: CheckboxSelector = Field(description="Selector info for the Closed status checkbox")
    
    overall_confidence: float = Field(description="Overall confidence level 0-1 for the analysis")
    html_structure_notes: str = Field(description="Notes about the HTML structure observed")
    recommendations: List[str] = Field(description="Step-by-step recommendations for filter setup")
######## REQUEST FILTER MANAGER ###########

######## REQUEST GENERATOR ###########
class RequestOption(BaseModel):
    title: str = Field(description="Brief title for this request")
    bullet_points: List[str] = Field(description="3-5 bullet points of what to request")
    context: str = Field(description="Brief context about what this request is seeking")

class RequestOptions(BaseModel):
    options: List[RequestOption] = Field(description="List of 1-3 request options")
    recommendation: str = Field(description="Which option is recommended and why")
######## REQUEST GENERATOR ###########

######## GMAIL MONITORING ###########
class PracticalCompletenessAssessment(BaseModel):
    """Assessment of whether Gmail captures important information for request management"""
    verdict: str = Field(description="PASS or FAIL")
    practical_score: float = Field(description="0.0 to 1.0 - how practically useful is Gmail?")
    summary: str = Field(description="2-3 sentences explaining verdict")
    critical_gaps: List[str] = Field(description="List of critical missing information (empty if PASS)")
    minor_gaps: List[str] = Field(description="List of acceptable missing information (system events)")
######## GMAIL MONITORING ###########