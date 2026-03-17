import time
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from llm_helper import LLMHelper
from models import ClickInstruction

logger = logging.getLogger(__name__)

class FormSubmitter:
    def __init__(self, driver, screenshot_func, llm_client=None):
        self.driver = driver
        self.take_screenshot = screenshot_func
        
        self.llm_client = llm_client  # Store the LLM client
        
        # Initialize LLM-based analyzers if LLM client is provided
        if llm_client:
            try:
                # Initialize LLM helper for submit button detection
                self.llm_helper = LLMHelper(llm_client)
                
                # from llm import CSSAndDOMAnalyzer, RichTextFormFiller
                self.css_dom_analyzer = None
                self.rich_text_filler = None
                logger.info("✅ LLM analyzers initialized - will use intelligent form analysis")
            except ImportError as e:
                logger.warning(f"Could not import LLM helper: {str(e)}")
                self.llm_helper = None
                self.css_dom_analyzer = None
                self.rich_text_filler = None
        else:
            self.llm_helper = None
            self.css_dom_analyzer = None
            self.rich_text_filler = None
            logger.info("⚠️ No LLM client provided - will use fallback methods only")
    
    def navigate_to_request_form(self) -> bool:
        """Navigate to the 'Make Request' form"""
        try:
            logger.info("Looking for 'Make Request' button on portal home page")
            
            make_request_selectors = [
                (By.XPATH, "//button[contains(text(), 'Make Request')]"),
                (By.LINK_TEXT, "Make Request"),
                (By.PARTIAL_LINK_TEXT, "Make Request"),
                (By.CSS_SELECTOR, "button:contains('Make Request')"),
                (By.CSS_SELECTOR, "a:contains('Make Request')"),
                (By.XPATH, "//a[contains(text(), 'Make Request')]"),
                (By.CSS_SELECTOR, "button[href*='request']"),
                (By.CSS_SELECTOR, "a[href*='request']")
            ]
            
            for selector_type, selector_value in make_request_selectors:
                try:
                    element = WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(1)
                    element.click()
                    time.sleep(4)
                    logger.info(f"Successfully clicked 'Make Request' using: {selector_type}")
                    self.take_screenshot("request_form_loaded")
                    return True
                except TimeoutException:
                    continue
                except Exception as e:
                    logger.warning(f"Failed to click Make Request with {selector_type}: {str(e)}")
                    continue
            
            logger.error("Could not find 'Make Request' button")
            return False
            
        except Exception as e:
            logger.error(f"Failed to navigate to request form: {str(e)}")
            return False
        
    def _handle_form_terms_checkbox(self) -> bool:
        """
        On some request forms, a terms/acknowledgement checkbox must be checked
        before the submit button is enabled. This clicks it if found.

        Returns:
            True  -> checkbox found and is now selected (or was already selected)
            False -> checkbox not found (non-fatal)
        """
        try:
            logger.info("🔍 Looking for form terms/acknowledgement checkbox...")

            # --- Candidate locators (exact first, then generic) ---
            candidates = []

            # MOST SPECIFIC: Target terms checkbox by name attribute (NextRequest standard)
            candidates.append(("css", "input[name='terms'][type='checkbox']"))

            # From the provided HTML (NR-style forms)
            candidates.append(("By.ID", "nr_form_input-16"))

            # Generic fallbacks with terms-related keywords
            candidates.append(("css", "input[type='checkbox'][id*='terms' i]"))
            candidates.append(("css", "input[type='checkbox'][name*='terms' i]"))
            candidates.append(("css", "input[type='checkbox'][id*='agree' i]"))
            candidates.append(("css", "input[type='checkbox'][name*='agree' i]"))
            candidates.append(("css", "input[type='checkbox'][id*='acknowledge' i]"))
            candidates.append(("css", "input[type='checkbox'][name*='acknowledge' i]"))

            checkbox = None

            for how, sel in candidates:
                try:
                    if how == "By.ID":
                        cb = self.driver.find_element(By.ID, sel)
                    elif how == "css":
                        cb = self.driver.find_element(By.CSS_SELECTOR, sel)
                    else:
                        cb = None

                    if cb and cb.is_displayed():
                        # Validate this is actually a terms checkbox, not a form field checkbox
                        cb_name = (cb.get_attribute('name') or '').lower()
                        cb_id = (cb.get_attribute('id') or '').lower()

                        # Reject if this is a form field checkbox (company, organization, etc.)
                        exclude_names = ['company', 'organization', 'business', 'individual']
                        if any(name in cb_name or name in cb_id for name in exclude_names):
                            logger.debug(f"Skipping form field checkbox: name={cb_name}, id={cb_id}")
                            continue

                        logger.info(f"✅ Found potential terms checkbox: name={cb_name}, id={cb_id}")
                        checkbox = cb
                        break
                except Exception:
                    continue

            # Label-based fallback (looks for label text or for=…)
            if checkbox is None:
                try:
                    # Find any label with acknowledge/terms/agree text
                    labels = self.driver.find_elements(
                        By.XPATH,
                        # matches the specific label 'for' and also text like "acknowledge"/"terms"
                        "//label[@for='nr_form_input-16' or "
                        "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'acknowledge') or "
                        "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'terms') or "
                        "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'agree')]"
                    )

                    for label in labels:
                        if not label.is_displayed():
                            continue

                        for_id = label.get_attribute("for")
                        if for_id:
                            try:
                                cb = self.driver.find_element(By.ID, for_id)
                                if cb and cb.get_attribute('type') == 'checkbox':
                                    logger.info(f"✅ Found checkbox via label: id='{for_id}', text='{label.text.strip()[:50]}'")
                                    checkbox = cb
                                    break
                            except Exception as e:
                                logger.debug(f"Could not find checkbox with id '{for_id}': {e}")
                                continue

                    if checkbox:
                        pass  # Found it, continue to use it

                except Exception as e:
                    logger.debug(f"Label-based search error: {e}")

            # STRATEGY 2: Find checkboxes near "Terms and Conditions" heading/text
            if checkbox is None:
                try:
                    logger.info("🔍 Strategy 2: Looking for checkbox near 'Terms and Conditions' text...")
                    # Find "Terms and Conditions" text on the page
                    terms_headings = self.driver.find_elements(
                        By.XPATH,
                        "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'terms and conditions')]"
                    )

                    for heading in terms_headings:
                        if not heading.is_displayed():
                            continue

                        # Look for checkbox after this heading
                        try:
                            # Find checkbox that follows the terms heading
                            cb = heading.find_element(By.XPATH, ".//following::input[@type='checkbox'][1]")
                            if cb and cb.is_displayed():
                                logger.info(f"✅ Found checkbox following 'Terms and Conditions' heading")
                                checkbox = cb
                                break
                        except Exception:
                            pass

                        # Also check for checkbox in parent/sibling containers
                        try:
                            parent = heading.find_element(By.XPATH, "./ancestor::*[1]")
                            cb = parent.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                            if cb and cb.is_displayed():
                                logger.info(f"✅ Found checkbox in same container as 'Terms and Conditions'")
                                checkbox = cb
                                break
                        except Exception:
                            pass

                except Exception as e:
                    logger.debug(f"Terms heading search error: {e}")

            # STRATEGY 3: Look for checkbox with label containing specific ID patterns
            if checkbox is None:
                try:
                    logger.info("🔍 Strategy 3: Looking for labels with 'inquiryr' or complex ID patterns...")
                    # Find labels with complex IDs that might be autogenerated
                    complex_labels = self.driver.find_elements(
                        By.XPATH,
                        "//label[@for and (contains(@for, 'inquiryr') or contains(@for, 'input') or contains(@for, 'form'))]"
                    )

                    for label in complex_labels:
                        if not label.is_displayed():
                            continue

                        # Check if label text contains acknowledgement/terms keywords
                        label_text = label.text.lower()
                        if any(keyword in label_text for keyword in ['acknowledge', 'terms', 'agree', 'conditions']):
                            for_id = label.get_attribute("for")
                            if for_id:
                                try:
                                    cb = self.driver.find_element(By.ID, for_id)
                                    if cb and cb.get_attribute('type') == 'checkbox':
                                        logger.info(f"✅ Found checkbox via complex label ID: {for_id}")
                                        checkbox = cb
                                        break
                                except Exception:
                                    pass

                except Exception as e:
                    logger.debug(f"Complex label search error: {e}")

            # STRATEGY 4: Find all checkboxes on the form and filter by context
            if checkbox is None:
                try:
                    logger.info("🔍 Strategy 4: Analyzing all checkboxes for terms-related context...")
                    all_checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")

                    for cb in all_checkboxes:
                        if not cb.is_displayed():
                            continue

                        # Get surrounding context (parent elements, siblings, labels)
                        try:
                            # Check ID for terms-related keywords
                            cb_id = cb.get_attribute('id') or ''
                            cb_name = cb.get_attribute('name') or ''

                            # Get parent container text
                            parent = cb.find_element(By.XPATH, "./ancestor::*[2]")
                            parent_text = parent.text.lower()

                            # Check if this checkbox is in a terms/acknowledgement context
                            if any(keyword in parent_text for keyword in ['acknowledge', 'terms and conditions', 'agree to', 'i acknowledge']):
                                logger.info(f"✅ Found checkbox in terms context via parent text analysis")
                                logger.info(f"   Checkbox ID: {cb_id}, Parent text preview: {parent_text[:100]}")
                                checkbox = cb
                                break

                        except Exception:
                            continue

                except Exception as e:
                    logger.debug(f"Contextual checkbox search error: {e}")

            # STRATEGY 5: Last resort - single unchecked visible checkbox near bottom of form
            if checkbox is None:
                try:
                    logger.info("🔍 Strategy 5: Looking for single unchecked checkbox...")
                    all_cbs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                    unchecked_visible = [cb for cb in all_cbs if cb.is_displayed() and not cb.is_selected()]
                    if len(unchecked_visible) == 1:
                        logger.info("✅ Found single unchecked checkbox (last resort)")
                        checkbox = unchecked_visible[0]
                except Exception:
                    pass

            if checkbox is None:
                logger.info("ℹ️ No terms checkbox found on the form.")
                return False

            # Scroll it into view (some are offscreen/hidden)
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", checkbox)
            except Exception:
                pass

            # Already selected?
            if checkbox.is_selected():
                logger.info("✅ Terms checkbox already checked.")
                return True

            # Click (prefer JS for custom/hidden inputs)
            logger.info("🖱️ Attempting to check the checkbox...")
            clicked = False

            # Try 1: Trigger comprehensive events (for custom checkboxes like NextRequest)
            try:
                logger.info("   🎯 Attempting comprehensive event triggering (custom checkbox)...")
                self.driver.execute_script("""
                    var checkbox = arguments[0];

                    // Focus the checkbox first
                    checkbox.focus();

                    // Trigger click event with all necessary event propagation
                    var clickEvent = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    checkbox.dispatchEvent(clickEvent);

                    // Trigger input and change events (for Vue/React/Angular)
                    checkbox.dispatchEvent(new Event('input', {bubbles: true}));
                    checkbox.dispatchEvent(new Event('change', {bubbles: true}));

                    // Manually set checked and value for custom implementations
                    checkbox.checked = true;
                    checkbox.value = 'true';
                    checkbox.setAttribute('checked', '');
                    checkbox.setAttribute('value', 'true');

                    // Trigger blur to ensure validation runs
                    checkbox.dispatchEvent(new Event('blur', {bubbles: true}));

                """, checkbox)
                clicked = True
                logger.info("   ✓ Comprehensive events triggered")
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"Comprehensive event triggering failed: {e}")

            # Try 2: Simple JavaScript click
            if not clicked or not checkbox.is_selected():
                try:
                    logger.info("   🎯 Attempting simple JS click...")
                    self.driver.execute_script("arguments[0].click();", checkbox)
                    clicked = True
                    logger.info("   ✓ JS click executed")
                    time.sleep(0.3)
                except Exception as e:
                    logger.debug(f"JS click failed: {e}")

            # Try 3: Direct Selenium click
            if not clicked or not checkbox.is_selected():
                try:
                    logger.info("   🎯 Attempting direct Selenium click...")
                    checkbox.click()
                    clicked = True
                    logger.info("   ✓ Direct click executed")
                    time.sleep(0.3)
                except Exception as e:
                    logger.debug(f"Direct click failed: {e}")

            # Try 4: Click the associated label
            if not checkbox.is_selected():
                try:
                    checkbox_id = checkbox.get_attribute('id')
                    if checkbox_id:
                        logger.info(f"   🎯 Attempting label click for checkbox '{checkbox_id}'...")
                        label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{checkbox_id}']")
                        if label and label.is_displayed():
                            label.click()
                            logger.info("   ✓ Label click executed")
                            time.sleep(0.5)
                except Exception as e:
                    logger.debug(f"Label click failed: {e}")

            # Final verification
            if checkbox.is_selected():
                logger.info("✅ Successfully checked the terms/acknowledgement checkbox.")
                # Verify the value attribute was updated (for NextRequest custom checkboxes)
                checkbox_value = checkbox.get_attribute('value')
                logger.info(f"   Checkbox value: {checkbox_value}, checked: {checkbox.is_selected()}")
                return True
            else:
                # Check if value was set even if checked attribute wasn't
                checkbox_value = checkbox.get_attribute('value')
                if checkbox_value == 'true':
                    logger.info("✅ Checkbox value set to 'true' (custom implementation detected)")
                    return True

                logger.warning(f"⚠️ Checkbox still not selected after all attempts. Value: {checkbox_value}")
                return False

        except Exception as e:
            logger.warning(f"❌ _handle_form_terms_checkbox error: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return False

    
    def fill_and_submit_form(self, request_text: str, user_info: Dict[str, str]) -> Dict[str, Any]:
        """Enhanced form filling with department selection and complete contact info"""
        
        result = {
            'success': False,
            'steps_completed': [],
            'errors': [],
            'llm_analysis': None,
            'filling_method': None
        }
        
        try:
            # Take screenshot
            self.take_screenshot("form_before_filling")
            
            # Step 1: Fill request description using existing logic
            logger.info("=== FILLING REQUEST DESCRIPTION ===")
            
            if self.rich_text_filler and self.css_dom_analyzer:
                logger.info("🧠 Using LLM-powered intelligent form analysis")
                
                fill_result = self.rich_text_filler.smart_fill_request_description(request_text)
                result['llm_analysis'] = fill_result.get('analysis')
                result['filling_method'] = fill_result.get('method_used')
                
                if fill_result['success']:
                    result['steps_completed'].append(f"Request description ({fill_result['method_used']})")
                    logger.info(f"✅ LLM-guided filling successful: {fill_result['method_used']}")
                else:
                    logger.warning("🔄 LLM analysis failed, trying enhanced fallback")
                    result['errors'].extend(fill_result.get('errors', []))
                    
                    if self._fill_request_description_fallback(request_text):
                        result['steps_completed'].append("Request description (enhanced fallback)")
                        result['filling_method'] = "enhanced fallback"
                    else:
                        result['errors'].append("CRITICAL: All request description filling methods failed")
                        return result
            else:
                logger.info("🔧 No LLM available, using enhanced fallback methods")
                if self._fill_request_description_fallback(request_text):
                    result['steps_completed'].append("Request description (enhanced fallback)")
                    result['filling_method'] = "enhanced fallback"
                else:
                    result['errors'].append("CRITICAL: Failed to fill request description")
                    return result
            
            # Step 2: Handle Department Selection
            logger.info("=== SELECTING DEPARTMENT ===")
            department_result = self._select_department(user_info.get('preferred_department', ''))
            
            if department_result['success']:
                result['steps_completed'].append(f"Department selection ({department_result['selected_department']})")
            else:
                result['errors'].extend(department_result['errors'])
                # Don't fail completely if department selection fails - continue with other fields
            
            # Step 3: Fill contact information with enhanced data
            logger.info("=== FILLING CONTACT INFORMATION ===")
            contact_result = self._fill_contact_information(user_info)
            
            if contact_result['filled_count'] > 0:
                result['steps_completed'].append(f"Contact information ({contact_result['filled_count']} fields)")
            
            result['errors'].extend(contact_result['errors'])
            
            # Step 4: Submit the form
            logger.info("=== SUBMITTING FORM ===")
            self.take_screenshot("before_form_submission")

            # NEW: handle terms checkbox if present
            try:
                if self._handle_form_terms_checkbox():
                    result['steps_completed'].append("Agreed to terms/conditions")
                    # brief pause in case the submit button becomes enabled after click
                    time.sleep(0.4)
            except Exception as e:
                # Non-fatal; still attempt submission
                logger.warning(f"⚠️ Terms checkbox handling skipped due to error: {e}")

            if self._submit_form():
                result['steps_completed'].append("Form submission")
                result['success'] = True
                time.sleep(4)
                self.take_screenshot("after_form_submission")

                confirmation = self._get_confirmation_info()
                result['confirmation'] = confirmation
            else:
                result['errors'].append("Failed to submit form")

            return result
        
        except Exception as e:
            logger.error(f"Form submission failed: {str(e)}")
            result['errors'].append(f"Unexpected error: {str(e)}")
            return result

    def _select_department(self, preferred_department: str) -> Dict[str, Any]:
        """Handle department selection dropdown with auto-population"""
        
        result = {
            'success': False,
            'selected_department': None,
            'errors': []
        }
        
        if not preferred_department:
            logger.warning("No preferred department specified")
            result['errors'].append("No preferred department specified")
            return result
        
        try:
            logger.info(f"🏛️ Attempting to select department: {preferred_department}")
            
            # Map department preferences to search terms
            department_mapping = {
                'police': ['police', 'police department', 'pd'],
                'sheriff': ['sheriff', "sheriff's office", 'sheriff office', 'so'],
                'district_attorney': ['district attorney', 'da', 'district attorney office', 'da office', 'prosecutor'],
                'probation': ['probation', 'probation office', 'probation department', 'probation services'],
                'other': ['other', 'municipal', 'city', 'county']
            }
                        
            search_terms = department_mapping.get(preferred_department.lower(), [preferred_department])
            
            # Strategy 1: Try dropdown/select element first
            try:
                select_elements = self.driver.find_elements(By.CSS_SELECTOR, "select")
                for select_element in select_elements:
                    try:
                        # Check if this looks like a department selector
                        select_html = select_element.get_attribute('outerHTML').lower()
                        if any(word in select_html for word in ['department', 'agency', 'office']):
                            
                            select = Select(select_element)
                            options = [option.text.lower() for option in select.options]
                            
                            # Try to find matching option
                            for search_term in search_terms:
                                for i, option_text in enumerate(options):
                                    if search_term.lower() in option_text:
                                        select.select_by_index(i)
                                        result['success'] = True
                                        result['selected_department'] = select.first_selected_option.text
                                        logger.info(f"✅ Selected department via dropdown: {result['selected_department']}")
                                        return result
                    except Exception as e:
                        logger.debug(f"Failed to handle select element: {str(e)}")
                        continue
            except Exception as e:
                logger.debug(f"No select elements found or error: {str(e)}")
            
            # Strategy 2: Auto-complete/searchable dropdown
            try:
                # Look for input fields that might be department selectors
                input_selectors = [
                    "input[placeholder*='department' i]",
                    "input[placeholder*='agency' i]",
                    "input[name*='department' i]",
                    "input[id*='department' i]",
                    "input[aria-label*='department' i]"
                ]
                
                for selector in input_selectors:
                    try:
                        department_inputs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        for dept_input in department_inputs:
                            # Try auto-complete approach
                            dept_input.click()
                            time.sleep(1)
                            
                            # Type the first search term
                            dept_input.clear()
                            dept_input.send_keys(search_terms[0])
                            time.sleep(2)  # Wait for autocomplete
                            
                            # Look for dropdown options that appear
                            dropdown_selectors = [
                                "div[role='option']",
                                "li[role='option']", 
                                ".dropdown-option",
                                ".autocomplete-option",
                                "[data-value]"
                            ]
                            
                            for dropdown_selector in dropdown_selectors:
                                try:
                                    options = self.driver.find_elements(By.CSS_SELECTOR, dropdown_selector)
                                    
                                    for option in options:
                                        option_text = option.text.lower()
                                        
                                        # Check if this option matches our department preference
                                        for search_term in search_terms:
                                            if search_term.lower() in option_text:
                                                option.click()
                                                result['success'] = True
                                                result['selected_department'] = option.text
                                                logger.info(f"✅ Selected department via autocomplete: {result['selected_department']}")
                                                return result
                                                
                                except Exception as e:
                                    continue
                                    
                    except Exception as e:
                        logger.debug(f"Failed with selector {selector}: {str(e)}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Auto-complete strategy failed: {str(e)}")
            
            # Strategy 3: Button-based selection
            try:
                button_texts = []
                for search_term in search_terms:
                    button_texts.extend([
                        f"//button[contains(text(), '{search_term}')]",
                        f"//div[contains(text(), '{search_term}') and contains(@class, 'option')]",
                        f"//span[contains(text(), '{search_term}') and ancestor::button]"
                    ])
                
                for button_xpath in button_texts:
                    try:
                        button = self.driver.find_element(By.XPATH, button_xpath)
                        button.click()
                        result['success'] = True
                        result['selected_department'] = button.text
                        logger.info(f"✅ Selected department via button: {result['selected_department']}")
                        return result
                    except Exception:
                        continue
                        
            except Exception as e:
                logger.debug(f"Button strategy failed: {str(e)}")
            
            # If we get here, department selection failed
            logger.warning(f"❌ Could not select department: {preferred_department}")
            result['errors'].append(f"Could not find or select department: {preferred_department}")
            return result
            
        except Exception as e:
            error_msg = f"Department selection error: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
            return result
    
    def _fill_request_description_fallback(self, request_text: str) -> bool:
        """Enhanced fallback that specifically avoids address fields and targets request description"""
        
        strategies = [
            ("Placeholder-based targeting", self._try_placeholder_based_selection),
            ("Size-based selection (avoiding address)", self._try_size_based_selection_smart),
            ("JavaScript rich text detection", self._try_javascript_detection),
            ("Content-editable detection", self._try_content_editable_detection),
            ("Position-based (top of form)", self._try_position_based_selection),
            ("Label association", self._try_label_association)
        ]
        
        for strategy_name, strategy_func in strategies:
            try:
                logger.info(f"🔍 Trying: {strategy_name}")
                if strategy_func(request_text):
                    logger.info(f"✅ {strategy_name} succeeded!")
                    return True
                else:
                    logger.info(f"❌ {strategy_name} failed")
            except Exception as e:
                logger.warning(f"❌ {strategy_name} error: {str(e)}")
                continue
        
        logger.error("💥 All enhanced fallback strategies failed")
        return False
    
    def _try_placeholder_based_selection(self, request_text: str) -> bool:
        """Target fields with request-specific placeholder text"""
        try:
            # Target the exact placeholder we saw in the screenshot
            selectors = [
                "textarea[placeholder*='Enter your request - please include all information']",
                "textarea[placeholder*='Enter your request']",
                "[contenteditable][placeholder*='Enter your request']",
                "textarea[placeholder*='please include all information']"
            ]
            
            for selector in selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    try:
                        # Must be a substantial field
                        rect = element.rect
                        if rect['height'] > 100:
                            return self._fill_element_with_verification(element, request_text, "placeholder-based")
                    except Exception:
                        continue
            
            return False
            
        except Exception as e:
            logger.error(f"Placeholder-based selection failed: {str(e)}")
            return False
    
    def _try_size_based_selection_smart(self, request_text: str) -> bool:
        """Find largest textarea but intelligently exclude address fields"""
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, "textarea, [contenteditable='true'], [contenteditable]")
            
            candidates = []
            for element in elements:
                try:
                    rect = element.rect
                    area = rect['width'] * rect['height']
                    
                    # Must be substantial size
                    if area < 10000:
                        continue
                    
                    # Check context to avoid address fields
                    is_address = self._is_likely_address_field(element)
                    
                    candidates.append({
                        'element': element,
                        'area': area,
                        'is_address': is_address,
                        'rect': rect
                    })
                    
                except Exception:
                    continue
            
            # Sort by area, but prioritize non-address fields
            candidates.sort(key=lambda x: (not x['is_address'], x['area']), reverse=True)
            
            # Try the best candidates
            for candidate in candidates[:3]:
                if not candidate['is_address']:  # Prioritize non-address fields
                    try:
                        if self._fill_element_with_verification(candidate['element'], request_text, "size-based-smart"):
                            return True
                    except Exception:
                        continue
            
            return False
            
        except Exception as e:
            logger.error(f"Smart size-based selection failed: {str(e)}")
            return False
    
    def _try_javascript_detection(self, request_text: str) -> bool:
        """Use JavaScript to detect and fill rich text editors"""
        try:
            success = self.driver.execute_script(f"""
                var requestText = `{request_text.replace('`', '\\`')}`;
                
                // Strategy 1: TinyMCE
                try {{
                    if (typeof tinymce !== 'undefined' && tinymce.editors && tinymce.editors.length > 0) {{
                        var editor = tinymce.editors[0];
                        editor.setContent(requestText);
                        return 'tinymce-api';
                    }}
                }} catch(e) {{}}
                
                // Strategy 2: CKEditor
                try {{
                    if (typeof CKEDITOR !== 'undefined') {{
                        for (var instance in CKEDITOR.instances) {{
                            CKEDITOR.instances[instance].setData(requestText);
                            return 'ckeditor-api';
                        }}
                    }}
                }} catch(e) {{}}
                
                // Strategy 3: Find largest textarea that's NOT for address
                var textareas = Array.from(document.querySelectorAll('textarea'));
                var candidates = textareas.map(ta => {{
                    var rect = ta.getBoundingClientRect();
                    var area = rect.width * rect.height;
                    var parentText = (ta.parentElement?.textContent || '').toLowerCase();
                    var isAddress = parentText.includes('street') || parentText.includes('address');
                    var placeholder = (ta.placeholder || '').toLowerCase();
                    var isRequest = placeholder.includes('request') || placeholder.includes('enter your');
                    
                    return {{
                        element: ta,
                        area: area,
                        isAddress: isAddress,
                        isRequest: isRequest,
                        score: area * (isRequest ? 2 : 1) * (isAddress ? 0.1 : 1)
                    }};
                }}).filter(c => c.area > 5000);
                
                candidates.sort((a, b) => b.score - a.score);
                
                if (candidates.length > 0 && !candidates[0].isAddress) {{
                    var best = candidates[0].element;
                    best.focus();
                    best.value = requestText;
                    best.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    best.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return 'textarea-smart';
                }}
                
                return false;
            """)
            
            if success:
                logger.info(f"JavaScript detection succeeded using: {success}")
                time.sleep(2)  # Allow event handlers to process
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"JavaScript detection failed: {str(e)}")
            return False
    
    def _try_content_editable_detection(self, request_text: str) -> bool:
        """Detect and fill contenteditable elements"""
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true'], [contenteditable]")
            
            for element in elements:
                try:
                    rect = element.rect
                    if rect['height'] > 100 and not self._is_likely_address_field(element):
                        return self._fill_element_with_verification(element, request_text, "contenteditable")
                except Exception:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Content-editable detection failed: {str(e)}")
            return False
    
    def _try_position_based_selection(self, request_text: str) -> bool:
        """Select based on position - request field should be near top"""
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, "textarea, [contenteditable='true'], [contenteditable]")
            
            positioned_elements = []
            for element in elements:
                try:
                    rect = element.rect
                    if rect['height'] > 50 and not self._is_likely_address_field(element):
                        positioned_elements.append((element, rect['y']))
                except:
                    continue
            
            positioned_elements.sort(key=lambda x: x[1])  # Sort by Y position
            
            # Try top 3 elements
            for element, y_pos in positioned_elements[:3]:
                try:
                    if self._fill_element_with_verification(element, request_text, "position-based"):
                        return True
                except Exception:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Position-based selection failed: {str(e)}")
            return False
    
    def _try_label_association(self, request_text: str) -> bool:
        """Find field by associated labels"""
        try:
            label_texts = ['request description', 'description', 'request', 'enter your request']
            
            for label_text in label_texts:
                try:
                    labels = self.driver.find_elements(By.XPATH, f"//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label_text}')]")
                    
                    for label in labels:
                        try:
                            # Get associated field
                            for_attr = label.get_attribute('for')
                            if for_attr:
                                field = self.driver.find_element(By.ID, for_attr)
                            else:
                                field = label.find_element(By.XPATH, ".//textarea | .//input | ./following-sibling::textarea | ./following-sibling::*//textarea")
                            
                            if self._fill_element_with_verification(field, request_text, "label-association"):
                                return True
                                
                        except Exception:
                            continue
                            
                except Exception:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Label association failed: {str(e)}")
            return False
    
    def _is_likely_address_field(self, element) -> bool:
        """Check if element is likely an address field"""
        try:
            # Check parent text for address indicators
            parent_text = ""
            try:
                parent = element.find_element(By.XPATH, "../..")
                parent_text = parent.text.lower()
            except:
                pass
            
            # Check element attributes
            element_attrs = ""
            try:
                element_attrs = f"{element.get_attribute('name')} {element.get_attribute('id')} {element.get_attribute('placeholder')}".lower()
            except:
                pass
            
            # Address indicators
            address_indicators = ['street', 'address', 'addr', 'mailing']
            request_indicators = ['request', 'description', 'enter your']
            
            has_address_indicator = any(indicator in parent_text or indicator in element_attrs for indicator in address_indicators)
            has_request_indicator = any(indicator in parent_text or indicator in element_attrs for indicator in request_indicators)
            
            # If it has request indicators, it's probably NOT an address field
            if has_request_indicator:
                return False
            
            return has_address_indicator
            
        except Exception:
            return False
    
    def _fill_element_with_verification(self, element, text: str, method: str) -> bool:
        """Fill element and verify success"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(1)
            
            # Handle different element types
            if element.tag_name.lower() == 'textarea':
                element.click()
                element.clear()
                element.send_keys(text)
                content = element.get_attribute('value')
            elif element.get_attribute('contenteditable'):
                element.click()
                element.send_keys(Keys.CONTROL + "a")
                element.send_keys(text)
                content = element.text or element.get_attribute('textContent')
            else:
                element.click()
                element.clear()
                element.send_keys(text)
                content = element.get_attribute('value') or element.text
            
            # Verify substantial content was entered
            if content and len(content) > 100:
                logger.info(f"✅ Successfully filled using {method}: {len(content)} characters")
                return True
            else:
                logger.warning(f"⚠️ {method} may have failed - only {len(content) if content else 0} characters")
                return False
                
        except Exception as e:
            logger.warning(f"❌ {method} fill failed: {str(e)}")
            return False
    
    def _fill_contact_information(self, user_info: Dict[str, str]) -> Dict[str, Any]:
        """Enhanced contact information filling with better field mapping"""
        
        result = {
            'filled_count': 0,
            'errors': [],
            'skipped_count': 0
        }
        
        try:
            logger.info("📝 Filling enhanced contact information")
            
            # Enhanced field mapping with multiple selectors for each field type
            field_mappings = [
                # Name field - try full name first, then first/last separately
                {
                    'name': 'Full Name',
                    'value': user_info.get('full_name', ''),
                    'selectors': [
                        "input[name*='name']:not([name*='first']):not([name*='last'])",
                        "input[placeholder*='full name' i]",
                        "input[placeholder*='your name' i]",
                        "input[id*='fullname' i]",
                        "input[id*='name']:not([id*='first']):not([id*='last'])"
                    ]
                },
                {
                    'name': 'First Name', 
                    'value': user_info.get('first_name', ''),
                    'selectors': [
                        "input[name*='first' i]",
                        "input[id*='first' i]",
                        "input[placeholder*='first' i]"
                    ]
                },
                {
                    'name': 'Last Name',
                    'value': user_info.get('last_name', ''),
                    'selectors': [
                        "input[name*='last' i]",
                        "input[id*='last' i]", 
                        "input[placeholder*='last' i]"
                    ]
                },
                # Email field
                {
                    'name': 'Email',
                    'value': user_info.get('email', ''),
                    'selectors': [
                        "input[type='email']",
                        "input[name*='email' i]",
                        "input[id*='email' i]",
                        "input[placeholder*='email' i]"
                    ]
                },
                # Phone field
                {
                'name': 'Phone',
                'value': user_info.get('phone', ''),
                'selectors': [
                    "input[type='tel']",
                    "input[name*='phone' i]",
                    "input[id*='phone' i]",
                    "input[placeholder*='phone' i]",
                    "input[id*='nr_form_input']",  
                    "label[for*='nr_form_input'] + div input",  
                    "label:contains('Phone') + div input"
                ]
            },
                # Organization field
                {
                    'name': 'Organization',
                    'value': user_info.get('organization', ''),
                    'selectors': [
                        "input[name*='organization' i]",
                        "input[name*='company' i]",
                        "input[id*='organization' i]",
                        "input[id*='company' i]",
                        "input[placeholder*='organization' i]",
                        "input[placeholder*='company' i]"
                    ]
                },
                # Street Address - use textarea or large input
                {
                    'name': 'Street Address',
                    'value': user_info.get('street_address', ''),
                    'selectors': [
                        "textarea[name*='address' i]:not([name*='email'])",
                        "textarea[id*='address' i]:not([id*='email'])",
                        "input[name*='street' i]",
                        "input[name*='address' i]:not([name*='email'])",
                        "textarea[placeholder*='street' i]",
                        "textarea[placeholder*='address' i]"
                    ]
                },
                # City field
                {
                    'name': 'City',
                    'value': user_info.get('city', ''),
                    'selectors': [
                        "input[name*='city' i]",
                        "input[id*='city' i]",
                        "input[placeholder*='city' i]"
                    ]
                },
                # ZIP Code field  
                {
                    'name': 'ZIP Code',
                    'value': user_info.get('zip_code', ''),
                    'selectors': [
                        "input[name*='zip' i]",
                        "input[name*='postal' i]",
                        "input[id*='zip' i]",
                        "input[id*='postal' i]",
                        "input[placeholder*='zip' i]"
                    ]
                }
            ]
            
            # Fill each field
            for field_info in field_mappings:
                if not field_info['value']:
                    continue
                    
                field_result = self._try_fill_field(
                    field_info['selectors'],
                    field_info['value'],
                    field_info['name']
                )
                
                if field_result:
                    result['filled_count'] += 1
                elif field_result is None:
                    result['skipped_count'] += 1
            
            # Handle State dropdown separately
            if user_info.get('state'):
                state_result = self._fill_state_field(user_info['state'])
                if state_result:
                    result['filled_count'] += 1
            
            logger.info(f"📊 Contact info filled: {result['filled_count']} fields, {result['skipped_count']} skipped")
            return result
            
        except Exception as e:
            logger.error(f"Error in enhanced contact filling: {str(e)}")
            result['errors'].append(f"Enhanced contact filling error: {str(e)}")
            return result
    
    
    def _try_fill_field(self, selectors: list, value: str, field_name: str) -> bool:
        """Enhanced field filling with better error handling"""
        
        if not value or not value.strip():
            return False
        
        for selector in selectors:
            try:
                fields = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for field in fields:
                    try:
                        # Check if field is visible and enabled
                        if not field.is_displayed() or not field.is_enabled():
                            continue
                        
                        # Check if field already has content
                        current_value = field.get_attribute('value') or ''
                        if current_value.strip():
                            logger.info(f"{field_name} already filled: '{current_value}'")
                            return None  # Field was pre-filled
                        
                        # Fill the field
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", field)
                        time.sleep(0.5)
                        
                        field.click()
                        field.clear()
                        field.send_keys(value)
                        
                        # Trigger events for dynamic forms
                        field.send_keys(Keys.TAB)
                        
                        # Verify
                        new_value = field.get_attribute('value') or ''
                        if value.strip().lower() in new_value.lower():
                            logger.info(f"✅ Filled {field_name}: '{value}'")
                            return True
                            
                    except Exception as e:
                        logger.debug(f"Failed to fill field {field_name}: {str(e)}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {str(e)}")
                continue
        
        logger.debug(f"Could not fill {field_name}")
        return False

    

    def _fill_state_field(self, state_value: str) -> bool:
        """Fill state field - Dynamic selection based on Supabase data with proper event triggering"""
        
        STATE_MAPPING = {
            'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
            'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
            'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
            'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
            'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
            'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
            'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
            'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
            'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
            'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'
        }
        
        try:
            logger.info(f"🗺️ DYNAMIC: Filling state field with Supabase value: '{state_value}'")
            
            # Determine both abbreviation and full name from the input
            if state_value.upper() in STATE_MAPPING:
                # Input is abbreviation (e.g., "LA")
                state_abbrev = state_value.upper()
                state_full_name = STATE_MAPPING[state_abbrev]
                logger.info(f"🗺️ Input is abbreviation: {state_abbrev} → {state_full_name}")
            else:
                # Input might be full name (e.g., "Louisiana")
                state_full_name = state_value.title()  # Capitalize properly
                state_abbrev = None
                
                # Find the abbreviation
                for abbrev, full_name in STATE_MAPPING.items():
                    if full_name.lower() == state_value.lower():
                        state_abbrev = abbrev
                        break
                
                if state_abbrev:
                    logger.info(f"🗺️ Input is full name: {state_full_name} → {state_abbrev}")
                else:
                    logger.warning(f"⚠️ Could not map '{state_value}' to a known state")
                    # Try to use the input as-is
                    state_full_name = state_value
                    state_abbrev = state_value.upper()
            
            # Target the HTML select element
            state_selectors = [
                "select[name='state']",  # Most specific
                "select[id*='nr_form_select']",  # NextRequest pattern
                "div.column.is-3 select",  # Select within state column
                "select[required]",  # Required select field
                "select"  # Fallback
            ]
            
            for i, selector in enumerate(state_selectors):
                try:
                    logger.info(f"🔍 Trying selector {i+1}: {selector}")
                    select_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    logger.info(f"🔍 Found {len(select_elements)} select elements")
                    
                    for j, select_element in enumerate(select_elements):
                        try:
                            if not select_element.is_displayed():
                                continue
                            
                            # Check if this looks like a state field
                            name = select_element.get_attribute('name') or ''
                            element_id = select_element.get_attribute('id') or ''
                            
                            logger.info(f"🔍 Select {j}: name='{name}', id='{element_id}'")
                            
                            # Skip if this doesn't look like a state field
                            if name and 'state' not in name.lower():
                                continue
                            
                            from selenium.webdriver.support.ui import Select
                            select = Select(select_element)
                            
                            logger.info(f"📋 Working with state select: {len(select.options)} options")
                            
                            # Strategy 1: Select by abbreviation value (most reliable for US states)
                            if state_abbrev:
                                try:
                                    logger.info(f"🎯 Trying to select by abbreviation value: '{state_abbrev}'")
                                    select.select_by_value(state_abbrev)
                                    
                                    # CRITICAL: Trigger events to update UI and form validation
                                    self._trigger_state_field_events(select_element)
                                    
                                    # Verify selection after events
                                    selected_option = select.first_selected_option
                                    selected_text = selected_option.text.strip()
                                    selected_value = selected_option.get_attribute('value')
                                    
                                    # Double-check that selection stuck
                                    if selected_value and selected_value != '':
                                        logger.info(f"✅ DYNAMIC: Selected by abbreviation - '{selected_text}' (value: '{selected_value}')")
                                        return True
                                    else:
                                        logger.warning(f"⚠️ Selection was reverted after events - trying next strategy")
                                        
                                except Exception as abbrev_error:
                                    logger.warning(f"Could not select by abbreviation '{state_abbrev}': {str(abbrev_error)}")
                            
                            # Strategy 2: Select by full state name
                            if state_full_name:
                                try:
                                    logger.info(f"🎯 Trying to select by full name: '{state_full_name}'")
                                    select.select_by_visible_text(state_full_name)
                                    
                                    # CRITICAL: Trigger events to update UI and form validation
                                    self._trigger_state_field_events(select_element)
                                    
                                    # Verify selection after events
                                    selected_option = select.first_selected_option
                                    selected_text = selected_option.text.strip()
                                    selected_value = selected_option.get_attribute('value')
                                    
                                    # Double-check that selection stuck
                                    if selected_value and selected_value != '':
                                        logger.info(f"✅ DYNAMIC: Selected by full name - '{selected_text}' (value: '{selected_value}')")
                                        return True
                                    else:
                                        logger.warning(f"⚠️ Selection was reverted after events - trying next strategy")
                                        
                                except Exception as name_error:
                                    logger.warning(f"Could not select by full name '{state_full_name}': {str(name_error)}")
                            
                            # Strategy 3: Manual search through options
                            logger.info(f"🔍 Manually searching for '{state_value}' in options...")
                            
                            for idx, option in enumerate(select.options):
                                option_text = option.text.strip()
                                option_value = option.get_attribute('value') or ''
                                
                                # Check multiple matching criteria
                                matches = [
                                    # Exact matches
                                    option_value.upper() == state_abbrev if state_abbrev else False,
                                    option_text.lower() == state_full_name.lower() if state_full_name else False,
                                    option_text.lower() == state_value.lower(),
                                    option_value.upper() == state_value.upper(),
                                    
                                    # Partial matches
                                    state_full_name and state_full_name.lower() in option_text.lower(),
                                    state_abbrev and state_abbrev.upper() in option_value.upper()
                                ]
                                
                                if any(matches):
                                    logger.info(f"🎯 FOUND MATCH at index {idx}: '{option_text}' (value: '{option_value}')")
                                    logger.info(f"🎯 Matched against target: '{state_value}' → abbrev:'{state_abbrev}', full:'{state_full_name}'")
                                    
                                    try:
                                        select.select_by_index(idx)
                                        
                                        # CRITICAL: Trigger events to update UI and form validation
                                        self._trigger_state_field_events(select_element)
                                        
                                        # Verify selection after events
                                        selected_option = select.first_selected_option
                                        selected_text = selected_option.text.strip()
                                        selected_value = selected_option.get_attribute('value')
                                        
                                        # Double-check that selection stuck
                                        if selected_value and selected_value != '':
                                            logger.info(f"✅ DYNAMIC: Selected by manual search - '{selected_text}' (value: '{selected_value}')")
                                            return True
                                        else:
                                            logger.warning(f"⚠️ Selection was reverted after events for index {idx}")
                                            continue
                                            
                                    except Exception as index_error:
                                        logger.warning(f"Could not select by index {idx}: {str(index_error)}")
                                        continue
                            
                            # Debug: Log available options if no match found
                            logger.warning(f"❌ No match found in select {j}. Available options:")
                            for idx, option in enumerate(select.options[:10]):  # Show first 10
                                option_text = option.text.strip()
                                option_value = option.get_attribute('value') or ''
                                logger.warning(f"  Option {idx}: value='{option_value}', text='{option_text}'")
                            
                            if len(select.options) > 10:
                                logger.warning(f"  ... and {len(select.options) - 10} more options")
                            
                        except Exception as select_error:
                            logger.warning(f"Error with select element {j}: {str(select_error)}")
                            continue
                            
                except Exception as selector_error:
                    logger.warning(f"Selector {i+1} failed: {str(selector_error)}")
                    continue
            
            logger.error(f"❌ DYNAMIC: Could not find or select state '{state_value}' in any dropdown")
            return False
            
        except Exception as e:
            logger.error(f"❌ DYNAMIC: State selection failed: {str(e)}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False

    def _trigger_state_field_events(self, select_element) -> None:
        """Trigger all necessary events to update UI and form validation after state selection"""
        try:
            logger.info("🔥 Triggering events to update UI and form validation")
            
            # Execute comprehensive event triggering via JavaScript
            self.driver.execute_script("""
                const selectEl = arguments[0];
                
                // Focus the element first
                selectEl.focus();
                
                // Trigger input events
                selectEl.dispatchEvent(new Event('input', {bubbles: true, cancelable: true}));
                selectEl.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
                
                // Trigger focus/blur cycle to ensure validation runs
                selectEl.dispatchEvent(new Event('blur', {bubbles: true, cancelable: true}));
                selectEl.dispatchEvent(new Event('focus', {bubbles: true, cancelable: true}));
                selectEl.dispatchEvent(new Event('blur', {bubbles: true, cancelable: true}));
                
                // Find and trigger form-level events
                const form = selectEl.closest('form');
                if (form) {
                    form.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
                    form.dispatchEvent(new Event('input', {bubbles: true, cancelable: true}));
                    
                    // Try to trigger form validation
                    if (typeof form.checkValidity === 'function') {
                        form.checkValidity();
                    }
                    
                    // Trigger any custom validation if it exists
                    if (typeof form.reportValidity === 'function') {
                        form.reportValidity();
                    }
                }
                
                // Look for any validation libraries and trigger them
                if (typeof $ !== 'undefined' && $(selectEl).valid) {
                    // jQuery Validation
                    $(selectEl).valid();
                }
                
                // Trigger any Angular/React/Vue validation if present
                const angularScope = selectEl.scope && selectEl.scope();
                if (angularScope && angularScope.$apply) {
                    angularScope.$apply();
                }
                
                // Custom event for any framework-specific validation
                selectEl.dispatchEvent(new CustomEvent('field-updated', {
                    bubbles: true,
                    detail: { field: 'state', value: selectEl.value }
                }));
                
            """, select_element)
            
            # Wait for UI updates and validation to process
            time.sleep(1.5)  # Increased wait time for UI to fully update
            
            # Additional verification with WebDriverWait
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            try:
                # Wait for any validation errors to clear or form to become valid
                WebDriverWait(self.driver, 3).until(
                    lambda driver: select_element.get_attribute('value') != ''
                )
            except TimeoutException:
                logger.warning("⚠️ Timeout waiting for state field validation to complete")
            
            logger.info("✅ State field events triggered successfully")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to trigger state field events: {str(e)}")
            # Don't fail the whole operation if event triggering fails
            pass

    def _validate_submit_button(self, element) -> bool:
        """Validate that an element is actually a submit button, not a file upload or formatting button"""
        try:
            # Get element information
            tag_name = element.tag_name.lower()
            element_type = (element.get_attribute("type") or "").lower()
            text_content = (element.text or "").lower().strip()
            value = (element.get_attribute("value") or "").lower()
            class_name = (element.get_attribute("class") or "").lower()
            
            # Create combined element info for pattern matching
            element_info = f"{text_content} {value} {class_name}".lower()
            
            # PRIORITY 1: Exclude file upload buttons (most important fix)
            file_upload_patterns = [
                'choose file', 'upload', 'browse', 'attach', 'select file', 
                'add file', 'file upload', 'browse file'
            ]
            
            for file_pattern in file_upload_patterns:
                if file_pattern in element_info:
                    logger.warning(f"❌ Excluding file upload button: {self._get_submit_element_info(element)}")
                    return False
            
            # PRIORITY 2: Exclude rich text editor and formatting buttons
            editor_patterns = [
                'ql-bold', 'ql-italic', 'ql-underline', 'ql-', 'editor-', 'format-'
            ]
            
            for editor_pattern in editor_patterns:
                if editor_pattern in element_info:
                    logger.warning(f"❌ Excluding editor button: {self._get_submit_element_info(element)}")
                    return False
            
            # PRIORITY 3: Exclude other non-submit actions
            exclude_patterns = [
                'btn-secondary', 'cancel', 'close', 'back', 'reset'
            ]
            
            for exclude_pattern in exclude_patterns:
                if exclude_pattern in element_info:
                    logger.warning(f"❌ Excluding non-submit button: {self._get_submit_element_info(element)}")
                    return False
            
            # PRIORITY 4: Positive validation - look for actual submit indicators
            submit_text_indicators = [
                'make request',      # Exact match for your case
                'submit request',
                'send request', 
                'create request',
                'submit',
                'send'
            ]
            
            # Check for submit text indicators
            has_submit_text = any(indicator in text_content for indicator in submit_text_indicators)
            
            # Check for submit-related class names (NextRequest specific)
            submit_class_indicators = [
                'nr-button',  # NextRequest button class
                'submit-btn',
                'form-submit',
                'btn-primary'
            ]
            
            has_submit_class = any(indicator in class_name for indicator in submit_class_indicators)
            
            # VALIDATION LOGIC:
            # 1. If it has "Make request" text, it's definitely the submit button
            if 'make request' in text_content:
                logger.info(f"✅ Found 'Make request' button: {self._get_submit_element_info(element)}")
                return True
            
            # 2. If it's type="submit" AND has submit text, it's valid
            if element_type == 'submit' and has_submit_text:
                logger.info(f"✅ Valid submit type with submit text: {self._get_submit_element_info(element)}")
                return True
            
            # 3. If it's a button with submit text AND submit-related classes
            if tag_name == 'button' and has_submit_text and has_submit_class:
                logger.info(f"✅ Valid button with submit indicators: {self._get_submit_element_info(element)}")
                return True
            
            # 4. Special case: NextRequest "nr-button" with submit-like text
            if 'nr-button' in class_name and any(word in text_content for word in ['submit', 'request', 'send']):
                logger.info(f"✅ Valid NextRequest button: {self._get_submit_element_info(element)}")
                return True
            
            # If none of the positive criteria match, reject
            logger.warning(f"❌ Element doesn't match submit criteria: {self._get_submit_element_info(element)}")
            logger.warning(f"   Text: '{text_content}', Type: '{element_type}', Class: '{class_name}'")
            
            return False
            
        except Exception as e:
            logger.warning(f"Error validating submit button: {str(e)}")
            return False  # If we can't validate, assume it's not a submit button

    def _find_and_click_submit_button(self) -> bool:
        """Updated to prioritize the exact 'Make request' button"""
        try:
            logger.info("Looking for submit button")
            
            # PRIORITY STRATEGY: Look for exact "Make request" button first
            try:
                logger.info("🎯 Looking specifically for 'Make request' button...")
                make_request_selectors = [
                    "button:contains('Make request')",
                    "//button[contains(text(), 'Make request')]",
                    "//button[text()='Make request']",
                    ".nr-button:contains('Make request')",
                    "button.nr-button:contains('Make request')"
                ]
                
                for selector in make_request_selectors:
                    try:
                        if selector.startswith("//"):
                            # XPath selector
                            elements = self.driver.find_elements(By.XPATH, selector)
                        else:
                            # Try CSS selector (though :contains might not work)
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        for element in elements:
                            if element.is_displayed() and element.is_enabled():
                                if 'make request' in (element.text or '').lower():
                                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                    time.sleep(0.5)
                                    element.click()
                                    logger.info(f"✅ Successfully clicked 'Make request' button: {self._get_submit_element_info(element)}")
                                    return True
                    except Exception as e:
                        logger.debug(f"Selector failed: {selector} - {str(e)}")
                        continue
            except Exception as e:
                logger.warning(f"Priority 'Make request' search failed: {str(e)}")
            
            # FALLBACK: Use original LLM + validation strategy
            logger.info("🔄 Falling back to LLM + validation strategy...")
            
            # Strategy 1: Use LLM to find submit button (if available)
            llm_selectors = []
            if self.llm_helper and self.llm_client:
                try:
                    llm_result = self._find_submit_button_with_llm()
                    if llm_result["success"]:
                        llm_selector_string = llm_result["instruction"].element_to_click
                        if llm_selector_string:
                            llm_selectors = [s.strip() for s in llm_selector_string.split(',') if s.strip()]
                            logger.info(f"🎯 LLM provided {len(llm_selectors)} selectors: {llm_selectors}")
                except Exception as e:
                    logger.warning(f"LLM submit button detection failed: {str(e)}")
            
            # Try LLM selectors with validation
            for i, selector in enumerate(llm_selectors):
                try:
                    logger.info(f"🎯 Trying LLM selector {i+1}/{len(llm_selectors)}: {selector}")
                    element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    
                    if self._validate_submit_button(element):
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        element.click()
                        logger.info(f"✅ Successfully clicked validated LLM selector: {selector}")
                        return True
                    else:
                        logger.warning(f"❌ LLM selector {i+1} failed validation")
                        
                except Exception as e:
                    logger.debug(f"   ❌ LLM selector {i+1} failed: {str(e)}")
                    continue
            
            # Strategy 2: Comprehensive fallback with strict validation
            logger.info("🔄 Trying comprehensive fallback selectors...")
            
            fallback_selectors = [
                # Exact text match selectors
                (By.XPATH, "//button[text()='Make request']"),
                (By.XPATH, "//button[contains(text(), 'Make request')]"),
                (By.XPATH, "//input[@value='Make request']"),
                
                # Primary submit patterns
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Submit')]"),
                
                # NextRequest specific patterns
                (By.CSS_SELECTOR, "button.nr-button"),
                (By.CSS_SELECTOR, ".nr-button"),
                
                # Generic patterns (last resort)
                (By.CSS_SELECTOR, "form button:last-child"),
                (By.CSS_SELECTOR, ".form-actions button"),
            ]
            
            for i, (selector_type, selector_value) in enumerate(fallback_selectors):
                try:
                    logger.info(f"🎯 Trying fallback {i+1}/{len(fallback_selectors)}: {selector_value}")
                    
                    elements = self.driver.find_elements(selector_type, selector_value)
                    
                    for j, element in enumerate(elements):
                        try:
                            if element.is_displayed() and element.is_enabled():
                                # Apply strict validation
                                if self._validate_submit_button(element):
                                    WebDriverWait(self.driver, 3).until(
                                        EC.element_to_be_clickable(element)
                                    )
                                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                    time.sleep(0.5)
                                    element.click()
                                    
                                    element_info = self._get_submit_element_info(element)
                                    logger.info(f"✅ Successfully clicked validated fallback element: {element_info}")
                                    return True
                                else:
                                    logger.debug(f"   ❌ Element {j+1} failed validation")
                                    
                        except Exception as e:
                            logger.debug(f"   ❌ Element {j+1} click failed: {str(e)}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"   ❌ Fallback selector {i+1} failed: {str(e)}")
                    continue
            
            logger.error("Could not find or click submit button")
            return False
            
        except Exception as e:
            logger.error(f"Error finding submit button: {str(e)}")
            return False
        
    def _submit_form(self) -> bool:
        """Submit the form with simple URL-based success validation"""
        try:
            logger.info("=== SUBMITTING FORM ===")
            
            # Store current URL to detect successful navigation
            initial_url = self.driver.current_url
            logger.info(f"📍 Initial URL: {initial_url}")
            
            # Take screenshot for debugging
            self.take_screenshot("before_form_submission")
            
            # Find and click submit button
            submit_success = self._find_and_click_submit_button()
            
            if not submit_success:
                logger.error("❌ Could not find or click submit button")
                return False
            
            # Wait for form submission to process
            time.sleep(5)
            
            # Validate submission success
            return self._validate_submission_success(initial_url)
            
        except Exception as e:
            logger.error(f"Error submitting form: {str(e)}")
            return False
        
    def _validate_submission_success(self, initial_url: str) -> bool:
        """Validate that form submission was successful by checking URL redirect"""
        try:
            current_url = self.driver.current_url
            logger.info(f"📍 After submission URL: {current_url}")
            
            # Check 1: URL should have changed from the form submission page
            if current_url == initial_url:
                logger.error("❌ URL did not change - form likely not submitted")
                return False
            
            # Check 2: Should not still be on the 'new request' form page
            if '/requests/new' in current_url.lower():
                logger.error("❌ Still on form page - submission failed")
                return False
            
            # Check 3: Look for request number pattern in URL (existing account flow)
            import re
            request_number_match = re.search(r'/requests/(\d+-\d+)', current_url)
            
            if request_number_match:
                request_number = request_number_match.group(1)
                logger.info(f"✅ SUCCESS: Redirected to request page: {request_number}")
                return True
            
            # Check 4: Check if redirected to account setup page (new account flow)
            # Trigger words: password, passwords, new, email
            account_setup_indicators = ['password', 'passwords', 'new', 'email']
            
            url_lower = current_url.lower()
            for indicator in account_setup_indicators:
                if indicator in url_lower:
                    logger.info(f"✅ SUCCESS: Redirected to account setup page (detected '{indicator}' in URL)")
                    logger.info(f"   This indicates new account creation flow")
                    return True
            
            # If URL changed but doesn't match expected patterns, log for debugging
            logger.warning(f"⚠️ URL changed but doesn't match request or setup pattern: {current_url}")
            self._debug_unexpected_redirect(current_url)
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error validating submission: {str(e)}")
            return False
        
    def _debug_unexpected_redirect(self, url: str):
        """Debug unexpected redirects to understand what happened"""
        try:
            logger.info("🔍 DEBUGGING UNEXPECTED REDIRECT:")
            logger.info(f"  URL: {url}")
            logger.info(f"  Title: {self.driver.title}")
            
            # Check for error messages on the page
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                
                # Look for common error indicators
                error_patterns = [
                    'error', 'failed', 'invalid', 'required', 'missing', 
                    'please fill', 'cannot be empty', 'validation'
                ]
                
                found_errors = []
                for pattern in error_patterns:
                    if pattern in page_text:
                        found_errors.append(pattern)
                
                if found_errors:
                    logger.warning(f"  ⚠️ Found potential error indicators: {found_errors}")
                else:
                    logger.info("  ℹ️ No obvious error indicators found")
                    
            except Exception as e:
                logger.warning(f"  Could not analyze page content: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error in redirect debugging: {str(e)}")


    def _debug_submit_elements(self) -> None:
        """Debug method to log all potential submit elements"""
        try:
            logger.info("🔍 Debugging all potential submit elements")
            
            # Find all buttons
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            logger.info(f"Found {len(buttons)} button elements:")
            
            for i, button in enumerate(buttons):
                try:
                    if button.is_displayed():
                        info = self._get_submit_element_info(button)
                        is_valid = self._validate_submit_button(button)
                        logger.info(f"  Button {i}: {info} | Valid: {is_valid}")
                except:
                    logger.info(f"  Button {i}: Could not get info")
            
            # Find all inputs
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            submit_inputs = [inp for inp in inputs if inp.get_attribute("type") in ["submit", "button"]]
            logger.info(f"Found {len(submit_inputs)} input submit/button elements:")
            
            for i, inp in enumerate(submit_inputs):
                try:
                    if inp.is_displayed():
                        info = self._get_submit_element_info(inp)
                        is_valid = self._validate_submit_button(inp)
                        logger.info(f"  Input {i}: {info} | Valid: {is_valid}")
                except:
                    logger.info(f"  Input {i}: Could not get info")
            
        except Exception as e:
            logger.error(f"Submit element debugging failed: {str(e)}")

    def _find_submit_button_with_llm(self) -> Dict[str, Any]:
        """Use LLM to find the submit button with improved prompting"""
        try:
            logger.info("🔍 Looking for submit button with LLM")
            
            if not self.llm_helper:
                return {"success": False, "error": "LLM helper not available"}
            
            screenshot_b64 = self.llm_helper.get_screenshot_from_driver(self.driver)
            page_text = self.llm_helper.extract_page_text(self.driver)
            
            if not screenshot_b64:
                return {"success": False, "error": "Could not capture screenshot"}
            
            button_prompt = """
            You are looking at a form submission page. Find the MAIN SUBMIT BUTTON that submits the entire form.
            
            Look for:
            - A "Submit" button
            - A "Make request" button  
            - A "Send" button
            - A button with type="submit"
            - Any button that would submit the entire form
            
            DO NOT select:
            - Rich text editor formatting buttons (bold, italic, underline)
            - Buttons with classes like "ql-bold", "ql-italic", etc.
            - Cancel, close, or secondary action buttons
            - Navigation buttons
            
            IMPORTANT: Provide EXACT CSS selectors that can be used to find the FORM SUBMISSION element.
            If multiple possible selectors exist, provide them separated by commas.
            Focus on the primary submit action, not formatting or editor buttons.
            """
            
            # Use the ClickInstruction model
            structured_llm = self.llm_helper.llm_client.with_structured_output(ClickInstruction)
            
            messages = [
                {"role": "system", "content": button_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Find the MAIN FORM SUBMIT button (not editor buttons) and provide EXACT CSS selectors. Page context:\n\n{page_text[:800]}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
                        }
                    ]
                }
            ]
            
            click_instruction = structured_llm.invoke(messages)
            
            logger.info(f"🎯 Submit button instruction: {click_instruction.reasoning}")
            logger.info(f"🎯 Element to click: {click_instruction.element_to_click}")
            logger.info(f"🎯 Click method: {click_instruction.click_method}")
            
            return {
                "success": True,
                "instruction": click_instruction
            }
            
        except Exception as e:
            logger.error(f"Failed to find submit button with LLM: {str(e)}")
            return {"success": False, "error": str(e)}

    def _get_submit_element_info(self, element) -> str:
        """Get debugging info about a submit element"""
        try:
            tag = element.tag_name
            text = element.text[:30] if element.text else ""
            value = element.get_attribute("value") or ""
            type_attr = element.get_attribute("type") or ""
            class_name = element.get_attribute("class") or ""
            return f"{tag} | text:'{text}' | value:'{value}' | type:'{type_attr}' | class:'{class_name[:30]}'"
        except:
            return "unknown element"
    def _check_for_form_submission(self) -> bool:
        """Check if form was successfully submitted"""
        try:
            # Look for common success indicators
            success_indicators = [
                "success",
                "submitted",
                "thank you",
                "confirmation",
                "received"
            ]
            
            # Check page content
            page_text = self.driver.page_source.lower()
            for indicator in success_indicators:
                if indicator in page_text:
                    return True
            
            # Check if URL changed (common after form submission)
            current_url = self.driver.current_url
            if "success" in current_url.lower() or "confirmation" in current_url.lower():
                return True
            
            return False
        except:
            return False

    
    
    def _get_confirmation_info(self) -> Optional[str]:
        """Get confirmation information - simplified for URL-based success"""
        try:
            current_url = self.driver.current_url
            
            # Extract request number from URL if present
            import re
            request_number_match = re.search(r'/requests/(\d+-\d+)', current_url)
            
            if request_number_match:
                request_number = request_number_match.group(1)
                return f"Request submitted successfully - Request #{request_number}"
            
            # If no request number found, provide current status
            return f"Form submitted - Current page: {self.driver.title} | URL: {current_url}"
            
        except Exception as e:
            logger.error(f"Failed to get confirmation: {str(e)}")
            return "Form submission status unknown due to error"
        
    def create_portal_account(self, email: str, password: str) -> Dict[str, Any]:
        """
        Fill account setup form with email and password, then create the account.
        
        After clicking "Create password", the portal redirects to a pending/confirmation page.
        We do NOT validate or analyze further - just return success.
        The bulk analysis worker will handle extracting the request after email confirmation.
        
        Args:
            email: User's email address
            password: User's password (must meet strength requirements)
            
        Returns:
            Dict with success status and details
        """
        
        result = {
            'success': False,
            'steps_completed': [],
            'errors': [],
            'account_created': False
        }
        
        try:
            logger.info("=== CREATING PORTAL ACCOUNT ===")
            logger.info(f"📧 Email: {email}")
            logger.info(f"🔐 Password: {'*' * len(password)}")
            
            # Take screenshot for debugging
            self.take_screenshot("account_setup_page")
            
            # Step 1: Fill email field (may already be filled)
            logger.info("📧 Step 1: Filling email field")
            email_result = self._fill_account_email_field(email)
            
            if email_result:
                result['steps_completed'].append('email_filled')
            elif email_result is None:
                result['steps_completed'].append('email_prefilled')
            else:
                result['errors'].append("Could not fill email field")
                # Don't fail yet - email might be pre-filled
            
            # Step 2: Fill password field
            logger.info("🔐 Step 2: Filling password field")
            password_result = self._fill_account_password_field(password)
            
            if not password_result:
                error_msg = "Failed to fill password field"
                logger.error(f"❌ {error_msg}")
                result['errors'].append(error_msg)
                return result
            
            result['steps_completed'].append('password_filled')
            
            # Step 3: Fill password confirmation field
            logger.info("🔐 Step 3: Filling password confirmation field")
            confirm_result = self._fill_account_password_confirmation_field(password)
            
            if not confirm_result:
                error_msg = "Failed to fill password confirmation field"
                logger.error(f"❌ {error_msg}")
                result['errors'].append(error_msg)
                return result
            
            result['steps_completed'].append('password_confirmation_filled')
            
            # Wait for password validation to complete
            time.sleep(2)
            
            # Take screenshot before clicking
            self.take_screenshot("before_create_password_click")
            
            # Step 4: Click "Create password" button
            logger.info("🔘 Step 4: Clicking 'Create password' button")
            create_button_result = self._click_create_password_button()
            
            if not create_button_result:
                error_msg = "Failed to click 'Create password' button"
                logger.error(f"❌ {error_msg}")
                result['errors'].append(error_msg)
                return result
            
            result['steps_completed'].append('create_password_clicked')
            
            # Wait for account creation and redirect to pending page
            time.sleep(4)
            
            # Take screenshot after clicking (should be on /pending page)
            self.take_screenshot("after_create_password_click")
            
            # SUCCESS - Account created, now on pending/confirmation page
            # We do NOT validate or look for request number
            # The bulk analysis worker will handle request extraction after email confirmation
            result['success'] = True
            result['account_created'] = True
            
            current_url = self.driver.current_url
            logger.info(f"✅ Portal account created successfully!")
            logger.info(f"📍 Redirected to: {current_url}")
            logger.info(f"📧 User must confirm email before request is officially submitted")
            logger.info(f"🔄 Bulk analysis worker will extract the request after confirmation")
            
            return result
            
        except Exception as e:
            error_msg = f"Account creation failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            result['errors'].append(error_msg)
            return result

    def _fill_account_email_field(self, email: str) -> Optional[bool]:
        """Fill the email field on account setup page"""
        
        email_selectors = [
            "input[name='email']",
            "input[type='email']",
            "input[id*='email' i]",
            "input[placeholder*='email' i]"
        ]
        
        try:
            for selector in email_selectors:
                fields = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for field in fields:
                    try:
                        if not field.is_displayed() or not field.is_enabled():
                            continue
                        
                        # Check if already filled
                        current_value = field.get_attribute('value') or ''
                        if current_value.strip():
                            logger.info(f"📧 Email field already filled: '{current_value}'")
                            # Verify it's the correct email
                            if email.lower() in current_value.lower():
                                return None  # Pre-filled correctly
                            else:
                                logger.warning(f"⚠️ Email mismatch - expected: {email}, found: {current_value}")
                                # Try to clear and re-fill
                                field.clear()
                        
                        # Fill the field
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", field)
                        time.sleep(0.5)
                        
                        field.click()
                        field.send_keys(email)
                        field.send_keys(Keys.TAB)  # Trigger validation
                        
                        # Verify
                        new_value = field.get_attribute('value') or ''
                        if email in new_value:
                            logger.info(f"✅ Email field filled: '{email}'")
                            return True
                            
                    except Exception as e:
                        logger.debug(f"Failed to fill email field: {str(e)}")
                        continue
            
            logger.warning("Could not fill email field")
            return False
            
        except Exception as e:
            logger.error(f"Email field filling error: {str(e)}")
            return False

    def _fill_account_password_field(self, password: str) -> bool:
        """Fill the password field on account setup page"""
        
        password_selectors = [
            "input[name='password']:not([name*='confirm']):not([name*='confirmation'])",
            "input[id*='password' i]:not([id*='confirm' i]):not([id*='confirmation' i])",
            "input[type='password']:nth-of-type(1)",
            "input[placeholder*='password' i]:not([placeholder*='confirm' i])"
        ]
        
        try:
            for selector in password_selectors:
                fields = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for field in fields:
                    try:
                        if not field.is_displayed() or not field.is_enabled():
                            continue
                        
                        # Scroll into view
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", field)
                        time.sleep(0.5)
                        
                        # Fill the field
                        field.click()
                        field.clear()
                        field.send_keys(password)
                        
                        # Trigger validation events
                        field.send_keys(Keys.TAB)
                        
                        # Small wait for validation to process
                        time.sleep(1)
                        
                        # Verify field has content (can't verify password text directly)
                        # Check if the field accepts input
                        if field.get_attribute('value'):
                            logger.info("✅ Password field filled successfully")
                            return True
                            
                    except Exception as e:
                        logger.debug(f"Failed to fill password field: {str(e)}")
                        continue
            
            logger.error("❌ Could not fill password field")
            return False
            
        except Exception as e:
            logger.error(f"Password field filling error: {str(e)}")
            return False

    def _fill_account_password_confirmation_field(self, password: str) -> bool:
        """Fill the password confirmation field on account setup page"""
        
        confirmation_selectors = [
            "input[name*='confirm' i]",
            "input[name*='confirmation' i]",
            "input[id*='confirm' i]",
            "input[id*='confirmation' i]",
            "input[type='password']:nth-of-type(2)",
            "input[placeholder*='confirm' i]"
        ]
        
        try:
            for selector in confirmation_selectors:
                fields = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for field in fields:
                    try:
                        if not field.is_displayed() or not field.is_enabled():
                            continue
                        
                        # Scroll into view
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", field)
                        time.sleep(0.5)
                        
                        # Fill the field
                        field.click()
                        field.clear()
                        field.send_keys(password)
                        
                        # Trigger validation events
                        field.send_keys(Keys.TAB)
                        
                        # Small wait for validation
                        time.sleep(1)
                        
                        # Verify field has content
                        if field.get_attribute('value'):
                            logger.info("✅ Password confirmation field filled successfully")
                            return True
                            
                    except Exception as e:
                        logger.debug(f"Failed to fill confirmation field: {str(e)}")
                        continue
            
            logger.error("❌ Could not fill password confirmation field")
            return False
            
        except Exception as e:
            logger.error(f"Password confirmation filling error: {str(e)}")
            return False

    def _click_create_password_button(self) -> bool:
        """Find and click the 'Create password' button"""
        
        try:
            logger.info("🔍 Looking for 'Create password' button")
            
            # Strategy 1: Exact text match with XPath
            xpath_selectors = [
                "//button[contains(text(), 'Create password')]",
                "//button[text()='Create password']",
                "//input[@type='submit' and @value='Create password']",
                "//button[contains(@class, 'submit') and contains(text(), 'Create')]"
            ]
            
            for xpath in xpath_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            logger.info(f"✅ Found 'Create password' button via XPath")
                            
                            # Scroll into view
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                            time.sleep(0.5)
                            
                            # Click
                            element.click()
                            logger.info("✅ Clicked 'Create password' button")
                            return True
                            
                except Exception as e:
                    logger.debug(f"XPath selector failed: {xpath} - {str(e)}")
                    continue
            
            # Strategy 2: CSS selectors
            css_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "button.submit",
                "button.btn-primary"
            ]
            
            for selector in css_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for element in elements:
                        # Check if button text contains "create" or "password"
                        button_text = (element.text or '').lower()
                        button_value = (element.get_attribute('value') or '').lower()
                        
                        if ('create' in button_text or 'create' in button_value) and \
                        ('password' in button_text or 'password' in button_value):
                            
                            if element.is_displayed() and element.is_enabled():
                                logger.info(f"✅ Found 'Create password' button via CSS")
                                
                                # Scroll and click
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.5)
                                element.click()
                                logger.info("✅ Clicked 'Create password' button")
                                return True
                                
                except Exception as e:
                    logger.debug(f"CSS selector failed: {selector} - {str(e)}")
                    continue
            
            # Strategy 3: LLM-based detection (if available)
            if self.llm_helper and self.llm_client:
                try:
                    logger.info("🧠 Trying LLM-based button detection")
                    llm_result = self._find_create_password_button_with_llm()
                    
                    if llm_result['success']:
                        selector = llm_result['selector']
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        
                        if element.is_displayed() and element.is_enabled():
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                            time.sleep(0.5)
                            element.click()
                            logger.info("✅ Clicked 'Create password' button via LLM")
                            return True
                            
                except Exception as e:
                    logger.warning(f"LLM button detection failed: {str(e)}")
            
            logger.error("❌ Could not find 'Create password' button")
            return False
            
        except Exception as e:
            logger.error(f"Error clicking create password button: {str(e)}")
            return False

    def _find_create_password_button_with_llm(self) -> Dict[str, Any]:
        """Use LLM to find the 'Create password' button"""
        try:
            if not self.llm_helper:
                return {"success": False, "error": "LLM helper not available"}
            
            screenshot_b64 = self.llm_helper.get_screenshot_from_driver(self.driver)
            page_text = self.llm_helper.extract_page_text(self.driver)
            
            if not screenshot_b64:
                return {"success": False, "error": "Could not capture screenshot"}
            
            button_prompt = """
            You are looking at an account setup page. Find the 'Create password' button.
            
            This button:
            - Should have text like "Create password"
            - Is the main action button for creating the account
            - NOT the "Do this later" button
            
            Provide the EXACT CSS selector to click this button.
            """
            
            structured_llm = self.llm_helper.llm_client.with_structured_output(ClickInstruction)
            
            messages = [
                {"role": "system", "content": button_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Find the 'Create password' button. Page context:\n\n{page_text[:800]}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
                        }
                    ]
                }
            ]
            
            click_instruction = structured_llm.invoke(messages)
            
            logger.info(f"🎯 LLM found button: {click_instruction.element_to_click}")
            
            return {
                "success": True,
                "selector": click_instruction.element_to_click
            }
            
        except Exception as e:
            logger.error(f"LLM button detection failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def _validate_account_creation(self) -> bool:
        """Validate that account was successfully created"""
        try:
            current_url = self.driver.current_url
            logger.info(f"📍 Current URL after account creation: {current_url}")
            
            # Check 1: URL should have changed from account setup
            if '/account' in current_url.lower() and '/setup' in current_url.lower():
                logger.warning("⚠️ Still on account setup page")
                return False
            
            # Check 2: Should be on request detail page (most common)
            import re
            request_number_match = re.search(r'/requests/(\d+-\d+)', current_url)
            
            if request_number_match:
                request_number = request_number_match.group(1)
                logger.info(f"✅ Redirected to request page: {request_number}")
                logger.info("✅ Account creation successful - on request detail page")
                return True
            
            # Check 3: Look for success indicators on the page
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                
                success_indicators = [
                    'account created',
                    'password set',
                    'welcome',
                    'successfully created'
                ]
                
                for indicator in success_indicators:
                    if indicator in page_text:
                        logger.info(f"✅ Found success indicator: '{indicator}'")
                        return True
                        
            except Exception as e:
                logger.warning(f"Could not check page text: {str(e)}")
            
            # Check 4: Check page title
            try:
                page_title = self.driver.title.lower()
                if 'request' in page_title or 'success' in page_title:
                    logger.info(f"✅ Success indicated by page title: {page_title}")
                    return True
            except:
                pass
            
            logger.warning("⚠️ Could not definitively confirm account creation")
            return False
            
        except Exception as e:
            logger.error(f"Error validating account creation: {str(e)}")
            return False