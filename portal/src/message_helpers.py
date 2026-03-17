from models import MessageInterfaceAnalysis
from typing import Dict, Any
import logging
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)


class MessageHelpers:
    """Class containing message-related helper methods"""
    
    def __init__(self, driver, llm_helper):
        self.driver = driver
        self.llm_helper = llm_helper
    
    def analyze_message_interface_with_llm(self) -> MessageInterfaceAnalysis:
        """Use LLM to analyze the actual HTML structure including rich text editors"""
        try:
            logger.info("🧠 Using LLM to analyze message interface HTML")
            
            # Extract relevant HTML elements including rich text editors
            html_analysis = self._extract_message_interface_html()
            
            if not html_analysis["success"]:
                return MessageInterfaceAnalysis(
                    message_field_found=False,
                    message_field_selector="",
                    message_field_method="",
                    send_button_found=False,
                    send_button_selector="",
                    send_button_method="",
                    subject_field_found=False,
                    interface_type="unknown",
                    additional_notes="Could not extract HTML elements",
                    confidence=0.0
                )
            
            interface_prompt = """
            You are analyzing the actual HTML of a message composition interface. The message field might be implemented as:
            
            1. **Standard textarea element**
            2. **Rich text editor** (div with contenteditable="true")
            3. **Iframe-based editor**
            4. **Custom div with role="textbox"**
            5. **Input field with message-related attributes**
            
            **Your Task:**
            Find the element where users can type their message and the button to send it.
            
            **CRITICAL REQUIREMENTS:**
            - Use the EXACT HTML provided - these are real DOM elements
            - Provide selectors that will work with Selenium WebDriver
            - For contenteditable divs, use CSS selector method
            - For iframes, provide the iframe selector and note it needs special handling
            - Choose the MOST SPECIFIC and RELIABLE selector for each element
            
            **Selector Method Guidelines:**
            - Use "id" if element has a unique ID attribute
            - Use "name" if element has a unique name attribute  
            - Use "css_selector" for CSS selectors (classes, attributes, role, aria-labels)
            - Use "xpath" only if CSS won't work
            - Use "text" for buttons identified by their text content
            
            **Special Cases:**
            - If it's a contenteditable div, use css_selector method
            - If it's an iframe, use css_selector method and note "iframe" in interface_type
            - If it's a role="textbox", use css_selector with [role="textbox"]
            
            **Important:** Only provide selectors for elements that actually exist in the HTML provided.
            Look carefully for the largest/most prominent text input area.
            """
            
            structured_llm = self.llm_helper.llm_client.with_structured_output(MessageInterfaceAnalysis)
            
            # Build comprehensive HTML context
            html_context = f"""Analyze this message interface HTML and provide exact selectors:

**TEXTAREAS FOUND ({len(html_analysis['textareas_html'])}):**
{html_analysis['textareas_html']}

**CONTENTEDITABLE ELEMENTS FOUND ({len(html_analysis['contenteditable_elements'])}):**
{html_analysis['contenteditable_elements']}

**IFRAME ELEMENTS FOUND ({len(html_analysis['iframe_elements'])}):**
{html_analysis['iframe_elements']}

**POTENTIAL MESSAGE DIVS FOUND ({len(html_analysis['potential_message_divs'])}):**
{html_analysis['potential_message_divs']}

**BUTTONS FOUND ({len(html_analysis['buttons_html'])}):**
{html_analysis['buttons_html']}

**INPUT FIELDS FOUND ({len(html_analysis['inputs_html'])}):**
{html_analysis['inputs_html']}

**FORM CONTEXT:**
{html_analysis['form_context']}

Based on this actual HTML, provide the most reliable selectors for the message field and send button.
Focus on finding the element where users can type their message - it could be any of the above types."""
            
            messages = [
                {"role": "system", "content": interface_prompt},
                {"role": "user", "content": html_context}
            ]
            
            result = structured_llm.invoke(messages)
            
            logger.info(f"🎯 Enhanced LLM HTML Analysis Results:")
            logger.info(f"   Message field: {result.message_field_selector} (method: {result.message_field_method})")
            logger.info(f"   Send button: {result.send_button_selector} (method: {result.send_button_method})")
            logger.info(f"   Interface type: {result.interface_type}")
            logger.info(f"   Confidence: {result.confidence}")
            logger.info(f"   Notes: {result.additional_notes}")
            
            return result
            
        except Exception as e:
            logger.error(f"Enhanced LLM HTML analysis failed: {str(e)}")
            return MessageInterfaceAnalysis(
                message_field_found=False,
                message_field_selector="",
                message_field_method="",
                send_button_found=False,
                send_button_selector="",
                send_button_method="",
                subject_field_found=False,
                interface_type="unknown",
                additional_notes=f"Analysis failed: {str(e)}",
                confidence=0.0
            )

    def _extract_message_interface_html(self) -> Dict[str, Any]:
        """Extract and format HTML elements relevant to message composition - including rich text editors"""
        try:
            logger.info("📄 Extracting HTML elements for analysis (including rich text editors)...")
            
            # Find all textareas (standard approach)
            textareas = self.driver.find_elements(By.TAG_NAME, "textarea")
            textareas_html = []
            
            for i, textarea in enumerate(textareas):
                try:
                    attrs = self.driver.execute_script("""
                        var items = {};
                        for (index = 0; index < arguments[0].attributes.length; ++index) {
                            items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value;
                        }
                        return items;
                    """, textarea)
                    
                    is_visible = textarea.is_displayed()
                    is_enabled = textarea.is_enabled()
                    
                    html_info = {
                        "index": i,
                        "tag": "textarea",
                        "attributes": attrs,
                        "is_visible": is_visible,
                        "is_enabled": is_enabled,
                        "text_content": textarea.get_attribute("value") or textarea.text,
                        "outer_html": textarea.get_attribute("outerHTML")[:200] + "..." if len(textarea.get_attribute("outerHTML")) > 200 else textarea.get_attribute("outerHTML")
                    }
                    textareas_html.append(html_info)
                    
                except Exception as e:
                    logger.debug(f"Could not analyze textarea {i}: {e}")
            
            # NEW: Find contenteditable elements (rich text editors)
            contenteditable_elements = []
            try:
                # Look for any element with contenteditable="true"
                editable_elements = self.driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true'], [contenteditable='']")
                
                for i, elem in enumerate(editable_elements):
                    try:
                        attrs = self.driver.execute_script("""
                            var items = {};
                            for (index = 0; index < arguments[0].attributes.length; ++index) {
                                items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value;
                            }
                            return items;
                        """, elem)
                        
                        is_visible = elem.is_displayed()
                        tag_name = elem.tag_name.lower()
                        
                        if is_visible:  # Only include visible contenteditable elements
                            html_info = {
                                "index": i,
                                "tag": tag_name,
                                "type": "contenteditable",
                                "attributes": attrs,
                                "is_visible": is_visible,
                                "text_content": elem.text[:100],  # First 100 chars
                                "inner_html": elem.get_attribute("innerHTML")[:200] + "..." if len(elem.get_attribute("innerHTML")) > 200 else elem.get_attribute("innerHTML"),
                                "outer_html": elem.get_attribute("outerHTML")[:200] + "..." if len(elem.get_attribute("outerHTML")) > 200 else elem.get_attribute("outerHTML")
                            }
                            contenteditable_elements.append(html_info)
                            
                    except Exception as e:
                        logger.debug(f"Could not analyze contenteditable element {i}: {e}")
                        
            except Exception as e:
                logger.debug(f"Could not find contenteditable elements: {e}")
            
            # NEW: Check for iframes (some rich text editors use iframes)
            iframe_elements = []
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                
                for i, iframe in enumerate(iframes):
                    try:
                        attrs = self.driver.execute_script("""
                            var items = {};
                            for (index = 0; index < arguments[0].attributes.length; ++index) {
                                items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value;
                            }
                            return items;
                        """, iframe)
                        
                        is_visible = iframe.is_displayed()
                        
                        if is_visible:
                            html_info = {
                                "index": i,
                                "tag": "iframe",
                                "attributes": attrs,
                                "is_visible": is_visible,
                                "outer_html": iframe.get_attribute("outerHTML")[:200] + "..." if len(iframe.get_attribute("outerHTML")) > 200 else iframe.get_attribute("outerHTML")
                            }
                            iframe_elements.append(html_info)
                            
                    except Exception as e:
                        logger.debug(f"Could not analyze iframe {i}: {e}")
                        
            except Exception as e:
                logger.debug(f"Could not find iframe elements: {e}")
            
            # NEW: Look for divs that might be message areas (common patterns)
            potential_message_divs = []
            try:
                # Look for divs with common message area patterns
                message_div_selectors = [
                    "[role='textbox']",
                    "[aria-label*='message' i]",
                    "[aria-label*='type' i]", 
                    "[placeholder*='message' i]",
                    "[placeholder*='type' i]",
                    ".message-input",
                    ".text-editor",
                    ".editor",
                    "[data-testid*='message']",
                    "[data-testid*='editor']"
                ]
                
                for selector in message_div_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elements:
                            if elem.is_displayed():
                                attrs = self.driver.execute_script("""
                                    var items = {};
                                    for (index = 0; index < arguments[0].attributes.length; ++index) {
                                        items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value;
                                    }
                                    return items;
                                """, elem)
                                
                                html_info = {
                                    "selector_used": selector,
                                    "tag": elem.tag_name.lower(),
                                    "attributes": attrs,
                                    "is_visible": elem.is_displayed(),
                                    "text_content": elem.text[:100],
                                    "outer_html": elem.get_attribute("outerHTML")[:300] + "..." if len(elem.get_attribute("outerHTML")) > 300 else elem.get_attribute("outerHTML")
                                }
                                potential_message_divs.append(html_info)
                                
                    except Exception as e:
                        logger.debug(f"Could not check selector {selector}: {e}")
                        
            except Exception as e:
                logger.debug(f"Could not find potential message divs: {e}")
            
            # Find all buttons (improved analysis)
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            buttons_html = []
            
            for i, button in enumerate(buttons):
                try:
                    attrs = self.driver.execute_script("""
                        var items = {};
                        for (index = 0; index < arguments[0].attributes.length; ++index) {
                            items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value;
                        }
                        return items;
                    """, button)
                    
                    is_visible = button.is_displayed()
                    is_enabled = button.is_enabled()
                    button_text = button.text.strip()
                    
                    # Check for send-related keywords in text or attributes
                    relevant_keywords = ["send", "submit", "post", "message", "external"]
                    is_relevant = (
                        any(keyword in button_text.lower() for keyword in relevant_keywords) or 
                        any(keyword in str(attrs).lower() for keyword in relevant_keywords)
                    )
                    
                    if is_relevant or (is_visible and len(button_text) > 0):  # Include if relevant or visible with text
                        html_info = {
                            "index": i,
                            "tag": "button", 
                            "attributes": attrs,
                            "is_visible": is_visible,
                            "is_enabled": is_enabled,
                            "text_content": button_text,
                            "outer_html": button.get_attribute("outerHTML")[:200] + "..." if len(button.get_attribute("outerHTML")) > 200 else button.get_attribute("outerHTML")
                        }
                        buttons_html.append(html_info)
                        
                except Exception as e:
                    logger.debug(f"Could not analyze button {i}: {e}")
            
            # Find all input fields
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            inputs_html = []
            
            for i, input_elem in enumerate(inputs):
                try:
                    attrs = self.driver.execute_script("""
                        var items = {};
                        for (index = 0; index < arguments[0].attributes.length; ++index) {
                            items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value;
                        }
                        return items;
                    """, input_elem)
                    
                    input_type = input_elem.get_attribute("type") or "text"
                    is_visible = input_elem.is_displayed()
                    
                    if input_type in ["text", "email", "search", "hidden"] and is_visible:
                        html_info = {
                            "index": i,
                            "tag": "input",
                            "type": input_type,
                            "attributes": attrs,
                            "is_visible": is_visible,
                            "outer_html": input_elem.get_attribute("outerHTML")[:200] + "..." if len(input_elem.get_attribute("outerHTML")) > 200 else input_elem.get_attribute("outerHTML")
                        }
                        inputs_html.append(html_info)
                        
                except Exception as e:
                    logger.debug(f"Could not analyze input {i}: {e}")
            
            # Try to get form context
            form_context = ""
            try:
                forms = self.driver.find_elements(By.TAG_NAME, "form")
                if forms:
                    form = forms[0]
                    form_html = form.get_attribute("outerHTML")
                    form_context = form_html[:500] + "..." if len(form_html) > 500 else form_html
            except Exception as e:
                logger.debug(f"Could not get form context: {e}")
            
            result = {
                "success": True,
                "textareas_html": textareas_html,
                "contenteditable_elements": contenteditable_elements,
                "iframe_elements": iframe_elements,
                "potential_message_divs": potential_message_divs,
                "buttons_html": buttons_html, 
                "inputs_html": inputs_html,
                "form_context": form_context,
                "summary": f"Found {len(textareas_html)} textareas, {len(contenteditable_elements)} contenteditable elements, {len(iframe_elements)} iframes, {len(potential_message_divs)} potential message divs, {len(buttons_html)} relevant buttons, {len(inputs_html)} input fields"
            }
            
            logger.info(f"📊 Enhanced HTML extraction complete: {result['summary']}")
            return result
            
        except Exception as e:
            logger.error(f"Enhanced HTML extraction failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def send_message_with_llm_selectors(self, subject: str, message: str) -> Dict[str, Any]:
        """Send message using LLM-provided selectors - simplified approach"""
        try:
            logger.info("📤 Sending message using LLM-analyzed interface")
            
            # Clean up the message
            cleaned_message = message.replace("SEND", "").strip()
            if not cleaned_message:
                return {"success": False, "error": "Message is empty after cleaning"}
            
            # Step 1: Analyze the interface with LLM
            interface_analysis = self.analyze_message_interface_with_llm()
            
            if not interface_analysis.message_field_found:
                return {
                    "success": False, 
                    "error": f"LLM could not find message field. Notes: {interface_analysis.additional_notes}"
                }
            
            if not interface_analysis.send_button_found:
                return {
                    "success": False, 
                    "error": f"LLM could not find send button. Notes: {interface_analysis.additional_notes}"
                }
            
            # Step 2: Fill subject field if it exists
            if interface_analysis.subject_field_found and interface_analysis.subject_field_selector and subject:
                try:
                    subject_element = self.find_element_by_llm_selector(
                        interface_analysis.subject_field_selector,
                        "css_selector"
                    )
                    if subject_element:
                        subject_element.clear()
                        subject_element.send_keys(subject)
                        logger.info("✅ Subject field filled")
                except Exception as e:
                    logger.warning(f"⚠️ Could not fill subject field: {str(e)}")
            
            # Step 3: Fill message field and trigger proper events
            try:
                logger.info(f"📝 Filling message field using: {interface_analysis.message_field_selector}")
                
                message_element = self.find_element_by_llm_selector(
                    interface_analysis.message_field_selector,
                    interface_analysis.message_field_method
                )
                
                if not message_element:
                    return {"success": False, "error": f"Could not find message field with LLM selector: {interface_analysis.message_field_selector}"}
                
                # Focus on getting the rich text editor to properly enable the send button
                success = self._fill_rich_text_editor_properly(message_element, cleaned_message)
                
                if not success:
                    return {"success": False, "error": "Failed to fill message field properly"}
                
                logger.info("✅ Message field filled successfully")
                
            except Exception as e:
                logger.error(f"❌ Failed to fill message field: {str(e)}")
                return {"success": False, "error": f"Failed to fill message field: {str(e)}"}
            
            # Step 4: Wait for send button to become enabled, then click it normally
            try:
                logger.info(f"📤 Waiting for send button to become enabled...")
                
                send_element = self.find_element_by_llm_selector(
                    interface_analysis.send_button_selector,
                    interface_analysis.send_button_method
                )
                
                if not send_element:
                    return {"success": False, "error": f"Could not find send button with LLM selector: {interface_analysis.send_button_selector}"}
                
                # Wait for button to become enabled (give it a few seconds)
                max_wait = 10
                for i in range(max_wait):
                    if send_element.is_enabled():
                        logger.info(f"✅ Send button is enabled after {i} seconds")
                        break
                    time.sleep(1)
                else:
                    logger.warning("⚠️ Send button did not become enabled, trying anyway...")
                
                # Simple button click - no special logic
                logger.info(f"📤 Clicking send button: {interface_analysis.send_button_selector}")
                send_element.click()
                logger.info("✅ Send button clicked successfully")
                
            except Exception as e:
                logger.error(f"❌ Failed to click send button: {str(e)}")
                return {"success": False, "error": f"Failed to click send button: {str(e)}"}
            
            # Step 5: Simple verification
            time.sleep(3)
            page_source = self.driver.page_source.lower()
            success_indicators = [
                "message sent", "successfully sent", "message delivered",
                "message posted", "thank you", "sent successfully"
            ]
            
            success_detected = any(indicator in page_source for indicator in success_indicators)
            
            if success_detected:
                return {
                    "success": True,
                    "message": f"Message sent successfully. Content: {cleaned_message[:50]}..."
                }
            else:
                # Check if modal closed (another success indicator)
                modal_elements = self.driver.find_elements(By.CSS_SELECTOR, "[class*='modal'], [class*='dialog']")
                modal_closed = len([m for m in modal_elements if m.is_displayed()]) == 0
                
                if modal_closed:
                    return {
                        "success": True,
                        "message": f"Message appears to have been sent (modal closed). Content: {cleaned_message[:50]}..."
                    }
                else:
                    return {
                        "success": False,
                        "error": "Message may not have been sent - no confirmation detected"
                    }
            
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            return {"success": False, "error": str(e)}

    def _fill_rich_text_editor_properly(self, message_element, message_text: str) -> bool:
        """Fill rich text editor and ensure it triggers the right events to enable send button"""
        try:
            # Scroll element into view and focus
            self.driver.execute_script("arguments[0].scrollIntoView(true);", message_element)
            time.sleep(0.5)
            message_element.click()
            time.sleep(0.5)
            
            # Check if it's a contenteditable element (rich text editor)
            is_contenteditable = message_element.get_attribute("contenteditable") == "true"
            
            if is_contenteditable:
                logger.info("🎨 Filling contenteditable rich text editor")
                
                # Clear existing content
                self.driver.execute_script("arguments[0].innerHTML = '';", message_element)
                
                # Method 1: Set content and trigger all the events that might enable the send button
                self.driver.execute_script("""
                    var element = arguments[0];
                    var text = arguments[1];
                    
                    // Set the content
                    element.innerHTML = text;
                    element.textContent = text;
                    
                    // Trigger focus event
                    var focusEvent = new Event('focus', { bubbles: true });
                    element.dispatchEvent(focusEvent);
                    
                    // Trigger input event (most important for enabling send buttons)
                    var inputEvent = new Event('input', { bubbles: true });
                    element.dispatchEvent(inputEvent);
                    
                    // Trigger change event
                    var changeEvent = new Event('change', { bubbles: true });
                    element.dispatchEvent(changeEvent);
                    
                    // Trigger keyup event (some editors listen for this)
                    var keyupEvent = new KeyboardEvent('keyup', { bubbles: true });
                    element.dispatchEvent(keyupEvent);
                    
                    // Trigger paste event (in case the editor treats this as a paste)
                    var pasteEvent = new Event('paste', { bubbles: true });
                    element.dispatchEvent(pasteEvent);
                    
                    // For Quill editors specifically, trigger text-change
                    if (window.Quill) {
                        var textChangeEvent = new CustomEvent('text-change', { bubbles: true });
                        element.dispatchEvent(textChangeEvent);
                    }
                """, message_element, message_text)
                
                time.sleep(5)
                
                # Verify content was set
                content = self.driver.execute_script("return arguments[0].textContent || arguments[0].innerText;", message_element)
                if message_text.strip() in content.strip():
                    logger.info("✅ Rich text editor content set and events triggered")
                    return True
                else:
                    logger.warning("⚠️ Content not properly set, trying typing method...")
                    
                    # Fallback: Type the message character by character
                    message_element.clear()
                    for char in message_text:
                        message_element.send_keys(char)
                        time.sleep(0.01)
                    
                    time.sleep(0.5)
                    return True
            else:
                # Standard textarea
                logger.info("📝 Filling standard textarea")
                message_element.clear()
                message_element.send_keys(message_text)
                time.sleep(0.5)
                return True
                
        except Exception as e:
            logger.error(f"Rich text editor filling failed: {str(e)}")
            return False

    def find_element_by_llm_selector(self, selector: str, method: str, timeout: int = 10):
        """Find element using LLM-provided selector and method"""
        try:
            if method == "id":
                return WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.ID, selector))
                )
            elif method == "name":
                return WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.NAME, selector))
                )
            elif method == "css_selector":
                return WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            elif method == "xpath":
                return WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
            elif method == "text":
                # For button text, use XPath
                xpath = f"//button[contains(text(), '{selector}')]"
                return WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
            else:
                logger.error(f"Unknown selector method: {method}")
                return None
                
        except TimeoutException:
            logger.error(f"Element not found with {method}: {selector}")
            return None
        except Exception as e:
            logger.error(f"Error finding element with {method} '{selector}': {str(e)}")
            return None