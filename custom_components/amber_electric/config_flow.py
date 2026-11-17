"""Config flow for Amber Electric integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AmberApiClient, AmberApiError, AmberAuthError
from .const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_SITE_ID,
    CONF_STATE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    VALID_STATES,
)

_LOGGER = logging.getLogger(__name__)


class AmberElectricConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Amber Electric."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api_key: str = ""
        self._sites: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where the user enters their API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            session = async_get_clientsession(self.hass)
            client = AmberApiClient(api_key, session)

            try:
                sites = await client.get_sites()
            except AmberAuthError:
                errors["base"] = "invalid_auth"
            except AmberApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Amber Electric API key")
                errors["base"] = "unknown"
            else:
                active_sites = [s for s in sites if s.get("status") != "closed"]
                if not active_sites:
                    errors["base"] = "no_sites"
                else:
                    self._api_key = api_key
                    self._sites = active_sites
                    if len(active_sites) == 1:
                        site = active_sites[0]
                        await self.async_set_unique_id(site["id"])
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Amber Electric ({site['nmi']})",
                            data={
                                CONF_API_KEY: self._api_key,
                                CONF_SITE_ID: site["id"],
                                CONF_STATE: user_input.get(CONF_STATE) or None,
                            },
                        )
                    return await self.async_step_site()

        state_options = {"": "None (Skip state grid renewables)"} | {
            s: s.upper() for s in VALID_STATES
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_STATE, default=""): vol.In(state_options),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_site(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle site selection when an account has multiple sites."""
        if user_input is not None:
            site_id = user_input[CONF_SITE_ID]
            site = next(s for s in self._sites if s["id"] == site_id)
            await self.async_set_unique_id(site_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Amber Electric ({site['nmi']})",
                data={
                    CONF_API_KEY: self._api_key,
                    CONF_SITE_ID: site_id,
                    CONF_STATE: user_input.get(CONF_STATE) or None,
                },
            )

        site_options = {
            s["id"]: f"NMI {s['nmi']} — {s['network']} ({s['status']})"
            for s in self._sites
        }
        state_options = {"": "None (Skip state grid renewables)"} | {
            s: s.upper() for s in VALID_STATES
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_SITE_ID): vol.In(site_options),
                vol.Optional(CONF_STATE, default=""): vol.In(state_options),
            }
        )

        return self.async_show_form(step_id="site", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return AmberElectricOptionsFlow(config_entry)


class AmberElectricOptionsFlow(OptionsFlow):
    """Handle options flow for Amber Electric."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_state = self._config_entry.options.get(
            CONF_STATE, self._config_entry.data.get(CONF_STATE, "")
        ) or ""

        state_options = {"": "None (Skip state grid renewables)"} | {
            s: s.upper() for s in VALID_STATES
        }

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current_interval,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Optional(CONF_STATE, default=current_state): vol.In(state_options),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
