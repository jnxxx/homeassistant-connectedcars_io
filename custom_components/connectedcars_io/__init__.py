"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
import asyncio

from homeassistant import config_entries, core
from .minvw import MinVW
from .const import DOMAIN, CONF_HEALTH_SENSITIVITY

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
    data[CONF_HEALTH_SENSITIVITY] = entry.options.get(CONF_HEALTH_SENSITIVITY, "medium")

    # Registers update listener to update config entry when options are updated, and store a reference to the unsubscribe function
    data["unsub_options_update_listener"] = entry.add_update_listener(
        options_update_listener
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


async def options_update_listener(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""

    data = hass.data[DOMAIN][entry.entry_id]

    # # Cancel previous timer
    # if ("timer_remove" in data) and (data["timer_remove"] is not None):
    #     _LOGGER.debug("Remove timer")
    #     data["timer_remove"]()

    unloaded = []
    for component in PLATFORMS:
        unloaded.append(
            await asyncio.gather(
                *[hass.config_entries.async_forward_entry_unload(entry, component)]
            )
        )
    unload_ok = all(unloaded)

    # Remove options_update_listener.
    hass.data[DOMAIN][entry.entry_id]["unsub_options_update_listener"]()

    # Remove config entry from domain.
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
