"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from homeassistant import config_entries, core
from homeassistant.const import TEMP_CELSIUS, ELECTRIC_POTENTIAL_VOLT, DEVICE_CLASS_VOLTAGE, DEVICE_CLASS_TEMPERATURE, VOLUME_LITERS, PERCENTAGE, LENGTH_KILOMETERS
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
#from custom_components.eforsyning.pyeforsyning.eforsyning import Eforsyning
#from custom_components.eforsyning.pyeforsyning.models import TimeSeries

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
    #        sensors.append(MinVwEntity(vehicle, vehicle['id'], vehicle['vin'], vehicle['make'], vehicle['model'], vehicle['name'], "Name", _connectedcarsclient))
            sensors.append(MinVwEntity(vehicle, vehicle['id'], vehicle['vin'], vehicle['make'], vehicle['model'], vehicle['name'], "outdoorTemperature", _connectedcarsclient))
            sensors.append(MinVwEntity(vehicle, vehicle['id'], vehicle['vin'], vehicle['make'], vehicle['model'], vehicle['name'], "BatteryVoltage", _connectedcarsclient))
            sensors.append(MinVwEntity(vehicle, vehicle['id'], vehicle['vin'], vehicle['make'], vehicle['model'], vehicle['name'], "fuelPercentage", _connectedcarsclient))
            sensors.append(MinVwEntity(vehicle, vehicle['id'], vehicle['vin'], vehicle['make'], vehicle['model'], vehicle['name'], "fuelLevel", _connectedcarsclient))
            sensors.append(MinVwEntity(vehicle, vehicle['id'], vehicle['vin'], vehicle['make'], vehicle['model'], vehicle['name'], "odometer", _connectedcarsclient))
            #sensors.append(MinVwEntity(vehicle, vehicle['id'], vehicle['vin'], vehicle['make'], vehicle['model'], vehicle['name'], "Geocoded Location", _connectedcarsclient))
            #sensors.append(CcTrackerEntity(vehicle, "GeoLocation", _connectedcarsclient))
            #sensors.append(CcBinaryEntity(vehicle, "IgnitionY", "moving", _connectedcarsclient))
        async_add_entities(sensors, update_before_add=True)

    except Exception:
        raise PlatformNotReady


# class CcBinaryEntity(BinarySensorEntity):
#     """Representation of a BinaryEntity."""

#     def __init__(self, vehicle, itemName, device_class, connectedcarsclient):
#         self._vehicle = vehicle
#         self._itemName = itemName
#         #self._icon = "mdi:map"
#         self._name = f"{self._vehicle['make']} {self._vehicle['model']} {self._itemName}"
#         self._unique_id = f"minvw-{self._vehicle['vin']}-{self._itemName}"
#         self._device_class = device_class
#         self._connectedcarsclient = connectedcarsclient
#         self._is_on = None

#     @property
#     def device_info(self):
#         _LOGGER.debug(f"device_info (BinaryEntity)")

#         return {
#             "identifiers": {
#                 # Serial numbers are unique identifiers within a specific domain
#                 (DOMAIN, self._vehicle['vin'])
#             },
#             "name": self._vehicle['name'],
#             "manufacturer": self._vehicle['make'],
#             "model": self._vehicle['model'],
#             "sw_version": self._vehicle['licensePlate'],
#             #"via_device": (hue.DOMAIN, self.api.bridgeid),
#         }

#     @property
#     def name(self):
#         """Return the name of the sensor."""
#         return self._name

#     # @property
#     # def icon(self):
#     #     return self._icon

#     @property
#     def unique_id(self):
#         """The unique id of the sensor."""
#         _LOGGER.debug(f"Setting unique_id: {self._unique_id}")
#         return self._unique_id

#     @property
#     def is_on(self):
#         return self._is_on

#     @property
#     def available(self):
#         return (self._is_on is not None)

#     @property
#     def device_class(self):
#         return self._device_class

#     async def async_update(self):
#         self._is_on = None
#         try:
#             if self._itemName == "IgnitionY":
#                 self._is_on = str(await self._connectedcarsclient._get_value(self._vehicle['id'], ["ignition", "on"])).lower() == "true"
#         except Exception as err:
#             _LOGGER.debug(f"Unable to get binary state: {err}")


# class CcTrackerEntity(TrackerEntity):
#     """Representation of a Device TrackerEntity."""

#     def __init__(self, vehicle, itemName, connectedcarsclient):
#         self._vehicle = vehicle
#         self._itemName = itemName
#         self._icon = "mdi:map"
#         self._name = f"{self._vehicle['make']} {self._vehicle['model']} {self._itemName}"
#         self._unique_id = f"minvw-{self._vehicle['vin']}-{self._itemName}"
#         self._device_class = None
#         self._connectedcarsclient = connectedcarsclient
#         self._latitude = None
#         self._longitude = None

