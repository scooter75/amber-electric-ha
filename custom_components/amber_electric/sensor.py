"""Sensor platform for Amber Electric."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy
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
    """Set up Amber Electric sensors from a config entry."""
    coordinator: AmberDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    site = coordinator.site
    entities: list[SensorEntity] = []

    # Discover active channels from site configuration (fallback to coordinator data)
    configured_channels = [ch["type"] for ch in site.get("channels", [])]
    if not configured_channels:
        configured_channels = list(coordinator.data.get("channels", {}).keys()) or ["general"]

    # Deduplicate while preserving order
    seen_channels: list[str] = []
    for ch_type in configured_channels:
        if ch_type not in seen_channels:
            seen_channels.append(ch_type)

    for ch_type in seen_channels:
        entities.extend(
            [
                AmberChannelPriceSensor(coordinator, ch_type),
                AmberChannelSpotPriceSensor(coordinator, ch_type),
                AmberChannelDescriptorSensor(coordinator, ch_type),
                AmberChannelForecastPriceSensor(coordinator, ch_type),
                AmberChannelDailyUsageSensor(coordinator, ch_type),
                AmberChannelDailyCostSensor(coordinator, ch_type),
            ]
        )

    # Site-wide renewables sensor from the general channel (or first available)
    primary_channel = "general" if "general" in seen_channels else seen_channels[0]
    entities.append(AmberGridRenewablesSensor(coordinator, primary_channel))

    # Optional State Grid Renewables sensor if user selected an NEM state
    if coordinator.state:
        entities.append(AmberStateRenewablesSensor(coordinator, coordinator.state))

    async_add_entities(entities)


class AmberBaseSensor(CoordinatorEntity[AmberDataUpdateCoordinator], SensorEntity):
    """Base entity for Amber Electric sensors."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: AmberDataUpdateCoordinator) -> None:
        """Initialize the base sensor."""
        super().__init__(coordinator)
        site = coordinator.site
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, site["id"])},
            name=f"Amber Electric ({site['nmi']})",
            manufacturer="Amber Electric",
            model=f"{site.get('network', 'NEM')} ({site.get('intervalLength', 30)}m interval)",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://app.amber.com.au",
        )


class AmberChannelPriceSensor(AmberBaseSensor):
    """Current retail price (c/kWh, incl. GST) for a meter channel."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "AUD/kWh"
    _attr_suggested_display_precision = 4
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the channel price sensor."""
        super().__init__(coordinator)
        self._channel_type = channel_type
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Price"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_price"

    def _get_current(self) -> dict[str, Any] | None:
        return (
            self.coordinator.data.get("channels", {})
            .get(self._channel_type, {})
            .get("current")
        )

    @property
    def native_value(self) -> float | None:
        """Return the price in $/kWh (converted from API c/kWh)."""
        current = self._get_current()
        if not current or current.get("perKwh") is None:
            return None
        # Convert cents/kWh to AUD/kWh for Home Assistant Energy Dashboard compatibility
        return round(float(current["perKwh"]) / 100.0, 6)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed interval attributes including full forecast array."""
        ch_data = self.coordinator.data.get("channels", {}).get(self._channel_type, {})
        current = ch_data.get("current") or {}
        forecasts = ch_data.get("forecasts") or []
        tariff = current.get("tariffInformation") or {}
        adv = current.get("advancedPrice") or {}
        rng = current.get("range") or {}

        return {
            "per_kwh_cents": current.get("perKwh"),
            "spot_per_kwh_cents": current.get("spotPerKwh"),
            "descriptor": current.get("descriptor"),
            "spike_status": current.get("spikeStatus"),
            "estimate": current.get("estimate"),
            "duration": current.get("duration"),
            "start_time": current.get("startTime"),
            "end_time": current.get("endTime"),
            "nem_time": current.get("nemTime"),
            "renewables": current.get("renewables"),
            "tariff_period": tariff.get("period"),
            "tariff_season": tariff.get("season"),
            "tariff_block": tariff.get("block"),
            "demand_window": tariff.get("demandWindow"),
            "advanced_price_low": adv.get("low"),
            "advanced_price_predicted": adv.get("predicted"),
            "advanced_price_high": adv.get("high"),
            "range_min": rng.get("min"),
            "range_max": rng.get("max"),
            "forecasts": [
                {
                    "start_time": f.get("startTime"),
                    "end_time": f.get("endTime"),
                    "per_kwh": f.get("perKwh"),
                    "spot_per_kwh": f.get("spotPerKwh"),
                    "descriptor": f.get("descriptor"),
                    "spike_status": f.get("spikeStatus"),
                    "renewables": f.get("renewables"),
                    "advanced_price": f.get("advancedPrice"),
                }
                for f in forecasts
            ],
        }


class AmberChannelSpotPriceSensor(AmberBaseSensor):
    """Current NEM wholesale spot price (c/kWh, incl. GST) for a meter channel."""

    _attr_native_unit_of_measurement = "c/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the spot price sensor."""
        super().__init__(coordinator)
        self._channel_type = channel_type
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Spot Price"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_spot_price"

    @property
    def native_value(self) -> float | None:
        """Return NEM spot price in c/kWh."""
        current = (
            self.coordinator.data.get("channels", {})
            .get(self._channel_type, {})
            .get("current")
        )
        if not current or current.get("spotPerKwh") is None:
            return None
        return round(float(current["spotPerKwh"]), 2)


