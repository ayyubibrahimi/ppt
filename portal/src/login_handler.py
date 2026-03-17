import time
import random
import logging
from typing import Dict, Any, List, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from models import LoginCredentials, ScreenshotAnalysis

logger = logging.getLogger(__name__)

class LoginHandler:
    def __init__(self, driver, screenshot_func, analyze_func):
        self.driver = driver
        self.take_screenshot = screenshot_func
        self.analyze_screenshot_with_llm = analyze_func
    
    def attempt_login(self, credentials: LoginCredentials) -> Dict[str, Any]:
        """Attempt to login to the portal"""
        try:
            logger.info("Attempting to login...")

            # First, look for "Sign in" button/link
            # Using more specific selectors first, then fallbacks
            sign_in_selectors = [
                # Submit buttons (for SSO/OpenID Connect portals like cityofwatsonvilleca)
                (By.CSS_SELECTOR, "input[type='Submit'][value*='Sign in']"),
                (By.CSS_SELECTOR, "input[type='submit'][value*='Sign in']"),
                (By.CSS_SELECTOR, "button[type='submit'].is-primary"),
                (By.XPATH, "//input[@type='Submit' and contains(@value, 'Sign in')]"),
                (By.XPATH, "//form[contains(@action, 'openid_connect')]//input[@type='Submit']"),

                # NextRequest-specific link selectors (for traditional auth)
                (By.XPATH, "//a[contains(@class, 'sign-in') or contains(@href, '/sign_in')]"),
                (By.CSS_SELECTOR, "a.sign-in"),
                (By.CSS_SELECTOR, "a[href*='/sign_in']"),
                (By.CSS_SELECTOR, "a[href*='sign_in']"),

                # Generic text-based selectors
                (By.LINK_TEXT, "Sign in"),
                (By.LINK_TEXT, "Sign In"),
                (By.LINK_TEXT, "Login"),
                (By.LINK_TEXT, "Log in"),
                (By.PARTIAL_LINK_TEXT, "Sign in"),

                # Fallback selectors
                (By.CSS_SELECTOR, "a[href*='sign']"),
                (By.CSS_SELECTOR, "button[data-test-id='sign-in']"),
                (By.CLASS_NAME, "sign-in-button"),
                (By.CLASS_NAME, "login-button")
            ]

            sign_in_clicked = self._try_click_elements(sign_in_selectors, "sign in", timeout=10)

            # FALLBACK: If not found, check if page uses dynamic rendering and retry
            if not sign_in_clicked and self._has_dynamic_rendering():
                logger.info("🔄 Dynamic rendering detected, waiting for content to load and retrying...")
                time.sleep(4)  # Wait for JavaScript to render
                sign_in_clicked = self._try_click_elements(sign_in_selectors, "sign in", timeout=10)
            
            if not sign_in_clicked:
                logger.info("✅ No sign in button found - assuming already logged in")
                
                # Take screenshot to confirm current state
                current_screenshot = self.take_screenshot("already_logged_in_check")
                current_analysis = self.analyze_screenshot_with_llm(current_screenshot)
                
                # Return success since we assume we're already logged in
                return {
                    'success': True,
                    'already_logged_in': True,
                    'message': 'No sign in button found - assuming already authenticated',
                    'current_screenshot': current_screenshot,
                    'current_analysis': current_analysis,
                    'final_url': self.driver.current_url
                }
            
            # If we found and clicked a sign in button, proceed with normal login flow
            logger.info("📝 Sign in button clicked - proceeding with login form")
            
            # Take screenshot after clicking sign in
            pre_login_screenshot = self.take_screenshot("after_sign_in_click")
            pre_login_analysis = self.analyze_screenshot_with_llm(pre_login_screenshot)
            
            # Find login form fields
            username_field = self._find_username_field()
            password_field = self._find_password_field()
            
            if not username_field or not password_field:
                return {
                    'success': False,
                    'error': 'Could not find login form fields',
                    'pre_login_screenshot': pre_login_screenshot,
                    'pre_login_analysis': pre_login_analysis,
                    'found_username': username_field is not None,
                    'found_password': password_field is not None
                }
            
            # Fill in credentials
            self._fill_credentials(username_field, password_field, credentials)

            # Check for terms agreement checkbox
            self._handle_terms_agreement()

            # Find and click submit button
            submit_clicked = self._try_submit()
            
            if not submit_clicked:
                return {
                    'success': False,
                    'error': 'Could not find submit button',
                    'credentials_filled': True
                }
            
            # Wait for login to process
            time.sleep(8)
            
            # Take screenshot after login attempt
            post_login_screenshot = self.take_screenshot("after_login_attempt")
            post_login_analysis = self.analyze_screenshot_with_llm(post_login_screenshot)
            
            # Check if login was successful
            login_success = self._evaluate_login_success(post_login_analysis, post_login_screenshot)
            
            return {
                'success': login_success,
                'already_logged_in': False,
                'pre_login_screenshot': pre_login_screenshot,
                'pre_login_analysis': pre_login_analysis,
                'post_login_screenshot': post_login_screenshot,
                'post_login_analysis': post_login_analysis,
                'final_url': self.driver.current_url
            }
            
        except Exception as e:
            logger.error(f"Login attempt failed: {str(e)}")
            error_screenshot = self.take_screenshot("login_error")
            return {
                'success': False,
                'error': str(e),
                'error_screenshot': error_screenshot
            }
    
    def _has_dynamic_rendering(self) -> bool:
        """
        Check if the page uses dynamic JavaScript rendering (Vue.js, React, etc.)
        Returns True if we detect common patterns of dynamic content
        """
        try:
            # Check for common dynamic rendering indicators
            has_vue = self.driver.execute_script(
                "return typeof Vue !== 'undefined' || "
                "document.querySelector('[data-v-]') !== null || "
                "document.querySelector('.mount') !== null || "
                "document.querySelector('#app') !== null"
            )

            has_react = self.driver.execute_script(
                "return typeof React !== 'undefined' || "
                "document.querySelector('[data-reactroot]') !== null || "
                "document.querySelector('[data-react-]') !== null"
            )

            # Check if page has module scripts (common in modern JS frameworks)
            has_modules = self.driver.execute_script(
                "return document.querySelector('script[type=\"module\"]') !== null"
            )

            is_dynamic = has_vue or has_react or has_modules

            if is_dynamic:
                logger.debug("🔍 Dynamic rendering detected (Vue/React/ES modules)")

            return is_dynamic

        except Exception as e:
            logger.debug(f"Error checking for dynamic rendering: {str(e)}")
            return False

    def _try_click_elements(self, selectors: List[Tuple], element_type: str, timeout: int = 3) -> bool:
        """Try to click elements using multiple selectors

        Args:
            selectors: List of (By.TYPE, selector_value) tuples
            element_type: Description of element type for logging
            timeout: Timeout in seconds for each selector attempt (default: 3)

        Returns:
            True if an element was found and clicked, False otherwise
        """
        for selector_type, selector_value in selectors:
            try:
                logger.debug(f"Trying to find {element_type} element: {selector_type}='{selector_value}' (timeout: {timeout}s)")
                element = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )

                # Add small random delay to appear more human (0.5-1.5 seconds)
                human_delay = random.uniform(0.5, 1.5)
                time.sleep(human_delay)

                # Scroll element into view before clicking (more human-like)
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                time.sleep(0.3)

                element.click()
                time.sleep(5)
                logger.info(f"✅ Clicked {element_type} element: {selector_type}='{selector_value}'")
                return True
            except TimeoutException:
                logger.debug(f"⏱️  Timeout waiting for {element_type} element: {selector_type}='{selector_value}'")
                continue
            except Exception as e:
                logger.debug(f"❌ Error clicking {element_type} element: {str(e)}")
                continue
        return False
    
    def _find_username_field(self):
        """Find username field using multiple selectors"""
        username_selectors = [
            (By.CSS_SELECTOR, 'input[type="email"]'),
            (By.CSS_SELECTOR, 'input[name="email"]'),
            (By.CSS_SELECTOR, 'input[name="username"]'),
            (By.CSS_SELECTOR, 'input[placeholder*="email"]'),
            (By.CSS_SELECTOR, 'input[placeholder*="username"]'),
            (By.CSS_SELECTOR, 'input[id*="email"]'),
            (By.CSS_SELECTOR, 'input[id*="username"]')
        ]
        
        for selector_type, selector_value in username_selectors:
            try:
                field = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                logger.info(f"Found username field: {selector_type}='{selector_value}'")
                return field
            except TimeoutException:
                continue
        return None
    
    def _find_password_field(self):
        """Find password field using multiple selectors"""
        password_selectors = [
            (By.CSS_SELECTOR, 'input[type="password"]'),
            (By.CSS_SELECTOR, 'input[name="password"]'),
            (By.CSS_SELECTOR, 'input[id*="password"]')
        ]
        
        for selector_type, selector_value in password_selectors:
            try:
                field = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                logger.info(f"Found password field: {selector_type}='{selector_value}'")
                return field
            except TimeoutException:
                continue
        return None
    
    def _fill_credentials(self, username_field, password_field, credentials: LoginCredentials):
        """Fill in login credentials"""
        username_field.clear()
        username_field.send_keys(credentials.username)
        time.sleep(1)
        
        password_field.clear()
        password_field.send_keys(credentials.password)
        time.sleep(1)
    
    def _try_submit(self) -> bool:
        """Try to find and click submit button"""
        submit_selectors = [
            (By.CSS_SELECTOR, 'button[type="submit"]'),
            (By.CSS_SELECTOR, 'input[type="submit"]'),
            (By.XPATH, "//button[contains(text(), 'Sign in')]"),
            (By.XPATH, "//button[contains(text(), 'Login')]"),
            (By.XPATH, "//button[contains(text(), 'Log in')]"),
            (By.CSS_SELECTOR, '[data-test-id="login-submit"]'),
            (By.CLASS_NAME, 'login-submit'),
            (By.CLASS_NAME, 'submit-button')
        ]
        
        return self._try_click_elements(submit_selectors, "submit")
    
    def _evaluate_login_success(self, analysis: ScreenshotAnalysis, screenshot: Dict[str, Any]) -> bool:
        """Evaluate if login was successful based on page analysis"""
        success_indicators = [
            analysis.page_type == 'logged_in_dashboard',
            'dashboard' in screenshot['title'].lower(),
            'welcome' in screenshot['url'].lower(),
            not analysis.login_required,
            any('make request' in elem.lower() for elem in analysis.key_elements)
        ]
        
        # Check for error indicators
        error_indicators = [
            analysis.page_type == 'error',
            'error' in screenshot['title'].lower(),
            any('invalid' in elem.lower() for elem in analysis.key_elements),
            any('incorrect' in elem.lower() for elem in analysis.key_elements),
            any('failed' in elem.lower() for elem in analysis.key_elements)
        ]
        
        if any(error_indicators):
            return False
            
        return any(success_indicators)
    
    def _handle_terms_agreement(self) -> bool:
        """
        Check for and click "I agree to terms" checkbox if present.
        This is required on some portals before the Sign in button becomes active.
        
        Returns:
            True if checkbox was found and clicked, False if not found (not an error)
        """
        try:
            logger.info("🔍 Checking for terms agreement checkbox...")
            
            # Strategy 1: Find label and click it (most reliable for custom checkboxes)
            logger.info("🎯 Strategy 1: Finding and clicking label...")
            terms_label_patterns = [
                "I agree to these terms",
                "agree to these terms",
                "agree to terms",
                "accept terms",
                "I agree"
            ]
            
            for pattern in terms_label_patterns:
                try:
                    # Find label containing this text (case-insensitive)
                    label_xpath = f"//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern.lower()}')]"
                    labels = self.driver.find_elements(By.XPATH, label_xpath)
                    
                    for label in labels:
                        try:
                            # Get the 'for' attribute
                            for_attr = label.get_attribute('for')
                            if for_attr:
                                # Find checkbox by ID to check if already selected
                                checkbox = self.driver.find_element(By.ID, for_attr)
                                
                                if checkbox.is_selected():
                                    logger.info(f"✅ Terms checkbox already checked")
                                    return True
                                
                                # Click the label (this is what works!)
                                label.click()
                                time.sleep(0.5)
                                
                                # Verify it worked
                                if checkbox.is_selected():
                                    logger.info(f"✅ Successfully checked terms checkbox via label click")
                                    return True
                                    
                        except Exception as e:
                            logger.debug(f"Label attempt failed: {str(e)}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"Pattern '{pattern}' not found: {str(e)}")
                    continue
            
            # Strategy 2: Direct checkbox selectors with label click fallback
            logger.info("🎯 Strategy 2: Finding checkbox and clicking its label...")
            checkbox_selectors = [
                "input#accept_terms",
                "input[name='accept_terms']",
                "input[id*='accept' i][id*='terms' i]",
                "input[name*='accept' i][name*='terms' i]",
                "input[class*='accept-terms' i]",
                "input[id*='terms' i][type='checkbox']",
                "input[name*='terms' i][type='checkbox']",
                "input[id*='agree' i][type='checkbox']",
                "input[name*='agree' i][type='checkbox']"
            ]
            
            for selector in checkbox_selectors:
                try:
                    checkboxes = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for checkbox in checkboxes:
                        # Check if already selected
                        if checkbox.is_selected():
                            logger.info(f"✅ Terms checkbox already checked")
                            return True
                        
                        # Try to find and click the associated label
                        try:
                            checkbox_id = checkbox.get_attribute('id')
                            if checkbox_id:
                                label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{checkbox_id}']")
                                label.click()
                                time.sleep(0.5)
                                
                                if checkbox.is_selected():
                                    logger.info(f"✅ Successfully checked terms checkbox via label")
                                    return True
                        except Exception:
                            pass
                        
                        # Fallback: Try JavaScript click on checkbox itself
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", checkbox)
                            time.sleep(0.3)
                            self.driver.execute_script("arguments[0].click();", checkbox)
                            time.sleep(0.5)
                            
                            if checkbox.is_selected():
                                logger.info(f"✅ Successfully checked terms checkbox via JS click")
                                return True
                                
                        except Exception as e:
                            logger.debug(f"JS click failed: {str(e)}")
                            
                except Exception as e:
                    logger.debug(f"Selector '{selector}' failed: {str(e)}")
                    continue
            
            # Strategy 3: Find checkbox inside label and click the label
            logger.info("🎯 Strategy 3: Finding checkbox inside label...")
            try:
                labels_with_checkboxes = self.driver.find_elements(By.XPATH, 
                    "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'terms')]")
                
                for label in labels_with_checkboxes:
                    try:
                        # Find checkbox inside this label
                        checkbox = label.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                        
                        if checkbox.is_selected():
                            logger.info("✅ Terms checkbox already checked")
                            return True
                        
                        # Click the label
                        label.click()
                        time.sleep(0.5)
                        
                        if checkbox.is_selected():
                            logger.info("✅ Successfully checked terms checkbox via label")
                            return True
                            
                    except Exception:
                        continue
                        
            except Exception as e:
                logger.debug(f"Inside label strategy failed: {str(e)}")
            
            # No terms checkbox found - not an error, just log and continue
            logger.info("ℹ️ No terms agreement checkbox found - continuing with login")
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Error checking for terms checkbox: {str(e)}")
            return False