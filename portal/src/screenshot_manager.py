import base64
import datetime
import logging
from typing import Dict, Any, List
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)

class ScreenshotManager:
    def __init__(self, driver):
        self.driver = driver
        self.screenshots: List[Dict[str, Any]] = []
    
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