import base64
import logging
import time
from typing import Dict, Optional, Any, List
from models import ScreenshotAnalysis, LoginCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from langchain_core.messages import HumanMessage, SystemMessage
import datetime
import json
import os
from llm import gpt_4o_mini
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SeleniumPortalAgent:
    def __init__(self, llm_client, headless: bool = False):
        self.llm_client = llm_client
        self.headless = headless
        self.driver = None
        self.screenshots = []  # Store screenshots with metadata
        
    def __enter__(self):
        self.setup_driver()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()

    def setup_driver(self):
        """Setup Chrome driver with stealth options"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless')
            
        # Stealth options to avoid detection
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--ignore-ssl-errors')
        chrome_options.add_argument('--ignore-certificate-errors-spki-list')
        
        # Set realistic window size
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Set realistic user agent
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
        
        # Exclude automation switches
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Additional prefs
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # Initialize driver
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Execute script to remove webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Set implicit wait
        self.driver.implicitly_wait(10)
        
        logger.info("Chrome driver initialized successfully")

    def take_screenshot(self, label: str = "") -> Dict[str, Any]:
        """Take screenshot and return metadata with base64 image"""
        screenshot_bytes = self.driver.get_screenshot_as_png()
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
        
        screenshot_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'url': self.driver.current_url,
            'title': self.driver.title,
            'label': label,
            'screenshot_b64': screenshot_b64,
            'screenshot_size': len(screenshot_bytes)
        }
        
        self.screenshots.append(screenshot_data)
        logger.info(f"Screenshot taken: {label} - {screenshot_data['url']}")
        return screenshot_data

    def get_page_text_content(self) -> str:
        """Get the text content of the current page"""
        try:
            text_content = self.driver.find_element(By.TAG_NAME, "body").text
            return text_content[:3000]  # Limit to first 3000 characters
        except Exception as e:
            logger.error(f"Error getting page text: {str(e)}")
            return "Error retrieving page content"

    def analyze_screenshot_with_llm(self, screenshot_data: Dict[str, Any]) -> ScreenshotAnalysis:
        """Use LLM to analyze the screenshot and page content"""
        
        page_text = self.get_page_text_content()
        
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
        
        structured_llm = self.llm_client.with_structured_output(ScreenshotAnalysis)
        result = structured_llm.invoke([
            SystemMessage(content=analysis_prompt),
            HumanMessage(content="Analyze this page and provide detailed assessment with ALL required fields.")
        ])
        
        return result

    def navigate_to_portal(self, portal_url: str) -> Dict[str, Any]:
        """Navigate to the portal with realistic human-like behavior"""
        try:
            logger.info(f"Navigating to portal: {portal_url}")
            
            # First, visit Google to establish a realistic browsing pattern
            self.driver.get("https://www.google.com")
            time.sleep(2)  # Human-like pause
            
            # Navigate to the actual portal
            self.driver.get(portal_url)
            
            # Wait for page to load
            time.sleep(5)
            
            # Perform human-like interactions
            try:
                # Scroll down and back up
                self.driver.execute_script("window.scrollTo(0, 100);")
                time.sleep(1)
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)
            except:
                pass  # Ignore scroll errors
            
            # Take initial screenshot
            screenshot = self.take_screenshot("initial_portal_view")
            
            # Check if we were redirected to a block page
            current_url = self.driver.current_url
            if 'block.php' in current_url or 'civicplus.com' in current_url:
                logger.warning(f"⚠️  Redirected to blocking page: {current_url}")
                analysis = self.analyze_screenshot_with_llm(screenshot)
                return {
                    'success': False,
                    'blocked': True,
                    'redirect_url': current_url,
                    'screenshot': screenshot,
                    'analysis': analysis,
                    'url': current_url,
                    'title': self.driver.title,
                    'error': f"Access blocked - redirected to {current_url}"
                }
            
            # Analyze the page
            analysis = self.analyze_screenshot_with_llm(screenshot)
            
            return {
                'success': True,
                'screenshot': screenshot,
                'analysis': analysis,
                'url': self.driver.current_url,
                'title': self.driver.title
            }
            
        except Exception as e:
            logger.error(f"Failed to navigate to portal: {str(e)}")
            
            # Try to take a screenshot even if navigation failed
            try:
                error_screenshot = self.take_screenshot("navigation_error")
                current_url = self.driver.current_url
                return {
                    'success': False,
                    'error': str(e),
                    'url': current_url,
                    'error_screenshot': error_screenshot,
                    'blocked': 'block.php' in current_url or 'civicplus.com' in current_url
                }
            except:
                return {
                    'success': False,
                    'error': str(e),
                    'url': portal_url
                }

    def attempt_login(self, credentials: LoginCredentials) -> Dict[str, Any]:
        """Attempt to login to the portal"""
        try:
            logger.info("Attempting to login...")
            
            # First, look for "Sign in" button/link
            sign_in_selectors = [
                (By.LINK_TEXT, "Sign in"),
                (By.LINK_TEXT, "Sign In"),
                (By.LINK_TEXT, "Login"),
                (By.LINK_TEXT, "Log in"),
                (By.PARTIAL_LINK_TEXT, "Sign in"),
                (By.CSS_SELECTOR, "a[href*='sign']"),
                (By.CSS_SELECTOR, "button[data-test-id='sign-in']"),
                (By.CLASS_NAME, "sign-in-button"),
                (By.CLASS_NAME, "login-button")
            ]
            
            sign_in_clicked = False
            for selector_type, selector_value in sign_in_selectors:
                try:
                    element = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    element.click()
                    time.sleep(5)  # Wait for login page to load
                    sign_in_clicked = True
                    logger.info(f"Clicked sign in element: {selector_type}='{selector_value}'")
                    break
                except TimeoutException:
                    continue
            
            if not sign_in_clicked:
                logger.warning("No sign in button found, checking if already on login page")
            
            # Take screenshot after clicking sign in
            pre_login_screenshot = self.take_screenshot("after_sign_in_click")
            pre_login_analysis = self.analyze_screenshot_with_llm(pre_login_screenshot)
            
            # Find username field
            username_selectors = [
                (By.CSS_SELECTOR, 'input[type="email"]'),
                (By.CSS_SELECTOR, 'input[name="email"]'),
                (By.CSS_SELECTOR, 'input[name="username"]'),
                (By.CSS_SELECTOR, 'input[placeholder*="email"]'),
                (By.CSS_SELECTOR, 'input[placeholder*="username"]'),
                (By.CSS_SELECTOR, 'input[id*="email"]'),
                (By.CSS_SELECTOR, 'input[id*="username"]')
            ]
            
            username_field = None
            for selector_type, selector_value in username_selectors:
                try:
                    username_field = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((selector_type, selector_value))
                    )
                    logger.info(f"Found username field: {selector_type}='{selector_value}'")
                    break
                except TimeoutException:
                    continue
            
            # Find password field
            password_selectors = [
                (By.CSS_SELECTOR, 'input[type="password"]'),
                (By.CSS_SELECTOR, 'input[name="password"]'),
                (By.CSS_SELECTOR, 'input[id*="password"]')
            ]
            
            password_field = None
            for selector_type, selector_value in password_selectors:
                try:
                    password_field = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((selector_type, selector_value))
                    )
                    logger.info(f"Found password field: {selector_type}='{selector_value}'")
                    break
                except TimeoutException:
                    continue
            
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
            username_field.clear()
            username_field.send_keys(credentials.username)
            time.sleep(1)
            
            password_field.clear()
            password_field.send_keys(credentials.password)
            time.sleep(1)
            
            # Find and click submit button
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
            
            submit_clicked = False
            for selector_type, selector_value in submit_selectors:
                try:
                    submit_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    submit_btn.click()
                    submit_clicked = True
                    logger.info(f"Clicked submit button: {selector_type}='{selector_value}'")
                    break
                except TimeoutException:
                    continue
            
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
            login_success = self.evaluate_login_success(post_login_analysis, post_login_screenshot)
            
            return {
                'success': login_success,
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

    def evaluate_login_success(self, analysis: ScreenshotAnalysis, screenshot: Dict[str, Any]) -> bool:
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

    def save_session_results(self, results: Dict[str, Any]):
        """Save all screenshots and analysis results to files"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Convert Pydantic models to dictionaries for JSON serialization
        def convert_to_dict(obj):
            if hasattr(obj, 'model_dump'):
                return obj.model_dump()
            elif hasattr(obj, 'dict'):
                return obj.dict()
            elif isinstance(obj, dict):
                return {k: convert_to_dict(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_to_dict(item) for item in obj]
            else:
                return obj
        
        # Save detailed results as JSON
        json_filename = f"alameda_portal_session_{timestamp}.json"
        json_data = {
            'session_timestamp': timestamp,
            'portal_url': 'https://alamedacountysheriffca.nextrequest.com/',
            'total_screenshots': len(self.screenshots),
            'results': convert_to_dict(results),
            'screenshots_metadata': [
                {
                    'timestamp': s['timestamp'],
                    'url': s['url'], 
                    'title': s['title'],
                    'label': s['label'],
                    'size_bytes': s['screenshot_size']
                }
                for s in self.screenshots
            ]
        }
        
        try:
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save JSON: {str(e)}")
        
        # Save summary text file
        summary_filename = f"alameda_portal_summary_{timestamp}.txt"
        with open(summary_filename, 'w', encoding='utf-8') as f:
            f.write(f"=== ALAMEDA COUNTY SHERIFF NEXTREQUEST PORTAL SESSION ===\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Portal URL: https://alamedacountysheriffca.nextrequest.com/\n")
            f.write(f"Total Screenshots: {len(self.screenshots)}\n\n")
            
            if 'navigation' in results:
                nav = results['navigation']
                f.write(f"PORTAL NAVIGATION:\n")
                f.write(f"- Success: {nav['success']}\n")
                f.write(f"- Final URL: {nav.get('url', 'N/A')}\n")
                f.write(f"- Page Title: {nav.get('title', 'N/A')}\n")
                if nav.get('blocked'):
                    f.write(f"- BLOCKED: Yes - redirected to {nav.get('redirect_url', 'unknown')}\n")
                if 'analysis' in nav:
                    analysis = nav['analysis']
                    if hasattr(analysis, 'model_dump'):
                        analysis_dict = analysis.model_dump()
                    else:
                        analysis_dict = analysis
                    f.write(f"- Page Type: {analysis_dict.get('page_type', 'unknown')}\n")
                    f.write(f"- Login Required: {analysis_dict.get('login_required', 'unknown')}\n")
                    f.write(f"- Key Elements: {analysis_dict.get('key_elements', [])}\n")
                    f.write(f"- Next Steps: {analysis_dict.get('next_steps', [])}\n")
                if nav.get('error'):
                    f.write(f"- Error: {nav['error']}\n")
                f.write("\n")
        
        logger.info(f"Session results saved to {json_filename} and {summary_filename}")

    def access_portal_session(self, portal_url: str, credentials: Optional[LoginCredentials] = None) -> Dict[str, Any]:
        """Complete portal access session: navigate, analyze, and optionally login"""
        
        session_results = {}
        
        try:
            # Step 1: Navigate to portal
            logger.info("=== STEP 1: NAVIGATING TO ALAMEDA COUNTY NEXTREQUEST PORTAL ===")
            navigation_result = self.navigate_to_portal(portal_url)
            session_results['navigation'] = navigation_result
            
            if not navigation_result['success']:
                if navigation_result.get('blocked'):
                    logger.error("❌ Portal access blocked by CivicPlus security")
                else:
                    logger.error("❌ Failed to access portal")
                return session_results
            
            # Step 2: Analyze initial page
            initial_analysis = navigation_result['analysis']
            logger.info(f"✅ Portal accessed successfully!")
            logger.info(f"Page type: {initial_analysis.page_type}")
            logger.info(f"Login required: {initial_analysis.login_required}")
            logger.info(f"Key elements found: {initial_analysis.key_elements}")
            logger.info(f"Recommended next steps: {initial_analysis.next_steps}")
            
            # Step 3: Login if credentials provided
            if credentials:
                logger.info("=== STEP 2: ATTEMPTING LOGIN ===")
                login_result = self.attempt_login(credentials)
                session_results['login'] = login_result
                
                if login_result['success']:
                    logger.info("✅ Login successful!")
                    
                    # Take final screenshot
                    final_screenshot = self.take_screenshot("final_logged_in_state")
                    final_analysis = self.analyze_screenshot_with_llm(final_screenshot)
                    
                    session_results['final_state'] = {
                        'screenshot': final_screenshot,
                        'analysis': final_analysis
                    }
                    
                    logger.info(f"Final state: {final_analysis.page_type}")
                    logger.info(f"Available actions: {final_analysis.next_steps}")
                    
                else:
                    logger.error(f"❌ Login failed: {login_result.get('error', 'Unknown error')}")
            
            else:
                logger.info("ℹ️  No login credentials provided - analyzing portal without authentication")
                session_results['login'] = {'skipped': True, 'reason': 'No credentials provided'}
            
            # Save results
            self.save_session_results(session_results)
            
            return session_results
            
        except Exception as e:
            logger.error(f"Portal access session failed: {str(e)}")
            session_results['session_error'] = str(e)
            self.save_session_results(session_results)
            return session_results

# Usage example
def main():
    # Portal URL
    portal_url = os.environ.get("PORTAL_URL")

    credentials = LoginCredentials(
        username= os.environ.get("USERNAME"),
        password= os.environ.get("PASSWORD")
    )
    

    # portal_url = "https://nola.nextrequest.com/"
    
    # # Credentials (optional)
    # credentials = LoginCredentials(
    #     username="",
    #     password=""
    # )
    
    # Run the session
    with SeleniumPortalAgent(gpt_4o_mini, headless=False) as agent:
        results = agent.access_portal_session(
            portal_url=portal_url,
            credentials=credentials  
        )
        
        print("\n" + "="*60)
        print("=== ALAMEDA COUNTY PORTAL SESSION COMPLETE ===")
        print("="*60)
        print(f"Portal URL: {portal_url}")
        print(f"Navigation successful: {results.get('navigation', {}).get('success', False)}")
        
        if 'navigation' in results and results['navigation']['success']:
            nav = results['navigation']
            print(f"✅ Successfully accessed portal")
            print(f"Final URL: {nav['url']}")
            print(f"Page title: {nav['title']}")
            print(f"Page type: {nav['analysis'].page_type}")
            print(f"Login required: {nav['analysis'].login_required}")
            print(f"Key elements: {nav['analysis'].key_elements}")
        else:
            print(f"❌ Failed to access portal")
            if 'error' in results.get('navigation', {}):
                print(f"Error: {results['navigation']['error']}")
        
        if 'login' in results:
            if results['login'].get('skipped'):
                print(f"Login skipped: {results['login']['reason']}")
            else:
                success = results['login'].get('success', False)
                print(f"Login successful: {success}")
        
        print(f"\nTotal screenshots taken: {len(agent.screenshots)}")
        print("📁 Check the generated files for detailed results!")

if __name__ == "__main__":
    main()

 