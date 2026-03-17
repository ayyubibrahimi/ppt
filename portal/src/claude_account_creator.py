"""
Claude SDK-powered account creation fallback for edge cases.

This module provides intelligent account creation when deterministic approaches fail.
It uses Claude Agent SDK with custom MCP tools to handle complex account creation flows
like hidden "Create Account" buttons, multi-step registration, etc.
"""

import time
import logging
from typing import Dict, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

# Feature flag - set to False to disable Claude SDK fallback
ENABLE_CLAUDE_ACCOUNT_CREATION = True


class ClaudeAccountCreator:
    """
    Handles account creation edge cases using Claude Agent SDK.

    This class wraps Selenium driver operations in MCP tools that Claude can use
    to autonomously navigate account creation flows that our deterministic logic can't handle.
    """

    def __init__(self, driver, screenshot_func):
        """
        Initialize the Claude account creator.

        Args:
            driver: Selenium WebDriver instance
            screenshot_func: Function to take screenshots
        """
        self.driver = driver
        self.take_screenshot = screenshot_func

    def create_account_with_claude(self, credentials: Dict[str, str]) -> Dict[str, Any]:
        """
        Use Claude SDK to create an account when deterministic methods fail.

        This is called as a fallback when:
        - Account creation page has unexpected layout
        - "Create Account" button needs to be clicked first
        - Multi-step registration flow

        Args:
            credentials: Dict containing account details:
                - email: User's email
                - password: User's password
                - full_name: User's full name (optional)
                - organization: User's organization (optional)

        Returns:
            Dict with:
                - success: bool
                - method: str ('claude_sdk')
                - cost_usd: float (optional)
                - error: str (if failed)
        """

        if not ENABLE_CLAUDE_ACCOUNT_CREATION:
            return {
                'success': False,
                'error': 'Claude SDK account creation is disabled',
                'method': 'claude_sdk'
            }

        logger.info("=" * 80)
        logger.info("🤖 CLAUDE SDK ACCOUNT CREATION FALLBACK")
        logger.info("=" * 80)
        logger.info("Deterministic account creation failed - using AI-powered fallback")
        logger.info(f"Email: {credentials.get('email')}")

        # Run async Claude SDK in sync context
        try:
            result = asyncio.run(self._run_claude_account_creation(credentials))
            return result
        except Exception as e:
            logger.error(f"❌ Claude SDK account creation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'method': 'claude_sdk'
            }

    async def _run_claude_account_creation(self, credentials: Dict[str, str]) -> Dict[str, Any]:
        """Async implementation of Claude SDK account creation"""

        try:
            from claude_agent_sdk import (
                tool,
                create_sdk_mcp_server,
                ClaudeSDKClient,
                ClaudeAgentOptions,
                AssistantMessage,
                TextBlock,
                ResultMessage
            )
        except ImportError:
            return {
                'success': False,
                'error': 'Claude Agent SDK not installed. Run: pip install claude-agent-sdk',
                'method': 'claude_sdk'
            }

        # Create custom MCP tools that wrap Selenium operations
        @tool("get_page_screenshot", "Get current page screenshot and HTML context", {})
        async def get_screenshot(args):
            """Take screenshot and return page context"""
            try:
                screenshot_b64 = self.driver.get_screenshot_as_base64()
                page_source = self.driver.page_source[:8000]  # First 8k chars for context
                current_url = self.driver.current_url
                page_title = self.driver.title

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Current URL: {current_url}\nPage Title: {page_title}\n\nHTML Preview:\n{page_source}"
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64
                            }
                        }
                    ]
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Error getting screenshot: {str(e)}"}],
                    "isError": True
                }

        @tool("click_element", "Click an element by text content or CSS selector",
              {"identifier": str, "identifier_type": str})
        async def click_element(args):
            """Click an element on the page"""
            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC

                identifier = args["identifier"]
                id_type = args.get("identifier_type", "text")

                element = None
                if id_type == "text":
                    # Try multiple XPath strategies
                    xpaths = [
                        f"//*[contains(text(), '{identifier}')]",
                        f"//button[contains(text(), '{identifier}')]",
                        f"//a[contains(text(), '{identifier}')]",
                        f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{identifier.lower()}')]"
                    ]
                    for xpath in xpaths:
                        try:
                            element = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.XPATH, xpath))
                            )
                            break
                        except:
                            continue
                else:  # css_selector
                    element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, identifier))
                    )

                if not element:
                    raise Exception(f"Could not find clickable element: {identifier}")

                # Scroll into view and click
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.5)
                element.click()
                time.sleep(2)  # Wait for page reaction

                # Take screenshot after click
                screenshot_b64 = self.driver.get_screenshot_as_base64()

                logger.info(f"✅ Clicked element: {identifier}")

                return {
                    "content": [
                        {"type": "text", "text": f"Successfully clicked: {identifier}"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64
                            }
                        }
                    ]
                }
            except Exception as e:
                logger.error(f"❌ Click failed for {args.get('identifier')}: {str(e)}")
                return {
                    "content": [{"type": "text", "text": f"Error clicking element: {str(e)}"}],
                    "isError": True
                }

        @tool("fill_input_field", "Fill an input field by label, placeholder, or name",
              {"field_identifier": str, "value": str})
        async def fill_field(args):
            """Fill an input field"""
            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.common.keys import Keys

                field_id = args["field_identifier"]
                value = args["value"]

                # Try multiple strategies to find the field
                element = None
                strategies = [
                    (By.XPATH, f"//input[@placeholder='{field_id}']"),
                    (By.XPATH, f"//input[contains(@placeholder, '{field_id}')]"),
                    (By.XPATH, f"//label[contains(text(), '{field_id}')]/following::input[1]"),
                    (By.XPATH, f"//label[contains(text(), '{field_id}')]/parent::*/input"),
                    (By.CSS_SELECTOR, f"input[name='{field_id.lower().replace(' ', '_')}']"),
                    (By.CSS_SELECTOR, f"input[name*='{field_id.lower()}']"),
                    (By.CSS_SELECTOR, f"input[id*='{field_id.lower()}']"),
                ]

                for by, selector in strategies:
                    try:
                        element = self.driver.find_element(by, selector)
                        if element.is_displayed() and element.is_enabled():
                            break
                    except:
                        continue

                if not element:
                    raise Exception(f"Could not find field: {field_id}")

                # Scroll into view
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.3)

                # Clear and fill
                element.clear()
                element.send_keys(value)
                element.send_keys(Keys.TAB)  # Trigger validation
                time.sleep(0.5)

                logger.info(f"✅ Filled field '{field_id}' with value")

                return {
                    "content": [{"type": "text", "text": f"Successfully filled '{field_id}'"}]
                }
            except Exception as e:
                logger.error(f"❌ Fill field failed for {args.get('field_identifier')}: {str(e)}")
                return {
                    "content": [{"type": "text", "text": f"Error filling field: {str(e)}"}],
                    "isError": True
                }

        @tool("submit_form", "Submit the current form or click submit button", {})
        async def submit_form(args):
            """Submit the form"""
            try:
                from selenium.webdriver.common.by import By

                # Find submit button
                submit_button = None
                submit_texts = ["Create Account", "Sign Up", "Register", "Create Password", "Submit"]

                for text in submit_texts:
                    try:
                        submit_button = self.driver.find_element(
                            By.XPATH,
                            f"//button[contains(text(), '{text}')]"
                        )
                        if submit_button.is_displayed():
                            break
                    except:
                        continue

                if not submit_button:
                    # Try generic submit button
                    submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")

                # Click submit
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
                time.sleep(0.5)
                submit_button.click()
                time.sleep(3)  # Wait for submission

                # Take screenshot after submission
                screenshot_b64 = self.driver.get_screenshot_as_base64()
                current_url = self.driver.current_url

                logger.info(f"✅ Form submitted, now at: {current_url}")

                return {
                    "content": [
                        {"type": "text", "text": f"Form submitted. Current URL: {current_url}"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64
                            }
                        }
                    ]
                }
            except Exception as e:
                logger.error(f"❌ Form submission failed: {str(e)}")
                return {
                    "content": [{"type": "text", "text": f"Error submitting form: {str(e)}"}],
                    "isError": True
                }

        @tool("check_success", "Check if account creation was successful", {})
        async def check_success(args):
            """Check if we're on a success/confirmation page"""
            try:
                current_url = self.driver.current_url
                page_title = self.driver.title.lower()
                page_source = self.driver.page_source.lower()

                # Success indicators
                success_indicators = [
                    'pending' in current_url,
                    'confirm' in current_url,
                    'success' in page_title,
                    'confirmation' in page_source,
                    'check your email' in page_source,
                    'account created' in page_source,
                ]

                is_success = any(success_indicators)

                return {
                    "content": [{
                        "type": "text",
                        "text": f"Success check: {'✅ SUCCESS' if is_success else '❌ NOT YET'}\nCurrent URL: {current_url}\nPage title: {page_title}"
                    }]
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Error checking success: {str(e)}"}],
                    "isError": True
                }

        # Create MCP server with browser tools
        browser_server = create_sdk_mcp_server(
            name="browser",
            version="1.0.0",
            tools=[get_screenshot, click_element, fill_field, submit_form, check_success]
        )

        # Configure Claude with minimal permissions and budget limits
        options = ClaudeAgentOptions(
            mcp_servers={"browser": browser_server},
            allowed_tools=[
                "mcp__browser__get_page_screenshot",
                "mcp__browser__click_element",
                "mcp__browser__fill_input_field",
                "mcp__browser__submit_form",
                "mcp__browser__check_success"
            ],
            max_turns=20,  # Limit to prevent infinite loops
            max_budget_usd=0.75,  # Cap cost at $0.75
            system_prompt="You are a browser automation assistant. Be efficient and stop as soon as the task is complete."
        )

        # Build the prompt with credentials
        prompt = f"""
I need to create an account on a public records portal. I'm currently on a page that requires account creation.

This portal has a SPECIFIC MULTI-STEP FLOW:

Step 1: Initial page with "Create Account" button
- Click the "Create Account" or "Sign Up" button

Step 2: Login page (you'll be redirected here)
- You'll see a login form asking for email/username and password
- Fill in the email: {credentials['email']}
- Fill in the password: {credentials['password']}
- Click "Sign in" or "Login" button

Step 3: Account creation page (final step)
- You'll be on the actual account setup page
- Fill in the password field: {credentials['password']}
- Fill in the "confirm password" or "re-enter password" field: {credentials['password']}
- Click "Create Password" or "Create Account" button

Step 4: Success
- You should land on a confirmation page or a URL containing "/requests/"
- Check for success

Credentials to use:
- Email: {credentials['email']}
- Password: {credentials['password']}
- Full Name: {credentials.get('full_name', credentials['email'].split('@')[0])}
{f"- Organization: {credentials['organization']}" if credentials.get('organization') else ""}

Important notes:
- The email/password will be entered TWICE - once on login page, once on account creation page
- Don't be confused by seeing a login form - that's expected, just fill it and continue
- Be efficient but thorough
- Stop immediately once you see a success/confirmation page or a URL with "/requests/"
- If you encounter an error, report it clearly

Begin by taking a screenshot to assess the current situation.
"""

        # Run Claude SDK
        success = False
        cost_usd = 0.0
        error_msg = None

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_lower = block.text.lower()
                            # Check for success indicators in Claude's responses
                            if any(phrase in text_lower for phrase in
                                   ['success', 'account created', 'confirmation', 'pending email']):
                                success = True
                            # Check for failure indicators
                            if any(phrase in text_lower for phrase in
                                   ['failed', 'error', 'could not', 'unable to']):
                                error_msg = block.text

                elif isinstance(msg, ResultMessage):
                    cost_usd = msg.total_cost_usd
                    logger.info(f"💰 Claude SDK cost: ${cost_usd:.4f}")

        # Final verification - check URL for success indicators
        final_url = self.driver.current_url
        final_url_lower = final_url.lower()

        # Check for success indicators in URL
        if any(indicator in final_url_lower for indicator in ['pending', 'confirm', 'success', '/requests/']):
            success = True

        # Extract request number from URL if present
        # URL format: https://scc-sheriffca.nextrequest.com/requests/25-452?email=...
        request_number = None
        if '/requests/' in final_url:
            try:
                # Extract request number (e.g., "25-452")
                url_parts = final_url.split('/requests/')[1]
                request_number = url_parts.split('?')[0].split('#')[0]
                logger.info(f"📋 Extracted request number from URL: {request_number}")
            except Exception as e:
                logger.warning(f"⚠️ Could not extract request number from URL: {str(e)}")

        result = {
            'success': success,
            'method': 'claude_sdk',
            'cost_usd': cost_usd,
            'request_number': request_number,
            'final_url': final_url
        }

        if not success and error_msg:
            result['error'] = error_msg

        if success:
            logger.info("✅ Claude SDK account creation successful!")
            if request_number:
                logger.info(f"   Request number: {request_number}")
        else:
            logger.warning(f"⚠️ Claude SDK account creation may have failed")

        return result