#     @property
#     def device_info(self):
#         _LOGGER.debug(f"device_info (TrackerEntity)")

#         return {
#             "identifiers": {
#                 # Serial numbers are unique identifiers within a specific domain
#                 (DOMAIN, self._vehicle['vin'])
#             },
#             "name": self._vehicle['name'],
#             "manufacturer": self._vehicle['make'],
#             "model": self._vehicle['model'],
#             "sw_version": self._vehicle['licensePlate'],
#             #"via_device": (hue.DOMAIN, self.api.bridgeid),
#         }

#     @property
#     def name(self):
#         """Return the name of the sensor."""
#         return self._name

#     @property
#     def icon(self):
#         return self._icon

#     @property
#     def unique_id(self):
#         """The unique id of the sensor."""
#         _LOGGER.debug(f"Setting unique_id: {self._unique_id}")
#         return self._unique_id

#     @property
#     def source_type(self) -> str:
#         return "gps"

#     @property
#     def location_accuracy(self) -> int:
#         return 1

#     @property
#     def latitude(self):
#         return self._latitude

#     @property
#     def longitude(self):
#         return self._longitude

#     @property
#     def available(self):
#         return (self._latitude is not None and self._longitude is not None)

#     # @property
#     # def state(self):
#     #     # State with location coordinates seems necessary to have it appear on the main map
#     #     return f"{self._latitude}, {self._longitude}"

#     @property
#     def extra_state_attributes(self):
#         attributes = dict()
#         attributes['device_class'] = self._device_class
#         return attributes

#     async def async_update(self):
#         self._latitude = None
#         self._longitude = None
#         try:
#             self._latitude = await self._connectedcarsclient._get_value(self._vehicle['id'], ["position", "latitude"])
#             self._longitude = await self._connectedcarsclient._get_value(self._vehicle['id'], ["position", "longitude"])
#         except Exception as err:
#             _LOGGER.debug(f"Unable to get vehicle location: {err}")


class MinVwEntity(Entity):
    """Representation of a Sensor."""

    def __init__(self, vehicle, id, vin, make, model, devicename, itemName, connectedcarsclient):
        """Initialize the sensor."""
        self._state = None
        self._data_date = None
        self._unit = None
        self._vehicle = vehicle
        #self._id = id
        #self._vin = vin
        #self._make = make
        #self._model = model
        #self._devicename = devicename
        self._itemName = itemName
        self._icon = "mdi:car"
#        self._sensor_value = f"{sensor_type}-{sensor_point}"
        self._name = f"{make} {model} {self._itemName}"
        self._unique_id = f"minvw-{self._vehicle['vin']}-{self._itemName}"
        self._device_class = None
        self._connectedcarsclient = connectedcarsclient
        self._data1 = None
        self._data2 = None
        
#        self._state_class = "measurement"
#        self._last_reset = None
        # if sensor_type == "energy":
        #     self._unit = "kWh"
        #     self._icon = "mdi:flash-circle"
        #     self._device_class = "energy"
        #     if sensor_point == 'end':
        #         self._state_class = "total_increasing"
        # elif sensor_type == "water":
        #     self._unit = "m³"
        #     self._icon = "mdi:water"
        #     #self._device_class = "volume"
        # else:
        #     self._unit = TEMP_CELSIUS
        #     self._icon = "mdi:thermometer"
        #     self._device_class = "temperature"
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
        elif self._itemName == "Geocoded Location":
            #self._unit = ATTR_LOCATION
            self._icon = "mdi:map"
            #self._device_class = DEVICE_CLASS_VOLTAGE




    @property
    def device_info(self):
        _LOGGER.debug(f"device_info (MinVwEntity)")

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
        _LOGGER.debug(f"Setting unique_id: {self._unique_id}")
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
        if self._itemName == "Geocoded Location":
            attributes['source_type'] = "gps"
            attributes['latitude'] = self._data1
            attributes['longitude'] = self._data2

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
        if self._itemName == "Geocoded Location":
            self._data1 = await self._connectedcarsclient._get_value(self._vehicle['id'], ["position", "latitude"])
            self._data2 = await self._connectedcarsclient._get_value(self._vehicle['id'], ["position", "longitude"])
            self._state = f"{self._data1}, {self._data2}"


        #self._data.update()
        #self._data_date = self._data.get_data_date()
        #self._state = self._data.get_data(self._sensor_value)

        #self._state = self._name

        #_LOGGER.debug(f"Done setting status for {self.name} = {self._state} {self._unit}")
        #_LOGGER.warning(f"eforsyning update: {self._name}")

