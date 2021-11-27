"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional
import traceback

from homeassistant import config_entries, core
from homeassistant.const import TEMP_CELSIUS, ELECTRIC_POTENTIAL_VOLT, DEVICE_CLASS_VOLTAGE, DEVICE_CLASS_TEMPERATURE, VOLUME_LITERS, PERCENTAGE, LENGTH_KILOMETERS
import homeassistant.helpers.config_validation as cv
from homeassistant.components.binary_sensor import BinarySensorEntity #,  BinarySensorEntityDescription
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

    try:
        sensors = []
        data = await _connectedcarsclient._get_vehicle_instances()
        for vehicle in data:
            if "Ignition" in vehicle["has"]:
                sensors.append(CcBinaryEntity(vehicle, "Ignition", "", "moving", True, _connectedcarsclient))
            if "Health" in vehicle["has"]:
                sensors.append(CcBinaryEntity(vehicle, "Health", "", "problem", True, _connectedcarsclient))            
            for lampState in vehicle['lampStates']:
                sensors.append(CcBinaryEntity(vehicle, "Lamp", lampState, "problem", False, _connectedcarsclient))
        async_add_entities(sensors, update_before_add=True)

    except Exception as e:
        _LOGGER.warning(f"Failed to add sensors: {e}")
        _LOGGER.debug(f"{traceback.format_exc()}")
        raise PlatformNotReady


class CcBinaryEntity(BinarySensorEntity):
    """Representation of a BinaryEntity."""

    def __init__(self, vehicle, itemName, subitemName, device_class, entity_registry_enabled_default, connectedcarsclient):
        self._vehicle = vehicle
        self._itemName = itemName
        self._subitemName = subitemName
        #self._icon = "mdi:map"
        self._name = f"{self._vehicle['make']} {self._vehicle['model']} {self._itemName}{self._subitemName.capitalize()}"
        self._unique_id = f"{DOMAIN}-{self._vehicle['vin']}-{self._itemName}{self._subitemName.capitalize()}"
        self._device_class = device_class
        self._connectedcarsclient = connectedcarsclient
        self._is_on = None
        self._entity_registry_enabled_default = entity_registry_enabled_default
        _LOGGER.debug(f"Adding sensor: {self._unique_id}")
        

    @property
    def device_info(self):
        return {
            "identifiers": {
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
    def entity_registry_enabled_default(self):
        return self._entity_registry_enabled_default



    # @property
    # def entity_description(self):
    #     _LOGGER.debug(f"entity_description")
    #     ret =   BinarySensorEntityDescription(key="desc_key", name="desc_name")
    #     return (ret)

    # @property
    # def icon(self):
    #     return self._icon

    @property
    def unique_id(self):
        """The unique id of the sensor."""
        return self._unique_id

    @property
    def is_on(self):
        return self._is_on

    @property
    def available(self):
        return (self._is_on is not None)

    @property
    def device_class(self):
        return self._device_class

    async def async_update(self):
        self._is_on = None
        try:
            if self._itemName == "Ignition":
                self._is_on = str(await self._connectedcarsclient._get_value(self._vehicle['id'], ["ignition", "on"])).lower() == "true"
            elif self._itemName == "Health":
                self._is_on = str(await self._connectedcarsclient._get_value(self._vehicle['id'], ["health", "ok"])).lower() != "true"
            elif self._itemName == "Lamp":
                self._is_on = str(await self._connectedcarsclient._get_lampstatus(self._vehicle['id'], self._subitemName)).lower() == "true"

        except Exception as err:
            _LOGGER.debug(f"Unable to get binary state: {err}")


