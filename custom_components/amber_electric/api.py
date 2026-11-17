"""Async API client for Amber Electric Public API v2.1.0."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import aiohttp

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class AmberApiError(Exception):
    """Base exception for Amber Electric API errors."""


class AmberAuthError(AmberApiError):
    """Exception raised for 401 Unauthorized errors."""


class AmberNotFoundError(AmberApiError):
    """Exception raised for 404 Not Found errors."""


class AmberRateLimitError(AmberApiError):
    """Exception raised when rate limit is exceeded."""


class AmberApiClient:
    """Async client for Amber Electric REST API (/v1)."""

    def __init__(self, api_key: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._api_key = api_key
        self._session = session
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset: int | None = None

    @property
    def _headers(self) -> dict[str, str]:
        """Return authorization headers."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        """Execute an HTTP request against the Amber Electric API."""
        url = f"{API_BASE_URL}{endpoint}"
        headers = self._headers if authenticated else {"Accept": "application/json"}

        try:
            async with asyncio.timeout(20):
                async with self._session.request(
                    method, url, headers=headers, params=params
                ) as response:
                    # Track rate limit headers from OpenAPI spec
                    if "RateLimit-Remaining" in response.headers:
                        try:
                            self.rate_limit_remaining = int(
                                response.headers["RateLimit-Remaining"]
                            )
                        except ValueError:
                            pass
                    if "RateLimit-Reset" in response.headers:
                        try:
                            self.rate_limit_reset = int(
                                response.headers["RateLimit-Reset"]
                            )
                        except ValueError:
                            pass

                    if response.status == 401:
                        raise AmberAuthError("Invalid or missing Amber Electric API key")
                    if response.status == 404:
                        raise AmberNotFoundError(f"Resource not found: {endpoint}")
                    if response.status == 429:
                        raise AmberRateLimitError("Amber Electric API rate limit exceeded")
                    if response.status >= 400:
                        text = await response.text()
                        raise AmberApiError(
                            f"API error {response.status} on {endpoint}: {text}"
                        )

                    return await response.json()
        except (AmberAuthError, AmberNotFoundError, AmberRateLimitError, AmberApiError):
            raise
        except TimeoutError as err:
            raise AmberApiError(f"Timeout connecting to Amber Electric API: {err}") from err
        except aiohttp.ClientError as err:
            raise AmberApiError(f"Network error connecting to Amber Electric API: {err}") from err

    async def get_sites(self) -> list[dict[str, Any]]:
        """Return all sites linked to the account (GET /sites)."""
        return await self._request("GET", "/sites")

    async def get_current_prices(
        self,
        site_id: str,
        next_intervals: int = 48,
        previous_intervals: int = 1,
        resolution: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return current and forecast prices for all channels (GET /sites/{siteId}/prices/current)."""
        params: dict[str, Any] = {
            "next": next_intervals,
            "previous": previous_intervals,
        }
        if resolution in (5, 30):
            params["resolution"] = resolution
        return await self._request("GET", f"/sites/{site_id}/prices/current", params=params)

    async def get_prices(
        self,
        site_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        resolution: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return prices between startDate and endDate (GET /sites/{siteId}/prices)."""
        params: dict[str, Any] = {}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        if resolution in (5, 30):
            params["resolution"] = resolution
        return await self._request("GET", f"/sites/{site_id}/prices", params=params)

    async def get_usage(
        self,
        site_id: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Return usage data between startDate and endDate (GET /sites/{siteId}/usage)."""
        params: dict[str, Any] = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        }
        return await self._request("GET", f"/sites/{site_id}/usage", params=params)

    async def get_current_renewables(
        self,
        state: str,
        next_intervals: int = 12,
        previous_intervals: int = 0,
        resolution: int = 30,
    ) -> list[dict[str, Any]]:
        """Return current percentage of renewables in the state grid (GET /state/{state}/renewables/current)."""
        params: dict[str, Any] = {
            "next": next_intervals,
            "previous": previous_intervals,
            "resolution": resolution,
        }
        return await self._request(
            "GET",
            f"/state/{state.lower()}/renewables/current",
            params=params,
            authenticated=False,
        )
