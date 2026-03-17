import json
import logging


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def load_pages_from_file_data(file_data, file_index):
    """
    Load pages from a single file's data within a case JSON.
    
    Args:
        file_data: Dict with OCR data in ocr_doc_text_per_page.page_texts
        file_index: The file index/identifier
        
    Returns:
        List of page dictionaries sorted by page number
    """
    # Navigate to the actual OCR data
    ocr_data = file_data.get('ocr_doc_text_per_page', {})
    page_texts = ocr_data.get('page_texts', [])
    
    if not page_texts:
        logger.warning(f"File {file_index} has no page_texts")
        return []
    
    pages = []
    for page_data in page_texts:
        pages.append({
            'page_number': page_data['page_number'],
            'page_content': page_data['text'],
            'sha1': file_data.get('sha1', f"file_{file_index}")
        })
    
    return sorted(pages, key=lambda x: x['page_number'])


