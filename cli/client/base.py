"""Base HTTP Client for Learning OS API"""

from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()


class LearningOSError(Exception):
    """Base exception for Learning OS API errors"""

    pass


class APIClient:
    """HTTP client for Learning OS API"""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = 30,
        headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_headers = headers or {}
        self.client = httpx.Client(
            base_url=self.base_url, timeout=timeout, headers=self.default_headers
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response and extract data"""
        try:
            data = response.json()
        except Exception:
            console.print(f"[red]Failed to parse response: {response.text}[/red]")
            raise LearningOSError(
                f"Invalid JSON response: {response.status_code}"
            ) from None

        if response.status_code >= 400:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            console.print(Panel(f"[red]{error_msg}[/red]", title="API Error"))
            raise LearningOSError(f"API Error {response.status_code}: {error_msg}")

        # Handle envelope format (with "ok" field)
        if "ok" in data:
            if not data.get("ok", False):
                error_msg = data.get("error", {}).get("message", "Request failed")
                console.print(Panel(f"[red]{error_msg}[/red]", title="Request Failed"))
                raise LearningOSError(error_msg)
            return data.get("data", {})

        # Handle direct response format (no envelope)
        return data

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make GET request"""
        try:
            # Merge request-specific headers with default headers
            request_headers = {**self.default_headers, **(headers or {})}
            response = self.client.get(
                f"/v1{path}", params=params, headers=request_headers
            )
            return self._handle_response(response)
        except httpx.RequestError as e:
            console.print(f"[red]Connection error: {e}[/red]")
            raise LearningOSError(f"Connection failed: {e}") from None

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make POST request"""
        try:
            # Merge request-specific headers with default headers
            request_headers = {**self.default_headers, **(headers or {})}
            response = self.client.post(
                f"/v1{path}", json=json, headers=request_headers
            )
            return self._handle_response(response)
        except httpx.RequestError as e:
            console.print(f"[red]Connection error: {e}[/red]")
            raise LearningOSError(f"Connection failed: {e}") from None
