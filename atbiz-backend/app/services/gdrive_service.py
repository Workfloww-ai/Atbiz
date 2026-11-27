import os
import io
import time
import random
import tempfile
from typing import List, Dict, Any, Generator, Optional
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from app.config import settings, BASE_DIR

# Full Drive scope to allow both reading resumes and auto-creating folders
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveService:
    def __init__(
        self,
        token_path: Optional[str] = None,
        oauth_client_path: Optional[str] = None,
        service_account_path: Optional[str] = None
    ):
        self.token_path = token_path or settings.TOKEN_FILE
        self.oauth_client_path = oauth_client_path or settings.OAUTH_CLIENT_FILE
        self.service_account_path = service_account_path or settings.GOOGLE_SERVICE_ACCOUNT_FILE
        self._service = None

    def execute_with_retry(self, request_fn, max_attempts: int = 5, backoff_base: float = 2.0):
        """
        Executes a Google Drive API request with exponential backoff and jitter.
        Catches 429 (Too Many Requests), 500, 503, and 403 (userRateLimitExceeded).
        Honors Retry-After header when present.
        """
        for attempt in range(max_attempts):
            try:
                return request_fn()
            except HttpError as e:
                is_rate_limit = False
                status = e.resp.status
                if status in (429, 500, 503):
                    is_rate_limit = True
                elif status == 403:
                    error_content = str(e.content).lower()
                    if "ratelimit" in error_content or "userratelimitexceeded" in error_content:
                        is_rate_limit = True

                if is_rate_limit and attempt < max_attempts - 1:
                    # Check Retry-After header
                    retry_after = e.resp.get('retry-after')
                    if retry_after and retry_after.isdigit():
                        sleep_sec = float(retry_after)
                    else:
                        sleep_sec = (backoff_base ** attempt) + random.uniform(0.1, 1.0)
                    time.sleep(sleep_sec)
                    continue
                raise

    def _get_service(self):
        """Lazy initialization of Google Drive API client."""
        if self._service is not None:
            return self._service

        creds = None

        # 1. User OAuth token
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(self.token_path, "w") as token:
                        token.write(creds.to_json())
                except Exception:
                    creds = None

        # 2. User OAuth client secrets
        if not creds and os.path.exists(self.oauth_client_path):
            flow = InstalledAppFlow.from_client_secrets_file(self.oauth_client_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        # 3. Service Account
        candidate_sa_paths = [
            self.service_account_path,
            os.path.join(BASE_DIR, "service_account.json"),
            os.path.join(os.path.dirname(BASE_DIR), "service_account.json"),
            os.path.abspath("service_account.json"),
            os.path.abspath("atbiz-backend/service_account.json"),
        ]
        sa_path = next((p for p in candidate_sa_paths if p and os.path.exists(p)), None)
        if not creds and sa_path:
            creds = service_account.Credentials.from_service_account_file(
                sa_path,
                scopes=SCOPES
            )

        if not creds:
            raise FileNotFoundError(
                "No Google Drive credentials found. Please place 'service_account.json' in 'atbiz-backend/'."
            )

        self._service = build('drive', 'v3', credentials=creds)
        return self._service

    def list_children(self, folder_id: str, mime_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List files and folders directly under a folder ID with retry."""
        service = self._get_service()
        query = f"'{folder_id}' in parents and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"

        results = []
        page_token = None
        while True:
            def req():
                return service.files().list(
                    q=query,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType, webViewLink, size)',
                    pageToken=page_token
                ).execute()

            response = self.execute_with_retry(req)
            results.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return results

    def find_folder(self, folder_name: str, parent_id: str) -> Optional[Dict[str, Any]]:
        """Check if a folder with this name already exists under parent_id."""
        service = self._get_service()
        safe_name = folder_name.replace("'", "\\'")
        query = (
            f"'{parent_id}' in parents and "
            f"name = '{safe_name}' and "
            f"mimeType = 'application/vnd.google-apps.folder' and "
            f"trashed = false"
        )
        def req():
            return service.files().list(
                q=query,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()

        response = self.execute_with_retry(req)
        files = response.get('files', [])
        return files[0] if files else None

    def create_folder(self, folder_name: str, parent_id: str) -> str:
        """Create a new folder under parent_id in Google Drive."""
        service = self._get_service()
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        def req():
            return service.files().create(
                body=file_metadata,
                supportsAllDrives=True,
                fields='id'
            ).execute()

        folder = self.execute_with_retry(req)
        return folder.get('id')

    def get_or_create_folder(self, folder_name: str, parent_id: str) -> str:
        """Smart Folder Resolver."""
        existing = self.find_folder(folder_name, parent_id)
        if existing:
            return existing['id']
        return self.create_folder(folder_name, parent_id)

    def ensure_path(self, path_segments: List[str], root_folder_id: str) -> str:
        """Ensures a nested hierarchy exists. Returns leaf folder ID."""
        current_parent = root_folder_id
        for segment in path_segments:
            current_parent = self.get_or_create_folder(segment, current_parent)
        return current_parent

    def get_whatsapp_folder_id(self) -> str:
        """Get or create the dedicated 'WhatsApp' folder under the root Google Drive folder."""
        root_id = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
        if not root_id:
            raise ValueError("GOOGLE_DRIVE_ROOT_FOLDER_ID is not configured in .env")
        return self.get_or_create_folder("WhatsApp", root_id)

    def upload_file(
        self,
        folder_id: str,
        file_name: str,
        file_bytes: bytes,
        mime_type: str = "application/pdf"
    ) -> Dict[str, Any]:
        """Upload a file directly into a designated Google Drive folder with retry."""
        from googleapiclient.http import MediaIoBaseUpload
        service = self._get_service()
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)

        def req():
            return service.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,
                fields='id, name, webViewLink, size'
            ).execute()

        return self.execute_with_retry(req)

    def download_file_bytes(self, file_id: str, max_size_mb: Optional[int] = None, mime_type: Optional[str] = None) -> bytes:
        """
        Download a file's binary content using temporary file streaming.
        Supports standard files via get_media and Google Docs via export_media.
        Enforces maximum file size chunk-by-chunk to prevent memory exhaustion.
        Guarantees temp file cleanup in a finally block.
        """
        limit_bytes = (max_size_mb or settings.MAX_RESUME_SIZE_MB) * 1024 * 1024
        service = self._get_service()
        if mime_type == 'application/vnd.google-apps.document':
            request = service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
        else:
            request = service.files().get_media(fileId=file_id, supportsAllDrives=True)

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_path = temp_file.name
        try:
            downloader = MediaIoBaseDownload(temp_file, request)
            done = False
            total_bytes = 0
            while not done:
                def req():
                    return downloader.next_chunk()
                status, done = self.execute_with_retry(req)
                if status:
                    total_bytes = status.resumable_progress
                    if total_bytes > limit_bytes:
                        raise ValueError(f"File size exceeds maximum allowed limit of {settings.MAX_RESUME_SIZE_MB}MB")

            temp_file.flush()
            temp_file.close()

            with open(temp_path, 'rb') as f:
                content = f.read()
            return content
        finally:
            if not temp_file.closed:
                temp_file.close()
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def crawl_resumes(self, root_folder_id: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Traverses nested folders (3 levels deep):
        [Root: Atbiz] -> [1. Client] -> [2. Site / State] -> [3. Role] -> [Resumes]
        Also records active file IDs, folder paths, and hierarchy metadata for deletion sync.
        """
        folder_id = root_folder_id or settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
        if not folder_id:
            raise ValueError("GOOGLE_DRIVE_ROOT_FOLDER_ID is not configured in .env")

        self.last_crawl_metadata = {
            "active_file_ids": set(),
            "active_folder_paths": set(),
            "hierarchy": {},
            "completed": False
        }

        folder_mime = 'application/vnd.google-apps.folder'
        max_bytes = settings.MAX_RESUME_SIZE_MB * 1024 * 1024

        # Level 1: Client Folders (e.g. RIL, JLL (Airtel MSC))
        client_folders = self.list_children(folder_id, mime_type=folder_mime)
        for client in client_folders:
            client_name = client['name']

            # Skip staging folders like 'WhatsApp' where unsegregated resumes land
            if client_name.strip().lower() in ("whatsapp", "whatsapp submissions", "trash", "archive"):
                continue

            self.last_crawl_metadata["active_folder_paths"].add(f"/{client_name}")
            self.last_crawl_metadata["hierarchy"].setdefault(client_name, {})

            # Level 2: Site / State Folders (e.g. Delhi, Punjab, UPE)
            site_folders = self.list_children(client['id'], mime_type=folder_mime)
            for site in site_folders:
                site_name = site['name']
                self.last_crawl_metadata["active_folder_paths"].add(f"/{client_name}/{site_name}")
                self.last_crawl_metadata["hierarchy"][client_name].setdefault(site_name, [])

                # Level 3: Role / Designation Folders (e.g. Lobby Assistant, Technician)
                role_folders = self.list_children(site['id'], mime_type=folder_mime)
                for role in role_folders:
                    role_name = role['name']
                    self.last_crawl_metadata["active_folder_paths"].add(f"/{client_name}/{site_name}/{role_name}")
                    if role_name not in self.last_crawl_metadata["hierarchy"][client_name][site_name]:
                        self.last_crawl_metadata["hierarchy"][client_name][site_name].append(role_name)

                    # Files: Resumes (.pdf, .docx, .doc, and Google Docs)
                    files = self.list_children(role['id'])
                    for f in files:
                        fname = f['name'].lower()
                        mime = f.get('mimeType', '')
                        is_gdoc = (mime == 'application/vnd.google-apps.document')
                        if fname.endswith(('.pdf', '.docx', '.doc')) or is_gdoc:
                            self.last_crawl_metadata["active_file_ids"].add(f['id'])
                            # Normalized file name with extension
                            f_display_name = f['name']
                            if is_gdoc and not f_display_name.lower().endswith(('.docx', '.doc', '.pdf')):
                                f_display_name = f"{f_display_name}.docx"

                            # Check metadata size if available
                            reported_size = int(f.get('size', 0)) if f.get('size') else 0
                            if reported_size > max_bytes and not is_gdoc:
                                yield {
                                    "file_id": f['id'],
                                    "file_name": f_display_name,
                                    "client_name": client_name,
                                    "site_name": site_name,
                                    "role_name": role_name,
                                    "folder_path": f"/{client_name}/{site_name}/{role_name}/{f_display_name}",
                                    "error": f"File exceeds {settings.MAX_RESUME_SIZE_MB}MB limit (Reported: {reported_size // (1024*1024)}MB)",
                                    "web_link": f.get('webViewLink'),
                                    "file_bytes": None
                                }
                                continue

                            try:
                                file_bytes = self.download_file_bytes(f['id'], mime_type=mime)
                                yield {
                                    "file_id": f['id'],
                                    "file_name": f_display_name,
                                    "client_name": client_name,
                                    "site_name": site_name,
                                    "role_name": role_name,
                                    "folder_path": f"/{client_name}/{site_name}/{role_name}/{f_display_name}",
                                    "file_bytes": file_bytes,
                                    "web_link": f.get('webViewLink'),
                                    "file_size_bytes": len(file_bytes)
                                }
                            except Exception as dl_err:
                                yield {
                                    "file_id": f['id'],
                                    "file_name": f_display_name,
                                    "client_name": client_name,
                                    "site_name": site_name,
                                    "role_name": role_name,
                                    "folder_path": f"/{client_name}/{site_name}/{role_name}/{f_display_name}",
                                    "error": f"Download failed: {str(dl_err)}",
                                    "web_link": f.get('webViewLink'),
                                    "file_bytes": None
                                }

        self.last_crawl_metadata["completed"] = True

    @classmethod
    def crawl_local_directory(cls, root_path: str) -> Generator[Dict[str, Any], None, None]:
        """Fallback local scanner with metadata tracking for testing."""
        if not os.path.exists(root_path):
            raise FileNotFoundError(f"Local test directory '{root_path}' does not exist.")

        cls.last_crawl_metadata = {
            "active_file_ids": set(),
            "active_folder_paths": set(),
            "hierarchy": {},
            "completed": False
        }

        for client_name in os.listdir(root_path):
            client_path = os.path.join(root_path, client_name)
            if not os.path.isdir(client_path) or client_name.startswith('.'):
                continue

            cls.last_crawl_metadata["active_folder_paths"].add(f"/{client_name}")
            cls.last_crawl_metadata["hierarchy"].setdefault(client_name, {})

            for site_name in os.listdir(client_path):
                site_path = os.path.join(client_path, site_name)
                if not os.path.isdir(site_path) or site_name.startswith('.'):
                    continue

                cls.last_crawl_metadata["active_folder_paths"].add(f"/{client_name}/{site_name}")
                cls.last_crawl_metadata["hierarchy"][client_name].setdefault(site_name, [])

                for role_name in os.listdir(site_path):
                    role_path = os.path.join(site_path, role_name)
                    if not os.path.isdir(role_path) or role_name.startswith('.'):
                        continue

                    cls.last_crawl_metadata["active_folder_paths"].add(f"/{client_name}/{site_name}/{role_name}")
                    if role_name not in cls.last_crawl_metadata["hierarchy"][client_name][site_name]:
                        cls.last_crawl_metadata["hierarchy"][client_name][site_name].append(role_name)

                    for file_name in os.listdir(role_path):
                        if file_name.lower().endswith(('.pdf', '.docx', '.doc')):
                            full_file_path = os.path.join(role_path, file_name)
                            with open(full_file_path, 'rb') as f:
                                file_bytes = f.read()

                            f_id = f"local_{client_name}_{site_name}_{file_name}"
                            cls.last_crawl_metadata["active_file_ids"].add(f_id)

                            yield {
                                "file_id": f_id,
                                "file_name": file_name,
                                "client_name": client_name,
                                "site_name": site_name,
                                "role_name": role_name,
                                "folder_path": f"/{client_name}/{site_name}/{role_name}/{file_name}",
                                "file_bytes": file_bytes,
                                "web_link": None
                            }

        cls.last_crawl_metadata["completed"] = True
