"""Binary sensor platform for Amber Electric."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CHANNEL_NAMES, DOMAIN
from .coordinator import AmberDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Amber Electric binary sensors from a config entry."""
    coordinator: AmberDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    site = coordinator.site
    entities: list[BinarySensorEntity] = []

    configured_channels = [ch["type"] for ch in site.get("channels", [])]
    if not configured_channels:
        configured_channels = list(coordinator.data.get("channels", {}).keys()) or ["general"]

    seen_channels: list[str] = []
    for ch_type in configured_channels:
        if ch_type not in seen_channels:
            seen_channels.append(ch_type)

    for ch_type in seen_channels:
        entities.extend(
            [
                AmberPriceSpikeBinarySensor(coordinator, ch_type),
                AmberPotentialSpikeBinarySensor(coordinator, ch_type),
                AmberPriceEstimateBinarySensor(coordinator, ch_type),
                AmberDemandWindowBinarySensor(coordinator, ch_type),
            ]
        )

    async_add_entities(entities)


class AmberBaseBinarySensor(
    CoordinatorEntity[AmberDataUpdateCoordinator], BinarySensorEntity
):
    """Base binary sensor for Amber Electric."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the base binary sensor."""
        super().__init__(coordinator)
        self._channel_type = channel_type
        site = coordinator.site
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, site["id"])},
            name=f"Amber Electric ({site['nmi']})",
            manufacturer="Amber Electric",
            model=f"{site.get('network', 'NEM')} ({site.get('intervalLength', 30)}m interval)",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://app.amber.com.au",
        )

    def _get_current(self) -> dict[str, Any] | None:
        return (
            self.coordinator.data.get("channels", {})
            .get(self._channel_type, {})
            .get("current")
        )


class AmberPriceSpikeBinarySensor(AmberBaseBinarySensor):
    """Binary sensor indicating an active price spike (spikeStatus == 'spike')."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-octagram"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the price spike binary sensor."""
        super().__init__(coordinator, channel_type)
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Price Spike"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_price_spike"

    @property
    def is_on(self) -> bool:
        """Return True if a price spike is currently active."""
        current = self._get_current()
        if not current:
            return False
        return current.get("spikeStatus") == "spike"


class AmberPotentialSpikeBinarySensor(AmberBaseBinarySensor):
    """Binary sensor indicating a potential price spike (spikeStatus in ['potential', 'spike'])."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:alert-outline"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the potential spike binary sensor."""
        super().__init__(coordinator, channel_type)
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Potential Spike"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_potential_spike"

    @property
    def is_on(self) -> bool:
        """Return True if a potential or active spike is present."""
        current = self._get_current()
        if not current:
            return False
        return current.get("spikeStatus") in ("potential", "spike")


class AmberPriceEstimateBinarySensor(AmberBaseBinarySensor):
    """Binary sensor indicating whether the current interval price is an estimate."""

    _attr_icon = "mdi:approximately-equal"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the price estimate binary sensor."""
        super().__init__(coordinator, channel_type)
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Price Estimate"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_price_estimate"

    @property
    def is_on(self) -> bool:
        """Return True if the current price is still an estimate."""
        current = self._get_current()
        if not current:
            return False
        return bool(current.get("estimate", False))


class AmberDemandWindowBinarySensor(AmberBaseBinarySensor):
    """Binary sensor indicating whether the site is currently in a tariff demand window."""

    _attr_icon = "mdi:clock-alert-outline"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the demand window binary sensor."""
        super().__init__(coordinator, channel_type)
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Demand Window"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_demand_window"

    @property
    def is_on(self) -> bool:
        """Return True if tariffInformation.demandWindow is True."""
        current = self._get_current()
        if not current:
            return False
        tariff = current.get("tariffInformation") or {}
        return bool(tariff.get("demandWindow", False))
