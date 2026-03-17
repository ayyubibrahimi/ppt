import logging, lxml.html, re, requests
from math import ceil
from pathlib import Path
from typing import Optional, Dict, Any, List
from tenacity import (
    retry,
    stop_after_attempt,
    wait_incrementing,
    before_sleep_log,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_csrf(page_txt: str):
    page = lxml.html.fromstring(page_txt)
    if meta_element := page.xpath("//meta[@name='csrf-token']"):
        return meta_element[0].get("content")
    return None


def find_max_pages(item_count: int, page_size: int):
    return ceil(item_count / page_size)


def make_download_path(document, outputdir):
    """
    Create download path for a document.
    Exported as a module-level function for use by coordinator.
    """
    filename = document['title']
    outpath = Path(outputdir)
    if not re.search(r'\.\w+$', filename):
        assert document['file_extension'], f"Document {document['title']} does not have a file extension"
        filename += document['file_extension']
    if document.get('folder_name', None):
        outpath = outpath / document['folder_name']
    if document.get('subfolder_name', None):
        outpath = outpath / document['subfolder_name']
    # to avoid collisions, we'll put each document in a folder named by its ID
    outpath = outpath / str(document['id'])
    outpath.mkdir(parents=True, exist_ok=True)
    return outpath / filename


class NextRequest:
    """
    NextRequest portal scraper for downloading FOIA documents.
    Used by DocumentDownloadCoordinator for automated downloads.
    """
    
    def __init__(
            self, url: str, request_id: str = '', outputdir: str = None,
            username: Optional[str] = None, password: Optional[str] = None,
            **kwargs
    ) -> None:
        """
        Initialize NextRequest scraper.
        
        Args:
            url: Portal URL (e.g., "https://agency.nextrequest.com/")
            request_id: Request ID to download documents from (e.g., "2024-001")
            outputdir: Output directory for downloads
            username: Optional portal username for authentication
            password: Optional portal password for authentication
        """
        # Normalize URL: strip whitespace and trailing slashes to prevent double slashes
        # when concatenating with API endpoints (e.g., /client/request_documents)
        normalized_url = url.strip().rstrip('/')

        # Remove /users/sign_in path if present - this is ONLY for authentication,
        # not the base URL for API endpoints
        if normalized_url.endswith('/users/sign_in'):
            normalized_url = normalized_url[:-len('/users/sign_in')]

        self.url = normalized_url
        self.request_id = request_id
        self.outputdir = Path(outputdir) if outputdir else Path('.')
        self.session = requests.Session()
        self.session.headers["user-agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        self.document_metadata = None
        
        # Authenticate if credentials provided
        if username and password:
            self._authenticate(username, password)

    def _authenticate(self, username: str, password: str):
        """
        Authenticate to the NextRequest portal.

        Args:
            username: Portal username/email
            password: Portal password
        """
        try:
            logger.info(f"🔐 Authenticating to {self.url}")

            # Build sign-in URL - check if /users/sign_in already exists in URL
            base_url = self.url.rstrip('/')
            if base_url.endswith('/users/sign_in'):
                signin_url = base_url
            else:
                signin_url = f"{base_url}/users/sign_in"

            signin_page = self.session.get(signin_url)
            signin_page.raise_for_status()

            csrf = get_csrf(signin_page.content)
            self.session.headers.update({"x-csrf-token": csrf})

            payload = {
                "authenticity_token": self.session.headers["x-csrf-token"],
                "user[email]": username,
                "user[password]": password,
            }

            resp = self.session.post(signin_url, params=payload)
            resp.raise_for_status()
            
            logger.info("✅ Authentication successful")
            
        except Exception as e:
            logger.error(f"❌ Authentication failed: {str(e)}")
            raise

    def get_document_metadata(self) -> Dict[str, Any]:
        """
        Retrieve document metadata from the portal.
        Supports both all documents and request-specific documents.
        
        Returns:
            Dict with 'documents' list and total count
        """
        if self.document_metadata is not None:
            return self.document_metadata
        
        try:
            logger.info(f"📥 Fetching document metadata for request {self.request_id}")
            
            page_size = 25
            
            # Choose endpoint based on whether we have a request_id
            if self.request_id == '':
                params = dict(page_size=page_size, page_number=1)
                first_response = self.session.get(
                    f"{self.url}/client/documents", params=params
                )
            else:
                params = dict(request_id=self.request_id, page_size=page_size, page_number=1)
                first_response = self.session.get(
                    f"{self.url}/client/request_documents", params=params
                )
            
            first_response.raise_for_status()
            accumulated_documents = first_response.json()
            
            # Get total document count
            if 'total_documents_count' in accumulated_documents:
                total_documents = accumulated_documents['total_documents_count']
            elif 'total_count' in accumulated_documents:
                total_documents = accumulated_documents['total_count']
            else:
                logger.warning("Could not find document count in response")
                total_documents = len(accumulated_documents.get('documents', []))
            
            n_pages = find_max_pages(total_documents, page_size)
            logger.info(f"📊 Total documents: {total_documents} across {n_pages} pages")
            
            # Fetch remaining pages if needed
            if n_pages > 1:
                logger.info(f'📥 Retrieving {n_pages-1} additional pages of metadata')
                for page_number in range(2, n_pages + 1):
                    params['page_number'] = page_number
                    
                    if self.request_id == '':
                        resp = self.session.get(
                            f"{self.url}/client/documents", params=params
                        )
                    else:
                        resp = self.session.get(
                            f"{self.url}/client/request_documents", params=params
                        )
                    
                    resp.raise_for_status()
                    resp_json = resp.json()
                    accumulated_documents['documents'].extend(resp_json['documents'])
            
            # Verify we got all documents
            actual_count = len(accumulated_documents['documents'])
            if actual_count != total_documents:
                logger.warning(f"⚠️ Expected {total_documents} documents but got {actual_count}")
            
            self.document_metadata = accumulated_documents
            logger.info(f"✅ Retrieved metadata for {actual_count} documents")
            
            return accumulated_documents
            
        except Exception as e:
            logger.error(f"❌ Failed to get document metadata: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_incrementing(30, 30, 300),
        before_sleep=before_sleep_log(logger, logging.INFO),
    )
    def download_document(self, document: Dict[str, Any], output: Path):
        """
        Download a single document from the portal.
        
        Args:
            document: Document metadata dict with 'id' field
            output: Output path for the downloaded file
        """
        try:
            logger.info(f"📥 Downloading document {document['id']}: {document.get('title', 'Untitled')}")
            
            with self.session.get(
                f"{self.url}/documents/{document['id']}/download",
                stream=True,
            ) as r:
                r.raise_for_status()
                with open(output, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            logger.info(f"✅ Downloaded to: {output}")
            
        except Exception as e:
            logger.error(f"❌ Failed to download document {document['id']}: {str(e)}")
            raise

    def download_all_documents(self):
        """
        Download all documents for the request.
        Creates folder structure based on document metadata.
        """
        try:
            logger.info(f"📥 Starting bulk download to {self.outputdir}")
            
            outputdir = self.outputdir
            document_metadata = self.get_document_metadata()
            documents = document_metadata['documents']
            
            # Verify no path collisions
            all_ids = set(document['id'] for document in documents)
            download_paths = set(make_download_path(document, outputdir) for document in documents)
            assert len(all_ids) <= len(download_paths), "collision in download paths"
            
            logger.info(f"📊 Downloading {len(all_ids)} documents to {outputdir}")
            
            # Download each document
            downloaded_count = 0
            skipped_count = 0
            
            for document in documents:
                output = make_download_path(document, outputdir)
                
                if not output.exists():
                    self.download_document(document, output)
                    downloaded_count += 1
                else:
                    logger.info(f"⏭️ Skipping existing file: {output.name}")
                    skipped_count += 1
            
            logger.info(f"✅ Download complete: {downloaded_count} downloaded, {skipped_count} skipped")
            
        except Exception as e:
            logger.error(f"❌ Bulk download failed: {str(e)}")
            raise
    
    def download_specific_documents(self, document_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Download specific documents by ID.
        Used by coordinator to download only classified documents.
        
        Args:
            document_ids: List of document IDs to download
            
        Returns:
            List of dicts with download results (path, size, etc.)
        """
        try:
            logger.info(f"📥 Downloading {len(document_ids)} specific documents")
            
            # Get all document metadata
            document_metadata = self.get_document_metadata()
            all_documents = document_metadata['documents']
            
            # Filter to requested documents
            documents_to_download = [
                doc for doc in all_documents 
                if str(doc['id']) in [str(did) for did in document_ids]
            ]
            
            if len(documents_to_download) != len(document_ids):
                found_ids = [doc['id'] for doc in documents_to_download]
                missing_ids = set(document_ids) - set(str(fid) for fid in found_ids)
                logger.warning(f"⚠️ Could not find documents: {missing_ids}")
            
            # Download each document
            downloaded_files = []
            
            for document in documents_to_download:
                try:
                    output = make_download_path(document, self.outputdir)
                    
                    if not output.exists():
                        self.download_document(document, output)
                    
                    if output.exists():
                        file_size = output.stat().st_size
                        downloaded_files.append({
                            'document_id': document['id'],
                            'title': document['title'],
                            'local_path': str(output),
                            'filename': output.name,
                            'size_bytes': file_size
                        })
                    
                except Exception as e:
                    logger.error(f"❌ Failed to download document {document['id']}: {str(e)}")
                    continue
            
            logger.info(f"✅ Successfully downloaded {len(downloaded_files)}/{len(document_ids)} documents")
            return downloaded_files
            
        except Exception as e:
            logger.error(f"❌ Specific document download failed: {str(e)}")
            return []