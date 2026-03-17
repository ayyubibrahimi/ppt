import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.remote.webelement import WebElement
import re

logger = logging.getLogger(__name__)

class TableScrollManager:
    """Manages infinite scroll tables and enables clicking requests at any position"""
    
    def __init__(self, driver, scroll_pause_time: float = 2.0):
        self.driver = driver
        self.scroll_pause_time = scroll_pause_time
        self.request_positions = {}  # Track request locations
        self.total_requests_found = 0
        self.scroll_attempts = 0
        self.max_scroll_attempts = 100  # Safety limit
        
    def load_all_requests(self) -> Dict[str, Any]:
        """Load all requests in the table using infinite scroll"""
        try:
            logger.info("🔄 Starting infinite scroll to load all requests")
            
            # Get initial count
            initial_count = self._count_current_requests()
            logger.info(f"📊 Initial requests visible: {initial_count}")
            
            # Detect total from page indicators if available
            expected_total = self._detect_total_from_page()
            if expected_total:
                logger.info(f"🎯 Page indicates {expected_total} total requests")
            
            # Perform scrolling
            scroll_result = self._perform_infinite_scroll()
            
            # Final validation
            final_count = self._count_current_requests()
            logger.info(f"✅ Final requests loaded: {final_count}")
            
            return {
                'success': scroll_result['success'],
                'initial_count': initial_count,
                'final_count': final_count,
                'expected_total': expected_total,
                'scroll_attempts': self.scroll_attempts,
                'error': scroll_result.get('error')
            }
            
        except Exception as e:
            logger.error(f"Failed to load all requests: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'final_count': self._count_current_requests()
            }
    
    def _detect_total_from_page(self) -> Optional[int]:
        """Try to detect total request count from page indicators"""
        try:
            # Look for patterns like "171 Requests filtered"
            indicators = [
                "//text()[contains(., 'Requests filtered')]",
                "//text()[contains(., 'requests found')]", 
                "//text()[contains(., 'showing') and contains(., 'of')]",
                "//*[contains(text(), 'Results:')]",
                "//*[contains(@class, 'total') or contains(@class, 'count')]"
            ]
            
            for indicator in indicators:
                try:
                    elements = self.driver.find_elements(By.XPATH, indicator)
                    for element in elements:
                        text = element.text if hasattr(element, 'text') else str(element)
                        # Extract numbers from text like "171 Requests filtered"
                        numbers = re.findall(r'\d+', text)
                        if numbers:
                            potential_total = int(numbers[0])
                            if potential_total > 10:  # Sanity check
                                return potential_total
                except:
                    continue
                    
            return None
            
        except Exception as e:
            logger.warning(f"Could not detect total from page: {str(e)}")
            return None
    
    def _count_current_requests(self) -> int:
        """Count currently loaded requests in the DOM"""
        try:
            # Try multiple selectors to find request rows
            selectors = [
                "table tbody tr",
                "tr[data-request]",
                "tr:has(td)",
                ".request-row",
                "[class*='row']:has([class*='request'])"
            ]
            
            max_count = 0
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    # Filter out header rows and empty rows
                    valid_rows = [el for el in elements if self._is_valid_request_row(el)]
                    max_count = max(max_count, len(valid_rows))
                except:
                    continue
            
            return max_count
            
        except Exception as e:
            logger.warning(f"Could not count requests: {str(e)}")
            return 0
    
    def _is_valid_request_row(self, element: WebElement) -> bool:
        """Check if element is a valid request row (not header/empty)"""
        try:
            text = element.text.strip()
            if not text:
                return False
            
            # Look for request number patterns
            has_request_number = bool(re.search(r'\d{2,4}-\d+', text))
            
            # Check for common table headers to exclude
            header_keywords = ['request', 'status', 'date', 'description', 'department']
            is_header = any(keyword.lower() in text.lower() for keyword in header_keywords) and len(text.split()) <= 3
            
            return has_request_number and not is_header
            
        except:
            return False
    
    def _perform_infinite_scroll(self) -> Dict[str, Any]:
        """Perform the actual infinite scrolling"""
        try:
            last_count = self._count_current_requests()
            no_change_count = 0
            max_no_change = 3  # Stop after 3 attempts with no new content
            
            while self.scroll_attempts < self.max_scroll_attempts:
                self.scroll_attempts += 1
                
                # Scroll down
                self._scroll_down()
                
                # Wait for content to load
                time.sleep(self.scroll_pause_time)
                
                # Check for new content
                current_count = self._count_current_requests()
                
                if current_count > last_count:
                    logger.info(f"📈 Loaded {current_count} requests (+{current_count - last_count})")
                    last_count = current_count
                    no_change_count = 0
                else:
                    no_change_count += 1
                    logger.debug(f"No new content, attempt {no_change_count}/{max_no_change}")
                
                # Check if we should stop
                if no_change_count >= max_no_change:
                    logger.info("🛑 No new content detected, stopping scroll")
                    break
                
                # Check for end-of-content indicators
                if self._is_end_of_content():
                    logger.info("🏁 End of content detected")
                    break
            
            self.total_requests_found = last_count
            
            return {
                'success': True,
                'final_count': last_count,
                'scroll_attempts': self.scroll_attempts
            }
            
        except Exception as e:
            logger.error(f"Scroll failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _scroll_down(self):
        """Scroll down to trigger infinite scroll loading"""
        try:
            # Try multiple scroll methods
            methods = [
                # Method 1: Scroll to bottom
                lambda: self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);"),
                
                # Method 2: Scroll by viewport height
                lambda: self.driver.execute_script("window.scrollBy(0, window.innerHeight);"),
                
                # Method 3: Scroll on table container
                lambda: self._scroll_table_container(),
                
                # Method 4: Page down key
                lambda: ActionChains(self.driver).send_keys(" ").perform()
            ]
            
            # Try first method, fallback to others if needed
            for i, method in enumerate(methods):
                try:
                    method()
                    break
                except Exception as e:
                    if i == len(methods) - 1:  # Last method failed
                        raise e
                    logger.debug(f"Scroll method {i+1} failed, trying next")
                    
        except Exception as e:
            logger.warning(f"Scroll down failed: {str(e)}")
    
    def _scroll_table_container(self):
        """Scroll within table container if it's separately scrollable"""
        try:
            # Find scrollable table containers
            containers = self.driver.find_elements(By.CSS_SELECTOR, 
                ".table-container, .scroll-container, [style*='overflow'], .datatable-scroll")
            
            for container in containers:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollHeight;", 
                        container
                    )
                    return
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"Table container scroll failed: {str(e)}")
    
    def _is_end_of_content(self) -> bool:
        """Check for indicators that we've reached the end"""
        try:
            # Look for end-of-content indicators
            end_indicators = [
                "//text()[contains(., 'No more results')]",
                "//text()[contains(., 'End of list')]", 
                "//text()[contains(., 'No additional')]",
                "//*[contains(@class, 'end-of-results')]",
                "//*[contains(@class, 'no-more')]"
            ]
            
            for indicator in end_indicators:
                try:
                    if self.driver.find_elements(By.XPATH, indicator):
                        return True
                except:
                    continue
                    
            # Check if we're at bottom and no loading indicators
            at_bottom = self.driver.execute_script(
                "return (window.innerHeight + window.scrollY) >= document.body.offsetHeight;"
            )
            
            has_loading = bool(self.driver.find_elements(By.CSS_SELECTOR, 
                ".loading, .spinner, [class*='load']"))
            
            return at_bottom and not has_loading
            
        except Exception as e:
            logger.debug(f"End of content check failed: {str(e)}")
            return False
    
    def click_request(self, request_number: str) -> Dict[str, Any]:
        """Click on a specific request, handling scrolling if needed"""
        try:
            logger.info(f"🖱️ Attempting to click request {request_number}")
            
            # First try to find and click without scrolling
            if self._try_click_visible_request(request_number):
                return {
                    'success': True,
                    'request_number': request_number,
                    'method': 'direct_click'
                }
            
            # If not visible, scroll to find it
            logger.info(f"Request {request_number} not visible, searching...")
            
            if self._scroll_to_find_request(request_number):
                if self._try_click_visible_request(request_number):
                    return {
                        'success': True,
                        'request_number': request_number,
                        'method': 'scroll_and_click'
                    }
            
            return {
                'success': False,
                'error': f"Could not find or click request {request_number}"
            }
            
        except Exception as e:
            logger.error(f"Failed to click request {request_number}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _try_click_visible_request(self, request_number: str) -> bool:
        """Try to click request if it's currently visible"""
        try:
            # Try multiple click strategies
            click_strategies = [
                # Strategy 1: Link text
                lambda: self._click_by_link_text(request_number),
                
                # Strategy 2: Partial link text  
                lambda: self._click_by_partial_link_text(request_number),
                
                # Strategy 3: Text content search
                lambda: self._click_by_text_content(request_number),
                
                # Strategy 4: Table cell search
                lambda: self._click_by_table_cell(request_number)
            ]
            
            for strategy in click_strategies:
                if strategy():
                    logger.info(f"✅ Successfully clicked {request_number}")
                    time.sleep(2)  # Wait for page load
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Click attempt failed: {str(e)}")
            return False
    
    def _click_by_link_text(self, request_number: str) -> bool:
        """Click by exact link text"""
        try:
            element = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.LINK_TEXT, request_number))
            )
            element.click()
            return True
        except:
            return False
    
    def _click_by_partial_link_text(self, request_number: str) -> bool:
        """Click by partial link text"""
        try:
            element = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, request_number))
            )
            element.click()
            return True
        except:
            return False
    
    def _click_by_text_content(self, request_number: str) -> bool:
        """Click by finding element containing the request number"""
        try:
            xpath = f"//*[contains(text(), '{request_number}') and (self::a or parent::a)]"
            element = self.driver.find_element(By.XPATH, xpath)
            
            # Click the link element (either the element itself or its parent)
            link_element = element if element.tag_name == 'a' else element.find_element(By.XPATH, "./parent::a")
            link_element.click()
            return True
        except:
            return False
    
    def _click_by_table_cell(self, request_number: str) -> bool:
        """Click by finding in table cells"""
        try:
            xpath = f"//td[contains(text(), '{request_number}')]//a | //td[contains(text(), '{request_number}')]/a"
            element = self.driver.find_element(By.XPATH, xpath)
            element.click()
            return True
        except:
            return False
    
    def _scroll_to_find_request(self, request_number: str) -> bool:
        """Scroll through the page to find a specific request"""
        try:
            logger.info(f"🔍 Searching for request {request_number} by scrolling")
            
            # Start from top
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # Scroll in increments, checking for the request
            scroll_increment = 500  # pixels
            max_scroll_height = self.driver.execute_script("return document.body.scrollHeight")
            current_scroll = 0
            
            while current_scroll < max_scroll_height:
                # Check if request is visible at current position
                if self._is_request_visible(request_number):
                    logger.info(f"Found {request_number} at scroll position {current_scroll}")
                    return True
                
                # Scroll down
                current_scroll += scroll_increment
                self.driver.execute_script(f"window.scrollTo(0, {current_scroll});")
                time.sleep(0.5)
            
            logger.warning(f"Request {request_number} not found after full scroll")
            return False
            
        except Exception as e:
            logger.error(f"Scroll search failed: {str(e)}")
            return False
    
    def _is_request_visible(self, request_number: str) -> bool:
        """Check if a request is currently visible in viewport"""
        try:
            elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{request_number}')]")
            
            for element in elements:
                if element.is_displayed():
                    return True
            
            return False
            
        except:
            return False
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current status of loaded requests"""
        return {
            'total_requests_found': self.total_requests_found,
            'scroll_attempts': self.scroll_attempts,
            'current_count': self._count_current_requests()
        }