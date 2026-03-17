"""
LLM-Guided Filter Manager - Let the LLM discover the correct selectors from HTML
"""
import time
import logging
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from models import CheckboxSelector, FilterAnalysis
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class RequestFilterManager:
    """LLM-guided filter manager that discovers selectors from actual HTML"""
    
    def __init__(self, driver: webdriver.Chrome, llm_client, screenshot_manager=None):
        self.driver = driver
        self.llm_client = llm_client
        self.screenshot_manager = screenshot_manager
        self.wait = WebDriverWait(driver, 10)
        
    def setup_filters(self) -> bool:
        """Complete filter setup using LLM to discover correct selectors"""
        logger.info("🎯 Setting up filters with LLM-guided selector discovery")
        
        # Initial delay to ensure page is fully loaded
        time.sleep(2)
        
        # Step 1: Let LLM analyze the full HTML and discover selectors
        print("🔍 Step 1: LLM analyzing HTML structure to discover selectors...")
        analysis = self._analyze_html_with_llm()
        
        if not analysis or analysis.overall_confidence < 0.3:
            logger.error("❌ LLM analysis failed or confidence too low")
            return False
        
        print(f"✅ LLM analysis completed with {analysis.overall_confidence:.2f} confidence")
        print(f"📝 Structure notes: {analysis.html_structure_notes}")
        
        # Step 2: Handle Requester checkbox using LLM-discovered selector
        print("🔍 Step 2: Setting up Requester filter with LLM selector...")
        if not self._handle_checkbox_with_llm_selector(analysis.requester_checkbox, "Requester", True):
            logger.error("❌ Could not set up Requester filter")
            return False
        
        time.sleep(1)
        
        # Step 3: Get user choice for status filters
        print("🔍 Step 3: Getting user preference for status filters...")
        status_choice = self._get_user_status_choice()
        
        # Step 4: Handle status checkboxes using LLM-discovered selectors
        if status_choice != "both":
            print(f"🔍 Step 4: Configuring status filters for: {status_choice}")
            if not self._handle_status_checkboxes_with_llm(analysis, status_choice):
                logger.warning("⚠️ Could not configure status filters, but continuing...")
            time.sleep(2)
        
        # Step 5: Apply filters using Ctrl+Enter
        print("🔍 Step 5: Applying filters with Ctrl+Enter...")
        if not self._apply_filters_with_ctrl_enter():
            logger.error("❌ Could not apply filters with Ctrl+Enter")
            return False
        
        logger.info("✅ Filter setup completed successfully with LLM guidance")
        return True
    
    def _apply_requester_filter_only(self) -> bool:
        """Apply only the requester filter for bulk analysis (skip status choice)"""
        try:
            logger.info("🎯 Applying requester filter for bulk analysis")
            
            # Analyze HTML to find requester checkbox
            analysis = self._analyze_html_with_llm()
            
            if not analysis or analysis.overall_confidence < 0.3:
                logger.error("❌ LLM analysis failed for requester filter")
                return False
            
            # Handle Requester checkbox
            if not self._handle_checkbox_with_llm_selector(analysis.requester_checkbox, "Requester", True):
                logger.error("❌ Could not set up Requester filter")
                return False
            
            time.sleep(1)
            
            # Apply filters
            if not self._apply_filters_with_ctrl_enter():
                logger.error("❌ Could not apply requester filter")
                return False
            
            logger.info("✅ Requester filter applied successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to apply requester filter: {str(e)}")
            return False
    
    def _analyze_html_with_llm(self) -> FilterAnalysis:
        """Let LLM analyze the complete HTML structure to find checkbox selectors"""
        try:
            # Take screenshot for visual context
            if self.screenshot_manager and callable(self.screenshot_manager):
                screenshot_data = self.screenshot_manager("llm_html_analysis")
            
            # Get the complete HTML, focusing on filter sections
            full_html = self.driver.page_source
            
            # Extract just the filter-related HTML sections to reduce token usage
            filter_html = self._extract_filter_html(full_html)
            
            # Create a comprehensive prompt for LLM analysis
            analysis_prompt = f"""
            You are analyzing a NextRequest public records portal filter interface to find precise selectors for checkboxes.
            
            Your task: Analyze the HTML structure and provide the EXACT selectors needed to target these 3 checkboxes:
            1. "Requester" checkbox (in "My requests" section)
            2. "Open" checkbox (in "Request status" section) 
            3. "Closed" checkbox (in "Request status" section)
            
            REQUIREMENTS:
            - Provide both CSS and XPath options, choose the most reliable one
            - Selectors must be precise and unique to avoid targeting wrong elements
            - Look for patterns in class names, IDs, data attributes, and DOM structure
            - Consider the checkbox input elements, not just labels
            - Analyze the current checked/unchecked state from the HTML
            
            HTML STRUCTURE TO ANALYZE:
            {filter_html}
            
            For each checkbox, provide:
            - The most reliable selector (CSS or XPath)
            - Current state (checked/unchecked)
            - Confidence level
            - Brief reasoning for selector choice
            
            Focus on accuracy over complexity. Simple, unique selectors are preferred.
            """
            
            # Use structured LLM output
            structured_llm = self.llm_client.with_structured_output(FilterAnalysis)
            
            messages = [
                SystemMessage(content="You are an expert at analyzing HTML DOM structures to create precise element selectors. Focus on reliability and uniqueness."),
                HumanMessage(content=analysis_prompt)
            ]
            
            result = structured_llm.invoke(messages)
            
            # Log the LLM's findings
            logger.info(f"🤖 LLM HTML Analysis Results:")
            logger.info(f"   Overall confidence: {result.overall_confidence:.2f}")
            logger.info(f"   Requester: {result.requester_checkbox.selector} (confidence: {result.requester_checkbox.confidence:.2f})")
            logger.info(f"   Open: {result.open_checkbox.selector} (confidence: {result.open_checkbox.confidence:.2f})")
            logger.info(f"   Closed: {result.closed_checkbox.selector} (confidence: {result.closed_checkbox.confidence:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ LLM HTML analysis failed: {str(e)}")
            return None
    
    def _extract_filter_html(self, full_html: str) -> str:
        """Extract just the filter-related HTML sections to reduce token usage"""
        try:
            soup = BeautifulSoup(full_html, 'html.parser')
            
            # Look for filter-related sections
            filter_sections = []
            
            # Find sections containing filter-related text
            for section in soup.find_all(['section', 'div', 'form'], class_=True):
                classes = ' '.join(section.get('class', []))
                if any(keyword in classes.lower() for keyword in ['filter', 'search', 'checkbox']):
                    filter_sections.append(str(section))
            
            # Also look for elements containing specific text
            for element in soup.find_all(text=lambda text: text and any(keyword in text.lower() for keyword in ['my requests', 'request status', 'requester', 'open', 'closed', 'filter'])):
                parent = element.parent
                while parent and parent.name not in ['section', 'div', 'form']:
                    parent = parent.parent
                if parent:
                    filter_sections.append(str(parent))
            
            # Combine and deduplicate
            filter_html = '\n'.join(set(filter_sections))
            
            # If we didn't find specific sections, return a subset of the full HTML
            if len(filter_html.strip()) < 500:
                # Return first 10KB of HTML which should contain the filters
                filter_html = full_html[:10000]
            
            return filter_html
            
        except Exception as e:
            logger.warning(f"⚠️ Could not extract filter HTML, using subset: {str(e)}")
            # Fallback: return first part of HTML
            return full_html[:10000]
    
    def _handle_checkbox_with_llm_selector(self, checkbox_info: CheckboxSelector, name: str, should_be_checked: bool) -> bool:
        """Handle a checkbox using LLM-discovered selector"""
        logger.info(f"🎯 Handling {name} checkbox with LLM selector")
        logger.info(f"   Selector: {checkbox_info.selector}")
        logger.info(f"   Type: {checkbox_info.selector_type}")
        logger.info(f"   Confidence: {checkbox_info.confidence:.2f}")
        logger.info(f"   Reasoning: {checkbox_info.reasoning}")
        
        if not checkbox_info.found or checkbox_info.confidence < 0.5:
            logger.warning(f"⚠️ LLM selector for {name} has low confidence or not found")
            return self._handle_checkbox_fallback(name, should_be_checked)
        
        try:
            # Find element using LLM-provided selector
            if checkbox_info.selector_type.lower() == 'xpath':
                element = self.driver.find_element(By.XPATH, checkbox_info.selector)
            else:
                element = self.driver.find_element(By.CSS_SELECTOR, checkbox_info.selector)
            
            if not element.is_displayed():
                logger.warning(f"⚠️ {name} checkbox found but not displayed")
                return self._handle_checkbox_fallback(name, should_be_checked)
            
            # Set the checkbox to the desired state
            if should_be_checked:
                return self._ensure_checkbox_checked_robust(element, name)
            else:
                return self._ensure_checkbox_unchecked_robust(element, name)
                
        except Exception as e:
            logger.warning(f"⚠️ LLM selector failed for {name}: {str(e)}")
            return self._handle_checkbox_fallback(name, should_be_checked)
    
    def _handle_status_checkboxes_with_llm(self, analysis: FilterAnalysis, status_choice: str) -> bool:
        """Handle Open/Closed checkboxes using LLM-discovered selectors"""
        logger.info(f"🎯 Configuring status checkboxes for: {status_choice}")
        
        success = True
        
        if status_choice == "open":
            # Ensure Open is checked, Closed is unchecked
            success &= self._handle_checkbox_with_llm_selector(analysis.open_checkbox, "Open", True)
            time.sleep(1)
            success &= self._handle_checkbox_with_llm_selector(analysis.closed_checkbox, "Closed", False)
            
        elif status_choice == "closed":
            # Ensure Closed is checked, Open is unchecked  
            success &= self._handle_checkbox_with_llm_selector(analysis.closed_checkbox, "Closed", True)
            time.sleep(1)
            success &= self._handle_checkbox_with_llm_selector(analysis.open_checkbox, "Open", False)
        
        return success
    
    def _ensure_checkbox_checked_robust(self, checkbox, name: str) -> bool:
        """Robust method to ensure checkbox is checked"""
        try:
            # Scroll into view
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", checkbox)
            time.sleep(0.5)
            
            current_state = checkbox.is_selected()
            logger.info(f"🔍 {name} current state: {'checked' if current_state else 'unchecked'}")
            
            if current_state:
                logger.info(f"✅ {name} already checked")
                return True
            
            # Try multiple click strategies
            strategies = [
                ("Standard click", lambda: checkbox.click()),
                ("JavaScript click", lambda: self.driver.execute_script("arguments[0].click();", checkbox)),
                ("Force checked state", lambda: self.driver.execute_script("""
                    arguments[0].checked = true;
                    arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                """, checkbox))
            ]
            
            for strategy_name, action in strategies:
                try:
                    logger.info(f"🎯 Trying {strategy_name} for {name}")
                    action()
                    time.sleep(1)
                    
                    if checkbox.is_selected():
                        logger.info(f"✅ {name} checked with {strategy_name}")
                        return True
                        
                except Exception as e:
                    logger.debug(f"❌ {strategy_name} failed: {str(e)}")
                    continue
            
            logger.error(f"❌ Could not check {name}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking {name}: {str(e)}")
            return False
    
    def _ensure_checkbox_unchecked_robust(self, checkbox, name: str) -> bool:
        """Robust method to ensure checkbox is unchecked"""
        try:
            # Scroll into view
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", checkbox)
            time.sleep(0.5)
            
            current_state = checkbox.is_selected()
            logger.info(f"🔍 {name} current state: {'checked' if current_state else 'unchecked'}")
            
            if not current_state:
                logger.info(f"✅ {name} already unchecked")
                return True
            
            # Try multiple click strategies
            strategies = [
                ("Standard click", lambda: checkbox.click()),
                ("JavaScript click", lambda: self.driver.execute_script("arguments[0].click();", checkbox)),
                ("Force unchecked state", lambda: self.driver.execute_script("""
                    arguments[0].checked = false;
                    arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                """, checkbox))
            ]
            
            for strategy_name, action in strategies:
                try:
                    logger.info(f"🎯 Trying {strategy_name} for {name}")
                    action()
                    time.sleep(1)
                    
                    if not checkbox.is_selected():
                        logger.info(f"✅ {name} unchecked with {strategy_name}")
                        return True
                        
                except Exception as e:
                    logger.debug(f"❌ {strategy_name} failed: {str(e)}")
                    continue
            
            logger.error(f"❌ Could not uncheck {name}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error unchecking {name}: {str(e)}")
            return False
    
    def _handle_checkbox_fallback(self, name: str, should_be_checked: bool) -> bool:
        """Fallback method when LLM selector fails"""
        logger.info(f"🔄 Using fallback method for {name}")
        
        # Simple fallback selectors based on common patterns
        fallback_selectors = [
            f"input[type='checkbox'][name*='{name.lower()}']",
            f"input[type='checkbox'][id*='{name.lower()}']",
            f"//label[contains(text(), '{name}')]//input[@type='checkbox']",
            f"//text()[contains(., '{name}')]/following::input[@type='checkbox'][1]"
        ]
        
        for selector in fallback_selectors:
            try:
                if selector.startswith("//"):
                    element = self.driver.find_element(By.XPATH, selector)
                else:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                
                if element and element.is_displayed():
                    if should_be_checked:
                        return self._ensure_checkbox_checked_robust(element, f"{name} (fallback)")
                    else:
                        return self._ensure_checkbox_unchecked_robust(element, f"{name} (fallback)")
                        
            except:
                continue
        
        logger.error(f"❌ Fallback failed for {name}")
        return False
    
    def _apply_filters_with_ctrl_enter(self) -> bool:
        """Apply filters using Ctrl+Enter keyboard shortcut"""
        logger.info("⌨️ Applying filters with Ctrl+Enter")
        
        try:
            # Focus on body and send Ctrl+Enter
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.CONTROL + Keys.ENTER)
            
            # Wait for page update
            time.sleep(3)
            
            logger.info("✅ Ctrl+Enter sent successfully")
            
            # Basic verification
            current_url = self.driver.current_url
            logger.info(f"📍 URL after filters: {current_url}")
            
            return True
                
        except Exception as e:
            logger.error(f"❌ Error applying filters: {str(e)}")
            return False
    
    def _get_user_status_choice(self) -> str:
        """Ask user for status preference"""
        print("\n" + "="*50)
        print("🔍 REQUEST STATUS FILTER")
        print("="*50)
        print("Which requests do you want to see?")
        print("1. 📋 Open requests only")
        print("2. ✅ Closed requests only") 
        print("3. 📊 Both open and closed")
        print("-"*50)
        
        while True:
            try:
                choice = input("Enter choice (1-3): ").strip()
                
                if choice == "1":
                    print("✅ Selected: Open requests only")
                    return "open"
                elif choice == "2":
                    print("✅ Selected: Closed requests only")
                    return "closed"
                elif choice == "3":
                    print("✅ Selected: Both open and closed")
                    return "both"
                else:
                    print("❌ Please enter 1, 2, or 3")
                    
            except KeyboardInterrupt:
                print("\n👋 Using default: Both")
                return "both"