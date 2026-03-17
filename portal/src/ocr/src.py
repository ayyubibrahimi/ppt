import os
import json
import pdf2image
import azure
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials
from io import BytesIO
import time
import logging
from PIL import Image
import PIL
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import easyocr
import numpy as np
import cv2
from multiprocessing import cpu_count
from dotenv import load_dotenv

load_dotenv()

def getcreds():
    """
    Get Azure Computer Vision credentials from environment variables.

    Returns:
        tuple: (endpoint, api_key)
    """
    endpoint = os.getenv('AZURE_CV_ENDPOINT')
    api_key = os.getenv('AZURE_CV_API_KEY')

    if not endpoint or not api_key:
        raise ValueError(
            "Azure Computer Vision credentials not found. "
            "Please set AZURE_CV_ENDPOINT and AZURE_CV_API_KEY in .env file"
        )

    return endpoint.strip(), api_key.strip()

class DocClient:
    def __init__(self, endpoint, key):
        self.client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(key))
        self.easyocr_reader = None  # Lazy-load to save memory

    def _get_easyocr_reader(self):
        """Lazy-load EasyOCR reader only when needed"""
        if self.easyocr_reader is None:
            self.easyocr_reader = easyocr.Reader(['en'], gpu=False, detect_network='craft', recog_network='english_g2')
        return self.easyocr_reader

    def close(self):
        """Clean up resources"""
        try:
            if self.client:
                self.client.close()
        except Exception as e:
            logging.warning(f"Error closing Azure CV client: {e}")

        # Clean up EasyOCR reader if initialized
        if self.easyocr_reader is not None:
            try:
                del self.easyocr_reader
                self.easyocr_reader = None
            except Exception as e:
                logging.warning(f"Error cleaning up EasyOCR reader: {e}")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self.close()

    def extract_content(self, result):
        contents = {}
        for read_result in result.analyze_result.read_results:
            lines = read_result.lines
            lines.sort(key=lambda line: line.bounding_box[1])

            if not lines:
                contents[f"page_{read_result.page}"] = ""
                continue
            page_height = max(line.bounding_box[7] for line in lines)
            header_height = footer_height = page_height * 0.01

            page_content = []
            for line in lines:
                if header_height < line.bounding_box[1] < (page_height - footer_height):
                    page_content.append(" ".join([word.text for word in line.words]))

            contents[f"page_{read_result.page}"] = "\n".join(page_content)

        return contents

    def process_with_easyocr(self, image_data):
        # Convert image data to format suitable for EasyOCR
        img = np.array(Image.open(image_data))
        
        # Preprocess the image
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        
        # Apply adaptive thresholding
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        # Perform OCR using EasyOCR
        result = self._get_easyocr_reader().readtext(binary)
        
        # Sort results by vertical position
        sorted_result = sorted(result, key=lambda x: x[0][0][1])
        
        # Extract text
        return "\n".join([text for _, text, _ in sorted_result])

    def process_page(self, pdf_data, page_num):
        """
        Process a single page and return OCR result.

        Returns:
            dict with 'page_content', 'page_number', and 'ocr_method'
        """
        try:
            image = pdf2image.convert_from_bytes(
                pdf_data, dpi=500, first_page=page_num, last_page=page_num
            )[0]

            # Check image dimensions
            width, height = image.size
            total_pixels = width * height
            MAX_PIXELS = 25000000  # 25 megapixels threshold

            if total_pixels > MAX_PIXELS:
                logging.warning(f"Image size ({width}x{height}={total_pixels} pixels) exceeds threshold of {MAX_PIXELS} pixels for page {page_num}")
                return {
                    "page_content": "This input is an image, no content to parse",
                    "page_number": page_num,
                    "ocr_method": "skipped"
                }

            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format="PNG")
            img_byte_arr.seek(0)

            ocr_method = "azure_cv"
            try:
                # Try Azure OCR first
                ocr_result = self.client.read_in_stream(img_byte_arr, raw=True)
                operation_id = ocr_result.headers["Operation-Location"].split("/")[-1]

                while True:
                    result = self.client.get_read_result(operation_id)
                    if result.status.lower() not in ["notstarted", "running"]:
                        break
                    time.sleep(1)

                if result.status.lower() == "failed":
                    raise azure.core.exceptions.HttpResponseError("Azure OCR failed")

                page_content = self.extract_content(result)

            except Exception as e:
                logging.warning(f"Azure OCR failed for page {page_num}, falling back to EasyOCR: {str(e)}")
                # Fallback to EasyOCR
                img_byte_arr.seek(0)  # Reset stream position
                page_content = {f"page_1": self.process_with_easyocr(img_byte_arr)}
                ocr_method = "easyocr"

            return {
                "page_content": page_content[f"page_1"],
                "page_number": page_num,
                "ocr_method": ocr_method
            }

        except PIL.Image.DecompressionBombError:
            logging.warning(f"Image size exceeds PIL limit for page {page_num}")
            return {
                "page_content": "This input is an image, no content to parse",
                "page_number": page_num,
                "ocr_method": "skipped"
            }

        except Exception as e:
            logging.error(f"Error processing page {page_num}: {str(e)}")
            return None

    def pdf2df(self, pdf_path):
        """
        Legacy method - processes PDF and returns list of page results.
        Kept for backward compatibility with existing CLI usage.
        """
        with open(pdf_path, "rb") as file:
            pdf_data = file.read()

        num_pages = pdf2image.pdfinfo_from_bytes(pdf_data)["Pages"]

        # Use all available CPUs for processing
        max_workers = cpu_count()

        # Calculate chunk size based on number of pages and CPUs
        chunk_size = max(1, num_pages // max_workers)

        def process_chunk(start_page, end_page):
            chunk_results = []
            for page_num in range(start_page, min(end_page, num_pages + 1)):
                result = self.process_page(pdf_data, page_num)
                if result:
                    chunk_results.append(result)
            return chunk_results

        with ThreadPoolExecutor() as executor:
            future_to_chunk = {
                executor.submit(process_chunk, i, i + chunk_size): i
                for i in range(1, num_pages + 1, chunk_size)
            }

            all_results = []
            for future in as_completed(future_to_chunk):
                try:
                    chunk_results = future.result()
                    all_results.extend(chunk_results)
                except Exception as exc:
                    logging.error(f'Chunk processing generated an exception: {exc}')

        all_results.sort(key=lambda x: x["page_number"])
        return all_results

    def process_pdf_to_data(self, pdf_path):
        """
        Process PDF and return structured OCR data (for integration with document pipeline).

        Args:
            pdf_path: Path to PDF file

        Returns:
            dict: {
                'ocr_data': {
                    'ocr_timestamp': '...',
                    'ocr_method': 'azure_cv' or 'mixed' or 'easyocr',
                    'page_texts': [
                        {'page_number': 1, 'text': '...'},
                        {'page_number': 2, 'text': '...'}
                    ]
                },
                'num_pages': int,
                'file_size_bytes': int
            }
        """
        from datetime import datetime
        import os

        logging.info(f"🔍 Starting OCR processing for: {os.path.basename(pdf_path)}")

        # Get file size
        file_size_bytes = os.path.getsize(pdf_path)

        # Process all pages
        page_results = self.pdf2df(pdf_path)

        # Determine overall OCR method used
        methods_used = set(page.get('ocr_method', 'azure_cv') for page in page_results)
        if len(methods_used) == 1:
            overall_method = methods_used.pop()
        elif 'azure_cv' in methods_used and 'easyocr' in methods_used:
            overall_method = 'mixed'
        elif 'easyocr' in methods_used:
            overall_method = 'easyocr'
        else:
            overall_method = 'azure_cv'

        # Convert to new format
        page_texts = [
            {
                'page_number': page['page_number'],
                'text': page['page_content']
            }
            for page in page_results
        ]

        ocr_data = {
            'ocr_data': {
                'ocr_timestamp': datetime.now().isoformat(),
                'ocr_method': overall_method,
                'page_texts': page_texts
            },
            'num_pages': len(page_results),
            'file_size_bytes': file_size_bytes
        }

        logging.info(f"✅ OCR complete: {len(page_results)} pages, method: {overall_method}")

        return ocr_data

    def process(self, pdf_path, output_dir):
        outname = os.path.basename(pdf_path).replace(".pdf", "")
        outstring = os.path.join(output_dir, "{}.json".format(outname))
        outpath = os.path.abspath(outstring)

        if os.path.exists(outpath):
            logging.info(f"skipping {outpath}, file already exists")
            return outpath

        logging.info(f"sending document {outname}")

        page_results = self.pdf2df(pdf_path)

        with open(outpath, "w") as f:
            json.dump({"messages": page_results}, f, indent=4)

        logging.info(f"finished writing to {outpath}")
        return outpath

def update_page_keys_in_json(json_file):
    with open(json_file, "r") as f:
        data = json.load(f)

    corrected_messages = []
    for page in data["messages"]:
        page_number = page["page_number"]
        corrected_messages.append({
            "page_content": page["page_content"],
            "page_number": page_number
        })

    with open(json_file, "w") as f:
        json.dump({"messages": corrected_messages}, f, indent=4)

def reformat_json_structure(json_file):
    with open(json_file, "r") as f:
        data = json.load(f)

    new_messages = []
    for page in data["messages"]:
        new_messages.append({
            "page_content": page["page_content"],
            "page_number": page["page_number"]
        })

    new_data = {"messages": new_messages}

    with open(json_file, "w") as f:
        json.dump(new_data, f, indent=4)

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    azurelogger = logging.getLogger("azure")
    azurelogger.setLevel(logging.ERROR)

    input_dir = "../data/input"
    output_base_dir = "../data/output"
    output_index_path = os.path.join(output_base_dir, "processing_index.csv")

    # Create output directory if it doesn't exist
    os.makedirs(output_base_dir, exist_ok=True)

    # Get list of all PDFs in input directory
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    
    # Create or update the index DataFrame
    index_data = []
    for pdf_file in pdf_files:
        pdf_path = os.path.join(input_dir, pdf_file)
        filename = os.path.splitext(pdf_file)[0]
        output_dir = os.path.join(output_base_dir, filename)
        json_path = os.path.join(output_dir, f"{filename}.json")
        
        os.makedirs(output_dir, exist_ok=True)
        index_data.append({
            'filename': filename,
            'pdf_path': pdf_path,
            'json_path': json_path,
            'status': 'pending',
            'error_message': ''
        })
    
    df = pd.DataFrame(index_data)
    df.to_csv(output_index_path, index=False)

    endpoint, key = getcreds()
    client = DocClient(endpoint, key)

    start_time = time.time()
    total_files = len(df)
    processed_files = 0

    for idx, row in df.iterrows():
        pdf_path = row['pdf_path']
        output_dir = os.path.dirname(row['json_path'])
        
        if not os.path.exists(pdf_path):
            logger.warning(f"PDF file not found at {pdf_path}")
            df.at[idx, 'status'] = 'failed'
            df.at[idx, 'error_message'] = 'PDF file not found'
            df.to_csv(output_index_path, index=False)
            continue
            
        file_start_time = time.time()
        
        try:
            # Process the PDF
            json_file_path = client.process(pdf_path, output_dir)
            if json_file_path:
                update_page_keys_in_json(json_file_path)
                reformat_json_structure(json_file_path)
                processed_files += 1

                file_end_time = time.time()
                file_duration = file_end_time - file_start_time
                logger.info(f"Processed {os.path.basename(pdf_path)} in {file_duration:.2f} seconds")
                
                df.at[idx, 'status'] = 'success'
                df.to_csv(output_index_path, index=False)
                
        except pdf2image.exceptions.PDFPageCountError as e:
            error_msg = f"PDF Page Count Error: {str(e)}"
            logger.error(f"Error processing {pdf_path}: {error_msg}")
            df.at[idx, 'status'] = 'failed'
            df.at[idx, 'error_message'] = error_msg
            df.to_csv(output_index_path, index=False)
            
        except Exception as e:
            error_msg = f"Processing Error: {str(e)}"
            logger.error(f"Error processing {pdf_path}: {error_msg}")
            df.at[idx, 'status'] = 'failed'
            df.at[idx, 'error_message'] = error_msg
            df.to_csv(output_index_path, index=False)
            
        # Log progress periodically
        if (idx + 1) % 10 == 0:
            elapsed_time = time.time() - start_time
            avg_time = elapsed_time / (idx + 1)
            remaining_files = total_files - (idx + 1)
            estimated_remaining_time = remaining_files * avg_time
            logger.info(f"Progress: {idx + 1}/{total_files} files processed")
            logger.info(f"Estimated remaining time: {estimated_remaining_time/60:.2f} minutes")

    client.close()

    end_time = time.time()
    total_duration = end_time - start_time
    
    logger.info(f"Total processing time: {total_duration:.2f} seconds")
    logger.info(f"Total files processed: {processed_files} out of {total_files}")
    if processed_files > 0:
        average_time = total_duration / processed_files
        logger.info(f"Average time per file: {average_time:.2f} seconds")

if __name__ == "__main__":
    main()