import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional
import traceback

from homeassistant import config_entries, core
from homeassistant.const import TEMP_CELSIUS, ELECTRIC_POTENTIAL_VOLT, DEVICE_CLASS_VOLTAGE, DEVICE_CLASS_TEMPERATURE, VOLUME_LITERS, PERCENTAGE, LENGTH_KILOMETERS, STATE_HOME, STATE_NOT_HOME
import homeassistant.helpers.config_validation as cv
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components import zone
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.exceptions import PlatformNotReady
from .minvw import MinVW

_LOGGER = logging.getLogger(__name__)
from .const import DOMAIN

SCAN_INTERVAL = timedelta(minutes=5)

_connectedcarsclient = None

async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    config = hass.data[DOMAIN][config_entry.entry_id]
    #_LOGGER.debug(f"Config: {config}")

    _connectedcarsclient = config["connectedcarsclient"]
    #_connectedcarsclient = MinVW(config["email"], config["password"], config["namespace"])

    try:
        sensors = []
        data = await _connectedcarsclient._get_vehicle_instances()
        for vehicle in data:
            if "GeoLocation" in vehicle["has"]:
                sensors.append(CcTrackerEntity(vehicle, "GeoLocation", _connectedcarsclient))
        async_add_entities(sensors, update_before_add=True)

    except Exception as e:
        _LOGGER.warning(f"Failed to add sensors: {e}")
        _LOGGER.debug(f"{traceback.format_exc()}")
        raise PlatformNotReady


class CcTrackerEntity(TrackerEntity):
    """Representation of a Device TrackerEntity."""

    def __init__(self, vehicle, itemName, connectedcarsclient):
        self._vehicle = vehicle
        self._itemName = itemName
        self._icon = "mdi:map"
        self._name = f"{self._vehicle['make']} {self._vehicle['model']} {self._itemName}"
        self._unique_id = f"{DOMAIN}-{self._vehicle['vin']}-{self._itemName}"
        self._device_class = None
        self._connectedcarsclient = connectedcarsclient
        self._latitude = None
        self._longitude = None
        _LOGGER.debug(f"Adding sensor: {self._unique_id}")


    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._vehicle['vin'])
            },
            "name": self._vehicle['name'],
            "manufacturer": self._vehicle['make'],
            "model": self._vehicle['model'],
            "sw_version": self._vehicle['licensePlate'],
            #"via_device": (hue.DOMAIN, self.api.bridgeid),
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        return self._icon

    @property
    def unique_id(self):
        """The unique id of the sensor."""
        return self._unique_id

    @property
    def source_type(self) -> str:
        return "gps"

    # @property
    # def location_accuracy(self) -> int:
    #     return 1

    @property
    def latitude(self):
        return self._latitude

    @property
    def longitude(self):
        return self._longitude

    @property
    def available(self):
        return (self._latitude is not None and self._longitude is not None)

    @property
    def should_poll(self) -> bool:
        """No polling for entities that have location pushed."""
        return True

    # @property
    # def state(self):
    #     _LOGGER.debug(f"zone_state...")
    #     if self.latitude is not None and self.longitude is not None:
    #         zone_state = zone.async_active_zone(
    #             self.hass, self.latitude, self.longitude, self.location_accuracy
    #         )
    #         _LOGGER.debug(f"zone_state: {zone_state}")
    #         if zone_state is None:
    #             state = STATE_NOT_HOME
    #         elif zone_state.entity_id == zone.ENTITY_ID_HOME:
    #             state = STATE_HOME
    #         else:
    #             state = zone_state.name
    #         _LOGGER.debug(f"state: {state}")
    #         return state
    #     return None
    #     return f"{self._latitude}, {self._longitude}"

    @property
    def extra_state_attributes(self):
        attributes = dict()
        attributes['device_class'] = self._device_class
        return attributes

    async def async_update(self):
        self._latitude = None
        self._longitude = None
        try:
            self._latitude = await self._connectedcarsclient._get_value_float(self._vehicle['id'], ["position", "latitude"])
            self._longitude = await self._connectedcarsclient._get_value_float(self._vehicle['id'], ["position", "longitude"])
        except Exception as err:
            _LOGGER.debug(f"Unable to get vehicle location: {err}")


