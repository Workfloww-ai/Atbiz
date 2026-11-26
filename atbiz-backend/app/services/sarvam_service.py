import hmac
import hashlib
import time
import logging
from typing import Dict, Any, List, Optional
import httpx
from app.config import settings

logger = logging.getLogger("sarvam_service")
logger.setLevel(logging.INFO)


class SarvamAPIError(Exception):
    """Custom exception raised when Sarvam API returns an error or fails."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class SarvamClient:
    """
    Client for interacting with Sarvam AI Voice Agent Campaign APIs.
    All operations are tenant-agnostic at the HTTP client level and parameterized.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        org_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 15.0
    ):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.org_id = org_id or settings.SARVAM_ORG_ID
        self.workspace_id = workspace_id or settings.SARVAM_WORKSPACE_ID
        self.campaign_id = campaign_id or settings.SARVAM_CAMPAIGN_ID
        self.webhook_secret = webhook_secret or settings.SARVAM_WEBHOOK_SECRET
        self.base_url = (base_url or settings.SARVAM_BASE_URL).rstrip("/")
        self.timeout = timeout_seconds

    @property
    def headers(self) -> Dict[str, str]:
        """
        Headers for Sarvam Voice Agent platform calls.
        Includes both API-Subscription-Key and X-API-Key for maximum compatibility.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["API-Subscription-Key"] = self.api_key
            headers["X-API-Key"] = self.api_key
        return headers

    def _cohort_stream_url(self) -> str:
        return (
            f"{self.base_url}/api/scheduling/v1/orgs/{self.org_id}/"
            f"workspaces/{self.workspace_id}/campaigns/{self.campaign_id}/cohorts/stream"
        )

    def _cohort_url(self, cohort_id: str) -> str:
        return (
            f"{self.base_url}/api/scheduling/v1/orgs/{self.org_id}/"
            f"workspaces/{self.workspace_id}/campaigns/{self.campaign_id}/cohorts/{cohort_id}"
        )

    def _campaign_cohorts_url(self) -> str:
        return (
            f"{self.base_url}/api/scheduling/v1/orgs/{self.org_id}/"
            f"workspaces/{self.workspace_id}/campaigns/{self.campaign_id}/cohorts"
        )

    async def stream_cohort(self, cohort_name: str, users: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Submits candidate cohort stream to the existing Sarvam campaign.
        
        Args:
            cohort_name: Deterministic unique cohort identifier (e.g. atbiz_org_20261126_xxxxxx)
            users: List of dicts, each containing:
                - phone_number: E.164 formatted Indian number (+91XXXXXXXXXX)
                - user_id: Screening cycle UUID
                - inputs: Dictionary of candidate & job context variables
        
        Returns:
            Dict containing Sarvam response (e.g. {"cohort_id": "...", "status": "processing"})
        """
        url = self._cohort_stream_url()
        payload = {
            "cohort_name": cohort_name,
            "users": users
        }

        logger.info(f"Submitting cohort stream '{cohort_name}' with {len(users)} user(s) to Sarvam")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)
                if response.status_code in (200, 201, 202):
                    return response.json()
                
                logger.error(f"Sarvam stream cohort failed with status {response.status_code}: {response.text}")
                raise SarvamAPIError(
                    message=f"Sarvam stream cohort rejected with status {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text
                )
            except httpx.TimeoutException as exc:
                logger.error(f"Sarvam stream cohort request timed out for cohort '{cohort_name}': {exc}")
                raise SarvamAPIError(
                    message=f"Sarvam stream cohort timed out after {self.timeout}s",
                    status_code=504
                ) from exc
            except httpx.RequestError as exc:
                logger.error(f"Network error communicating with Sarvam for cohort '{cohort_name}': {exc}")
                raise SarvamAPIError(
                    message=f"Network error communicating with Sarvam: {str(exc)}",
                    status_code=502
                ) from exc

    async def get_cohort_status(self, cohort_id: str) -> Dict[str, Any]:
        """Polls current execution status of a submitted cohort."""
        url = self._cohort_url(cohort_id)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self.headers)
                if response.status_code == 200:
                    return response.json()
                
                raise SarvamAPIError(
                    message=f"Failed to fetch cohort status ({response.status_code})",
                    status_code=response.status_code,
                    response_body=response.text
                )
            except httpx.RequestError as exc:
                raise SarvamAPIError(message=f"Network error polling cohort: {str(exc)}", status_code=502) from exc

    async def find_cohort_by_name(self, cohort_name: str) -> Optional[Dict[str, Any]]:
        """
        Reconciliation helper: Searches campaign cohorts for a cohort matching cohort_name.
        Used when stream_cohort call times out to check if Sarvam successfully received the cohort.
        """
        url = self._campaign_cohorts_url()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params={"cohort_name": cohort_name, "limit": 10}, headers=self.headers)
                if response.status_code == 200:
                    data = response.json()
                    cohorts = data.get("cohorts") or data.get("data") or (data if isinstance(data, list) else [])
                    for c in cohorts:
                        if isinstance(c, dict) and c.get("cohort_name") == cohort_name:
                            return c
                return None
            except Exception as exc:
                logger.warning(f"Failed to lookup cohort by name '{cohort_name}': {exc}")
                return None

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: Optional[str],
        timestamp: Optional[str],
        tolerance_seconds: int = 300
    ) -> bool:
        """
        Verifies Sarvam HMAC-SHA256 signature and prevents replay attacks.
        
        Algorithm:
            expected_signature = hmac_sha256(secret, f"{timestamp}.{raw_body}")
        
        Args:
            raw_body: Exact unmodified byte content of the request body
            signature: Sarvam-Signature header value
            timestamp: Sarvam-Timestamp header value
            tolerance_seconds: Maximum allowed clock drift in seconds (default: 300s / 5 mins)
            
        Returns:
            bool: True if signature is valid and within replay window, False otherwise.
        """
        if not self.webhook_secret:
            logger.warning("SARVAM_WEBHOOK_SECRET is not configured; webhook verification failed.")
            return False

        if not signature or not timestamp:
            logger.warning("Missing Sarvam-Signature or Sarvam-Timestamp header.")
            return False

        # Validate timestamp replay window
        try:
            ts_val = float(timestamp)
            # If timestamp is in milliseconds, normalize to seconds
            if ts_val > 1e11:
                ts_val /= 1000.0

            current_time = time.time()
            if abs(current_time - ts_val) > tolerance_seconds:
                logger.warning(
                    f"Webhook timestamp outside tolerance window: delta={abs(current_time - ts_val):.1f}s > {tolerance_seconds}s"
                )
                return False
        except (ValueError, TypeError):
            logger.warning(f"Invalid Sarvam-Timestamp format: {timestamp}")
            return False

        # Compute HMAC-SHA256
        try:
            signing_string = f"{timestamp}.".encode("utf-8") + raw_body
            expected_mac = hmac.new(
                self.webhook_secret.encode("utf-8"),
                signing_string,
                hashlib.sha256
            ).hexdigest()

            # Constant-time comparison to prevent timing attacks
            return hmac.compare_digest(expected_mac.lower(), signature.strip().lower())
        except Exception as exc:
            logger.error(f"Error computing webhook HMAC signature: {exc}")
            return False


sarvam_client = SarvamClient()
