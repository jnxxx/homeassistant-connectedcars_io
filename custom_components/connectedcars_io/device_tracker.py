"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
from datetime import timedelta, datetime
import traceback

from homeassistant import config_entries, core
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.exceptions import PlatformNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Set up the Connectedcars_io device_tracker platform."""
    config = hass.data[DOMAIN][config_entry.entry_id]

    _connectedcarsclient = config["connectedcarsclient"]

    try:
        sensors = []
        data = await _connectedcarsclient.get_vehicle_instances()
        for vehicle in data:
            if "GeoLocation" in vehicle["has"]:
                sensors.append(
                    CcTrackerEntity(vehicle, "GeoLocation", _connectedcarsclient)
                )
        async_add_entities(sensors, update_before_add=True)

    except Exception as err:
        _LOGGER.warning("Failed to add sensors: %s", err)
        _LOGGER.debug("%s", traceback.format_exc())
        raise PlatformNotReady from err


class CcTrackerEntity(TrackerEntity):
    """Representation of a Device TrackerEntity."""

    def __init__(self, vehicle, itemName, connectedcarsclient) -> None:
        self._vehicle = vehicle
        self._itemName = itemName
        self._icon = "mdi:map"
        self._name = (
            f"{self._vehicle['make']} {self._vehicle['model']} {self._itemName}"
        )
        self._unique_id = f"{DOMAIN}-{self._vehicle['vin']}-{self._itemName}"
        self._device_class = None
        self._connectedcarsclient = connectedcarsclient
        self._latitude = None
        self._longitude = None
        self._cached_location = None
        self._cached_time = None
        _LOGGER.debug("Adding sensor: %s", self._unique_id)

    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._vehicle["vin"])
            },
            "name": f"{self._vehicle['make']} {self._vehicle['model']}",  # self._vehicle["name"],
            "manufacturer": self._vehicle["make"],
            "model": self._vehicle["name"]
            .removeprefix("VW")
            .removeprefix("Skoda")
            .removeprefix("Seat")
            .removeprefix("Audi")
            .strip(),
            "sw_version": self._vehicle["licensePlate"],
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
        return self._latitude is not None and self._longitude is not None

    @property
    def device_class(self):
        return self._device_class

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
        # attributes['device_class'] = self._device_class
        return attributes

    async def async_update(self):
        """Update data."""
        self._latitude = None
        self._longitude = None
        try:
            ignition = (
                str(
                    await self._connectedcarsclient.get_value(
                        self._vehicle["id"], ["ignition", "on"]
                    )
                ).lower()
                == "true"
            )
            ignition_time = None
            timestamp = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["ignition", "time"]
            )
            if is_date_valid(timestamp):
                ignition_time = datetime.fromisoformat(
                    str(timestamp).replace("Z", "+00:00")
                )
            _LOGGER.debug("ignition: %s, time: %s", ignition, ignition_time)

            latitude = await self._connectedcarsclient.get_value_float(
                self._vehicle["id"], ["position", "latitude"]
            )
            longitude = await self._connectedcarsclient.get_value_float(
                self._vehicle["id"], ["position", "longitude"]
            )
            position = tuple((latitude, longitude))

            if ignition:
                self._cached_location = None
                self._cached_time = None
            else:
                if (
                    self._cached_location is None
                    or ignition_time is None
                    or self._cached_time is None
                    or ignition_time > self._cached_time
                ):
                    self._cached_location = position
                    self._cached_time = ignition_time
                    _LOGGER.debug("position: %s", position)
                else:
                    position = self._cached_location
                    _LOGGER.debug("cached_location: %s", position)

            self._latitude = position[0]
            self._longitude = position[1]

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Unable to get vehicle location: %s", err)


def is_date_valid(date) -> bool:
    valid_date = True
    try:
        valid_date = (
            False
            if (date is None)
            else bool(datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z"))
        )
    except ValueError:
        valid_date = False
    return valid_date
