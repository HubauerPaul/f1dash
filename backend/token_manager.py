"""OAuth2 Token Manager for OpenF1 API.

Automatically obtains and refreshes access tokens using
username/password credentials. Tokens are refreshed proactively
before they expire.
"""

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger("f1dash.token")

TOKEN_URL = "https://api.openf1.org/token"
# Refresh 5 minutes before expiry to avoid race conditions
REFRESH_BUFFER_SECONDS = 300


class TokenManager:
    """Manages OAuth2 access tokens with automatic refresh."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._access_token: Optional[str] = None
        self._expires_at: float = 0  # Unix timestamp
        self._refresh_lock = asyncio.Lock()
        self._http = httpx.AsyncClient(timeout=15.0)

    @property
    def token(self) -> Optional[str]:
        """Current access token, or None if not yet obtained."""
        return self._access_token

    @property
    def is_valid(self) -> bool:
        """Check if current token is still valid (with buffer)."""
        if not self._access_token:
            return False
        return time.time() < (self._expires_at - REFRESH_BUFFER_SECONDS)

    @property
    def expires_in(self) -> float:
        """Seconds until token expires (negative = expired)."""
        return self._expires_at - time.time()

    async def ensure_valid_token(self) -> Optional[str]:
        """Get a valid token, refreshing if necessary.

        Thread-safe: uses a lock to prevent multiple simultaneous
        refresh attempts.
        """
        if self.is_valid:
            return self._access_token

        async with self._refresh_lock:
            # Double-check after acquiring lock
            if self.is_valid:
                return self._access_token
            return await self._fetch_token()

    async def _fetch_token(self) -> Optional[str]:
        """Request a new access token from the API."""
        if not self.username or not self.password:
            logger.warning("No OpenF1 credentials configured — running unauthenticated")
            return None

        try:
            resp = await self._http.post(
                TOKEN_URL,
                data={
                    "username": self.username,
                    "password": self.password,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

            self._access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))
            self._expires_at = time.time() + expires_in

            logger.info(
                f"Token refreshed — valid for {expires_in}s "
                f"(expires at {time.strftime('%H:%M:%S', time.localtime(self._expires_at))})"
            )
            return self._access_token

        except httpx.HTTPStatusError as e:
            logger.error(f"Token request failed: HTTP {e.response.status_code} — {e.response.text}")
            return self._access_token  # Return old token if still set
        except Exception as e:
            logger.error(f"Token request error: {e}")
            return self._access_token

    async def get_auth_headers(self) -> dict:
        """Get Authorization headers with a valid token."""
        token = await self.ensure_valid_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def close(self):
        await self._http.aclose()
