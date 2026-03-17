import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import requests
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
import json
            

logger = logging.getLogger(__name__)


class GoogleDriveManager:
    """
    Manages Google Drive operations including token refresh and file uploads.
    Organizes documents in folders by request number.
    """
    
    def __init__(self, supabase_db):
        """
        Initialize Google Drive manager.
        
        Args:
            supabase_db: SupabaseIntegration instance for database operations
        """
        self.db = supabase_db
        self.service = None
        self.current_user_id = None
        self.credentials = None
        
        # Get OAuth credentials from environment
        self.client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            logger.warning("⚠️ Google OAuth credentials not found in environment")
    
    def initialize_for_user(self, user_id: str) -> bool:
        """
        Initialize Google Drive service for a specific user.
        Handles token refresh if needed.
        
        Args:
            user_id: ID of the user
            
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            logger.info(f"🔧 Initializing Google Drive for user {user_id}")
            
            # Get user's Google Drive tokens from database
            tokens = self.db.get_google_drive_tokens(user_id)
            
            if not tokens:
                logger.error(f"❌ No Google Drive tokens found for user {user_id}")
                return False
            
            access_token = tokens['access_token']
            refresh_token = tokens['refresh_token']
            token_expiry = tokens['token_expiry']
            
            # Check if token needs refresh
            if self._is_token_expired(token_expiry):
                logger.info("🔄 Access token expired, refreshing...")
                access_token = self._refresh_access_token(user_id, refresh_token)
                if not access_token:
                    logger.error("❌ Failed to refresh access token")
                    return False
            
            # Store credentials
            self.credentials = {
                'access_token': access_token,
                'refresh_token': refresh_token
            }
            self.current_user_id = user_id
            
            logger.info(f"✅ Google Drive initialized for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Drive: {str(e)}")
            return False
    
    def _is_token_expired(self, token_expiry: str) -> bool:
        """
        Check if access token is expired or expiring soon.
        
        Args:
            token_expiry: ISO format timestamp
            
        Returns:
            True if token is expired or expiring within 5 minutes
        """
        try:
            expiry_dt = datetime.fromisoformat(token_expiry.replace('Z', '+00:00'))
            now = datetime.now()
            
            # Add 5 minute buffer to refresh before actual expiry
            expiry_with_buffer = expiry_dt.replace(tzinfo=None) - timedelta(minutes=5)
            
            is_expired = now >= expiry_with_buffer
            
            if is_expired:
                logger.info(f"Token expired at {token_expiry}")
            
            return is_expired
            
        except Exception as e:
            logger.error(f"Error checking token expiry: {str(e)}")
            return True  # Assume expired if we can't parse
    
    def _refresh_access_token(self, user_id: str, refresh_token: str) -> Optional[str]:
        """
        Refresh the access token using refresh token.
        
        Args:
            user_id: ID of the user
            refresh_token: OAuth refresh token
            
        Returns:
            New access token if successful, None otherwise
        """
        try:
            logger.info("🔄 Refreshing Google Drive access token")
            
            # Call Google's token endpoint
            response = requests.post('https://oauth2.googleapis.com/token', data={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token'
            })
            
            if not response.ok:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return None
            
            token_data = response.json()
            new_access_token = token_data['access_token']
            expires_in = token_data['expires_in']  # seconds
            
            # Calculate new expiry time
            new_expiry = datetime.now() + timedelta(seconds=expires_in)
            new_expiry_iso = new_expiry.isoformat()
            
            # Update database with new token
            self.db.update_google_drive_tokens(user_id, new_access_token, new_expiry_iso)
            
            logger.info(f"✅ Access token refreshed, expires at {new_expiry_iso}")
            return new_access_token
            
        except Exception as e:
            logger.error(f"❌ Failed to refresh access token: {str(e)}")
            return None
    
    def create_request_folder(self, request_number: str, parent_folder_id: str = None) -> Optional[str]:
        """
        Create or find a folder for a specific request in Google Drive.
        
        Args:
            request_number: Request number (e.g., "2024-001")
            parent_folder_id: Optional parent folder ID (defaults to root)
            
        Returns:
            Folder ID if successful, None otherwise
        """
        try:
            if not self.credentials:
                logger.error("Google Drive not initialized")
                return None
            
            folder_name = f"FOIA Request {request_number}"
            
            # First, check if folder already exists
            existing_folder_id = self._find_folder(folder_name, parent_folder_id)
            if existing_folder_id:
                logger.info(f"✅ Found existing folder: {folder_name}")
                return existing_folder_id
            
            # Create new folder
            logger.info(f"📁 Creating folder: {folder_name}")
            
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_folder_id:
                folder_metadata['parents'] = [parent_folder_id]
            
            headers = {
                'Authorization': f'Bearer {self.credentials["access_token"]}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                'https://www.googleapis.com/drive/v3/files',
                json=folder_metadata,
                headers=headers
            )
            
            if not response.ok:
                logger.error(f"Failed to create folder: {response.status_code} - {response.text}")
                return None
            
            folder_data = response.json()
            folder_id = folder_data['id']
            
            logger.info(f"✅ Created folder with ID: {folder_id}")
            return folder_id
            
        except Exception as e:
            logger.error(f"❌ Failed to create request folder: {str(e)}")
            return None
    
    def _find_folder(self, folder_name: str, parent_folder_id: str = None) -> Optional[str]:
        """
        Search for existing folder by name.
        
        Args:
            folder_name: Name of folder to find
            parent_folder_id: Optional parent folder to search within
            
        Returns:
            Folder ID if found, None otherwise
        """
        try:
            # Build query
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            if parent_folder_id:
                query += f" and '{parent_folder_id}' in parents"
            
            headers = {
                'Authorization': f'Bearer {self.credentials["access_token"]}'
            }
            
            params = {
                'q': query,
                'fields': 'files(id, name)',
                'pageSize': 1
            }
            
            response = requests.get(
                'https://www.googleapis.com/drive/v3/files',
                params=params,
                headers=headers
            )
            
            if not response.ok:
                logger.error(f"Failed to search for folder: {response.status_code}")
                return None
            
            results = response.json()
            files = results.get('files', [])
            
            if files:
                return files[0]['id']
            
            return None
            
        except Exception as e:
            logger.error(f"Error searching for folder: {str(e)}")
            return None
    
    def upload_file(
        self,
        local_file_path: str,
        drive_filename: str,
        folder_id: str,
        mime_type: str = None,
        user_email: str = None
    ) -> Optional[Dict[str, str]]:
        """
        Upload a file to Google Drive.

        Args:
            local_file_path: Path to local file
            drive_filename: Name for file in Google Drive
            folder_id: ID of folder to upload to
            mime_type: Optional MIME type (auto-detected if not provided)
            user_email: Optional email for setting file permissions

        Returns:
            Dict with 'file_id' and 'web_link' if successful, None otherwise
        """
        try:
            if not self.credentials:
                logger.error("Google Drive not initialized")
                return None
            
            logger.info(f"📤 Uploading file: {drive_filename}")
            
            # Check file exists
            file_path = Path(local_file_path)
            if not file_path.exists():
                logger.error(f"File not found: {local_file_path}")
                return None
            
            # Auto-detect MIME type if not provided
            if not mime_type:
                mime_type = self._get_mime_type(file_path.suffix)
            
            # Read file content
            with open(local_file_path, 'rb') as f:
                file_content = f.read()
            
            # Upload metadata
            file_metadata = {
                'name': drive_filename,
                'parents': [folder_id]
            }
            
            headers = {
                'Authorization': f'Bearer {self.credentials["access_token"]}'
            }

            # Create multipart message
            boundary = 'upload_boundary'
            
            body = (
                f'--{boundary}\r\n'
                f'Content-Type: application/json; charset=UTF-8\r\n\r\n'
                f'{json.dumps(file_metadata)}\r\n'
                f'--{boundary}\r\n'
                f'Content-Type: {mime_type}\r\n\r\n'
            ).encode('utf-8')
            
            body += file_content
            body += f'\r\n--{boundary}--'.encode('utf-8')
            
            headers['Content-Type'] = f'multipart/related; boundary={boundary}'
            headers['Content-Length'] = str(len(body))
            
            response = requests.post(
                'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart',
                data=body,
                headers=headers
            )
            
            if not response.ok:
                logger.error(f"Upload failed: {response.status_code} - {response.text}")
                return None
            
            file_data = response.json()
            file_id = file_data['id']

            logger.info(f"✅ Uploaded file with ID: {file_id}")

            # Set permissions and get shareable link if user_email provided
            web_link = None
            if user_email:
                web_link = self.set_file_permissions_and_get_link(file_id, user_email)

            return {
                'file_id': file_id,
                'web_link': web_link
            }

        except Exception as e:
            logger.error(f"❌ Failed to upload file: {str(e)}")
            return None

    def download_file(
        self,
        google_drive_file_id: str,
        local_file_path: str
    ) -> bool:
        """
        Download a file from Google Drive.

        Args:
            google_drive_file_id: Google Drive file ID to download
            local_file_path: Local path where file should be saved

        Returns:
            True if download successful, False otherwise
        """
        try:
            if not self.credentials:
                logger.error("Google Drive not initialized")
                return False

            logger.info(f"📥 Downloading file from Google Drive: {google_drive_file_id}")

            # Download file content using Google Drive API
            headers = {
                'Authorization': f'Bearer {self.credentials["access_token"]}'
            }

            # Use alt=media to download file content
            response = requests.get(
                f'https://www.googleapis.com/drive/v3/files/{google_drive_file_id}?alt=media',
                headers=headers,
                stream=True
            )

            if not response.ok:
                logger.error(f"Download failed: {response.status_code} - {response.text}")
                return False

            # Ensure parent directory exists
            local_path = Path(local_file_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file content to local path
            with open(local_file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size = local_path.stat().st_size
            logger.info(f"✅ Downloaded {file_size} bytes to {local_file_path}")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to download file: {str(e)}")
            return False

    def _get_mime_type(self, file_extension: str) -> str:
        """
        Get MIME type for file extension.

        Args:
            file_extension: File extension (e.g., '.pdf')

        Returns:
            MIME type string
        """
        mime_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.txt': 'text/plain',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.zip': 'application/zip'
        }

        return mime_types.get(file_extension.lower(), 'application/octet-stream')

    def set_file_permissions_and_get_link(self, file_id: str, user_email: str) -> Optional[str]:
        """
        Set file permissions for specific user and generate shareable link.

        Args:
            file_id: Google Drive file ID
            user_email: Email address of the user who should have access

        Returns:
            Shareable web link if successful, None otherwise
        """
        try:
            if not self.credentials:
                logger.error("Google Drive not initialized")
                return None

            logger.info(f"🔐 Setting permissions for {user_email} on file {file_id}")

            # Set file permissions for the specific user
            permission_metadata = {
                'type': 'user',
                'role': 'reader',
                'emailAddress': user_email
            }

            headers = {
                'Authorization': f'Bearer {self.credentials["access_token"]}',
                'Content-Type': 'application/json'
            }

            # Create permission
            permission_response = requests.post(
                f'https://www.googleapis.com/drive/v3/files/{file_id}/permissions',
                json=permission_metadata,
                headers=headers
            )

            if not permission_response.ok:
                logger.error(f"Failed to set permissions: {permission_response.status_code} - {permission_response.text}")
                return None

            logger.info(f"✅ Permissions set for {user_email}")

            # Get file metadata including webViewLink
            file_response = requests.get(
                f'https://www.googleapis.com/drive/v3/files/{file_id}',
                params={'fields': 'webViewLink'},
                headers=headers
            )

            if not file_response.ok:
                logger.error(f"Failed to get file metadata: {file_response.status_code}")
                return None

            file_data = file_response.json()
            web_link = file_data.get('webViewLink')

            if web_link:
                logger.info(f"✅ Generated shareable link: {web_link[:50]}...")
            else:
                logger.warning("⚠️ No webViewLink in response")

            return web_link

        except Exception as e:
            logger.error(f"❌ Failed to set permissions and get link: {str(e)}")
            return None
    
    def upload_multiple_files(
        self,
        files: List[Dict[str, str]],
        request_number: str,
        user_email: str = None
    ) -> Dict[str, Any]:
        """
        Upload multiple files to a request folder.

        Args:
            files: List of dicts with 'local_path' and 'filename' keys
            request_number: Request number for folder organization
            user_email: Optional email for setting file permissions

        Returns:
            Dict with results: successful uploads, failed uploads, folder_id
        """
        try:
            logger.info(f"📤 Uploading {len(files)} files for request {request_number}")
            
            # Create/get request folder
            folder_id = self.create_request_folder(request_number)
            if not folder_id:
                return {
                    'success': False,
                    'error': 'Failed to create request folder',
                    'successful_uploads': [],
                    'failed_uploads': files
                }
            
            successful_uploads = []
            failed_uploads = []
            
            # Upload each file
            for file_info in files:
                try:
                    local_path = file_info['local_path']
                    filename = file_info['filename']

                    upload_result = self.upload_file(local_path, filename, folder_id, user_email=user_email)

                    if upload_result and upload_result.get('file_id'):
                        successful_uploads.append({
                            'filename': filename,
                            'file_id': upload_result['file_id'],
                            'web_link': upload_result.get('web_link'),
                            'local_path': local_path
                        })
                    else:
                        failed_uploads.append({
                            'filename': filename,
                            'local_path': local_path,
                            'error': 'Upload failed'
                        })
                        
                except Exception as e:
                    logger.error(f"Failed to upload {file_info.get('filename')}: {str(e)}")
                    failed_uploads.append({
                        'filename': file_info.get('filename', 'unknown'),
                        'local_path': file_info.get('local_path', ''),
                        'error': str(e)
                    })
            
            success_count = len(successful_uploads)
            fail_count = len(failed_uploads)
            
            logger.info(f"📊 Upload complete: {success_count} successful, {fail_count} failed")
            
            return {
                'success': success_count > 0,
                'folder_id': folder_id,
                'successful_uploads': successful_uploads,
                'failed_uploads': failed_uploads,
                'total_files': len(files),
                'success_count': success_count,
                'fail_count': fail_count
            }
            
        except Exception as e:
            logger.error(f"❌ Batch upload failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'successful_uploads': [],
                'failed_uploads': files
            }