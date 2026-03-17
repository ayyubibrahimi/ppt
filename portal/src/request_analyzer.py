import time
import logging
from typing import Dict, Any, List, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
from message_helpers import MessageHelpers
from request_filter_manager import RequestFilterManager
import re
from template_utils import generate_templates
from models import RequestTableExtraction, ClickableRequest, ClickInstruction, MessageComposerAnalysis
from llm_helper import LLMHelper
from supabase_integration import SupabaseIntegration

logger = logging.getLogger(__name__)


class RequestAnalyzer:
    """Simplified LLM-driven request analyzer with messaging capability"""
    def __init__(self, driver, screenshot_func, llm_client=None, workflow_state_helper=None):
        self.driver = driver
        self.take_screenshot = screenshot_func
        self.workflow_state_helper = workflow_state_helper

        # Initialize LLM helper if available
        if llm_client:
            try:
                self.llm_helper = LLMHelper(llm_client)
                logger.info("✅ LLM helper initialized")
            except ImportError as e:
                logger.warning(f"Could not import LLM helper, using basic analysis: {str(e)}")
                self.llm_helper = None
        else:
            self.llm_helper = None

        try:
            self.db = SupabaseIntegration()
            self.user_id = None
            self.portal_name = "Unknown Portal"
            self.submission_queue_id = None  # Track submission_queue_id for linking
            logger.info("✅ Database integration enabled")
        except Exception as e:
            logger.warning(f"⚠️ Database integration disabled: {str(e)}")
            self.db = None
    
    def set_user_info(self, email: str, full_name: str, phone: str = None, organization: str = None, portal_name: str = "Unknown Portal"):
        """Set the current user for database operations"""
        if self.db:
            try:
                self.user_id = self.db.save_user(email, full_name, phone, organization)
                self.portal_name = portal_name
                logger.info(f"✅ User set: {email}")
            except Exception as e:
                logger.error(f"❌ Failed to set user: {str(e)}")


    def navigate_to_all_requests(self) -> Dict[str, Any]:
        """Navigate to the 'All requests' page"""
        try:
            logger.info("🔍 Navigating to 'All requests' page")
            
            all_requests_selectors = [
                (By.LINK_TEXT, "All requests"),
                (By.PARTIAL_LINK_TEXT, "All requests"),
                (By.XPATH, "//a[contains(text(), 'All requests')]"),
                (By.CSS_SELECTOR, "a[href*='requests']"),
                (By.XPATH, "//nav//a[contains(text(), 'requests')]")
            ]
            
            for selector_type, selector_value in all_requests_selectors:
                try:
                    element = WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(1)
                    element.click()
                    time.sleep(3)
                    
                    logger.info(f"✅ Successfully navigated to All requests")
                    self.take_screenshot("all_requests_page")
                    
                    return {
                        'success': True,
                        'url': self.driver.current_url,
                        'title': self.driver.title
                    }
                    
                except TimeoutException:
                    continue
                except Exception as e:
                    logger.warning(f"Failed to click All requests with {selector_type}: {str(e)}")
                    continue
            
            logger.error("❌ Could not find 'All requests' navigation link")
            return {
                'success': False,
                'error': "Could not find 'All requests' navigation link"
            }
            
        except Exception as e:
            logger.error(f"Failed to navigate to all requests: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    

    def extract_requests_with_llm(self) -> RequestTableExtraction:
        """Extract all clickable requests directly from DOM with improved coverage"""
        try:
            logger.info("🔍 Extracting requests directly from DOM")
            
            # Step 1: Scroll to bottom to trigger any lazy loading
            logger.info("📜 Scrolling to load all requests...")
            self._scroll_to_load_all_requests()
            
            # Step 2: Try multiple selector patterns to catch all request links
            all_request_links = []
            
            # Different selector patterns that might be used
            selector_patterns = [
                "a[href*='/requests/']",           # Current pattern
                "a[href*='/request/']",            # Alternative singular
                "a[href*='requests']",             # Broader pattern
            ]
            
            for pattern in selector_patterns:
                try:
                    links = self.driver.find_elements(By.CSS_SELECTOR, pattern)
                    all_request_links.extend(links)
                    logger.info(f"   Found {len(links)} links with pattern: {pattern}")
                    
                except Exception as e:
                    logger.debug(f"Pattern {pattern} failed: {str(e)}")
                    continue
            
            # Step 3: Extract and validate request IDs
            request_ids = []
            seen_hrefs = set()  # Track to avoid duplicates from multiple selectors
            
            for link in all_request_links:
                try:
                    href = link.get_attribute("href")
                    if not href or href in seen_hrefs:
                        continue
                        
                    seen_hrefs.add(href)
                    
                    # Extract ID from href like "/requests/23-8848"
                    if "/requests/" in href:
                        request_id = href.split("/requests/")[-1].strip('/')
                        # Remove any query parameters
                        request_id = request_id.split('?')[0].split('#')[0]
                        
                        # Validate the ID matches expected pattern (XX-XXXX or XX-XXXXX)
                        if re.match(r'^\d+-\d+$', request_id):
                            request_ids.append(request_id)
                        
                except Exception as e:
                    logger.debug(f"Failed to process link: {str(e)}")
                    continue
            
            # Step 4: Remove duplicates and sort
            unique_ids = list(set(request_ids))  
            
            # Step 5: Debug logging to understand what we found
            logger.info(f"📊 Extraction Summary:")
            logger.info(f"   Total links found: {len(all_request_links)}")
            logger.info(f"   Unique hrefs: {len(seen_hrefs)}")
            logger.info(f"   Valid request IDs: {len(unique_ids)}")
            
            # Step 6: Log some examples for debugging
            if len(seen_hrefs) > 0:
                logger.info(f"   Sample hrefs: {list(seen_hrefs)[:5]}")
            
            if len(unique_ids) > 0:
                logger.info(f"   Sample IDs: {unique_ids[:5]}")
            
            # Step 7: Create ClickableRequest objects for compatibility
            clickable_requests = []
            for request_id in unique_ids:
                clickable_requests.append(ClickableRequest(
                    request_number=request_id,
                    status="Unknown",  # Will be determined when clicked
                    description="Click to view details",
                    urgency_level="Low",  # Default, will be determined when analyzed
                    clickable_element_description=f"Link for request {request_id}"
                ))
            
            logger.info(f"✅ Found {len(unique_ids)} request IDs")
            
            return RequestTableExtraction(
                total_requests_visible=len(unique_ids),
                clickable_requests=clickable_requests,
                extraction_successful=True,
                table_analysis=f"Direct DOM extraction found {len(unique_ids)} requests using multiple selectors"
            )
            
        except Exception as e:
            logger.error(f"Direct extraction failed: {str(e)}")
            return RequestTableExtraction(
                total_requests_visible=0,
                clickable_requests=[],
                extraction_successful=False,
                table_analysis=f"Extraction failed: {str(e)}"
            )

    def _scroll_to_load_all_requests(self):
        """Scroll down to trigger lazy loading of all requests"""
        try:
            logger.info("📜 Scrolling to ensure all requests are loaded...")
            
            # Get initial height
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            
            scroll_attempts = 0
            max_attempts = 10
            
            while scroll_attempts < max_attempts:
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
                # Wait for new content to load
                time.sleep(5)
                
                # Calculate new scroll height
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                
                if new_height == last_height:
                    # No new content loaded
                    break
                    
                last_height = new_height
                scroll_attempts += 1
                logger.info(f"   Scroll attempt {scroll_attempts}: height now {new_height}")
            
            # Scroll back to top
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(5)
            
            logger.info(f"✅ Scrolling completed after {scroll_attempts} attempts")
            
        except Exception as e:
            logger.warning(f"⚠️ Scrolling failed: {str(e)}")

    def click_request_with_llm(self, request_number: str) -> Dict[str, Any]:
        """Use LLM to find and click on a specific request"""
        try:
            logger.info(f"🖱️ Using LLM to click request {request_number}")
            
            # Take screenshot for click analysis
            screenshot_b64 = self.llm_helper.get_screenshot_from_driver(self.driver)
            page_text = self.llm_helper.extract_page_text(self.driver)
            
            if not screenshot_b64:
                return {"success": False, "error": "Could not capture screenshot"}
            
            # Create click instruction prompt
            click_prompt = f"""
            You are looking at a screenshot and need to identify exactly how to click on request {request_number}.
            
            Your job is to:
            1. **Find request {request_number}** in the table
            2. **Identify the clickable element** (usually a blue link)
            3. **Provide specific instructions** for clicking it
            
            Options for clicking:
            - If it's a clear link with the request number, provide the link text
            - If you can see specific coordinates, provide X,Y coordinates
            - If there's a CSS pattern, describe the selector
            
            Be very specific about what element to click and why you're confident it will work.
            """
            
            structured_llm = self.llm_helper.llm_client.with_structured_output(ClickInstruction)
            
            messages = [
                {"role": "system", "content": click_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": f"Find and provide click instructions for request {request_number}. Page context:\n\n{page_text[:800]}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
                        }
                    ]
                }
            ]
            
            click_instruction = structured_llm.invoke(messages)
            
            logger.info(f"🎯 LLM click instruction: {click_instruction.reasoning}")
            
            # Execute the click based on LLM instruction
            success = self._execute_click_instruction(click_instruction, request_number)
            
            if success:
                time.sleep(3)  # Wait for page load
                self.take_screenshot(f"request_detail_{request_number}")
                return {
                    "success": True,
                    "request_number": request_number,
                    "url": self.driver.current_url,
                    "click_method": click_instruction.click_method
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to execute click instruction: {click_instruction.element_to_click}"
                }
            
        except Exception as e:
            logger.error(f"LLM click failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _execute_click_instruction(self, instruction: ClickInstruction, request_number: str) -> bool:
        """Execute the click instruction provided by LLM"""
        try:
            if instruction.click_method == "link_text":
                element = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.LINK_TEXT, request_number))
                )
                element.click()
                return True
            
            elif instruction.click_method == "css_selector":
                element = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, instruction.element_to_click))
                )
                element.click()
                return True
            
            elif instruction.click_method == "coordinates" and instruction.click_coordinates:
                x, y = instruction.click_coordinates
                ActionChains(self.driver).move_to_element_with_offset(
                    self.driver.find_element(By.TAG_NAME, "body"), x, y
                ).click().perform()
                return True
            
            else:
                # Fallback: try partial link text
                element = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, request_number))
                )
                element.click()
                return True
                
        except Exception as e:
            logger.warning(f"Click execution failed: {str(e)}")
            return False
    
    def analyze_request_detail_with_llm(self, request_number: str, auto_save: bool = True) -> Dict[str, Any]:
        """Use existing LLM helper to analyze request detail page"""
        try:
            logger.info(f"🧠 Analyzing request {request_number} detail page")

            screenshot_b64 = self.llm_helper.get_screenshot_from_driver(self.driver)
            page_text = self.llm_helper.extract_page_text(self.driver)

            if not screenshot_b64:
                return {"success": False, "error": "Could not capture screenshot"}

            # Append document upload status to page_text if available
            if self.db and self.user_id:
                try:
                    docs = self.db.supabase.table('document_downloads').select('document_title, download_status').eq('request_number', request_number).execute()
                    if docs.data:
                        page_text += "\n\n=== DOCUMENT UPLOAD STATUS ===\n"
                        for doc in docs.data:
                            page_text += f"- {doc['document_title']}: {doc['download_status']}\n"
                except Exception as e:
                    logger.warning(f"Could not fetch document status: {str(e)}")

            analysis = self.llm_helper.analyze_request_detail_page(
                screenshot_b64, page_text, request_number
            )

            # Validate that analysis contains meaningful request data
            has_content = self._validate_analysis_content(analysis, request_number)

            if not has_content:
                logger.warning(f"⚠️ Request {request_number} page lacks meaningful content (may be pending/incomplete)")
                return {
                    "success": False,
                    "error": "Request page exists but lacks meaningful content (pending confirmation or incomplete data)",
                    "request_number": request_number,
                    "saved_to_db": False
                }

            result = {
                "success": True,
                "analysis": analysis,
                "request_number": request_number
            }

            # Only auto-save if explicitly requested (default True for backward compatibility)
            if auto_save and self.db and self.user_id:
                try:
                    # Determine workflow_state if helper available
                    workflow_state = 'monitoring'  # Default
                    if self.workflow_state_helper:
                        try:
                            request_data = {
                                'current_status': analysis.current_status,
                                'agent_attention_needed': analysis.needs_attention,
                                'agent_attention_reason': analysis.attention_reason,
                                'agent_attention_priority': analysis.attention_priority,
                                'latest_analysis': {
                                    'outstanding_payments': analysis.outstanding_payments,
                                    'documents_available': analysis.documents_available
                                }
                            }
                            # For new requests, we don't have request_id yet, so can't check drafts/docs
                            workflow_state = self.workflow_state_helper.determine_workflow_state(
                                request_data=request_data,
                                has_pending_draft=False,
                                documents_status=None
                            )
                            logger.info(f"🔄 Determined workflow_state: {workflow_state}")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to determine workflow_state: {e}")

                    saved = self.db.save_request_analysis(
                        self.user_id,
                        self.portal_name,
                        analysis,
                        submission_queue_id=self.submission_queue_id,  # Pass submission_queue_id for linking
                        workflow_state=workflow_state
                    )
                    result['saved_to_db'] = saved
                    if saved:
                        logger.info(f"💾 Request {request_number} saved to database with workflow_state={workflow_state}")
                        if self.submission_queue_id:
                            logger.info(f"🔗 Linked to submission_queue: {self.submission_queue_id}")
                except Exception as e:
                    logger.error(f"❌ Database save failed for {request_number}: {str(e)}")
                    result['saved_to_db'] = False
            else:
                result['saved_to_db'] = False
                if not auto_save:
                    logger.info(f"📝 Request {request_number} analyzed but not saved (monitoring mode)")

            return result

        except Exception as e:
            logger.error(f"Request detail analysis failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def _validate_analysis_content(self, analysis, request_number: str) -> bool:
        """
        Validate that the analysis contains meaningful request data.
        Returns False if page is pending/incomplete.
        """
        try:
            # Check if analysis has required attributes
            if not hasattr(analysis, 'request_text') or not hasattr(analysis, 'current_status'):
                logger.warning(f"⚠️ Analysis missing required attributes")
                return False

            # Check if request_text has content (not empty or just whitespace)
            request_text = getattr(analysis, 'request_text', '').strip()
            if not request_text or len(request_text) < 20:
                logger.warning(f"⚠️ Request text too short or empty: {len(request_text)} chars")
                return False

            # Check if status is meaningful (not just "Pending" or empty)
            status = getattr(analysis, 'current_status', '').strip().lower()
            if not status or status in ['pending', 'unknown', 'n/a', 'not available']:
                logger.warning(f"⚠️ Status indicates incomplete page: '{status}'")
                return False

            # Check if there are timeline events (good indicator of a complete page)
            timeline_events = getattr(analysis, 'all_timeline_events', [])
            if not timeline_events or len(timeline_events) == 0:
                logger.warning(f"⚠️ No timeline events found (may indicate pending page)")
                return False

            logger.info(f"✅ Request {request_number} has valid content (status: {status}, {len(timeline_events)} timeline events)")
            return True

        except Exception as e:
            logger.error(f"❌ Error validating analysis content: {str(e)}")
            return False
        
    def find_message_button_with_llm(self) -> Dict[str, Any]:
        """Use LLM to find the message/letter button on the request detail page"""
        try:
            logger.info("🔍 Looking for message button with LLM")
            
            screenshot_b64 = self.llm_helper.get_screenshot_from_driver(self.driver)
            page_text = self.llm_helper.extract_page_text(self.driver)
            
            if not screenshot_b64:
                return {"success": False, "error": "Could not capture screenshot"}
            
            button_prompt = """
            You are looking at a request detail page. Find the message/letter button that allows sending a new message to the request staff.
            
            Look for:
            - A letter/envelope icon (usually in the top right corner)
            - A "Send message" or "New message" button  
            - An email or communication icon
            - Any clickable element that would open a message composition interface
            
            IMPORTANT: Provide the EXACT CSS selector, XPath, or specific attributes that can be used to find this element.
            Look for:
            - Specific class names
            - ID attributes
            - Data attributes
            - Exact positioning elements
            
            Be very specific about the selector - avoid generic terms like "envelope" and provide the actual HTML attributes.
            """
            
            structured_llm = self.llm_helper.llm_client.with_structured_output(ClickInstruction)
            
            messages = [
                {"role": "system", "content": button_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Find the message button and provide EXACT CSS selector or XPath. Page context:\n\n{page_text[:800]}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
                        }
                    ]
                }
            ]
            
            click_instruction = structured_llm.invoke(messages)
            
            logger.info(f"🎯 Message button instruction: {click_instruction.reasoning}")
            logger.info(f"🎯 Element to click: {click_instruction.element_to_click}")
            logger.info(f"🎯 Click method: {click_instruction.click_method}")
            
            return {
                "success": True,
                "instruction": click_instruction
            }
            
        except Exception as e:
            logger.error(f"Failed to find message button: {str(e)}")
            return {"success": False, "error": str(e)}

    def _execute_message_click(self, instruction: ClickInstruction) -> bool:
        """Execute the message button click instruction with comprehensive fallback strategies"""
        try:
            logger.info(f"🖱️ Attempting to click message button using method: {instruction.click_method}")
            logger.info(f"🖱️ Target element: {instruction.element_to_click}")
            
            # Strategy 1: Use LLM's specific instruction first
            if instruction.element_to_click and instruction.click_method == "css_selector":
                try:
                    logger.info(f"🎯 Trying LLM CSS selector: {instruction.element_to_click}")
                    element = WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, instruction.element_to_click))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.5)
                    element.click()
                    logger.info("✅ Successfully clicked using LLM CSS selector")
                    return True
                except Exception as e:
                    logger.warning(f"❌ LLM CSS selector failed: {str(e)}")
            
            # Strategy 2: Try XPath if provided
            if instruction.element_to_click and instruction.click_method == "xpath":
                try:
                    logger.info(f"🎯 Trying LLM XPath: {instruction.element_to_click}")
                    element = WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((By.XPATH, instruction.element_to_click))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.5)
                    element.click()
                    logger.info("✅ Successfully clicked using LLM XPath")
                    return True
                except Exception as e:
                    logger.warning(f"❌ LLM XPath failed: {str(e)}")
            
            # Strategy 3: Coordinates if provided
            if instruction.click_coordinates and instruction.click_method == "coordinates":
                try:
                    x, y = instruction.click_coordinates
                    logger.info(f"🎯 Trying coordinates: ({x}, {y})")
                    ActionChains(self.driver).move_to_element_with_offset(
                        self.driver.find_element(By.TAG_NAME, "body"), x, y
                    ).click().perform()
                    logger.info("✅ Successfully clicked using coordinates")
                    return True
                except Exception as e:
                    logger.warning(f"❌ Coordinates click failed: {str(e)}")
            
            # Strategy 4: Comprehensive fallback selectors based on common patterns
            logger.info("🔄 Trying fallback selectors...")
            
            fallback_selectors = [
                # Envelope/message icon patterns
                (By.CSS_SELECTOR, "[class*='envelope']"),
                (By.CSS_SELECTOR, "[class*='message']"),
                (By.CSS_SELECTOR, "[class*='mail']"),
                (By.CSS_SELECTOR, "[title*='message'], [title*='Message']"),
                (By.CSS_SELECTOR, "[title*='send'], [title*='Send']"),
                (By.CSS_SELECTOR, "[title*='email'], [title*='Email']"),
                
                # Icon classes
                (By.CSS_SELECTOR, ".fa-envelope"),
                (By.CSS_SELECTOR, ".fa-mail"),
                (By.CSS_SELECTOR, ".fa-message"),
                (By.CSS_SELECTOR, "[class*='icon-envelope']"),
                (By.CSS_SELECTOR, "[class*='icon-mail']"),
                
                # Button patterns
                (By.XPATH, "//button[contains(@title, 'message') or contains(@title, 'Message')]"),
                (By.XPATH, "//a[contains(@title, 'message') or contains(@title, 'Message')]"),
                (By.XPATH, "//button[contains(@class, 'message') or contains(@class, 'envelope')]"),
                (By.XPATH, "//a[contains(@class, 'message') or contains(@class, 'envelope')]"),
                
                # Top-right corner elements (common placement)
                (By.CSS_SELECTOR, ".top-right a, .header-right a, .actions a"),
                (By.CSS_SELECTOR, ".top-right button, .header-right button, .actions button"),
                
                # Data attributes
                (By.CSS_SELECTOR, "[data-action*='message']"),
                (By.CSS_SELECTOR, "[data-toggle*='message']"),
                (By.CSS_SELECTOR, "[data-target*='message']"),
                
                # Generic icon buttons in top area
                (By.XPATH, "//div[contains(@class, 'top') or contains(@class, 'header')]//a"),
                (By.XPATH, "//div[contains(@class, 'top') or contains(@class, 'header')]//button"),
            ]
            
            for i, (selector_type, selector_value) in enumerate(fallback_selectors):
                try:
                    logger.info(f"🎯 Trying fallback {i+1}/{len(fallback_selectors)}: {selector_value}")
                    
                    # Find all matching elements
                    elements = self.driver.find_elements(selector_type, selector_value)
                    
                    for j, element in enumerate(elements):
                        try:
                            # Check if element is visible and clickable
                            if element.is_displayed() and element.is_enabled():
                                # Get element info for debugging
                                element_info = self._get_element_info(element)
                                logger.info(f"   📍 Found element {j+1}: {element_info}")
                                
                                # Try to click
                                WebDriverWait(self.driver, 3).until(
                                    EC.element_to_be_clickable(element)
                                )
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.5)
                                element.click()
                                
                                logger.info(f"✅ Successfully clicked fallback element: {element_info}")
                                return True
                                
                        except Exception as e:
                            logger.debug(f"   ❌ Element {j+1} click failed: {str(e)}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"   ❌ Fallback selector {i+1} failed: {str(e)}")
                    continue
            
            # Strategy 5: JavaScript click on all potentially relevant elements
            logger.info("🔄 Trying JavaScript click strategy...")
            try:
                # Get all clickable elements in the top area
                js_script = """
                var elements = document.querySelectorAll('a, button');
                var candidates = [];
                
                for (var i = 0; i < elements.length; i++) {
                    var el = elements[i];
                    var rect = el.getBoundingClientRect();
                    var text = el.textContent.toLowerCase();
                    var title = (el.title || '').toLowerCase();
                    var className = (el.className || '').toLowerCase();
                    
                    // Look for elements in top area or with message-related attributes
                    if (rect.top < 200 || 
                        text.includes('message') || 
                        title.includes('message') || 
                        title.includes('send') ||
                        className.includes('envelope') || 
                        className.includes('message') ||
                        className.includes('mail')) {
                        
                        candidates.push({
                            element: el,
                            text: text,
                            title: title,
                            className: className,
                            position: {x: rect.left, y: rect.top}
                        });
                    }
                }
                
                return candidates;
                """
                
                candidates = self.driver.execute_script(js_script)
                
                for i, candidate in enumerate(candidates):
                    try:
                        logger.info(f"🎯 Trying JS candidate {i+1}: {candidate}")
                        
                        # Try JavaScript click
                        self.driver.execute_script("arguments[0].click();", candidate['element'])
                        time.sleep(1)
                        
                        # Check if something changed (message composer opened)
                        if self._check_for_message_composer():
                            logger.info(f"✅ Successfully clicked JS candidate: {candidate}")
                            return True
                            
                    except Exception as e:
                        logger.debug(f"   ❌ JS candidate {i+1} failed: {str(e)}")
                        continue
            
            except Exception as e:
                logger.warning(f"❌ JavaScript strategy failed: {str(e)}")
            
            logger.error("❌ All click strategies failed")
            return False
            
        except Exception as e:
            logger.error(f"❌ Message click execution failed: {str(e)}")
            return False

    def _get_element_info(self, element) -> str:
        """Get debugging info about an element"""
        try:
            tag = element.tag_name
            text = element.text[:20] if element.text else ""
            title = element.get_attribute("title") or ""
            class_name = element.get_attribute("class") or ""
            return f"{tag} | text:'{text}' | title:'{title}' | class:'{class_name[:30]}'"
        except:
            return "unknown element"

    def _check_for_message_composer(self) -> bool:
        """Check if message composer interface opened"""
        try:
            # Look for common message composer indicators
            composer_selectors = [
                "textarea[placeholder*='message']",
                "textarea[name*='message']",
                "input[placeholder*='subject']",
                "[class*='message-composer']",
                "[class*='modal']",
                "form[action*='message']"
            ]
            
            for selector in composer_selectors:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
            
            return False
        except:
            return False

    # Also add this debugging method to help troubleshoot
    def debug_page_elements(self) -> Dict[str, Any]:
        """Debug method to find all potentially clickable elements"""
        try:
            logger.info("🔍 Debugging all clickable elements on page")
            
            # Get all clickable elements
            clickable_elements = self.driver.find_elements(By.CSS_SELECTOR, "a, button, [onclick], [role='button']")
            
            elements_info = []
            for i, element in enumerate(clickable_elements):
                try:
                    if element.is_displayed():
                        info = {
                            'index': i,
                            'tag': element.tag_name,
                            'text': element.text[:50] if element.text else "",
                            'title': element.get_attribute("title") or "",
                            'class': element.get_attribute("class") or "",
                            'id': element.get_attribute("id") or "",
                            'href': element.get_attribute("href") or "",
                            'onclick': element.get_attribute("onclick") or "",
                            'position': element.location,
                            'size': element.size
                        }
                        elements_info.append(info)
                except:
                    continue
            
            # Log top-area elements (likely candidates for message button)
            top_elements = [el for el in elements_info if el['position']['y'] < 200]
            
            logger.info(f"Found {len(top_elements)} clickable elements in top area:")
            for el in top_elements:
                logger.info(f"  {el['index']}: {el['tag']} | {el['text']} | {el['title']} | {el['class']}")
            
            return {
                "success": True,
                "total_elements": len(clickable_elements),
                "visible_elements": len(elements_info),
                "top_area_elements": len(top_elements),
                "elements": elements_info
            }
            
        except Exception as e:
            logger.error(f"Debug failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def click_message_button(self, instruction: ClickInstruction) -> Dict[str, Any]:
        """Click the message button based on LLM instruction"""
        try:
            logger.info("📧 Clicking message button")
            
            # Execute the click
            success = self._execute_message_click(instruction)
            
            if success:
                time.sleep(2)  # Wait for message interface to load
                self.take_screenshot("message_composer_opened")
                return {"success": True}
            else:
                return {"success": False, "error": "Failed to click message button"}
                
        except Exception as e:
            logger.error(f"Failed to click message button: {str(e)}")
            return {"success": False, "error": str(e)}
    

    
    def analyze_message_composer_with_llm(self) -> MessageComposerAnalysis:
        """Analyze the message composition interface"""
        try:
            logger.info("🔍 Analyzing message composer interface")
            
            screenshot_b64 = self.llm_helper.get_screenshot_from_driver(self.driver)
            page_text = self.llm_helper.extract_page_text(self.driver)
            
            if not screenshot_b64:
                return MessageComposerAnalysis(
                    message_box_found=False,
                    subject_field_available=False,
                    message_field_available=False,
                    send_button_location="Screenshot capture failed",
                    interface_description="Could not capture screenshot"
                )
            
            composer_prompt = """
            You are analyzing a message composition interface for a public records request.
            
            Identify:
            1. Whether the message composition box/modal is visible
            2. If there's a subject field for the message
            3. If there's a message body text area
            4. Where the send button is located
            5. Any other important elements of the interface
            
            Describe what you see so the user knows how to compose their message.
            """
            
            structured_llm = self.llm_helper.llm_client.with_structured_output(MessageComposerAnalysis)
            
            messages = [
                {"role": "system", "content": composer_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Analyze this message composition interface. Page context:\n\n{page_text[:800]}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
                        }
                    ]
                }
            ]
            
            result = structured_llm.invoke(messages)
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze message composer: {str(e)}")
            return MessageComposerAnalysis(
                message_box_found=False,
                subject_field_available=False,
                message_field_available=False,
                send_button_location="Analysis failed",
                interface_description=f"Analysis error: {str(e)}"
            )
    
    def send_message_to_request(self, subject: str, message: str) -> Dict[str, Any]:
        """Send message using LLM-driven interface analysis"""
        message_helper = MessageHelpers(self.driver, self.llm_helper)
        return message_helper.send_message_with_llm_selectors(subject, message)
    

    def debug_message_interface(self) -> Dict[str, Any]:
        """Debug the message interface to see available elements"""
        try:
            logger.info("🔍 Debugging message interface elements")
            
            # Find all text areas
            textareas = self.driver.find_elements(By.TAG_NAME, "textarea")
            logger.info(f"Found {len(textareas)} textarea elements:")
            
            for i, textarea in enumerate(textareas):
                try:
                    info = {
                        'index': i,
                        'visible': textarea.is_displayed(),
                        'enabled': textarea.is_enabled(),
                        'placeholder': textarea.get_attribute("placeholder"),
                        'name': textarea.get_attribute("name"),
                        'id': textarea.get_attribute("id"),
                        'class': textarea.get_attribute("class"),
                        'text': textarea.text[:30] if textarea.text else ""
                    }
                    logger.info(f"  Textarea {i}: {info}")
                except:
                    logger.info(f"  Textarea {i}: Could not get info")
            
            # Find all buttons
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            logger.info(f"Found {len(buttons)} button elements:")
            
            for i, button in enumerate(buttons):
                try:
                    info = {
                        'index': i,
                        'visible': button.is_displayed(),
                        'enabled': button.is_enabled(),
                        'text': button.text.strip(),
                        'type': button.get_attribute("type"),
                        'class': button.get_attribute("class"),
                        'id': button.get_attribute("id")
                    }
                    logger.info(f"  Button {i}: {info}")
                except:
                    logger.info(f"  Button {i}: Could not get info")
            
            return {"success": True, "textareas": len(textareas), "buttons": len(buttons)}
            
        except Exception as e:
            logger.error(f"Debug failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def run_simplified_workflow(self) -> Dict[str, Any]:
        """Run the simplified 4-step workflow"""
        try:
            logger.info("🚀 Starting simplified LLM-driven workflow")
            
            # Check if LLM helper is available
            if not self.llm_helper:
                return {
                    "success": False, 
                    "error": "LLM helper not available - cannot run multimodal analysis"
                }
            
            # Step 0: Navigate to "All requests" page first
            print("\n🧭 Step 0: Navigating to 'All requests' page...")
            nav_result = self.navigate_to_all_requests()
            if not nav_result['success']:
                return {
                    'success': False,
                    'error': f"Failed to navigate to All requests page: {nav_result['error']}"
                }
            
            # NEW STEP 0.5: Apply mandatory filters for requester and status
            print("\n🎯 Step 0.5: Applying request filters...")
            filter_manager = RequestFilterManager(self.driver, self.llm_helper.llm_client, self.take_screenshot)
            
            if not filter_manager.setup_filters():
                print("❌ CRITICAL: Could not filter for your requests!")
                print("   Without filtering, you'll see ALL users' requests, not just yours.")
                
                # Give user choice to continue or exit
                while True:
                    choice = input("\nContinue anyway? (y/n): ").strip().lower()
                    if choice in ['y', 'yes']:
                        print("⚠️  Proceeding without filters - you may see other users' requests")
                        break
                    elif choice in ['n', 'no']:
                        return {
                            'success': False,
                            'error': "Cannot proceed without requester filter - exiting"
                        }
                    else:
                        print("Please enter 'y' for yes or 'n' for no")
            else:
                print("✅ Filters applied successfully - showing only your requests")
            
            # Step 1: Extract all requests using LLM
            print("\n🔍 Step 1: Finding all available requests...")
            extraction = self.extract_requests_with_llm()
            
            if not extraction.extraction_successful or not extraction.clickable_requests:
                print(f"❌ No requests found. LLM analysis: {extraction.table_analysis}")
                return {"success": False, "error": "No requests found"}
            
            # Step 2: Present options to user
            print(f"\n📋 Step 2: Found {extraction.total_requests_visible} request(s):")
            print("-" * 80)
            
            for i, req in enumerate(extraction.clickable_requests):
                urgency_emoji = "🚨" if req.urgency_level == "High" else "⚠️" if req.urgency_level == "Medium" else "📄"
                print(f"{i+1}. {urgency_emoji} Request {req.request_number} - {req.status}")
                print(f"   {req.description[:60]}...")
                print()
            
            print("0. Analyze all requests")
            print("-" * 80)
            
            # Step 3: Get user choice
            while True:
                try:
                    choice = input(f"Choose a request to analyze (0-{len(extraction.clickable_requests)}): ").strip()
                    
                    if choice == "0":
                        return self._analyze_all_requests(extraction.clickable_requests)
                    
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(extraction.clickable_requests):
                        selected_request = extraction.clickable_requests[choice_num - 1]
                        return self._analyze_single_request(selected_request)
                    else:
                        print(f"Please enter a number between 0 and {len(extraction.clickable_requests)}")
                        
                except ValueError:
                    print("Please enter a valid number")
                except KeyboardInterrupt:
                    print("\n👋 Analysis cancelled")
                    return {"success": False, "error": "User cancelled"}
            
        except Exception as e:
            logger.error(f"Simplified workflow failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _analyze_single_request(self, request: ClickableRequest) -> Dict[str, Any]:
        """Analyze a single selected request with messaging options"""
        try:
            print(f"\n🔍 Step 4: Analyzing Request {request.request_number}...")
            print("-" * 60)
            
            # Click on the request using LLM
            click_result = self.click_request_with_llm(request.request_number)
            if not click_result["success"]:
                return {
                    "success": False,
                    "error": f"Failed to click request: {click_result['error']}"
                }
            
            # Analyze the detail page
            analysis_result = self.analyze_request_detail_with_llm(request.request_number)
            if not analysis_result["success"]:
                return {
                    "success": False,
                    "error": f"Failed to analyze request: {analysis_result['error']}"
                }
            
            # Display results
            analysis = analysis_result["analysis"]
            self._display_analysis_summary(analysis)
            
            # Present action options to user
            print(f"\n🎯 NEXT ACTIONS:")
            print("-" * 50)
            print("1. Send a message to request staff")
            print("2. Return to main requests page")
            print("3. Exit analysis")
            print("-" * 50)
            
            while True:
                try:
                    action_choice = input("Choose an action (1-3): ").strip()
                    
                    if action_choice == "1":
                        # Handle message sending
                        message_result = self._handle_message_sending(request.request_number, analysis)
                        if message_result["success"]:
                            print("✅ Message sent successfully!")
                        else:
                            print(f"❌ Failed to send message: {message_result['error']}")
                        
                        # Ask if they want to do anything else
                        continue_choice = input("\nDo something else? (y/n): ").strip().lower()
                        if continue_choice != 'y':
                            break
                    
                    elif action_choice == "2":
                        print("🔙 Returning to main requests page...")
                        break
                    
                    elif action_choice == "3":
                        print("👋 Exiting analysis...")
                        return {
                            "success": True,
                            "request_number": request.request_number,
                            "analysis": analysis,
                            "action": "exit"
                        }
                    
                    else:
                        print("Please enter 1, 2, or 3")
                        
                except ValueError:
                    print("Please enter a valid number")
                except KeyboardInterrupt:
                    print("\n👋 Analysis cancelled")
                    break
            
            return {
                "success": True,
                "request_number": request.request_number,
                "analysis": analysis,
                "action": "completed"
            }
            
        except Exception as e:
            logger.error(f"Single request analysis failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _handle_message_sending(self, request_number: str, analysis=None) -> Dict[str, Any]:
        """Handle the complete message sending workflow with improved terminal input"""
        try:
            print(f"\n📧 Sending message for request {request_number}...")
            
            # Step 1: Find the message button
            button_result = self.find_message_button_with_llm()
            if not button_result["success"]:
                return {"success": False, "error": f"Could not find message button: {button_result['error']}"}
            
            # Step 2: Click the message button
            click_result = self.click_message_button(button_result["instruction"])
            if not click_result["success"]:
                return {"success": False, "error": f"Could not click message button: {click_result['error']}"}
            
            # Step 3: Analyze the message composer
            composer_analysis = self.analyze_message_composer_with_llm()
            if not composer_analysis.message_box_found:
                return {"success": False, "error": "Message composition interface not found"}
            
            print(f"\n📝 Message Composer Interface:")
            print(f"   {composer_analysis.interface_description}")
            print(f"   Subject field: {'Available' if composer_analysis.subject_field_available else 'Not available'}")
            print(f"   Message field: {'Available' if composer_analysis.message_field_available else 'Not available'}")
            
            # Step 4: Get message content from user with improved interface (now with AI context)
            message_data = self._get_message_input_from_terminal_with_templates(
                composer_analysis.subject_field_available, 
                analysis, 
                request_number
            )
            
            if not message_data["success"]:
                return {"success": False, "error": message_data["error"]}
            
            # Step 5: Send the message
            print(f"\n📤 Sending message...")
            send_result = self.send_message_to_request(
                message_data["subject"], 
                message_data["message"]
            )
            
            return send_result
            
        except Exception as e:
            logger.error(f"Message sending workflow failed: {str(e)}")
            return {"success": False, "error": str(e)}


    def _get_message_input_from_terminal(self, has_subject_field: bool) -> Dict[str, Any]:
        """Get message content from user via terminal with improved UX"""
        try:
            print(f"\n" + "="*70)
            print(f"✍️  COMPOSE YOUR MESSAGE")
            print(f"="*70)
            
            subject = ""
            
            # Get subject if field is available
            if has_subject_field:
                print(f"\n📌 SUBJECT:")
                print(f"   Enter a brief subject line for your message")
                while True:
                    subject = input(f"   Subject: ").strip()
                    if subject:
                        break
                    print(f"   ⚠️  Subject cannot be empty. Please enter a subject.")
            
            # Get message content with better instructions
            print(f"\n📄 MESSAGE:")
            print(f"   Write your message below.")
            print(f"   Tips:")
            print(f"   • Be clear and specific about what you need")
            print(f"   • Include any relevant details or reference numbers")
            print(f"   • Be polite and professional")
            print(f"   • When finished, type 'SEND' on a new line to send")
            print(f"   • Type 'CANCEL' to cancel the message")
            print(f"   • Type 'PREVIEW' to review your message before sending")
            print(f"\n   Start typing your message:")
            print(f"   " + "-"*50)
            
            message_lines = []
            
            while True:
                try:
                    line = input("   ")
                    
                    # Handle special commands
                    if line.upper() == "SEND":
                        if message_lines:
                            break
                        else:
                            print(f"   ⚠️  Message cannot be empty. Please write something or type CANCEL.")
                            continue
                    
                    elif line.upper() == "CANCEL":
                        print(f"\n❌ Message cancelled.")
                        return {"success": False, "error": "User cancelled message"}
                    
                    elif line.upper() == "PREVIEW":
                        self._preview_message(subject, "\n".join(message_lines))
                        print(f"\n   Continue editing or type SEND to send:")
                        continue
                    
                    else:
                        message_lines.append(line)
                
                except KeyboardInterrupt:
                    print(f"\n\n❌ Message cancelled by user.")
                    return {"success": False, "error": "User cancelled message"}
            
            message = "\n".join(message_lines).strip()
            
            # Final confirmation
            print(f"\n" + "="*70)
            self._preview_message(subject, message)
            print(f"="*70)
            
            while True:
                confirm = input(f"\nSend this message? (y/n/edit): ").strip().lower()
                
                if confirm in ['y', 'yes']:
                    return {
                        "success": True,
                        "subject": subject,
                        "message": message
                    }
                elif confirm in ['n', 'no']:
                    print(f"❌ Message not sent.")
                    return {"success": False, "error": "User chose not to send message"}
                elif confirm in ['e', 'edit']:
                    # Allow editing
                    edit_result = self._edit_message(subject, message, has_subject_field)
                    if edit_result["success"]:
                        return edit_result
                    else:
                        return {"success": False, "error": "Message editing cancelled"}
                else:
                    print(f"Please enter 'y' for yes, 'n' for no, or 'edit' to make changes.")
            
        except Exception as e:
            logger.error(f"Terminal message input failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def _preview_message(self, subject: str, message: str):
        """Preview the message before sending"""
        print(f"\n📋 MESSAGE PREVIEW:")
        if subject:
            print(f"   📌 Subject: {subject}")
        print(f"   📄 Message:")
        for line in message.split('\n'):
            print(f"      {line}")
        print(f"   📊 Character count: {len(message)}")
        print(f"   📊 Word count: {len(message.split())}")

    def _edit_message(self, current_subject: str, current_message: str, has_subject_field: bool) -> Dict[str, Any]:
        """Allow user to edit the message"""
        try:
            print(f"\n📝 EDIT MESSAGE:")
            print(f"1. Edit subject" + (" (current: " + current_subject + ")" if current_subject else ""))
            print(f"2. Edit message body")
            print(f"3. Rewrite entire message")
            print(f"4. Cancel editing")
            
            while True:
                choice = input(f"\nWhat would you like to edit? (1-4): ").strip()
                
                if choice == "1" and has_subject_field:
                    print(f"Current subject: {current_subject}")
                    new_subject = input(f"New subject (or press Enter to keep current): ").strip()
                    if new_subject:
                        current_subject = new_subject
                    print(f"✅ Subject updated.")
                    
                elif choice == "2":
                    print(f"\nCurrent message:")
                    for i, line in enumerate(current_message.split('\n'), 1):
                        print(f"   {i:2d}: {line}")
                    
                    print(f"\nEdit options:")
                    print(f"a. Add lines to the end")
                    print(f"b. Replace entire message")
                    print(f"c. Cancel")
                    
                    edit_choice = input(f"Choose option (a/b/c): ").strip().lower()
                    
                    if edit_choice == 'a':
                        print(f"\nAdd additional lines (type 'DONE' when finished):")
                        additional_lines = []
                        while True:
                            line = input(f"   ")
                            if line.upper() == "DONE":
                                break
                            additional_lines.append(line)
                        
                        if additional_lines:
                            current_message += "\n" + "\n".join(additional_lines)
                            print(f"✅ Lines added to message.")
                    
                    elif edit_choice == 'b':
                        print(f"\nEnter new message (type 'DONE' when finished):")
                        new_lines = []
                        while True:
                            line = input(f"   ")
                            if line.upper() == "DONE":
                                break
                            new_lines.append(line)
                        
                        if new_lines:
                            current_message = "\n".join(new_lines)
                            print(f"✅ Message replaced.")
                    
                elif choice == "3":
                    # Restart the entire message input process
                    return self._get_message_input_from_terminal(has_subject_field)
                    
                elif choice == "4":
                    return {"success": False, "error": "Editing cancelled"}
                
                else:
                    print(f"Invalid choice. Please enter 1-4.")
                    continue
                
                # Show preview after edit
                self._preview_message(current_subject, current_message)
                
                # Ask if they want to make more edits or send
                while True:
                    next_action = input(f"\nMake more edits (e), send message (s), or cancel (c)? ").strip().lower()
                    if next_action in ['e', 'edit']:
                        break  # Continue editing loop
                    elif next_action in ['s', 'send']:
                        return {
                            "success": True,
                            "subject": current_subject,
                            "message": current_message
                        }
                    elif next_action in ['c', 'cancel']:
                        return {"success": False, "error": "Editing cancelled"}
                    else:
                        print(f"Please enter 'e' for edit, 's' for send, or 'c' for cancel.")
            
        except Exception as e:
            logger.error(f"Message editing failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def _get_quick_message_templates(self, analysis=None, request_number=None) -> Dict[str, str]:
        """Provide quick message templates for common requests - now AI-powered when context available"""
        
        # If we have analysis context, generate AI templates
        if analysis is not None and request_number is not None and self.llm_helper:
            try:
                print(f"🤖 Generating contextual templates...")
                ai_templates = generate_templates(self.llm_helper.llm_client, analysis, request_number)
                return ai_templates
            except Exception as e:
                logger.warning(f"AI template generation failed, using fallback: {e}")
                # Fall through to original templates
        
        # Fallback to original hard-coded templates
        return {
            "1": {
                "subject": "Request Status Update",
                "message": "Hello,\n\nI am writing to inquire about the status of my public records request. Could you please provide an update on the progress and expected completion timeline?\n\nThank you for your time and assistance.\n\nBest regards"
            },
            "2": {
                "subject": "Additional Information",
                "message": "Hello,\n\nI wanted to provide additional information that may help with processing my request:\n\n[Please add your additional details here]\n\nThank you for your assistance.\n\nBest regards"
            },
            "3": {
                "subject": "Request Clarification",
                "message": "Hello,\n\nI would like to clarify my request to ensure you have all the necessary information:\n\n[Please add your clarification here]\n\nPlease let me know if you need any additional details.\n\nBest regards"
            },
            "4": {
                "subject": "Thank You",
                "message": "Hello,\n\nThank you for your work on processing my public records request. I appreciate your time and effort.\n\nBest regards"
            }
        }

    def _offer_message_templates(self, analysis=None, request_number=None) -> Dict[str, Any]:
        """Offer pre-written message templates to the user"""
        try:
            templates = self._get_quick_message_templates(analysis, request_number)
            
            # Show different header if AI-generated
            if analysis is not None and request_number is not None:
                print(f"\n💬 CONTEXTUAL MESSAGE TEMPLATES:")
                print(f"   AI-generated templates based on your request analysis:")
            else:
                print(f"\n💬 QUICK MESSAGE TEMPLATES:")
                print(f"   Would you like to use a pre-written template?")
            
            print(f"")
            for key, template in templates.items():
                print(f"   {key}. {template['subject']}")
            print(f"   5. Write custom message")
            print(f"   6. Cancel")
            
            while True:
                choice = input(f"\nChoose option (1-6): ").strip()
                
                if choice in templates:
                    selected = templates[choice]
                    
                    # Show different preview header if AI-generated
                    if analysis is not None:
                        print(f"\n📋 AI-GENERATED TEMPLATE PREVIEW:")
                        print(f"   🎯 Context-aware content based on your request analysis")
                    else:
                        print(f"\n📋 TEMPLATE PREVIEW:")
                    
                    self._preview_message(selected['subject'], selected['message'])
                    
                    while True:
                        action = input(f"\nUse this template? (y/n/edit): ").strip().lower()
                        if action in ['y', 'yes']:
                            return {
                                "success": True,
                                "subject": selected['subject'],
                                "message": selected['message']
                            }
                        elif action in ['n', 'no']:
                            break  # Go back to template selection
                        elif action in ['e', 'edit']:
                            # Allow editing the template
                            return self._edit_message(selected['subject'], selected['message'], True)
                        else:
                            print(f"Please enter 'y', 'n', or 'edit'.")
                
                elif choice == "5":
                    return {"success": False, "use_custom": True}  # Signal to use custom input
                
                elif choice == "6":
                    return {"success": False, "error": "User cancelled"}
                
                else:
                    print(f"Please enter a number from 1-6.")
            
        except Exception as e:
            logger.error(f"Template selection failed: {str(e)}")
            return {"success": False, "error": str(e)}

    # Update the main message input function to include templates
    def _get_message_input_from_terminal_with_templates(self, has_subject_field: bool, analysis=None, request_number=None) -> Dict[str, Any]:
        """Enhanced message input with template options"""
        try:
            # First offer templates (now with AI context if available)
            template_result = self._offer_message_templates(analysis, request_number)
            
            if template_result["success"]:
                # User selected a template
                return template_result
            elif template_result.get("use_custom"):
                # User wants to write custom message
                return self._get_message_input_from_terminal(has_subject_field)
            else:
                # User cancelled or error
                return template_result
                
        except Exception as e:
            logger.error(f"Enhanced message input failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _analyze_all_requests(self, requests: List[ClickableRequest]) -> Dict[str, Any]:
        """Analyze all available requests"""
        try:
            print(f"\n🔍 Analyzing all {len(requests)} requests...")
            print("-" * 60)
            
            analyses = []
            failed = []
            
            for req in requests:
                try:
                    print(f"\n📊 Analyzing {req.request_number}...")
                    
                    # Click and analyze
                    click_result = self.click_request_with_llm(req.request_number)
                    if not click_result["success"]:
                        failed.append({"request": req.request_number, "error": click_result["error"]})
                        continue
                    
                    analysis_result = self.analyze_request_detail_with_llm(req.request_number)
                    if analysis_result["success"]:
                        analyses.append(analysis_result["analysis"])
                        print(f"✅ {req.request_number}: {analysis_result['analysis'].current_status}")
                    else:
                        failed.append({"request": req.request_number, "error": analysis_result["error"]})
                    
                    # Navigate back
                    self.driver.back()
                    time.sleep(2)
                    
                except Exception as e:
                    failed.append({"request": req.request_number, "error": str(e)})
                    continue
            
            # Generate summary
            if analyses:
                summary = self.llm_helper.generate_multi_request_summary(analyses)
                self._display_multi_request_summary(summary, failed)
                
                # Ask if user wants to send messages to any requests
                if analyses:
                    print(f"\n💬 MESSAGE OPTIONS:")
                    print("-" * 50)
                    print("Would you like to send follow-up messages to any requests?")
                    for i, analysis in enumerate(analyses):
                        status_emoji = "🚨" if analysis.action_required else "📄"
                        print(f"{i+1}. {status_emoji} {analysis.request_number} - {analysis.current_status}")
                    print("0. No messages needed")
                    print("-" * 50)
                    
                    while True:
                        try:
                            msg_choice = input(f"Send message to which request? (0-{len(analyses)}): ").strip()
                            
                            if msg_choice == "0":
                                break
                            
                            msg_num = int(msg_choice)
                            if 1 <= msg_num <= len(analyses):
                                selected_analysis = analyses[msg_num - 1]
                                
                                # Navigate back to that specific request
                                print(f"\n🔍 Opening {selected_analysis.request_number} for messaging...")
                                
                                # Find and click the request again
                                click_result = self.click_request_with_llm(selected_analysis.request_number)
                                if click_result["success"]:
                                    message_result = self._handle_message_sending(selected_analysis.request_number)
                                    if message_result["success"]:
                                        print("✅ Message sent successfully!")
                                    else:
                                        print(f"❌ Failed to send message: {message_result['error']}")
                                    
                                    # Navigate back to requests list
                                    self.driver.back()
                                    time.sleep(2)
                                else:
                                    print(f"❌ Could not open request {selected_analysis.request_number}")
                                
                                # Ask if they want to send more messages
                                continue_choice = input("\nSend another message? (y/n): ").strip().lower()
                                if continue_choice != 'y':
                                    break
                            else:
                                print(f"Please enter a number between 0 and {len(analyses)}")
                                
                        except ValueError:
                            print("Please enter a valid number")
                        except KeyboardInterrupt:
                            print("\n👋 Messaging cancelled")
                            break
            
            return {
                "success": True,
                "total_analyzed": len(analyses),
                "total_failed": len(failed),
                "analyses": analyses,
                "failed": failed
            }
            
        except Exception as e:
            logger.error(f"Multi-request analysis failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _display_analysis_summary(self, analysis):
        """Display analysis for a single request"""
        print(f"\n📊 ANALYSIS SUMMARY FOR REQUEST {analysis.request_number}")
        print("=" * 70)
        print(f"📈 Status: {analysis.current_status}")
        print(f"👤 Contact: {analysis.staff_contact}")
        
        if analysis.all_timeline_events:
            print(f"\n📅 EVENT IMELINE:")
            for event in analysis.all_timeline_events:
                print(f"   • {event}")
        
        if analysis.needs_attention:
                print(f"\n💡 Needs attention: {analysis.needs_attention}")

        if analysis.attention_reason:
            print(f"\n💡 Needs attention: {analysis.attention_reason}")
    
        print("=" * 70)
    
    def _display_multi_request_summary(self, summary, failed):
        """Display summary for multiple requests"""
        print(f"\n📊 MULTI-REQUEST SUMMARY")
        print("=" * 70)
        print(f"📈 Total Requests: {summary.total_requests}")
        print(f"🚨 Urgent: {len(summary.urgent_requests)}")
        print(f"✅ Completed: {len(summary.completed_requests)}")
        print(f"⏳ Waiting: {len(summary.waiting_requests)}")
        print(f"❌ Failed to Analyze: {len(failed)}")
        
        print(f"\n📋 OVERALL STATUS: {summary.overall_status}")
        
        if summary.urgent_requests:
            print(f"\n🚨 URGENT REQUESTS:")
            for req in summary.urgent_requests:
                print(f"   • {req}")
        
        if summary.recommended_actions:
            print(f"\n🎯 RECOMMENDED ACTIONS:")
            for action in summary.recommended_actions:
                print(f"   • {action}")
        
        print(f"\n📝 EXECUTIVE SUMMARY:")
        print(f"{summary.summary}")
        print("=" * 70)
    
    # Add method to maintain compatibility with your existing calling code
    def interactive_analysis_workflow(self) -> Dict[str, Any]:
        """Wrapper method for compatibility with existing code"""
        return self.run_simplified_workflow()
    
    def navigate_back_to_home(self) -> bool:
        """Navigate back to portal home"""
        try:
            self.driver.back()
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"Failed to navigate back: {str(e)}")
            return False
        

    ######## MONITORING AGENT ###########
    def send_pre_drafted_message(self, subject: str, message: str) -> Dict[str, Any]:
        """
        Send a pre-drafted message directly without template selection.
        Used by MessageCoordinator to send AI-generated drafts.
        
        Args:
            subject: Pre-written subject (may be empty if no subject field)
            message: Pre-written message content
            
        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"📤 Sending pre-drafted message directly")
            
            # Step 1: Find and click message button
            button_result = self.find_message_button_with_llm()
            if not button_result["success"]:
                return {"success": False, "error": f"Could not find message button: {button_result['error']}"}
            
            # Step 2: Click the message button
            click_result = self.click_message_button(button_result["instruction"])
            if not click_result["success"]:
                return {"success": False, "error": f"Could not click message button: {click_result['error']}"}
            
            # Step 3: Analyze the message composer
            composer_analysis = self.analyze_message_composer_with_llm()
            if not composer_analysis.message_box_found:
                return {"success": False, "error": "Message composition interface not found"}
            
            logger.info(f"✅ Message composer opened successfully")
            
            # Step 4: Send the message directly using existing helper
            send_result = self.send_message_to_request(subject, message)
            
            if send_result['success']:
                logger.info(f"✅ Pre-drafted message sent successfully")
            else:
                logger.error(f"❌ Failed to send pre-drafted message: {send_result.get('error', 'Unknown error')}")
            
            return send_result
            
        except Exception as e:
            logger.error(f"❌ Pre-drafted message sending failed: {str(e)}")
            return {"success": False, "error": str(e)}