class AmberChannelDescriptorSensor(AmberBaseSensor):
    """Current price descriptor (extremelyLow, veryLow, low, neutral, high, spike)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "negative",
        "extremelyLow",
        "veryLow",
        "low",
        "neutral",
        "high",
        "spike",
    ]
    _attr_icon = "mdi:tag-text-outline"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the descriptor sensor."""
        super().__init__(coordinator)
        self._channel_type = channel_type
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Price Descriptor"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_descriptor"

    @property
    def native_value(self) -> str | None:
        """Return the price descriptor."""
        current = (
            self.coordinator.data.get("channels", {})
            .get(self._channel_type, {})
            .get("current")
        )
        return current.get("descriptor") if current else None


class AmberChannelForecastPriceSensor(AmberBaseSensor):
    """Next interval predicted/forecast price (c/kWh) for a meter channel."""

    _attr_native_unit_of_measurement = "c/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the next interval forecast sensor."""
        super().__init__(coordinator)
        self._channel_type = channel_type
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Next Interval Price"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_next_price"

    @property
    def native_value(self) -> float | None:
        """Return next interval forecast price in c/kWh."""
        forecasts = (
            self.coordinator.data.get("channels", {})
            .get(self._channel_type, {})
            .get("forecasts", [])
        )
        if not forecasts:
            return None
        next_iv = forecasts[0]
        adv = next_iv.get("advancedPrice")
        if adv and adv.get("predicted") is not None:
            return round(float(adv["predicted"]), 2)
        if next_iv.get("perKwh") is not None:
            return round(float(next_iv["perKwh"]), 2)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return next interval metadata."""
        forecasts = (
            self.coordinator.data.get("channels", {})
            .get(self._channel_type, {})
            .get("forecasts", [])
        )
        if not forecasts:
            return {}
        next_iv = forecasts[0]
        return {
            "start_time": next_iv.get("startTime"),
            "end_time": next_iv.get("endTime"),
            "per_kwh": next_iv.get("perKwh"),
            "descriptor": next_iv.get("descriptor"),
            "advanced_price": next_iv.get("advancedPrice"),
            "range": next_iv.get("range"),
        }


class AmberChannelDailyUsageSensor(AmberBaseSensor):
    """Today's cumulative energy usage/generation (kWh) for a meter channel."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the daily usage sensor."""
        super().__init__(coordinator)
        self._channel_type = channel_type
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Daily Usage"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_daily_usage"

    @property
    def native_value(self) -> float | None:
        """Return today's kWh for the channel."""
        usage = self.coordinator.data.get("usage_today", {}).get(self._channel_type)
        if not usage:
            return 0.0
        # Feed-in kWh is negative in Amber API; expose absolute kWh for HA Energy compatibility
        val = float(usage["kwh"])
        return round(abs(val) if self._channel_type == "feedIn" else val, 4)


class AmberChannelDailyCostSensor(AmberBaseSensor):
    """Today's cumulative cost/credit (AUD) for a meter channel."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "AUD"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the daily cost sensor."""
        super().__init__(coordinator)
        self._channel_type = channel_type
        ch_label = CHANNEL_NAMES.get(channel_type, channel_type)
        self._attr_name = f"{ch_label} Daily Cost"
        self._attr_unique_id = f"{coordinator.site_id}_{channel_type}_daily_cost"

    @property
    def native_value(self) -> float | None:
        """Return today's cost in AUD."""
        usage = self.coordinator.data.get("usage_today", {}).get(self._channel_type)
        if not usage:
            return 0.0
        return round(float(usage["cost"]), 2)


class AmberGridRenewablesSensor(AmberBaseSensor):
    """Current percentage of renewables in the grid from the site interval."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:leaf"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, channel_type: str) -> None:
        """Initialize the renewables sensor."""
        super().__init__(coordinator)
        self._channel_type = channel_type
        self._attr_name = "Grid Renewables"
        self._attr_unique_id = f"{coordinator.site_id}_grid_renewables"

    @property
    def native_value(self) -> float | None:
        """Return current renewables percentage."""
        current = (
            self.coordinator.data.get("channels", {})
            .get(self._channel_type, {})
            .get("current")
        )
        if not current or current.get("renewables") is None:
            return None
        return round(float(current["renewables"]), 1)


class AmberStateRenewablesSensor(AmberBaseSensor):
    """Current NEM state grid renewables percentage (/state/{state}/renewables/current)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: AmberDataUpdateCoordinator, state: str) -> None:
        """Initialize the state renewables sensor."""
        super().__init__(coordinator)
        self._state = state.upper()
        self._attr_name = f"{self._state} Grid Renewables"
        self._attr_unique_id = f"{coordinator.site_id}_state_{state.lower()}_renewables"

    @property
    def native_value(self) -> float | None:
        """Return state renewables percentage."""
        ren_data = self.coordinator.data.get("state_renewables") or {}
        current = ren_data.get("current")
        if not current or current.get("renewables") is None:
            return None
        return round(float(current["renewables"]), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return descriptor and upcoming state renewables forecast."""
        ren_data = self.coordinator.data.get("state_renewables") or {}
        current = ren_data.get("current") or {}
        return {
            "descriptor": current.get("descriptor"),
            "start_time": current.get("startTime"),
            "end_time": current.get("endTime"),
            "forecasts": ren_data.get("forecasts", []),
        }
