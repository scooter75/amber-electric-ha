"""Constants for the Amber Electric integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "amber_electric"
API_BASE_URL = "https://api.amber.com.au/v1"

CONF_API_KEY = "api_key"
CONF_SITE_ID = "site_id"
CONF_STATE = "state"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 600

VALID_STATES = ["nsw", "sa", "qld", "vic"]

CHANNEL_GENERAL = "general"
CHANNEL_CONTROLLED_LOAD = "controlledLoad"
CHANNEL_FEED_IN = "feedIn"

CHANNEL_NAMES = {
    CHANNEL_GENERAL: "General",
    CHANNEL_CONTROLLED_LOAD: "Controlled Load",
    CHANNEL_FEED_IN: "Feed In",
}

ATTRIBUTION = "Data provided by Amber Electric"
