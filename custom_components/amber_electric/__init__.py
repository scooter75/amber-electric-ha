"""The Amber Electric integration."""
from __future__ import annotations

from datetime import date
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AmberApiClient, AmberApiError
from .const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_SITE_ID,
    CONF_STATE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import AmberDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

SERVICE_GET_PRICES = "get_prices"
SERVICE_GET_USAGE = "get_usage"

SERVICE_PRICES_SCHEMA = vol.Schema(
    {
        vol.Optional("site_id"): cv.string,
        vol.Optional("start_date"): cv.date,
        vol.Optional("end_date"): cv.date,
        vol.Optional("resolution"): vol.In([5, 30]),
    }
)

SERVICE_USAGE_SCHEMA = vol.Schema(
    {
        vol.Optional("site_id"): cv.string,
        vol.Required("start_date"): cv.date,
        vol.Required("end_date"): cv.date,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Amber Electric from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api_key: str = entry.data[CONF_API_KEY]
    site_id: str = entry.data[CONF_SITE_ID]
    state: str | None = entry.options.get(CONF_STATE, entry.data.get(CONF_STATE))
    scan_interval: int = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    session = async_get_clientsession(hass)
    client = AmberApiClient(api_key, session)

    try:
        sites = await client.get_sites()
    except AmberApiError as err:
        raise ConfigEntryNotReady(f"Unable to connect to Amber Electric API: {err}") from err

    site = next((s for s in sites if s["id"] == site_id), None)
    if site is None:
        raise ConfigEntryNotReady(f"Site {site_id} not found in Amber Electric account")

    coordinator = AmberDataUpdateCoordinator(
        hass=hass,
        client=client,
        site=site,
        state=state,
        scan_interval=scan_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    _register_services(hass)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_GET_PRICES)
        hass.services.async_remove(DOMAIN, SERVICE_GET_USAGE)
    return unload_ok


def _get_coordinator_for_site(
    hass: HomeAssistant, site_id: str | None
) -> AmberDataUpdateCoordinator:
    """Resolve the coordinator matching site_id or return the first available."""
    coordinators: list[AmberDataUpdateCoordinator] = list(hass.data[DOMAIN].values())
    if not coordinators:
        raise HomeAssistantError("No Amber Electric sites configured")
    if site_id:
        for coord in coordinators:
            if coord.site_id == site_id:
                return coord
        raise HomeAssistantError(f"Amber Electric site {site_id} not found")
    return coordinators[0]


def _register_services(hass: HomeAssistant) -> None:
    """Register Amber Electric action services if not already registered."""
    if not hass.services.has_service(DOMAIN, SERVICE_GET_PRICES):

        async def handle_get_prices(call: ServiceCall) -> ServiceResponse:
            coord = _get_coordinator_for_site(hass, call.data.get("site_id"))
            start_d: date | None = call.data.get("start_date")
            end_d: date | None = call.data.get("end_date")
            resolution: int | None = call.data.get("resolution")
            try:
                intervals = await coord.client.get_prices(
                    coord.site_id,
                    start_date=start_d,
                    end_date=end_d,
                    resolution=resolution,
                )
            except AmberApiError as err:
                raise HomeAssistantError(f"Failed to fetch prices: {err}") from err
            return {"site_id": coord.site_id, "intervals": intervals}

        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_PRICES,
            handle_get_prices,
            schema=SERVICE_PRICES_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_USAGE):

        async def handle_get_usage(call: ServiceCall) -> ServiceResponse:
            coord = _get_coordinator_for_site(hass, call.data.get("site_id"))
            start_d: date = call.data["start_date"]
            end_d: date = call.data["end_date"]
            try:
                usage = await coord.client.get_usage(
                    coord.site_id,
                    start_date=start_d,
                    end_date=end_d,
                )
            except AmberApiError as err:
                raise HomeAssistantError(f"Failed to fetch usage: {err}") from err
            return {"site_id": coord.site_id, "usage": usage}

        hass.services.async_register(
            DOMAIN,
            SERVICE_USAGE_SCHEMA and SERVICE_GET_USAGE,
            handle_get_usage,
            schema=SERVICE_USAGE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
