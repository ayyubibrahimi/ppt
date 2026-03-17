import json
import datetime
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SessionManager:
    @staticmethod
    def convert_to_dict(obj):
        """Convert Pydantic models to dictionaries for JSON serialization"""
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        elif hasattr(obj, 'dict'):
            return obj.dict()
        elif isinstance(obj, dict):
            return {k: SessionManager.convert_to_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [SessionManager.convert_to_dict(item) for item in obj]
        else:
            return obj
    
    @staticmethod
    def save_session_results(results: Dict[str, Any], screenshots: list, portal_url: str):
        """Save all screenshots and analysis results to files"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed results as JSON
        json_filename = f"alameda_portal_session_{timestamp}.json"
        json_data = {
            'session_timestamp': timestamp,
            'portal_url': portal_url,
            'total_screenshots': len(screenshots),
            'results': SessionManager.convert_to_dict(results),
            'screenshots_metadata': [
                {
                    'timestamp': s['timestamp'],
                    'url': s['url'], 
                    'title': s['title'],
                    'label': s['label'],
                    'size_bytes': s['screenshot_size']
                }
                for s in screenshots
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
            f.write(f"Portal URL: {portal_url}\n")
            f.write(f"Total Screenshots: {len(screenshots)}\n\n")
            
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
            
            if 'login' in results:
                login = results['login']
                f.write(f"LOGIN ATTEMPT:\n")
                f.write(f"- Success: {login.get('success', 'N/A')}\n")
                if 'error' in login:
                    f.write(f"- Error: {login['error']}\n")
                if 'final_url' in login:
                    f.write(f"- Final URL: {login['final_url']}\n")
                f.write("\n")
        
        logger.info(f"Session results saved to {json_filename} and {summary_filename}")
