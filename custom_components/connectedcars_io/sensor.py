"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from homeassistant import config_entries, core
from homeassistant.const import TEMP_CELSIUS, ELECTRIC_POTENTIAL_VOLT, DEVICE_CLASS_VOLTAGE, DEVICE_CLASS_TEMPERATURE, VOLUME_LITERS, PERCENTAGE, LENGTH_KILOMETERS, DEVICE_CLASS_BATTERY, DEVICE_CLASS_TEMPERATURE
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
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
            if "outdoorTemperature" in vehicle["has"]:
                sensors.append(MinVwEntity(vehicle, "outdoorTemperature", True, _connectedcarsclient))
            if "BatteryVoltage" in vehicle["has"]:
                sensors.append(MinVwEntity(vehicle, "BatteryVoltage", True, _connectedcarsclient))
            if "fuelPercentage" in vehicle["has"]:
                sensors.append(MinVwEntity(vehicle, "fuelPercentage", True, _connectedcarsclient))
            if "fuelLevel" in vehicle["has"]:
                sensors.append(MinVwEntity(vehicle, "fuelLevel", True, _connectedcarsclient))
            if "odometer" in vehicle["has"]:
                sensors.append(MinVwEntity(vehicle, "odometer", True, _connectedcarsclient))
            if "NextServicePredicted" in vehicle["has"]:
                sensors.append(MinVwEntity(vehicle, "NextServicePredicted", False, _connectedcarsclient))
            if "EVchargePercentage" in vehicle["has"]:
                sensors.append(MinVwEntity(vehicle, "EVchargePercentage", True, _connectedcarsclient))
            if "EVHVBattTemp" in vehicle["has"]:
                sensors.append(MinVwEntity(vehicle, "EVHVBattTemp", True, _connectedcarsclient))
        async_add_entities(sensors, update_before_add=True)

    except Exception as e:
        _LOGGER.warning(f"Failed to add sensors: {e}")
        raise PlatformNotReady



class MinVwEntity(Entity):
    """Representation of a Sensor."""

    def __init__(self, vehicle, itemName, entity_registry_enabled_default, connectedcarsclient):
        """Initialize the sensor."""
        self._state = None
        self._data_date = None
        self._unit = None
        self._vehicle = vehicle
        self._itemName = itemName
        self._icon = "mdi:car"
        self._name = f"{self._vehicle['make']} {self._vehicle['model']} {self._itemName}"
        self._unique_id = f"minvw-{self._vehicle['vin']}-{self._itemName}"
        self._device_class = None
        self._connectedcarsclient = connectedcarsclient
        self._entity_registry_enabled_default = entity_registry_enabled_default
        
        if self._itemName == "outdoorTemperature":
            self._unit = TEMP_CELSIUS
            self._icon = "mdi:thermometer"
            self._device_class = DEVICE_CLASS_TEMPERATURE
        elif self._itemName == "BatteryVoltage":
            self._unit = ELECTRIC_POTENTIAL_VOLT
            self._icon = "mdi:car-battery"
            self._device_class = DEVICE_CLASS_VOLTAGE
        elif self._itemName == "fuelPercentage":
            self._unit = PERCENTAGE
            self._icon = "mdi:gas-station"
            #self._device_class = DEVICE_CLASS_VOLTAGE
        elif self._itemName == "fuelLevel":
            self._unit = VOLUME_LITERS
            self._icon = "mdi:gas-station"
            #self._device_class = DEVICE_CLASS_VOLTAGE
        elif self._itemName == "odometer":
            self._unit = LENGTH_KILOMETERS
            self._icon = "mdi:counter"
            #self._device_class = DEVICE_CLASS_VOLTAGE
        elif self._itemName == "NextServicePredicted":
            #self._unit = ATTR_LOCATION
            self._icon = "mdi:wrench"
            self._device_class = "date"  # DEVICE_CLASS_DATE
        elif self._itemName == "EVchargePercentage":
            self._unit = PERCENTAGE
            self._icon = "mdi:battery"
            self._device_class = DEVICE_CLASS_BATTERY
        elif self._itemName == "EVHVBattTemp":
            self._unit = TEMP_CELSIUS
            self._icon = "mdi:thermometer"
            self._device_class = DEVICE_CLASS_TEMPERATURE



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
    def entity_registry_enabled_default(self):
        return self._entity_registry_enabled_default

    @property
    def icon(self):
        return self._icon

    @property
    def unique_id(self):
        """The unique id of the sensor."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def available(self):
        return (self._state is not None)

    @property
    def extra_state_attributes(self):
        """Return state attributes."""
        attributes = dict()
        #attributes['state_class'] = self._state_class
        attributes['device_class'] = self._device_class
        return attributes

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    async def async_update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        #_LOGGER.debug(f"Setting status for {self._name}")

        if self._itemName == "outdoorTemperature":
            self._state = await self._connectedcarsclient._get_value(self._vehicle['id'], ["outdoorTemperatures", 0, "celsius"])
        if self._itemName == "BatteryVoltage":
            self._state = await self._connectedcarsclient._get_value(self._vehicle['id'], ["latestBatteryVoltage", "voltage"])
        if self._itemName == "fuelPercentage":
            self._state = await self._connectedcarsclient._get_value(self._vehicle['id'], ["fuelPercentage", "percent"])
        if self._itemName == "fuelLevel":
            self._state = await self._connectedcarsclient._get_value(self._vehicle['id'], ["fuelLevel", "liter"])
        if self._itemName == "odometer":
            self._state = await self._connectedcarsclient._get_value(self._vehicle['id'], ["odometer", "odometer"])
        if self._itemName == "NextServicePredicted":
            self._state = await self._connectedcarsclient._get_next_service_data_predicted(self._vehicle['id'])

        # EV
        if self._itemName == "EVchargePercentage":
            self._state = await self._connectedcarsclient._get_value(self._vehicle['id'], ["chargePercentage", "percent"])
            batlevel = round(self._state / 10)*10
            if batlevel == 100:
                self._icon = "mdi:battery"
            elif batlevel == 0:
                self._icon = "mdi:battery-outline"
            else:
                self._icon = f"mdi:battery-{batlevel}"
        if self._itemName == "EVHVBattTemp":
            self._state = await self._connectedcarsclient._get_value(self._vehicle['id'], ["highVoltageBatteryTemperature", "celsius"])



