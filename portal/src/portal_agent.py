import time
import logging
import datetime
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from models import LoginCredentials
from browser_setup import BrowserSetup
from screenshot_manager import ScreenshotManager
from llm import LLMAnalyzer
from login_handler import LoginHandler
from session_manager import SessionManager
from request_analyzer import RequestAnalyzer
from request_workflow import RequestWorkflow 
from selenium.webdriver.support import expected_conditions as EC
from monitoring_agent import MonitoringAgent
from llm_helper import LLMHelper
from message_coordinator import MessageCoordinator
from workflow_state_helper import WorkflowStateHelper

logger = logging.getLogger(__name__)

class PortalAgent:
    def __init__(self, llm_client, headless: bool = False):
        self.llm_client = llm_client
        self.headless = headless
        self.driver = None
        self.screenshot_manager = None
        self.llm_analyzer = None
        self.llm_helper = None
        self.workflow_state_helper = WorkflowStateHelper(llm_client)
        self.login_handler = None
        self.request_workflow = None
        self.request_analyzer = None
        self.is_logged_in = False
        self.results_dir = Path(".")  
        
    def __enter__(self):
        self.setup()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()
    
    def setup(self):
        """Initialize all components"""
        self.driver = BrowserSetup.create_chrome_driver(self.headless)
        self.screenshot_manager = ScreenshotManager(self.driver)
        self.llm_analyzer = LLMAnalyzer(self.llm_client)
        self.llm_helper = LLMHelper(self.llm_client)
        self.login_handler = LoginHandler(
            self.driver,
            self.screenshot_manager.take_screenshot,
            self.analyze_screenshot_with_llm
        )
        self.request_analyzer = RequestAnalyzer(
            driver=self.driver,
            screenshot_func=self.take_screenshot,
            llm_client=self.llm_client,
            workflow_state_helper=self.workflow_state_helper
        )
        
    def setup_request_workflow(self):
        """Setup request workflow after successful login"""
        try:
            self.request_workflow = RequestWorkflow(
                self.llm_client,
                self.driver,
                self.screenshot_manager.take_screenshot
            )
            logger.info("Request workflow initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import request workflow: {str(e)}")
            logger.error("Make sure request_workflow.py and related modules are available")
            raise

    def _is_request_in_database(self, request_number: str) -> bool:
        """Check if request is already in database"""
        try:
            if self.request_analyzer.db and self.request_analyzer.user_id:
                result = self.request_analyzer.db.supabase.table('requests').select('id').eq('user_id', self.request_analyzer.user_id).eq('request_number', request_number).execute()
                return len(result.data) > 0
            return False
        except Exception as e:
            logger.debug(f"Database check failed for {request_number}: {str(e)}")
            return False
        
    def _navigate_to_first_page(self) -> bool:
        """Navigate to the first page (optimized)"""
        try:
            logger.info("🔍 Navigating to first page")
            
            # Check what page we're currently on
            current_url = self.driver.current_url
            logger.info(f"🔍 Current URL: {current_url}")
            
            import re
            page_match = re.search(r'page=(\d+)', current_url)
            if page_match:
                current_page_num = int(page_match.group(1))
                logger.info(f"🔍 Currently on page {current_page_num}")
                
                if current_page_num == 1:
                    logger.info("✅ Already on first page")
                    return True
            
            # Use JavaScript directly since it works reliably
            logger.info("🔧 Using JavaScript to navigate to page 1")
            js_script = """
            var links = document.querySelectorAll('a, button');
            for (var i = 0; i < links.length; i++) {
                if (links[i].textContent.trim() === '1') {
                    console.log('Found page 1 element:', links[i]);
                    links[i].click();
                    return true;
                }
            }
            return false;
            """
            
            result = self.driver.execute_script(js_script)
            if result:
                time.sleep(3)
                new_url = self.driver.current_url
                logger.info(f"✅ Successfully navigated to page 1. New URL: {new_url}")
                return True
            else:
                logger.error("❌ JavaScript could not find page 1 element")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error navigating to first page: {str(e)}")
            return False
    
    def _navigate_to_last_page(self) -> Optional[int]:
        """Navigate to the last page by finding the highest page number (optimized)"""
        try:
            logger.info("🔍 Finding and navigating to last page using JavaScript")
            
            # Use JavaScript to find the highest page number and click it
            js_script = """
            var pageNumbers = [];
            var links = document.querySelectorAll('a, button');
            
            // Find all numeric page links
            for (var i = 0; i < links.length; i++) {
                var text = links[i].textContent.trim();
                if (/^\\d+$/.test(text)) {  // Check if text is purely numeric
                    pageNumbers.push({
                        number: parseInt(text),
                        element: links[i]
                    });
                }
            }
            
            if (pageNumbers.length === 0) {
                return null;  // No pagination found
            }
            
            // Find the highest page number
            var maxPage = Math.max(...pageNumbers.map(p => p.number));
            var lastPageElement = pageNumbers.find(p => p.number === maxPage);
            
            if (lastPageElement) {
                console.log('Found last page:', maxPage);
                lastPageElement.element.click();
                return maxPage;
            }
            
            return null;
            """
            
            result = self.driver.execute_script(js_script)
            if result:
                time.sleep(3)
                logger.info(f"✅ Successfully navigated to last page: {result}")
                return result
            else:
                logger.info("📄 No pagination found or only one page")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error navigating to last page: {str(e)}")
            return None

    def _navigate_to_page_number(self, page_number: int) -> bool:
        """Navigate to a specific page number using JavaScript"""
        try:
            logger.info(f"🎯 Navigating to page {page_number}")
            
            js_script = f"""
            var links = document.querySelectorAll('a, button');
            for (var i = 0; i < links.length; i++) {{
                if (links[i].textContent.trim() === '{page_number}') {{
                    links[i].click();
                    return true;
                }}
            }}
            return false;
            """
            
            result = self.driver.execute_script(js_script)
            if result:
                time.sleep(3)
                logger.info(f"✅ Successfully navigated to page {page_number}")
                return True
            else:
                logger.error(f"❌ Could not navigate to page {page_number}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error navigating to page {page_number}: {str(e)}")
            return False
        
    def _navigate_to_previous_page(self) -> bool:
        """Navigate to previous page using JavaScript (optimized)"""
        try:
            logger.info("🔍 Looking for Previous page button using JavaScript")
            
            # Use JavaScript to find and click previous page button
            js_script = """
            // Look for previous page indicators
            var elements = document.querySelectorAll('a, button');
            
            for (var i = 0; i < elements.length; i++) {
                var element = elements[i];
                var text = element.textContent.trim();
                var ariaLabel = element.getAttribute('aria-label') || '';
                var classes = element.className || '';
                
                // Check for previous page indicators
                if (text === '◁' || text === '‹' || text === '<' || 
                    ariaLabel.toLowerCase().includes('previous') ||
                    classes.toLowerCase().includes('prev')) {
                    
                    // Make sure it's not disabled
                    if (!classes.toLowerCase().includes('disabled') && 
                        element.getAttribute('aria-current') !== 'true') {
                        console.log('Found previous button:', element);
                        element.click();
                        return true;
                    }
                }
            }
            return false;
            """
            
            result = self.driver.execute_script(js_script)
            if result:
                time.sleep(2)
                logger.info("✅ Successfully navigated to previous page")
                return True
            else:
                logger.info("📄 No previous page available (reached first page)")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error navigating to previous page: {str(e)}")
            return False

    def _navigate_to_next_page(self) -> bool:
        """Navigate to next page using HTML-based approach"""
        try:
            logger.info("🔍 Looking for Next page button")
            
            # Common next page selectors
            next_selectors = [
                "a[aria-label='Next page']",
                "a[title*='Next']",
                "button[aria-label='Next page']",
                ".pagination a:contains('Next')",
                ".pagination .next",
                "a.next",
                ".pagination a[rel='next']"
            ]
            
            # Also look for the arrow symbol
            arrow_selectors = [
                "a:contains('▷')",
                "a:contains('›')", 
                "a:contains('>')",
                "button:contains('▷')",
                "button:contains('›')",
                "button:contains('>')"
            ]
            
            all_selectors = next_selectors + arrow_selectors
            
            for selector in all_selectors:
                try:
                    # Handle CSS selectors with :contains() (not standard CSS)
                    if ':contains(' in selector:
                        # Convert to XPath
                        text = selector.split("':contains('")[1].split("')")[0]
                        tag = selector.split(':contains(')[0]
                        xpath = f"//{tag}[contains(text(), '{text}')]"
                        
                        from selenium.webdriver.common.by import By
                        from selenium.webdriver.support.ui import WebDriverWait
                        from selenium.webdriver.support import expected_conditions as EC
                        
                        element = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                    else:
                        element = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    
                    if element and element.is_displayed() and element.is_enabled():
                        # Check if it's not disabled
                        classes = element.get_attribute('class') or ''
                        if 'disabled' not in classes.lower():
                            logger.info(f"✅ Found Next button with selector: {selector}")
                            element.click()
                            time.sleep(2)
                            return True
                            
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {str(e)}")
                    continue
            
            logger.info("📄 No more pages found")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error navigating to next page: {str(e)}")
            return False
    
    def analyze_screenshot_with_llm(self, screenshot_data: Dict[str, Any]):
        """Wrapper method for LLM analysis"""
        page_text = self.screenshot_manager.get_page_text_content()
        return self.llm_analyzer.analyze_page(screenshot_data, page_text)
    
    def take_screenshot(self, label: str = "screenshot"):
        """Wrapper for screenshot functionality"""
        return self.screenshot_manager.take_screenshot(label)
    
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
            screenshot = self.screenshot_manager.take_screenshot("initial_portal_view")
            
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
                error_screenshot = self.screenshot_manager.take_screenshot("navigation_error")
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
                login_result = self.login_handler.attempt_login(credentials)
                session_results['login'] = login_result
                
                if login_result['success']:
                    logger.info("✅ Login successful!")
                    self.is_logged_in = True  # Track login status
                    
                    # Take final screenshot
                    final_screenshot = self.screenshot_manager.take_screenshot("final_logged_in_state")
                    final_analysis = self.analyze_screenshot_with_llm(final_screenshot)
                    
                    session_results['final_state'] = {
                        'screenshot': final_screenshot,
                        'analysis': final_analysis
                    }
                    
                    logger.info(f"Final state: {final_analysis.page_type}")
                    logger.info(f"Available actions: {final_analysis.next_steps}")
                    
                    # Initialize request workflow after successful login
                    try:
                        self.setup_request_workflow()
                        logger.info("✅ Request functionality ready!")
                    except Exception as e:
                        logger.warning(f"⚠️  Request functionality not available: {str(e)}")
                    
                else:
                    logger.error(f"❌ Login failed: {login_result.get('error', 'Unknown error')}")
                    self.is_logged_in = False
            
            else:
                logger.info("ℹ️  No login credentials provided - analyzing portal without authentication")
                session_results['login'] = {'skipped': True, 'reason': 'No credentials provided'}
                self.is_logged_in = False
            
            # Save results
            SessionManager.save_session_results(
                session_results, 
                self.screenshot_manager.screenshots, 
                portal_url
            )
            
            return session_results
            
        except Exception as e:
            logger.error(f"Portal access session failed: {str(e)}")
            session_results['session_error'] = str(e)
            SessionManager.save_session_results(
                session_results, 
                self.screenshot_manager.screenshots, 
                portal_url
            )
            return session_results
    
    def submit_public_records_request(self, user_topic: str, user_info: Dict[str, str]) -> Dict[str, Any]:
        """Submit a public records request based on user topic"""
        
        if not self.is_logged_in:
            return {
                'success': False,
                'error': 'Must be logged in to submit requests',
                'user_topic': user_topic
            }
        
        if not self.request_workflow:
            try:
                self.setup_request_workflow()
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Request functionality not available: {str(e)}',
                    'user_topic': user_topic
                }
        
        logger.info(f"=== SUBMITTING PUBLIC RECORDS REQUEST FOR: '{user_topic}' ===")
        
        try:
            result = self.request_workflow.execute_request_workflow(user_topic, user_info)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to submit request: {str(e)}")
            return {
                'success': False,
                'error': f'Request submission failed: {str(e)}',
                'user_topic': user_topic
            }

    def analyze_specific_requests(self) -> Dict[str, Any]:
        """
        PHASE 3 INTERACTIVE: Let user choose specific requests to analyze
        """
        try:
            logger.info("🎯 PHASE 3 INTERACTIVE: Starting specific request analysis")
            
            if not self.is_logged_in:
                return {
                    'success': False,
                    'error': 'Must be logged in to analyze requests'
                }
            
            # Use the persistent RequestAnalyzer instance with database integration
            if not self.request_analyzer:
                return {
                    'success': False,
                    'error': 'Request analyzer not initialized'
                }
            
            # Run interactive workflow
            result = self.request_analyzer.interactive_analysis_workflow()
            
            # Navigate back to home
            self.request_analyzer.navigate_back_to_home()
            
            return result
            
        except Exception as e:
            logger.error(f"Interactive analysis failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
        
    def analyze_all_requests(self) -> Dict[str, Any]:
        """
        Analyze ALL requests across all pages to populate database completely
        Starting from the last page and working backwards (newest first)
        """
        try:
            logger.info("🔄 Starting bulk analysis of ALL requests (newest first)")
            
            if not self.is_logged_in:
                return {
                    'success': False,
                    'error': 'Must be logged in to analyze requests'
                }
            
            if not self.request_analyzer:
                return {
                    'success': False,
                    'error': 'Request analyzer not initialized'
                }
            
            # Navigate to All requests page first
            nav_result = self.request_analyzer.navigate_to_all_requests()
            if not nav_result['success']:
                return {
                    'success': False,
                    'error': f"Could not navigate to all requests page: {nav_result['error']}"
                }

            # Set up filters to show only user's requests
            logger.info("🔍 Setting up filters to show only your requests")
            from request_filter_manager import RequestFilterManager
            filter_manager = RequestFilterManager(
                driver=self.driver,
                llm_client=self.llm_client,
                screenshot_manager=self.take_screenshot
            )

            # Apply requester filter (skip the interactive status choice for bulk analysis)
            if not filter_manager._apply_requester_filter_only():
                logger.warning("⚠️ Could not apply requester filter, continuing with all requests")
            else:
                logger.info("✅ Filters applied - now showing only your requests")
            
            time.sleep(3)  # Wait for filter to apply
            
            # PAGINATION TEST: Test navigation before processing
            logger.info("🧪 TESTING PAGINATION: Navigating through all pages to verify navigation works")
            
            # Test 1: Go to last page
            logger.info("🧪 Test 1: Navigating to last page...")
            last_page = self._navigate_to_last_page()
            if not last_page:
                logger.warning("⚠️ Could not determine last page during test")
                last_page = 1
            else:
                logger.info(f"✅ Test 1 passed: Successfully reached last page {last_page}")
            
            # Test 2: Go back to first page
            logger.info("🧪 Test 2: Navigating back to first page...")
            first_page_success = self._navigate_to_first_page()
            if not first_page_success:
                logger.error("❌ Test 2 failed: Could not navigate back to first page")
                return {
                    'success': False,
                    'error': 'Pagination test failed: Cannot navigate to first page'
                }
            else:
                logger.info("✅ Test 2 passed: Successfully reached first page")
            
            # Test 3: Go back to last page again
            if last_page > 1:
                logger.info("🧪 Test 3: Navigating to last page again...")
                final_last_page = self._navigate_to_last_page()
                if not final_last_page:
                    logger.error("❌ Test 3 failed: Could not navigate to last page again")
                    return {
                        'success': False,
                        'error': 'Pagination test failed: Cannot navigate to last page consistently'
                    }
                else:
                    logger.info(f"✅ Test 3 passed: Successfully reached last page {final_last_page} again")
            
            logger.info("🎉 PAGINATION TEST COMPLETE: All navigation tests passed!")
            
            # Initialize tracking variables
            total_requests = 0
            successful_analyses = 0
            skipped_existing = 0
            failed_analyses = 0
            pages_processed = 0
            
            # Start from last page (we're already there from the test)
            current_page = last_page
            logger.info(f"📄 Starting processing from last page: {current_page}")

            has_more_pages = True
            
            while has_more_pages:
                try:
                    logger.info(f"📄 Processing page {current_page} (working backwards)")
                    pages_processed += 1
                    
                    # Extract requests from current page
                    extraction_result = self.request_analyzer.extract_requests_with_llm()
                    
                    if not extraction_result.extraction_successful:
                        logger.error(f"Failed to extract requests from page {current_page}")
                        break
                    
                    page_requests = extraction_result.clickable_requests
                    total_requests += len(page_requests)
                    
                    logger.info(f"📊 Found {len(page_requests)} requests on page {current_page}")
                    
                    # Analyze each request on this page
                    for i, request in enumerate(page_requests):
                        request_number = request.request_number
                        
                        try:
                            # Check if already in database
                            if self._is_request_in_database(request_number):
                                logger.info(f"⏭️  Skipping {request_number} (already in database)")
                                skipped_existing += 1
                                continue
                            
                            # Progress update
                            progress = (successful_analyses + skipped_existing + failed_analyses + 1)
                            logger.info(f"🔍 Analyzing request {progress}: {request_number} (page {current_page})")
                            
                            # Click on request
                            click_result = self.request_analyzer.click_request_with_llm(request_number)
                            
                            if not click_result['success']:
                                logger.error(f"❌ Failed to click request {request_number}: {click_result['error']}")
                                failed_analyses += 1
                                continue
                            
                            # Analyze request detail
                            analysis_result = self.request_analyzer.analyze_request_detail_with_llm(request_number)
                            
                            if analysis_result['success']:
                                if analysis_result.get('saved_to_db', False):
                                    successful_analyses += 1
                                    logger.info(f"✅ Successfully analyzed and saved {request_number}")
                                else:
                                    failed_analyses += 1
                                    logger.error(f"❌ Analysis succeeded but database save failed for {request_number}")
                            else:
                                failed_analyses += 1
                                logger.error(f"❌ Analysis failed for {request_number}: {analysis_result['error']}")
                            
                            # Navigate back to requests list
                            self.driver.back()
                            time.sleep(2)  # Wait for page load
                            
                            # Rate limiting
                            time.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"❌ Unexpected error analyzing {request_number}: {str(e)}")
                            failed_analyses += 1
                            
                            # Try to get back to requests list
                            try:
                                self.driver.back()
                                time.sleep(2)
                            except:
                                # If back doesn't work, re-navigate to all requests and re-apply filters
                                self.request_analyzer.navigate_to_all_requests()
                                if filter_manager._apply_requester_filter_only():
                                    # Navigate back to the current page using optimized method
                                    self._navigate_to_page_number(current_page)
                                time.sleep(3)
                            continue
                    
                    # Check for previous page (going backwards)
                    has_more_pages = self._navigate_to_previous_page()
                    if has_more_pages:
                        current_page -= 1
                        time.sleep(3)  # Wait for page load
                    else:
                        logger.info("📄 Reached first page - bulk analysis complete")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing page {current_page}: {str(e)}")
                    break
            
            # Save resume information
            resume_info = {
                'last_page_processed': pages_processed,
                'timestamp': datetime.datetime.now().isoformat(),
                'total_found': total_requests,
                'completed': successful_analyses + skipped_existing,
                'direction': 'backwards',
                'final_page': current_page,
                'pagination_test_passed': True
            }
            
            
            logger.info(f"🎉 Bulk analysis completed!")
            logger.info(f"📊 Pages processed: {pages_processed}")
            logger.info(f"📊 Total requests: {total_requests}")
            logger.info(f"📊 Successfully analyzed: {successful_analyses}")
            logger.info(f"📊 Skipped (existing): {skipped_existing}")
            logger.info(f"📊 Failed: {failed_analyses}")
            
            return {
                'success': True,
                'total_requests': total_requests,
                'successful_analyses': successful_analyses,
                'skipped_existing': skipped_existing,
                'failed_analyses': failed_analyses,
                'pages_processed': pages_processed,
                'resume_info': resume_info
            }
            
        except Exception as e:
            logger.error(f"❌ Bulk analysis failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'partial_results': f"Processed {pages_processed} pages before failure"
            }
    def get_portal_status(self) -> Dict[str, Any]:
        """Get current portal status and capabilities"""
        return {
            'is_logged_in': self.is_logged_in,
            'current_url': self.driver.current_url if self.driver else None,
            'request_functionality_available': self.request_workflow is not None,
            'total_screenshots': len(self.screenshot_manager.screenshots) if self.screenshot_manager else 0
        }
    

    # ============================================================================
    # MONITORING AGENT
    # ============================================================================
    
    def initialize_monitoring_agent(self, check_interval_minutes: int = 60, current_portal_url: str = None) -> bool:
        """
        Initialize the monitoring agent for automated change detection.
        """
        try:
            if not self.is_logged_in:
                logger.error("Cannot initialize monitoring - not logged in")
                return False
            
            if not self.request_analyzer or not self.request_analyzer.db:
                logger.error("Cannot initialize monitoring - database not available")
                return False
            
            # Get current portal URL if not provided
            if not current_portal_url:
                current_portal_url = self.driver.current_url
            
            self.monitoring_agent = MonitoringAgent(
                portal_agent=self,
                db=self.request_analyzer.db,
                check_interval_minutes=check_interval_minutes,
                current_portal_url=current_portal_url  # NEW: Pass the current portal URL
            )
            
            logger.info(f"✅ Monitoring agent initialized (check interval: {check_interval_minutes} minutes, portal: {current_portal_url})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize monitoring agent: {str(e)}")
            return False


    def run_manual_monitoring_cycle(self, current_portal_url: str = None) -> Dict[str, Any]:
        """
        Run a single monitoring cycle manually (for testing).
        """
        try:
            if not hasattr(self, 'monitoring_agent') or not self.monitoring_agent:
                # Get current portal URL if not provided
                if not current_portal_url:
                    current_portal_url = self.driver.current_url
                
                success = self.initialize_monitoring_agent(current_portal_url=current_portal_url)
                if not success:
                    return {'success': False, 'error': 'Failed to initialize monitoring agent'}
            
            user_id = self.request_analyzer.user_id
            if not user_id:
                return {'success': False, 'error': 'User ID not available'}
            
            logger.info("🔄 Running manual monitoring cycle...")
            result = self.monitoring_agent.run_single_monitoring_cycle(user_id)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Manual monitoring cycle failed: {str(e)}")
            return {'success': False, 'error': str(e)}

    def start_monitoring(self, check_interval_minutes: int = 60) -> Dict[str, Any]:
        """
        Start automated monitoring of open requests.
        """
        try:
            if not hasattr(self, 'monitoring_agent') or not self.monitoring_agent:
                success = self.initialize_monitoring_agent(check_interval_minutes)
                if not success:
                    return {'success': False, 'error': 'Failed to initialize monitoring agent'}
            
            user_id = self.request_analyzer.user_id
            if not user_id:
                return {'success': False, 'error': 'User ID not available'}
            
            success = self.monitoring_agent.start_monitoring(user_id)
            
            if success:
                return {
                    'success': True,
                    'message': f'Monitoring started (checking every {check_interval_minutes} minutes)',
                    'check_interval_minutes': check_interval_minutes,
                    'user_id': user_id
                }
            else:
                return {'success': False, 'error': 'Failed to start monitoring'}
                
        except Exception as e:
            logger.error(f"❌ Failed to start monitoring: {str(e)}")
            return {'success': False, 'error': str(e)}

    def stop_monitoring(self) -> Dict[str, Any]:
        """
        Stop automated monitoring.
        """
        try:
            if hasattr(self, 'monitoring_agent') and self.monitoring_agent:
                self.monitoring_agent.stop_monitoring()
                return {'success': True, 'message': 'Monitoring stopped'}
            else:
                return {'success': False, 'error': 'No monitoring agent running'}
                
        except Exception as e:
            logger.error(f"❌ Failed to stop monitoring: {str(e)}")
            return {'success': False, 'error': str(e)}


    def get_monitoring_status(self) -> Dict[str, Any]:
        """
        Get monitoring agent status and statistics.
        """
        try:
            if hasattr(self, 'monitoring_agent') and self.monitoring_agent:
                agent_status = self.monitoring_agent.get_monitoring_status()
                
                # Add database statistics
                if self.request_analyzer and self.request_analyzer.db:
                    db_stats = self.request_analyzer.db.get_monitoring_statistics(
                        self.request_analyzer.user_id, days_back=1
                    )
                    agent_status['database_stats'] = db_stats
                
                return agent_status
            else:
                return {'is_running': False, 'message': 'No monitoring agent initialized'}
                
        except Exception as e:
            logger.error(f"❌ Failed to get monitoring status: {str(e)}")
            return {'error': str(e)}
        
    # ============================================================================
    # MESSAGE COORDINATOR FOR MONITOR AGENT 
    # ============================================================================
        
    def review_and_send_messages(self) -> Dict[str, Any]:
        """Entry point for message drafting workflow"""
        coordinator = MessageCoordinator(self)
        return coordinator.process_all_flagged_requests()
    
    # ============================================================================
    # MONITOR SUPABASE FOR PRRS THAT NEED TO BE SUBMITTED
    # ============================================================================

    def process_submission_queue(self, test_user_id: str = None, max_requests: int = 10) -> Dict[str, Any]:
        """
        Process pending requests from the Supabase submission queue.
        Fetches requests, navigates to portals, logs in, and submits forms.
        """
        
        # Import Supabase integration
        try:
            from supabase_integration import SupabaseIntegration
        except ImportError:
            return {
                'success': False,
                'error': 'SupabaseIntegration not available',
                'processed': 0
            }
        
        # Initialize results tracking
        results = {
            'success': False,
            'total_fetched': 0,
            'processed': 0,
            'successful_submissions': 0,
            'failed_submissions': 0,
            'errors': [],
            'processing_details': []
        }
        
        try:
            # Initialize database connection
            logger.info("🔄 Initializing Supabase connection for queue processing")
            db = SupabaseIntegration()
            
            # Fetch pending requests from queue
            logger.info("📥 Fetching pending requests from submission queue")
            pending_requests = self._fetch_pending_requests(db, test_user_id, max_requests)
            
            if not pending_requests:
                logger.info("📭 No pending requests found in queue")
                results['success'] = True
                results['message'] = 'No pending requests to process'
                return results
            
            results['total_fetched'] = len(pending_requests)
            logger.info(f"📊 Found {len(pending_requests)} pending requests to process")
            
            # Process each request
            for i, request_data in enumerate(pending_requests, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"🔄 PROCESSING REQUEST {i}/{len(pending_requests)}")
                logger.info(f"Request ID: {request_data['id']}")
                logger.info(f"Agency: {request_data['agency_name']}")
                logger.info(f"Topic: {request_data.get('request_topic', 'N/A')}")
                logger.info(f"{'='*60}")
                
                # Update status to 'processing'
                self._update_request_status(db, request_data['id'], 'processing', 'Started processing request')
                
                # Process individual request
                processing_result = self._process_single_request(db, request_data)
                
                results['processing_details'].append({
                    'request_id': request_data['id'],
                    'agency_name': request_data['agency_name'],
                    'result': processing_result
                })
                
                if processing_result['success']:
                    results['successful_submissions'] += 1
                    logger.info(f"✅ Successfully processed request {request_data['id']}")
                else:
                    results['failed_submissions'] += 1
                    logger.error(f"❌ Failed to process request {request_data['id']}: {processing_result['error']}")
                    results['errors'].append(f"Request {request_data['id']}: {processing_result['error']}")
                
                results['processed'] += 1
                
                # Add delay between requests to avoid overwhelming portals
                if i < len(pending_requests):
                    logger.info("⏰ Waiting 10 seconds before next request...")
                    time.sleep(10)
            
            # Calculate final results
            results['success'] = results['processed'] > 0
            success_rate = (results['successful_submissions'] / results['processed'] * 100) if results['processed'] > 0 else 0
            
            logger.info(f"\n🎉 QUEUE PROCESSING COMPLETE!")
            logger.info(f"📊 Total processed: {results['processed']}")
            logger.info(f"✅ Successful: {results['successful_submissions']}")
            logger.info(f"❌ Failed: {results['failed_submissions']}")
            logger.info(f"📈 Success rate: {success_rate:.1f}%")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Queue processing failed: {str(e)}")
            results['error'] = f"Queue processing failed: {str(e)}"
            return results

    def _fetch_pending_requests_fallback(self, db: 'SupabaseIntegration', test_user_id: str = None, max_requests: int = 10) -> List[Dict[str, Any]]:
        """Fallback method using individual queries - UPDATED to include contact info"""
        try:
            # Get pending submissions
            query = db.supabase.table('submission_queue').select('*').eq('status', 'pending')
            
            if test_user_id:
                query = query.eq('user_id', test_user_id)
            
            result = query.order('priority').order('created_at').limit(max_requests).execute()
            
            if not result.data:
                return []
            
            # Enrich with portal and credential data
            enriched_requests = []
            
            for request in result.data:
                try:
                    # Get portal info
                    portal_result = db.supabase.table('portals').select('*').eq('id', request['portal_id']).single().execute()
                    
                    if not portal_result.data:
                        logger.warning(f"Portal not found for request {request['id']}")
                        continue
                    
                    # Get credentials WITH CONTACT INFORMATION
                    cred_result = db.supabase.table('user_portal_credentials').select('''
                        *,
                        requester_name,
                        requester_email,
                        requester_phone,
                        requester_organization,
                        street_address,
                        city,
                        state,
                        zip_code,
                        preferred_department
                    ''').eq('user_id', request['user_id']).eq('portal_id', request['portal_id']).eq('is_active', True).single().execute()
                    
                    if not cred_result.data:
                        logger.warning(f"No credentials found for request {request['id']}")
                        continue
                    
                    # Combine data with full contact information
                    enriched_request = {
                        **request,
                        'agency_name': portal_result.data['agency_name'],
                        'portal_url': portal_result.data['portal_url'],
                        'portal_type': portal_result.data['portal_type'],
                        'encrypted_username': cred_result.data['encrypted_username'],
                        'encrypted_password': cred_result.data['encrypted_password'],
                        # Add contact information from credentials
                        'contact_info': {
                            'requester_name': cred_result.data.get('requester_name'),
                            'requester_email': cred_result.data.get('requester_email'),
                            'requester_phone': cred_result.data.get('requester_phone'),
                            'requester_organization': cred_result.data.get('requester_organization'),
                            'street_address': cred_result.data.get('street_address'),
                            'city': cred_result.data.get('city'),
                            'state': cred_result.data.get('state'),
                            'zip_code': cred_result.data.get('zip_code'),
                            'preferred_department': cred_result.data.get('preferred_department')
                        }
                    }
                    
                    enriched_requests.append(enriched_request)
                    
                except Exception as e:
                    logger.error(f"Failed to enrich request {request['id']}: {str(e)}")
                    continue
            
            logger.info(f"📊 Successfully enriched {len(enriched_requests)} requests with contact info")
            return enriched_requests
            
        except Exception as e:
            logger.error(f"❌ Fallback fetch failed: {str(e)}")
            return []


    def _update_request_status(self, db: 'SupabaseIntegration', request_id: str, status: str,
                            message: str, submission_result: Dict[str, Any] = None,
                            queued_for_analysis: bool = None):
        """Update request status in the database"""
        try:
            update_data = {
                'status': status,
                'updated_at': datetime.datetime.now().isoformat()
            }

            # Add processing timestamps
            if status == 'processing':
                update_data['started_processing_at'] = datetime.datetime.now().isoformat()
            elif status in ['completed', 'failed']:
                update_data['completed_at'] = datetime.datetime.now().isoformat()

            # Add results if provided
            if submission_result:
                update_data['submission_result'] = submission_result

            # Add error details for failed requests
            if status == 'failed':
                update_data['error_details'] = message

            # Add queued_for_analysis flag if provided
            if queued_for_analysis is not None:
                update_data['queued_for_analysis'] = queued_for_analysis

            # Mark as tracked submission (for new tracking feature)
            # This ensures the submission appears in the new status tracking UI
            if status == 'processing':
                update_data['tracked_submission'] = True

            # Update the record
            db.supabase.table('submission_queue').update(update_data).eq('id', request_id).execute()

            logger.info(f"📊 Updated request {request_id} status to: {status}")
            if queued_for_analysis is not None:
                logger.info(f"   queued_for_analysis: {queued_for_analysis}")

        except Exception as e:
            logger.error(f"❌ Failed to update request status: {str(e)}")

    def _fetch_pending_requests(self, db: 'SupabaseIntegration', test_user_id: str = None, max_requests: int = 10) -> List[Dict[str, Any]]:
        """Fetch pending requests with portal and credential information"""
        try:
            # For now, let's use the fallback method since it's more reliable
            # The complex JOIN query with RPC might not be necessary
            return self._fetch_pending_requests_fallback(db, test_user_id, max_requests)
                
        except Exception as e:
            logger.error(f"❌ Failed to fetch pending requests: {str(e)}")
            return self._fetch_pending_requests_fallback(db, test_user_id, max_requests)

    
    def _process_single_request(self, db: 'SupabaseIntegration', request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single request from queue to portal submission with post-submission analysis.
        
        SMART CREDENTIALS FLOW:
        - Tries to login with stored credentials
        - If login succeeds: authenticated submission
        - If login fails: continues to form anyway (portal will create account during submission)
        """
        
        request_id = request_data['id']
        portal_url = request_data['portal_url']
        
        processing_result = {
            'success': False,
            'request_id': request_id,
            'steps_completed': [],
            'errors': [],
            'submitted_request_number': None,
            'saved_to_monitoring': False,
            'account_created': False  # Track if new account was created
        }
        
        try:
            # Step 1: Navigate to portal
            logger.info(f"🌐 Navigating to portal: {portal_url}")
            
            navigation_result = self.navigate_to_portal(portal_url)
            
            if not navigation_result['success']:
                error_msg = f"Navigation failed: {navigation_result.get('error', 'Unknown error')}"
                processing_result['errors'].append(error_msg)
                self._update_request_status(db, request_id, 'failed', error_msg)
                return processing_result
            
            processing_result['steps_completed'].append('portal_navigation')
            
            # Step 2: Try to login with stored credentials (SMART FLOW)
            logger.info("🔐 Attempting login with stored credentials")
            
            # TODO: In production, decrypt the credentials here
            credentials = LoginCredentials(
                username=request_data['encrypted_username'],
                password=request_data['encrypted_password']
            )
            
            login_result = self.login_handler.attempt_login(credentials)
            
            if login_result['success']:
                # Existing account - authenticated submission
                processing_result['steps_completed'].append('portal_login')
                self.is_logged_in = True
                logger.info("✅ Login successful - proceeding with authenticated flow")
            else:
                # Account doesn't exist - will create during submission
                logger.warning(f"⚠️ Login failed: {login_result.get('error')}")
                logger.info("📝 Navigating back to homepage for account creation flow")
                processing_result['account_created'] = True  # Flag for new account
                self.is_logged_in = False
                
                # Navigate back to portal homepage
                logger.info(f"🏠 Navigating back to portal homepage: {portal_url}")
                self.driver.get(portal_url)
                time.sleep(3)  # Wait for page load
                logger.info("✅ Back on homepage - ready to find 'Make Request' button")
            
            # Step 3: Navigate to request form
            logger.info("📝 Navigating to request form")
            
            # Initialize form submitter if not already done
            if not hasattr(self, 'form_submitter') or not self.form_submitter:
                from form_submitter import FormSubmitter
                self.form_submitter = FormSubmitter(
                    self.driver,
                    self.screenshot_manager.take_screenshot,
                    self.llm_client
                )
            
            if not self.form_submitter.navigate_to_request_form():
                error_msg = "Failed to navigate to request form"
                processing_result['errors'].append(error_msg)
                self._update_request_status(db, request_id, 'failed', error_msg)
                return processing_result
            
            processing_result['steps_completed'].append('form_navigation')
            
            # Step 4: Fill and submit form with ENHANCED CONTACT INFO + CREDENTIALS
            logger.info("📋 Filling and submitting request form with enhanced contact information")
            
            # Use contact info from portal credentials (much more complete)
            contact_info = request_data.get('contact_info', {})
            
            # Create enhanced user info with all required fields
            user_info = {
                # Basic info
                'full_name': contact_info.get('requester_name', ''),
                'email': contact_info.get('requester_email', ''),
                'phone': contact_info.get('requester_phone', ''),
                'organization': contact_info.get('requester_organization', ''),
                
                # Address info
                'street_address': contact_info.get('street_address', ''),
                'city': contact_info.get('city', ''),
                'state': contact_info.get('state', ''),
                'zip_code': contact_info.get('zip_code', ''),
                
                # Department preference
                'preferred_department': contact_info.get('preferred_department', ''),
                
                # Credentials (for account creation if needed)
                'username': request_data.get('encrypted_username', ''),
                'password': request_data.get('encrypted_password', ''),
                
                # Legacy fields for backward compatibility
                'first_name': contact_info.get('requester_name', '').split(' ')[0] if contact_info.get('requester_name') else '',
                'last_name': ' '.join(contact_info.get('requester_name', '').split(' ')[1:]) if contact_info.get('requester_name') else '',
                'address': contact_info.get('street_address', ''),
                'zip': contact_info.get('zip_code', '')
            }
            
            logger.info(f"📋 Using contact info: {user_info.get('full_name')} from {user_info.get('city')}, {user_info.get('state')}")
            logger.info(f"📋 Preferred department: {user_info.get('preferred_department', 'Not specified')}")
            
            if processing_result['account_created']:
                logger.info(f"📋 Including credentials for account creation: {user_info.get('username')}")
            
            # Submit the form with pre-written request text and enhanced contact info
            submission_result = self.form_submitter.fill_and_submit_form(
                request_data['request_text'],
                user_info
            )
            
            if not submission_result['success']:
                error_msg = f"Form submission failed: {'; '.join(submission_result.get('errors', []))}"
                processing_result['errors'].append(error_msg)
                self._update_request_status(db, request_id, 'failed', error_msg, submission_result)
                processing_result['submission_details'] = submission_result
                return processing_result
            
            processing_result = processing_result or {'steps_completed': [], 'errors': [], 'success': False}
                        
            processing_result['steps_completed'].append('form_submission')
            processing_result['submission_details'] = submission_result
            
            logger.info(f"✅ Request {request_id} submitted successfully!")
            if processing_result['account_created']:
                logger.info(f"✅ New account will be created on account setup page")
            
            # Step 4.5: CREATE PORTAL ACCOUNT (if new account)
            if processing_result['account_created']:
                logger.info("🔐 STEP 4.5: Creating portal account with password")
                
                try:
                    # We're now on the account setup page - create the account
                    current_url = self.driver.current_url
                    logger.info(f"📍 Account setup page URL: {current_url}")
                    
                    account_creation_result = self.form_submitter.create_portal_account(
                        email=user_info.get('email'),
                        password=user_info.get('password')
                    )
                    
                    if account_creation_result['success']:
                        processing_result['steps_completed'].append('portal_account_created')
                        logger.info("✅ Portal account created successfully!")
                        logger.info("📧 Account is pending email confirmation")
                        
                        # Add portal to bulk analysis queue for future request extraction
                        logger.info("📋 Adding portal to bulk analysis queue")
                        logger.info("   This will extract the newly submitted request after email confirmation")
                        
                        # Use new db method with portal_id
                        portal_name = request_data.get('agency_name', 'Unknown Portal')
                        queue_result = db.add_portal_to_bulk_analysis_queue(
                            user_id=request_data['user_id'],
                            portal_id=request_data['portal_id'],
                            portal_name=portal_name,
                            submission_queue_id=request_id  # Link back to original submission
                        )

                        if queue_result:
                            processing_result['steps_completed'].append('added_to_bulk_analysis_queue')
                            logger.info("✅ Portal added to bulk analysis queue")
                            logger.info("   The bulk analysis worker will extract the request after email confirmation")
                        else:
                            logger.warning("⚠️ Failed to add portal to bulk analysis queue")
                            logger.warning("   The request will need to be manually analyzed or re-queued")
                            processing_result['errors'].append("Failed to add portal to bulk analysis queue")
                        
                        # CRITICAL: Mark as success and SKIP Step 5
                        # We're on /pending page, not /requests/xxx page
                        # The request will be extracted by bulk analysis after email confirmation
                        processing_result['success'] = True
                        
                        logger.info("✅ Account creation flow complete")
                        logger.info("⏭️  Skipping Step 5 (post-submission analysis)")
                        logger.info("   Reason: Request is pending email confirmation")
                        logger.info("   The bulk analysis worker will handle request extraction")
                        
                        # Update database with completion status
                        self._update_request_status(
                            db,
                            request_id,
                            'completed' if queue_result else 'partial_failure',
                            'Request submitted and account created - pending email confirmation' if queue_result else 'Form submitted but failed to queue for analysis',
                            processing_result,
                            queued_for_analysis=bool(queue_result)
                        )
                        
                        # RETURN HERE - Skip Step 5
                        return processing_result
                        
                    else:
                        error_msg = f"Account creation failed: {'; '.join(account_creation_result.get('errors', []))}"
                        logger.warning(f"⚠️ {error_msg}")
                        processing_result['errors'].append(error_msg)

                        # FALLBACK: Try Claude SDK account creation
                        logger.info("=" * 80)
                        logger.info("🤖 ATTEMPTING CLAUDE SDK ACCOUNT CREATION FALLBACK")
                        logger.info("=" * 80)
                        logger.info("Deterministic account creation failed - trying AI-powered approach")

                        try:
                            from claude_account_creator import ClaudeAccountCreator

                            claude_creator = ClaudeAccountCreator(
                                driver=self.driver,
                                screenshot_func=self.take_screenshot
                            )

                            claude_result = claude_creator.create_account_with_claude({
                                'email': user_info.get('email'),
                                'password': user_info.get('password'),
                                'full_name': user_info.get('full_name', ''),
                                'organization': user_info.get('organization', '')
                            })

                            if claude_result['success']:
                                logger.info("✅ Claude SDK account creation successful!")
                                processing_result['steps_completed'].append('claude_sdk_account_created')

                                # Extract request number from result
                                request_number = claude_result.get('request_number')
                                final_url = claude_result.get('final_url', '')

                                if request_number:
                                    logger.info(f"📋 Request number extracted: {request_number}")
                                    processing_result['submitted_request_number'] = request_number
                                else:
                                    logger.warning(f"⚠️ No request number found in URL: {final_url}")

                                # Save verified credentials to Supabase
                                logger.info("💾 Saving verified credentials to Supabase")
                                credentials_saved = db.save_verified_credentials(
                                    user_id=request_data['user_id'],
                                    portal_id=request_data['portal_id'],
                                    email=user_info.get('email'),
                                    password=user_info.get('password')
                                )

                                if credentials_saved:
                                    logger.info("✅ Credentials saved successfully")
                                    processing_result['steps_completed'].append('credentials_saved')
                                else:
                                    logger.warning("⚠️ Failed to save credentials")
                                    processing_result['errors'].append("Failed to save credentials")

                                # Add to bulk analysis queue (same as current flow)
                                logger.info("📋 Adding portal to bulk analysis queue")
                                portal_name = request_data.get('agency_name', 'Unknown Portal')
                                queue_result = db.add_portal_to_bulk_analysis_queue(
                                    user_id=request_data['user_id'],
                                    portal_id=request_data['portal_id'],
                                    portal_name=portal_name,
                                    submission_queue_id=request_id
                                )

                                if queue_result:
                                    processing_result['steps_completed'].append('added_to_bulk_analysis_queue')
                                    processing_result['saved_to_monitoring'] = True
                                    logger.info("✅ Portal added to bulk analysis queue")
                                    logger.info("   The bulk analysis worker will extract the request after email confirmation")
                                else:
                                    logger.warning("⚠️ Failed to add portal to bulk analysis queue")
                                    processing_result['errors'].append("Failed to add portal to bulk analysis queue")

                                # Mark as success
                                processing_result['success'] = True

                                # Update database
                                self._update_request_status(
                                    db,
                                    request_id,
                                    'completed' if queue_result else 'partial_failure',
                                    f"Account created via Claude SDK (cost: ${claude_result.get('cost_usd', 0):.4f}) - pending email confirmation",
                                    processing_result,
                                    queued_for_analysis=bool(queue_result)
                                )

                                logger.info(f"💰 Claude SDK cost for this account creation: ${claude_result.get('cost_usd', 0):.4f}")
                                logger.info("✅ Claude SDK account creation flow complete")
                                logger.info("⏭️  Skipping Step 5 (post-submission analysis)")
                                logger.info("   Reason: Request is pending email confirmation")
                                logger.info("   The bulk analysis worker will handle request extraction")

                                # RETURN HERE - Skip Step 5
                                return processing_result
                            else:
                                logger.error(f"❌ Claude SDK account creation failed: {claude_result.get('error', 'Unknown error')}")
                                processing_result['errors'].append(f"Claude SDK fallback failed: {claude_result.get('error', 'Unknown error')}")
                                logger.warning("⚠️ Both deterministic and Claude SDK account creation failed")
                                logger.warning("   Continuing to Step 5 to attempt analysis anyway...")

                        except ImportError as import_error:
                            logger.error(f"❌ Claude SDK not available: {str(import_error)}")
                            logger.error("   Install with: pip install claude-agent-sdk")
                            processing_result['errors'].append(f"Claude SDK not installed: {str(import_error)}")
                        except Exception as claude_error:
                            logger.error(f"❌ Claude SDK fallback error: {str(claude_error)}")
                            processing_result['errors'].append(f"Claude SDK fallback error: {str(claude_error)}")
                            logger.warning("   Continuing to Step 5 to attempt analysis anyway...")

                except Exception as e:
                    error_msg = f"Account creation step error: {str(e)}"
                    logger.warning(f"⚠️ {error_msg}")
                    processing_result['errors'].append(error_msg)
                    # Don't fail the whole process - continue
            
            # Step 5: POST-SUBMISSION ANALYSIS - Find and save the newly submitted request
            logger.info("🔍 STEP 5: Finding and analyzing newly submitted request...")
            if not processing_result.get('success'): 
                try:
                    # Initialize RequestAnalyzer with database connection if not already done
                    if not self.request_analyzer:
                        self.request_analyzer = RequestAnalyzer(
                            driver=self.driver,
                            screenshot_func=self.take_screenshot,
                            llm_client=self.llm_client,
                            workflow_state_helper=self.workflow_state_helper
                        )
                    
                    # Ensure database connection is established
                    if not self.request_analyzer.db:
                        self.request_analyzer.db = db

                    # Set submission_queue_id for linking (Path 1: existing account flow)
                    self.request_analyzer.submission_queue_id = request_id
                    logger.info(f"🔗 Set submission_queue_id: {request_id}")

                    # Set user_id from contact info for database operations
                    if not self.request_analyzer.user_id:
                        # Try to get or create user ID from contact info
                        try:
                            user_id = db.save_user(
                                email=contact_info.get('requester_email', ''),
                                full_name=contact_info.get('requester_name', ''),
                                phone=contact_info.get('requester_phone'),
                                organization=contact_info.get('requester_organization')
                            )
                            self.request_analyzer.user_id = user_id
                        except Exception as e:
                            logger.warning(f"⚠️ Could not establish user_id: {str(e)}")
                    
                    # Find the newly submitted request
                    new_request_analysis = self._find_and_analyze_newest_request(
                        db, request_data, processing_result
                    )
                    
                    if new_request_analysis['success']:
                        processing_result['steps_completed'].append('post_submission_analysis')
                        processing_result['submitted_request_number'] = new_request_analysis.get('request_number')
                        processing_result['saved_to_monitoring'] = new_request_analysis.get('saved_to_db', False)
                        
                        # Link the submitted request to the original queue entry
                        self._link_submission_to_request(
                            db, request_id, new_request_analysis.get('request_number'), 
                            new_request_analysis.get('database_request_id')
                        )
                        
                        logger.info(f"✅ Successfully analyzed and saved submitted request: {new_request_analysis.get('request_number')}")
                    else:
                        logger.warning(f"⚠️ Could not analyze submitted request: {new_request_analysis.get('error')}")
                        processing_result['errors'].append(f"Post-submission analysis failed: {new_request_analysis.get('error')}")
                        
                except Exception as e:
                    logger.error(f"❌ Post-submission analysis failed: {str(e)}")
                    processing_result['errors'].append(f"Post-submission analysis error: {str(e)}")
            
            # Update final status
            processing_result['success'] = True

            # Determine if request was queued for analysis (saved to DB)
            queued_for_analysis = processing_result.get('saved_to_monitoring', False)

            # Update database with success
            self._update_request_status(
                db,
                request_id,
                'completed' if queued_for_analysis else 'partial_failure',
                'Request submitted successfully' if queued_for_analysis else 'Form submitted but request not saved to database',
                processing_result,
                queued_for_analysis=queued_for_analysis
            )
            
            return processing_result
            
        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            logger.error(f"❌ Error processing request {request_id}: {error_msg}")
            processing_result['errors'].append(error_msg)
            self._update_request_status(db, request_id, 'failed', error_msg)
            return processing_result
        
        finally:
            # Reset login status for next request
            self.is_logged_in = False

    def _add_portal_to_bulk_analysis_queue(self, db: 'SupabaseIntegration', user_id: str,
                                       portal_id: str, portal_name: str,
                                       priority: str = 'normal', submission_queue_id: str = None) -> bool:
        """
        Add a portal to the bulk analysis queue for comprehensive request extraction.

        This is typically called after:
        - Creating a new account and submitting a request
        - User manually requests a full portal analysis
        - Periodic re-analysis of a portal

        Args:
            db: SupabaseIntegration instance
            user_id: ID of the user
            portal_id: ID of the portal to analyze
            portal_name: Name of portal for logging/display
            priority: Priority level ('high', 'normal', 'low')
            submission_queue_id: Optional ID of submission_queue entry that triggered this (for linking)

        Returns:
            True if successfully added to queue, False otherwise
        """
        try:
            logger.info(f"📋 Adding portal '{portal_name}' to bulk analysis queue")
            logger.info(f"   User ID: {user_id}")
            logger.info(f"   Portal ID: {portal_id}")
            logger.info(f"   Priority: {priority}")
            
            # Check if job already exists for this user/portal combination
            existing_job = db.supabase.table('bulk_analysis_queue').select('id, status').eq(
                'user_id', user_id
            ).eq('portal_id', portal_id).eq('status', 'pending').execute()
            
            if existing_job.data and len(existing_job.data) > 0:
                logger.info(f"⚠️ Bulk analysis job already exists for this portal (ID: {existing_job.data[0]['id']})")
                logger.info(f"   Status: {existing_job.data[0]['status']}")
                logger.info(f"   Skipping duplicate job creation")
                return True  # Not an error - job already queued
            
            # Create new bulk analysis job
            job_data = {
                'user_id': user_id,
                'portal_id': portal_id,
                'job_name': f"Bulk analysis for {portal_name}",
                'analysis_type': 'full_portal_scan',
                'priority': priority,
                'status': 'pending',
                'created_at': datetime.datetime.now().isoformat(),
                'updated_at': datetime.datetime.now().isoformat(),
                'progress_data': {
                    'created_reason': 'account_creation',
                    'initial_status': 'queued'
                }
            }

            # Add submission_queue_id if provided (for linking back after analysis)
            if submission_queue_id:
                job_data['submission_queue_id'] = submission_queue_id
                job_data['progress_data']['triggered_by_submission'] = submission_queue_id
                logger.info(f"   Linked to submission_queue ID: {submission_queue_id}")
            
            result = db.supabase.table('bulk_analysis_queue').insert(job_data).execute()
            
            if result.data and len(result.data) > 0:
                job_id = result.data[0]['id']
                logger.info(f"✅ Successfully added bulk analysis job to queue")
                logger.info(f"   Job ID: {job_id}")
                logger.info(f"   Job will be processed by bulk analysis worker")
                return True
            else:
                logger.error("❌ Failed to add bulk analysis job - no data returned")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to add portal to bulk analysis queue: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _find_and_analyze_newest_request(self, db: 'SupabaseIntegration', request_data: Dict[str, Any], 
                                processing_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find and analyze the newest request after submission.
        SIMPLIFIED: Since successful submissions redirect to the request page, we just analyze the current page.
        """
        
        analysis_result = {
            'success': False,
            'request_number': None,
            'saved_to_db': False,
            'database_request_id': None
        }
        
        try:
            current_url = self.driver.current_url
            logger.info(f"🔍 Current URL after submission: {current_url}")
            
            # Extract request number from current URL
            import re
            request_number_match = re.search(r'/requests/(\d+-\d+)', current_url)
            
            if not request_number_match:
                analysis_result['error'] = f"Could not extract request number from URL: {current_url}"
                logger.error(f"❌ {analysis_result['error']}")
                return analysis_result
            
            newest_request_number = request_number_match.group(1)
            logger.info(f"🎯 Found request number from URL: {newest_request_number}")
            
            # Check if this request is already in database (shouldn't be for a newly submitted request)
            if self._is_request_in_database(newest_request_number):
                logger.warning(f"⚠️ Request {newest_request_number} already exists in database")
                analysis_result['error'] = f"Request {newest_request_number} already exists in database"
                return analysis_result
            
            # FIX: Set correct portal name before analysis (use portal URL)
            portal_name = request_data.get('portal_url', 'Unknown Portal')
            logger.info(f"🏢 Using portal name (URL): {portal_name}")
            
            # Initialize RequestAnalyzer if needed
            if not self.request_analyzer:
                self.request_analyzer = RequestAnalyzer(
                    driver=self.driver,
                    screenshot_func=self.take_screenshot,
                    llm_client=self.llm_client,
                    workflow_state_helper=self.workflow_state_helper
                )
            
            # Ensure database connection is established
            if not self.request_analyzer.db:
                self.request_analyzer.db = db
                
            # Set user_id from contact info for database operations
            if not self.request_analyzer.user_id:
                try:
                    contact_info = request_data.get('contact_info', {})
                    user_id = db.save_user(
                        email=contact_info.get('requester_email', ''),
                        full_name=contact_info.get('requester_name', ''),
                        phone=contact_info.get('requester_phone'),
                        organization=contact_info.get('requester_organization')
                    )
                    self.request_analyzer.user_id = user_id
                except Exception as e:
                    logger.warning(f"⚠️ Could not establish user_id: {str(e)}")
            
            # Temporarily override the portal name in request_analyzer
            original_portal_name = getattr(self.request_analyzer, 'portal_name', None)
            self.request_analyzer.portal_name = portal_name
            
            try:
                # Analyze request detail - we're already on the right page!
                logger.info(f"🎯 Analyzing request detail on current page: {newest_request_number}")
                detail_analysis = self.request_analyzer.analyze_request_detail_with_llm(newest_request_number)
                
                if detail_analysis['success']:
                    analysis_result['success'] = True
                    analysis_result['request_number'] = newest_request_number
                    analysis_result['saved_to_db'] = detail_analysis.get('saved_to_db', False)
                    
                    # Get the database request ID for linking
                    if self.request_analyzer.db and self.request_analyzer.user_id:
                        try:
                            stored_request = self.request_analyzer.db.get_stored_analysis(
                                newest_request_number, 
                                self.request_analyzer.user_id, 
                                portal_name  # Use correct portal name (URL)
                            )
                            if stored_request:
                                analysis_result['database_request_id'] = stored_request['id']
                        except Exception as e:
                            logger.warning(f"⚠️ Could not get database request ID: {str(e)}")
                    
                    logger.info(f"✅ Successfully analyzed newly submitted request: {newest_request_number}")
                    logger.info(f"   Portal: {portal_name}")
                    logger.info(f"   Saved to DB: {analysis_result['saved_to_db']}")
                else:
                    analysis_result['error'] = f"Analysis failed for {newest_request_number}: {detail_analysis['error']}"
            
            finally:
                # Restore original portal name
                if original_portal_name is not None:
                    self.request_analyzer.portal_name = original_portal_name
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"❌ Error finding and analyzing newest request: {str(e)}")
            analysis_result['error'] = str(e)
            return analysis_result

    def _is_request_in_database(self, request_number: str) -> bool:
        """Check if a request number already exists in the database"""
        try:
            if not self.request_analyzer or not self.request_analyzer.db or not self.request_analyzer.user_id:
                logger.warning("⚠️ Cannot check database - missing analyzer, db, or user_id")
                return False
            
            portal_name = getattr(self.request_analyzer, 'portal_name', 'Unknown Portal')
            stored_request = self.request_analyzer.db.get_stored_analysis(
                request_number, 
                self.request_analyzer.user_id, 
                portal_name
            )
            
            exists = stored_request is not None
            logger.info(f"🔍 Request {request_number} exists in database: {exists}")
            return exists
            
        except Exception as e:
            logger.warning(f"⚠️ Could not check if request exists in database: {str(e)}")
            return False  # Assume it doesn't exist if we can't check

    def _link_submission_to_request(self, db: 'SupabaseIntegration', submission_queue_id: str, 
                                request_number: str, database_request_id: str = None):
        """
        Link the submitted request to the original submission queue entry for audit trail.
        This creates a connection between the queue entry and the actual submitted request.
        """
        try:
            if not database_request_id:
                logger.warning("⚠️ No database request ID available for linking")
                return
            
            # Update the submission queue entry with the submitted request details
            link_data = {
                'submitted_request_number': request_number,
                'submitted_request_id': database_request_id,
                'linked_at': datetime.datetime.now().isoformat(),
                'updated_at': datetime.datetime.now().isoformat()
            }
            
            db.supabase.table('submission_queue').update(link_data).eq('id', submission_queue_id).execute()
            
            logger.info(f"🔗 Linked submission queue entry {submission_queue_id} to request {request_number}")
            
        except Exception as e:
            logger.error(f"❌ Failed to link submission to request: {str(e)}")

    
    def run_continuous_queue_processing(self, test_user_id: str = None, 
                                    check_interval_minutes: int = 5, 
                                    max_requests_per_batch: int = 5) -> Dict[str, Any]:
        """
        Run continuous queue processing - polls for new requests periodically
        
        Args:
            test_user_id: Hardcoded user ID for testing
            check_interval_minutes: How often to check for new requests
            max_requests_per_batch: Maximum requests to process in each batch
        """
        
        logger.info(f"🔄 Starting continuous queue processing")
        logger.info(f"⏰ Check interval: {check_interval_minutes} minutes")
        logger.info(f"📊 Max requests per batch: {max_requests_per_batch}")
        
        total_processed = 0
        total_successful = 0
        total_failed = 0
        
        try:
            while True:
                logger.info(f"\n{'='*80}")
                logger.info(f"🔄 QUEUE CHECK CYCLE - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'='*80}")
                
                # Process batch of requests
                batch_result = self.process_submission_queue(test_user_id, max_requests_per_batch)
                
                # Update totals
                total_processed += batch_result.get('processed', 0)
                total_successful += batch_result.get('successful_submissions', 0)
                total_failed += batch_result.get('failed_submissions', 0)
                
                # Log cycle summary
                if batch_result.get('processed', 0) > 0:
                    logger.info(f"📊 Batch processed: {batch_result['processed']} requests")
                    logger.info(f"📊 Session totals: {total_processed} processed, {total_successful} successful, {total_failed} failed")
                else:
                    logger.info("📭 No requests to process this cycle")
                
                # Wait for next cycle
                logger.info(f"⏰ Waiting {check_interval_minutes} minutes until next check...")
                time.sleep(check_interval_minutes * 60)
                
        except KeyboardInterrupt:
            logger.info(f"\n🛑 Queue processing stopped by user")
            return {
                'success': True,
                'message': 'Stopped by user',
                'total_processed': total_processed,
                'total_successful': total_successful,
                'total_failed': total_failed
            }
        except Exception as e:
            logger.error(f"❌ Continuous processing failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'total_processed': total_processed,
                'total_successful': total_successful,
                'total_failed': total_failed
            }
        

    # ============================================================================
    # BULK ANALYSIS QUEUE PROCESSING METHODS START
    # ============================================================================

    def process_bulk_analysis_queue(self, test_user_id: str = None, max_jobs: int = 5) -> Dict[str, Any]:
        """
        Process pending bulk analysis jobs from the Supabase queue.
        Each job runs the equivalent of analyze_all_requests() for a specific portal.
        """
        
        # Import Supabase integration
        try:
            from supabase_integration import SupabaseIntegration
        except ImportError:
            return {
                'success': False,
                'error': 'SupabaseIntegration not available',
                'processed': 0
            }
        
        # Initialize results tracking
        results = {
            'success': False,
            'total_fetched': 0,
            'processed': 0,
            'successful_jobs': 0,
            'failed_jobs': 0,
            'total_requests_analyzed': 0,
            'total_new_requests': 0,
            'total_skipped': 0,
            'errors': [],
            'processing_details': []
        }
        
        try:
            # Initialize database connection
            logger.info("🔬 Initializing Supabase connection for bulk analysis queue processing")
            db = SupabaseIntegration()
            
            # Fetch pending bulk analysis jobs from queue (priority order)
            logger.info("📥 Fetching pending bulk analysis jobs from queue")
            pending_jobs = self._fetch_pending_bulk_analysis_jobs(db, test_user_id, max_jobs)
            
            if not pending_jobs:
                logger.info("📭 No pending bulk analysis jobs found in queue")
                results['success'] = True
                results['message'] = 'No pending bulk analysis jobs to process'
                return results
            
            results['total_fetched'] = len(pending_jobs)
            logger.info(f"📊 Found {len(pending_jobs)} pending bulk analysis jobs to process")
            
            # Process each job
            for i, job_data in enumerate(pending_jobs, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"🔬 PROCESSING BULK ANALYSIS JOB {i}/{len(pending_jobs)}")
                logger.info(f"Job ID: {job_data['id']}")
                logger.info(f"Agency: {job_data['agency_name']}")
                logger.info(f"User: {job_data['user_email']}")
                logger.info(f"Priority: {job_data['priority']}")
                logger.info(f"{'='*60}")
                
                # Update status to 'processing'
                self._update_bulk_analysis_job_status(
                    db, job_data['id'], 'processing', 
                    'Started bulk analysis processing'
                )
                
                # Process individual job
                job_result = self._process_single_bulk_analysis_job(db, job_data)
                
                results['processing_details'].append({
                    'job_id': job_data['id'],
                    'agency_name': job_data['agency_name'],
                    'user_email': job_data['user_email'],
                    'result': job_result
                })
                
                if job_result['success']:
                    results['successful_jobs'] += 1
                    results['total_requests_analyzed'] += job_result.get('total_requests', 0)
                    results['total_new_requests'] += job_result.get('successful_analyses', 0)
                    results['total_skipped'] += job_result.get('skipped_existing', 0)
                    logger.info(f"✅ Successfully processed bulk analysis job {job_data['id']}")
                else:
                    results['failed_jobs'] += 1
                    logger.error(f"❌ Failed to process bulk analysis job {job_data['id']}: {job_result['error']}")
                    results['errors'].append(f"Job {job_data['id']}: {job_result['error']}")
                
                results['processed'] += 1
                
                # Add delay between jobs to avoid overwhelming system
                if i < len(pending_jobs):
                    logger.info("⏰ Waiting 30 seconds before next job...")
                    time.sleep(30)
            
            # Calculate final results
            results['success'] = results['processed'] > 0
            success_rate = (results['successful_jobs'] / results['processed'] * 100) if results['processed'] > 0 else 0
            
            logger.info(f"\n🎉 BULK ANALYSIS QUEUE PROCESSING COMPLETE!")
            logger.info(f"📊 Total jobs processed: {results['processed']}")
            logger.info(f"✅ Successful: {results['successful_jobs']}")
            logger.info(f"❌ Failed: {results['failed_jobs']}")
            logger.info(f"📈 Success rate: {success_rate:.1f}%")
            logger.info(f"🔍 Total requests analyzed: {results['total_requests_analyzed']}")
            logger.info(f"🆕 New requests found: {results['total_new_requests']}")
            logger.info(f"⏭️  Existing requests skipped: {results['total_skipped']}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Bulk analysis queue processing failed: {str(e)}")
            results['error'] = f"Bulk analysis queue processing failed: {str(e)}"
            return results

    def _fetch_pending_bulk_analysis_jobs(self, db: 'SupabaseIntegration', test_user_id: str = None, max_jobs: int = 5) -> List[Dict[str, Any]]:
        """Fetch pending bulk analysis jobs with portal and credential information"""
        try:
            logger.info(f"🔍 Fetching bulk analysis jobs for user: {test_user_id}")
            
            # Get basic job data first - explicitly select all columns including submission_queue_id
            result = db.supabase.table('bulk_analysis_queue').select(
                'id, user_id, portal_id, job_name, analysis_type, priority, created_at, '
                'status, submission_queue_id, job_description, progress_data, resume_info, '
                'final_results, error_details, started_processing_at, completed_at'
            ).eq('user_id', test_user_id).eq('status', 'pending').order('priority').order('created_at').limit(max_jobs).execute()

            logger.info(f"📊 Found {len(result.data) if result.data else 0} pending jobs")
            if result.data and len(result.data) > 0:
                logger.info(f"🐛 DEBUG: First job columns from DB: {list(result.data[0].keys())}")
            
            if not result.data:
                return []
            
            # Enrich each job with portal, user, and credential data
            enriched_jobs = []
            for job in result.data:
                try:
                    logger.info(f"🔍 Processing job {job['id']} for portal {job['portal_id']}")
                    logger.info(f"🐛 DEBUG: Raw job keys from DB: {list(job.keys())}")
                    logger.info(f"🐛 DEBUG: Raw job.get('submission_queue_id') = {job.get('submission_queue_id')}")
                    
                    # Fetch portal data
                    portal_result = db.supabase.table('portals').select('agency_name, portal_url, portal_type').eq('id', job['portal_id']).single().execute()
                    
                    if not portal_result.data:
                        logger.warning(f"⚠️ Portal not found for job {job['id']}")
                        continue
                    
                    # Fetch user data
                    user_result = db.supabase.table('users').select('email, full_name').eq('id', job['user_id']).single().execute()
                    
                    if not user_result.data:
                        logger.warning(f"⚠️ User not found for job {job['id']}")
                        continue
                    
                    # Fetch credentials
                    cred_result = db.supabase.table('user_portal_credentials').select('''
                        encrypted_username,
                        encrypted_password
                    ''').eq('user_id', job['user_id']).eq('portal_id', job['portal_id']).eq('is_active', True).single().execute()
                    
                    if not cred_result.data:
                        logger.warning(f"⚠️ No credentials found for job {job['id']}")
                        continue
                    
                    # Create enriched job data
                    enriched_job = {
                        # Basic job data
                        'id': job['id'],
                        'user_id': job['user_id'],
                        'portal_id': job['portal_id'],
                        'job_name': job['job_name'],
                        'analysis_type': job['analysis_type'],
                        'priority': job['priority'],
                        'created_at': job['created_at'],
                        'submission_queue_id': job.get('submission_queue_id'), 

                        # Portal data
                        'agency_name': portal_result.data['agency_name'],
                        'portal_url': portal_result.data['portal_url'],
                        'portal_type': portal_result.data['portal_type'],

                        # User data
                        'user_email': user_result.data['email'],
                        'user_full_name': user_result.data['full_name'],

                        # Credentials
                        'encrypted_username': cred_result.data['encrypted_username'],
                        'encrypted_password': cred_result.data['encrypted_password']
                    }
                    
                    enriched_jobs.append(enriched_job)
                    logger.info(f"✅ Successfully enriched job for {enriched_job['agency_name']}")
                    logger.info(f"🐛 DEBUG: enriched_job['submission_queue_id'] = {enriched_job.get('submission_queue_id')}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to enrich job {job['id']}: {str(e)}")
                    import traceback
                    logger.error(f"Full traceback: {traceback.format_exc()}")
                    continue
            
            logger.info(f"📊 Successfully processed {len(enriched_jobs)} bulk analysis jobs")
            return enriched_jobs
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch pending bulk analysis jobs: {str(e)}")
            logger.error(f"Error details: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def _process_single_bulk_analysis_job(self, db: 'SupabaseIntegration', job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single bulk analysis job by logging into the portal and running analyze_all_requests equivalent
        """
        
        job_id = job_data['id']
        portal_url = job_data['portal_url']
        agency_name = job_data['agency_name']
        
        processing_result = {
            'success': False,
            'job_id': job_id,
            'agency_name': agency_name,
            'steps_completed': [],
            'errors': [],
            'total_requests': 0,
            'successful_analyses': 0,
            'skipped_existing': 0,
            'failed_analyses': 0,
            'pages_processed': 0
        }
        
        try:
            # Step 1: Navigate to portal
            logger.info(f"🌐 Navigating to portal: {portal_url}")
            
            navigation_result = self.navigate_to_portal(portal_url)
            
            if not navigation_result['success']:
                error_msg = f"Navigation failed: {navigation_result.get('error', 'Unknown error')}"
                processing_result['errors'].append(error_msg)
                self._update_bulk_analysis_job_status(db, job_id, 'failed', error_msg)
                return processing_result
            
            processing_result['steps_completed'].append('portal_navigation')
            
            # Step 2: Login using stored credentials
            logger.info("🔐 Attempting login with stored credentials")
            
            # TODO: In production, decrypt the credentials here
            credentials = LoginCredentials(
                username=job_data['encrypted_username'],
                password=job_data['encrypted_password']
            )
            
            login_result = self.login_handler.attempt_login(credentials)
            
            if not login_result['success']:
                error_msg = f"Login failed: {login_result.get('error', 'Unknown error')}"
                processing_result['errors'].append(error_msg)
                self._update_bulk_analysis_job_status(db, job_id, 'failed', error_msg)
                return processing_result
            
            processing_result['steps_completed'].append('portal_login')
            self.is_logged_in = True
            
            # Step 3: Initialize request analyzer with user context
            logger.info("🔍 Initializing request analyzer for bulk analysis")
            
            if not self.request_analyzer:
                self.request_analyzer = RequestAnalyzer(
                    driver=self.driver,
                    screenshot_func=self.take_screenshot,
                    llm_client=self.llm_client,
                    workflow_state_helper=self.workflow_state_helper
                )
            
            # Set up database connection and user context
            self.request_analyzer.db = db

            # Set submission_queue_id if this bulk analysis was triggered by a submission (Path 2: new account flow)
            # Each bulk_analysis job now has exactly one submission_queue_id (1:1 relationship)
            logger.info(f"🐛 DEBUG: job_data keys = {list(job_data.keys())}")
            logger.info(f"🐛 DEBUG: job_data.get('submission_queue_id') = {job_data.get('submission_queue_id')}")
            submission_queue_id = job_data.get('submission_queue_id')
            if submission_queue_id:
                self.request_analyzer.submission_queue_id = submission_queue_id
                logger.info(f"🔗 Bulk analysis triggered by submission_queue: {submission_queue_id}")
                logger.info(f"   All new requests will be linked to this submission")
            else:
                self.request_analyzer.submission_queue_id = None
                logger.info("📋 Bulk analysis not linked to specific submission (general portal scan)")

            # Get or create user ID for database operations
            try:
                user_id = db.save_user(
                    email=job_data['user_email'],
                    full_name=job_data['user_full_name']
                )
                self.request_analyzer.user_id = user_id
                self.request_analyzer.portal_name = portal_url  # Use portal URL as identifier
            except Exception as e:
                logger.warning(f"⚠️ Could not establish database user context: {str(e)}")
            
            processing_result['steps_completed'].append('analyzer_setup')
            
            # Step 4: Run bulk analysis (equivalent to analyze_all_requests)
            logger.info("🔬 Starting bulk analysis of all requests for this portal")
            
            analysis_result = self._run_portal_bulk_analysis(db, job_data)
            
            if analysis_result['success']:
                processing_result['steps_completed'].append('bulk_analysis')
                processing_result['total_requests'] = analysis_result['total_requests']
                processing_result['successful_analyses'] = analysis_result['successful_analyses']
                processing_result['skipped_existing'] = analysis_result['skipped_existing']
                processing_result['failed_analyses'] = analysis_result['failed_analyses']
                processing_result['pages_processed'] = analysis_result['pages_processed']
                
                # Update job with final results
                final_results = {
                    'summary': f"Completed bulk analysis for {agency_name}",
                    'total_requests_found': analysis_result['total_requests'],
                    'new_requests_analyzed': analysis_result['successful_analyses'],
                    'existing_requests_skipped': analysis_result['skipped_existing'],
                    'analysis_errors': analysis_result['failed_analyses'],
                    'pages_covered': analysis_result['pages_processed'],
                    'processing_time_seconds': analysis_result.get('processing_duration', 0)
                }
                
                self._update_bulk_analysis_job_status(
                    db, job_id, 'completed',
                    'Bulk analysis completed successfully',
                    final_results=final_results
                )

                # Link back to original submission if this was triggered by one
                self._link_bulk_analysis_to_submission(db, job_data, job_id)

                processing_result['success'] = True
                logger.info(f"✅ Bulk analysis completed for {agency_name}")
                
            else:
                error_msg = f"Bulk analysis failed: {analysis_result.get('error', 'Unknown error')}"
                processing_result['errors'].append(error_msg)
                self._update_bulk_analysis_job_status(db, job_id, 'failed', error_msg)
            
            return processing_result
            
        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            logger.error(f"❌ Error processing bulk analysis job {job_id}: {error_msg}")
            processing_result['errors'].append(error_msg)
            self._update_bulk_analysis_job_status(db, job_id, 'failed', error_msg)
            return processing_result
        
        finally:
            # Reset login status for next job
            self.is_logged_in = False

    def _run_portal_bulk_analysis(self, db: 'SupabaseIntegration', job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the bulk analysis for a specific portal (adapted from analyze_all_requests)
        """
        job_id = job_data['id']

        try:
            start_time = time.time()

            # Set submission_queue_id on analyzer for proper linking
            submission_queue_id = job_data.get('submission_queue_id')
            if submission_queue_id:
                self.request_analyzer.submission_queue_id = submission_queue_id
                logger.info(f"🔗 Analyzer configured to link requests to submission: {submission_queue_id}")
            else:
                # Clear submission_queue_id if not provided (for non-submission bulk analysis)
                self.request_analyzer.submission_queue_id = None

            # Navigate to All requests page first
            nav_result = self.request_analyzer.navigate_to_all_requests()
            if not nav_result['success']:
                return {
                    'success': False,
                    'error': f"Could not navigate to all requests page: {nav_result['error']}"
                }

            # Set up filters to show only user's requests
            logger.info("🔍 Setting up filters to show only user's requests")
            from request_filter_manager import RequestFilterManager
            filter_manager = RequestFilterManager(
                driver=self.driver,
                llm_client=self.llm_client,
                screenshot_manager=self.take_screenshot
            )

            # Apply requester filter
            if not filter_manager._apply_requester_filter_only():
                logger.warning("⚠️ Could not apply requester filter, continuing with all requests")
            else:
                logger.info("✅ Filters applied - now showing only user's requests")
            
            time.sleep(3)  # Wait for filter to apply
            
            # Update progress: setup complete
            self._update_bulk_analysis_progress(db, job_id, {
                'setup_complete': True,
                'current_phase': 'pagination_test'
            })
            
            # PAGINATION TEST
            logger.info("🧪 TESTING PAGINATION")
            
            last_page = self._navigate_to_last_page()
            if not last_page:
                last_page = 1
            
            first_page_success = self._navigate_to_first_page()
            if not first_page_success:
                return {
                    'success': False,
                    'error': 'Pagination test failed: Cannot navigate to first page'
                }
            
            if last_page > 1:
                final_last_page = self._navigate_to_last_page()
                if not final_last_page:
                    return {
                        'success': False,
                        'error': 'Pagination test failed: Cannot navigate to last page consistently'
                    }
            
            logger.info("🎉 PAGINATION TEST COMPLETE")
            
            # Update progress: pagination test passed
            self._update_bulk_analysis_progress(db, job_id, {
                'pagination_test_passed': True,
                'total_pages': last_page,
                'current_phase': 'processing_requests'
            })
            
            # Initialize tracking variables
            total_requests = 0
            successful_analyses = 0
            skipped_existing = 0
            failed_analyses = 0
            pages_processed = 0
            
            # Start from last page (we're already there)
            current_page = last_page
            has_more_pages = True
            
            while has_more_pages:
                try:
                    logger.info(f"📄 Processing page {current_page} (working backwards)")
                    pages_processed += 1
                    
                    # Update progress regularly
                    completion_percentage = (pages_processed / last_page * 100) if last_page > 0 else 0
                    self._update_bulk_analysis_progress(db, job_id, {
                        'current_page': current_page,
                        'pages_processed': pages_processed,
                        'completion_percentage': min(completion_percentage, 99),  # Cap at 99% until complete
                        'processed_requests': successful_analyses + skipped_existing + failed_analyses
                    })
                    
                    # Extract requests from current page
                    extraction_result = self.request_analyzer.extract_requests_with_llm()
                    
                    if not extraction_result.extraction_successful:
                        logger.error(f"Failed to extract requests from page {current_page}")
                        break
                    
                    page_requests = extraction_result.clickable_requests
                    total_requests += len(page_requests)
                    
                    logger.info(f"📊 Found {len(page_requests)} requests on page {current_page}")
                    
                    # Analyze each request on this page
                    for i, request in enumerate(page_requests):
                        request_number = request.request_number
                        
                        try:
                            # Check if already in database
                            if self._is_request_in_database(request_number):
                                logger.info(f"⏭️  Skipping {request_number} (already in database)")
                                skipped_existing += 1
                                continue
                            
                            # Progress update
                            progress = (successful_analyses + skipped_existing + failed_analyses + 1)
                            logger.info(f"🔍 Analyzing request {progress}: {request_number} (page {current_page})")
                            
                            # Click on request
                            click_result = self.request_analyzer.click_request_with_llm(request_number)
                            
                            if not click_result['success']:
                                logger.error(f"❌ Failed to click request {request_number}: {click_result['error']}")
                                failed_analyses += 1
                                continue
                            
                            # Analyze request detail
                            analysis_result = self.request_analyzer.analyze_request_detail_with_llm(request_number)
                            
                            if analysis_result['success']:
                                if analysis_result.get('saved_to_db', False):
                                    successful_analyses += 1
                                    logger.info(f"✅ Successfully analyzed and saved {request_number}")
                                else:
                                    failed_analyses += 1
                                    logger.error(f"❌ Analysis succeeded but database save failed for {request_number}")
                            else:
                                failed_analyses += 1
                                logger.error(f"❌ Analysis failed for {request_number}: {analysis_result['error']}")
                            
                            # Navigate back to requests list
                            self.driver.back()
                            time.sleep(2)
                            
                            # Rate limiting
                            time.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"❌ Unexpected error analyzing {request_number}: {str(e)}")
                            failed_analyses += 1
                            
                            # Try to get back to requests list
                            try:
                                self.driver.back()
                                time.sleep(2)
                            except:
                                # Re-navigate if needed
                                self.request_analyzer.navigate_to_all_requests()
                                if filter_manager._apply_requester_filter_only():
                                    self._navigate_to_page_number(current_page)
                                time.sleep(3)
                            continue
                    
                    # Check for previous page (going backwards)
                    has_more_pages = self._navigate_to_previous_page()
                    if has_more_pages:
                        current_page -= 1
                        time.sleep(3)
                    else:
                        logger.info("📄 Reached first page - bulk analysis complete")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing page {current_page}: {str(e)}")
                    break
            
            # Final progress update
            processing_duration = int(time.time() - start_time)
            self._update_bulk_analysis_progress(db, job_id, {
                'completion_percentage': 100,
                'current_phase': 'completed',
                'processing_duration_seconds': processing_duration
            })
            
            logger.info(f"🎉 Portal bulk analysis completed!")
            logger.info(f"📊 Pages processed: {pages_processed}")
            logger.info(f"📊 Total requests: {total_requests}")
            logger.info(f"📊 Successfully analyzed: {successful_analyses}")
            logger.info(f"📊 Skipped (existing): {skipped_existing}")
            logger.info(f"📊 Failed: {failed_analyses}")
            
            return {
                'success': True,
                'total_requests': total_requests,
                'successful_analyses': successful_analyses,
                'skipped_existing': skipped_existing,
                'failed_analyses': failed_analyses,
                'pages_processed': pages_processed,
                'processing_duration': processing_duration
            }
            
        except Exception as e:
            logger.error(f"❌ Portal bulk analysis failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def _update_bulk_analysis_job_status(self, db: 'SupabaseIntegration', job_id: str, status: str, 
                                       message: str, final_results: Dict[str, Any] = None):
        """Update bulk analysis job status in the database"""
        try:
            update_data = {
                'status': status,
                'updated_at': datetime.datetime.now().isoformat()
            }
            
            # Add processing timestamps
            if status == 'processing':
                update_data['started_processing_at'] = datetime.datetime.now().isoformat()
            elif status in ['completed', 'failed']:
                update_data['completed_at'] = datetime.datetime.now().isoformat()
                
            # Add results if provided
            if final_results:
                update_data['final_results'] = final_results
                
            # Add error details for failed jobs
            if status == 'failed':
                update_data['error_details'] = message
                
            # Update the record
            db.supabase.table('bulk_analysis_queue').update(update_data).eq('id', job_id).execute()
            
            logger.info(f"📊 Updated bulk analysis job {job_id} status to: {status}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update bulk analysis job status: {str(e)}")

    def _update_bulk_analysis_progress(self, db: 'SupabaseIntegration', job_id: str, progress_data: Dict[str, Any]):
        """Update bulk analysis job progress in real-time"""
        try:
            # Get current progress data and merge with new data
            current_job = db.supabase.table('bulk_analysis_queue').select('progress_data').eq('id', job_id).single().execute()
            
            if current_job.data:
                current_progress = current_job.data.get('progress_data', {})
                current_progress.update(progress_data)
            else:
                current_progress = progress_data
            
            update_data = {
                'progress_data': current_progress,
                'updated_at': datetime.datetime.now().isoformat()
            }
            
            db.supabase.table('bulk_analysis_queue').update(update_data).eq('id', job_id).execute()

        except Exception as e:
            logger.error(f"❌ Failed to update bulk analysis progress: {str(e)}")

    def _link_bulk_analysis_to_submission(self, db: 'SupabaseIntegration', job_data: Dict[str, Any], job_id: str):
        """
        Link the request(s) from bulk analysis back to the original submission_queue entry.
        Now simplified: requests table has submission_queue_id, so we just query by that!

        Args:
            db: SupabaseIntegration instance
            job_data: Bulk analysis job data (includes submission_queue_id if present)
            job_id: Bulk analysis job ID
        """
        try:
            # Check if this job was triggered by a submission
            submission_queue_id = job_data.get('submission_queue_id')

            if not submission_queue_id:
                logger.debug(f"Bulk analysis job {job_id} was not triggered by a submission, skipping linking")
                return

            logger.info(f"🔗 Linking bulk analysis results back to submission_queue {submission_queue_id}")

            # Query requests table by submission_queue_id (direct link!)
            requests = db.supabase.table('requests').select('id, request_number').eq(
                'submission_queue_id', submission_queue_id
            ).execute()

            if not requests.data or len(requests.data) == 0:
                logger.warning(f"⚠️ No requests found with submission_queue_id {submission_queue_id}")
                logger.warning(f"   This might be normal if the request hasn't been analyzed yet")
                return

            # Link back to submission_queue (take the first one, should only be one anyway)
            request = requests.data[0]
            link_data = {
                'submitted_request_id': request['id'],
                'submitted_request_number': request['request_number'],
                'linked_at': datetime.datetime.now().isoformat(),
                'updated_at': datetime.datetime.now().isoformat()
            }

            db.supabase.table('submission_queue').update(link_data).eq('id', submission_queue_id).execute()

            logger.info(f"✅ Successfully linked submission {submission_queue_id} to request {request['request_number']}")

        except Exception as e:
            logger.error(f"❌ Failed to link bulk analysis to submission: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    def run_continuous_bulk_analysis_processing(self, test_user_id: str = None, 
                                              check_interval_minutes: int = 60, 
                                              max_jobs_per_batch: int = 5) -> Dict[str, Any]:
        """
        Run continuous bulk analysis queue processing - polls for new jobs periodically
        
        Args:
            test_user_id: User ID for testing
            check_interval_minutes: How often to check for new jobs (default 60min for bulk analysis)
            max_jobs_per_batch: Maximum jobs to process in each batch (default 5 for resource management)
        """
        
        logger.info(f"🔬 Starting continuous bulk analysis queue processing")
        logger.info(f"⏰ Check interval: {check_interval_minutes} minutes")
        logger.info(f"📊 Max jobs per batch: {max_jobs_per_batch}")
        
        total_processed = 0
        total_successful = 0
        total_failed = 0
        total_requests_analyzed = 0
        
        try:
            while True:
                logger.info(f"\n{'='*80}")
                logger.info(f"🔬 BULK ANALYSIS QUEUE CHECK - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'='*80}")
                
                # Process batch of jobs
                batch_result = self.process_bulk_analysis_queue(test_user_id, max_jobs_per_batch)
                
                # Update totals
                total_processed += batch_result.get('processed', 0)
                total_successful += batch_result.get('successful_jobs', 0)
                total_failed += batch_result.get('failed_jobs', 0)
                total_requests_analyzed += batch_result.get('total_requests_analyzed', 0)
                
                # Log cycle summary
                if batch_result.get('processed', 0) > 0:
                    logger.info(f"📊 Batch processed: {batch_result['processed']} jobs")
                    logger.info(f"📊 Requests analyzed this batch: {batch_result.get('total_requests_analyzed', 0)}")
                    logger.info(f"📊 Session totals: {total_processed} jobs, {total_successful} successful, {total_failed} failed")
                    logger.info(f"📊 Total requests analyzed: {total_requests_analyzed}")
                else:
                    logger.info("📭 No bulk analysis jobs to process this cycle")
                
                # Wait for next cycle
                logger.info(f"⏰ Waiting {check_interval_minutes} minutes until next check...")
                time.sleep(check_interval_minutes * 60)
                
        except KeyboardInterrupt:
            logger.info(f"\n🛑 Bulk analysis processing stopped by user")
            return {
                'success': True,
                'message': 'Stopped by user',
                'total_processed': total_processed,
                'total_successful': total_successful,
                'total_failed': total_failed,
                'total_requests_analyzed': total_requests_analyzed
            }
        except Exception as e:
            logger.error(f"❌ Continuous bulk analysis processing failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'total_processed': total_processed,
                'total_successful': total_successful,
                'total_failed': total_failed,
                'total_requests_analyzed': total_requests_analyzed
            }
        
    # ============================================================================
    # BULK ANALYSIS QUEUE PROCESSING METHODS END
    # ============================================================================