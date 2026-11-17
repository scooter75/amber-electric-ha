"""DataUpdateCoordinator for Amber Electric."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AmberApiClient, AmberApiError, AmberAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AmberDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Amber Electric data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AmberApiClient,
        site: dict[str, Any],
        state: str | None,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{site['id']}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.site = site
        self.site_id: str = site["id"]
        self.state = state
        self._last_usage_fetch: datetime | None = None
        self._cached_usage: list[dict[str, Any]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest prices, usage, and state renewables from Amber Electric."""
        try:
            # 1. Fetch current + next 48 intervals (24h at 30m, 4h at 5m)
            raw_intervals = await self.client.get_current_prices(
                self.site_id, next_intervals=48, previous_intervals=1
            )
        except AmberAuthError as err:
            raise ConfigEntryAuthFailed("Invalid Amber Electric API key") from err
        except AmberApiError as err:
            raise UpdateFailed(f"Error communicating with Amber Electric API: {err}") from err

        # Group intervals by channelType (OpenAPI note: index offset can change, always group by channelType)
        channels: dict[str, dict[str, Any]] = {}
        for item in raw_intervals:
            ch_type = item.get("channelType", "general")
            ch_bucket = channels.setdefault(
                ch_type,
                {
                    "current": None,
                    "actual": [],
                    "forecasts": [],
                },
            )
            interval_type = item.get("type")
            if interval_type == "CurrentInterval":
                ch_bucket["current"] = item
            elif interval_type == "ActualInterval":
                ch_bucket["actual"].append(item)
            elif interval_type == "ForecastInterval":
                ch_bucket["forecasts"].append(item)

        # Fallback if CurrentInterval wasn't explicitly flagged
        for ch_type, ch_bucket in channels.items():
            if ch_bucket["current"] is None:
                if ch_bucket["forecasts"]:
                    ch_bucket["current"] = ch_bucket["forecasts"][0]
                elif ch_bucket["actual"]:
                    ch_bucket["current"] = ch_bucket["actual"][-1]

        # 2. Fetch today's usage every 15 minutes to keep within rate limits
        now = dt_util.utcnow()
        if (
            self._last_usage_fetch is None
            or (now - self._last_usage_fetch) >= timedelta(minutes=15)
        ):
            try:
                local_today = dt_util.now().date()
                yesterday = local_today - timedelta(days=1)
                self._cached_usage = await self.client.get_usage(
                    self.site_id, start_date=yesterday, end_date=local_today
                )
                self._last_usage_fetch = now
            except AmberApiError as err:
                _LOGGER.debug("Could not refresh usage data: %s", err)

        # Aggregate today's usage by channelType
        local_today_str = dt_util.now().date().isoformat()
        usage_summary: dict[str, dict[str, float]] = {}
        for u_item in self._cached_usage:
            if u_item.get("date") != local_today_str:
                continue
            ch_type = u_item.get("channelType", "general")
            summary = usage_summary.setdefault(
                ch_type, {"kwh": 0.0, "cost": 0.0}
            )
            summary["kwh"] += float(u_item.get("kwh", 0.0))
            summary["cost"] += float(u_item.get("cost", 0.0))

        # 3. Optionally fetch state grid renewables (public endpoint)
        state_renewables: dict[str, Any] | None = None
        if self.state:
            try:
                ren_list = await self.client.get_current_renewables(
                    self.state, next_intervals=12, previous_intervals=0
                )
                current_ren = next(
                    (r for r in ren_list if r.get("type") == "CurrentRenewable"),
                    ren_list[0] if ren_list else None,
                )
                state_renewables = {
                    "current": current_ren,
                    "forecasts": [
                        r for r in ren_list if r.get("type") == "ForecastRenewable"
                    ],
                }
            except AmberApiError as err:
                _LOGGER.debug("Could not fetch state renewables for %s: %s", self.state, err)

        return {
            "site": self.site,
            "channels": channels,
            "usage_today": usage_summary,
            "state_renewables": state_renewables,
            "rate_limit_remaining": self.client.rate_limit_remaining,
        }
