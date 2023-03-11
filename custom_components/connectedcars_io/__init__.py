"""Support for connectedcars.io / Min Volkswagen integration."""

import logging

from homeassistant import config_entries, core
from .minvw import MinVW
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "device_tracker"]


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("async_setup_entry: [%a][%s]", DOMAIN, entry.entry_id)

    data = {}
    data["email"] = entry.data["email"]
    data["password"] = entry.data["password"]
    data["namespace"] = entry.data["namespace"]
    data["connectedcarsclient"] = MinVW(
        entry.data["email"], entry.data["password"], entry.data["namespace"]
    )
    hass.data[DOMAIN][entry.entry_id] = data  # entry.data

    # Forward the setup to the sensor platform.
    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    """Set up the GitHub Custom component from yaml configuration."""
    hass.data.setdefault(DOMAIN, {})
    return True
