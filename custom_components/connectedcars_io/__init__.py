"""Support for connectedcars.io / Min Volkswagen integration."""

import logging

import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.core import ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import CONF_HEALTH_SENSITIVITY, DOMAIN
from .connectedcars import ConnectedCarsClient
from .map_view import (
    ConnectedCarsMapTileTokenView,
    ConnectedCarsTripsMapView,
    async_ensure_map_token,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["binary_sensor", "device_tracker", "sensor"]

SERVICE_GET_TRIPS = "get_trips"
GET_TRIPS_SCHEMA = vol.Schema(
    {
        vol.Optional("vin"): cv.string,
        vol.Optional("from_time"): cv.datetime,
        vol.Optional("to_time"): cv.datetime,
        vol.Optional("limit", default=20): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional("include_events", default=False): cv.boolean,
    }
)


def _to_api_time(value):
    """Convert a service datetime to the API's ISO-8601 Zulu format."""
    if value is None:
        return None
    return (
        dt_util.as_utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _async_setup_services(hass: core.HomeAssistant) -> None:
    """Register domain services (once)."""

    async def handle_get_trips(call: ServiceCall) -> ServiceResponse:
        vin = call.data.get("vin")

        # A vehicle may live in any config entry (one per brand namespace).
        matches = []
        for config in hass.data[DOMAIN].values():
            client = config["connectedcarsclient"]
            for vehicle in await client.get_vehicle_instances():
                if vin is None or vehicle["vin"] == vin:
                    matches.append((client, vehicle))
        if not matches:
            raise ServiceValidationError(
                f"No vehicle found with VIN {vin}"
                if vin is not None
                else "No vehicles found"
            )
        if vin is None and len(matches) > 1:
            raise ServiceValidationError(
                "Multiple vehicles on the account; specify which with 'vin'"
            )

        client, vehicle = matches[0]
        trips = await client.get_trips(
            vehicle["id"],
            from_iso=_to_api_time(call.data.get("from_time")),
            to_iso=_to_api_time(call.data.get("to_time")),
            limit=call.data["limit"],
            include_events=call.data["include_events"],
        )
        return {
            "vin": vehicle["vin"],
            "name": vehicle["name"],
            "trips": trips if trips is not None else [],
        }

    if not hass.services.has_service(DOMAIN, SERVICE_GET_TRIPS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_TRIPS,
            handle_get_trips,
            schema=GET_TRIPS_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("async_setup_entry: [%a][%s]", DOMAIN, entry.entry_id)

    # Must happen before add_update_listener: writing the generated token to
    # the entry would otherwise trigger a reload loop.
    map_token = async_ensure_map_token(hass, entry)

    data = {}
    data["email"] = entry.data["email"]
    data["password"] = entry.data["password"]
    data["namespace"] = entry.data["namespace"]
    data["map_token"] = map_token
    data["connectedcarsclient"] = ConnectedCarsClient(
        entry.data["email"], entry.data["password"], entry.data["namespace"]
    )
    # Lets entities expose the map URL without changing their constructor.
    data["connectedcarsclient"].map_token = map_token
    data[CONF_HEALTH_SENSITIVITY] = entry.options.get(CONF_HEALTH_SENSITIVITY, "medium")

    if not hass.data.get(f"{DOMAIN}_map_view_registered"):
        hass.http.register_view(ConnectedCarsTripsMapView(hass))
        hass.http.register_view(ConnectedCarsMapTileTokenView(hass))
        hass.data[f"{DOMAIN}_map_view_registered"] = True

    # Registers update listener to update config entry when options are updated, and store a reference to the unsubscribe function
    data["unsub_options_update_listener"] = entry.add_update_listener(
        options_update_listener
    )

    hass.data[DOMAIN][entry.entry_id] = data  # entry.data

    _async_setup_services(hass)

    # Forward the setup to the sensor platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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

    # data = hass.data[DOMAIN][entry.entry_id]
    # # Cancel previous timer
    # if ("timer_remove" in data) and (data["timer_remove"] is not None):
    #     _LOGGER.debug("Remove timer")
    #     data["timer_remove"]()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove options_update_listener.
    hass.data[DOMAIN][entry.entry_id]["unsub_options_update_listener"]()

    # Remove config entry from domain.
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_GET_TRIPS)

    return unload_ok
