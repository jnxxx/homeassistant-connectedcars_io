"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
from datetime import timedelta, datetime, timezone
import traceback

from homeassistant import config_entries, core
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfVolume,
    PERCENTAGE,
    UnitOfLength,
    UnitOfSpeed,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

# from homeassistant.helpers.entity import Entity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    RestoreSensor,
    # SensorEntityDescription,
    SensorStateClass,
)


from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Set up the Connectedcars_io sensor platform."""
    config = hass.data[DOMAIN][config_entry.entry_id]

    _connectedcarsclient = config["connectedcarsclient"]

    try:
        sensors = []
        sensors_update_later = []
        data = await _connectedcarsclient.get_vehicle_instances(True)
        for vehicle in data:
            if "outdoorTemperature" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(
                        vehicle, "outdoorTemperature", True, _connectedcarsclient
                    )
                )
            if "BatteryVoltage" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(vehicle, "BatteryVoltage", True, _connectedcarsclient)
                )
            if "odometer" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(vehicle, "odometer", True, _connectedcarsclient)
                )
            if "fuelPercentage" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(vehicle, "fuelPercentage", True, _connectedcarsclient)
                )
            if "fuelLevel" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(vehicle, "fuelLevel", True, _connectedcarsclient)
                )
            if "fuelEconomy" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(vehicle, "fuel economy", False, _connectedcarsclient)
                )
            if "NextServicePredicted" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(
                        vehicle, "NextServicePredicted", False, _connectedcarsclient
                    )
                )
            if "EVchargePercentage" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(
                        vehicle, "EVchargePercentage", True, _connectedcarsclient
                    )
                )
            if "EVHVBattTemp" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(vehicle, "EVHVBattTemp", True, _connectedcarsclient)
                )
            if "Speed" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(vehicle, "Speed", True, _connectedcarsclient)
                )
            if "totalTripStatistics" in vehicle["has"]:
                sensors.append(
                    MinVwEntity(
                        vehicle, "mileage latest year", False, _connectedcarsclient
                    )
                )
                sensors.append(
                    MinVwEntity(
                        vehicle, "mileage latest month", False, _connectedcarsclient
                    )
                )
            if (
                "refuelEvents" in vehicle["has"]
                and "trips" in vehicle["has"]
                and "odometer" in vehicle["has"]
            ):
                sensors_update_later.append(
                    MinVwEntityRestore(
                        vehicle, "mileage since refuel", False, _connectedcarsclient
                    )
                )
        async_add_entities(sensors, update_before_add=True)
        async_add_entities(sensors_update_later, update_before_add=False)

    except Exception as err:
        _LOGGER.warning("Failed to add sensors: %s", err)
        _LOGGER.debug("%s", traceback.format_exc())
        raise PlatformNotReady from err

    # Build array with devices to keep
    devices = []
    for vehicle in data:
        devices.append((DOMAIN, vehicle["vin"]))

    # Remove devices no longer reported
    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(
        device_registry, config_entry.entry_id
    ):
        for identifier in device_entry.identifiers:
            if identifier not in devices:
                _LOGGER.warning("Removing device: %s", identifier)
                device_registry.async_remove_device(device_entry.id)


class MinVwEntity(SensorEntity):
    """Representation of a Sensor."""

    def __init__(
        self, vehicle, itemName, entity_registry_enabled_default, connectedcarsclient
    ) -> None:
        """Initialize the sensor."""
        self._state = None
        self._data_date = None
        self._unit = None
        self._vehicle = vehicle
        self._itemName = itemName
        self._icon = "mdi:car"
        self._name = (
            f"{self._vehicle['make']} {self._vehicle['model']} {self._itemName}"
        )
        self._unique_id = f"{DOMAIN}-{self._vehicle['vin']}-{self._itemName}"
        self._device_class = None
        self._connectedcarsclient = connectedcarsclient
        self._entity_registry_enabled_default = entity_registry_enabled_default
        self._dict = dict()

        if self._itemName == "outdoorTemperature":
            self._unit = UnitOfTemperature.CELSIUS
            self._icon = "mdi:thermometer"
            self._device_class = SensorDeviceClass.TEMPERATURE
        elif self._itemName == "BatteryVoltage":
            self._unit = UnitOfElectricPotential.VOLT
            self._icon = "mdi:car-battery"
            self._device_class = SensorDeviceClass.VOLTAGE
        elif self._itemName == "fuelPercentage":
            self._unit = PERCENTAGE
            self._icon = "mdi:gas-station"
            # self._device_class = SensorDeviceClass.
        elif self._itemName == "fuelLevel":
            self._unit = UnitOfVolume.LITERS
            self._icon = "mdi:gas-station"
            self._device_class = SensorDeviceClass.VOLUME
        elif self._itemName == "odometer":
            self._unit = UnitOfLength.KILOMETERS
            self._icon = "mdi:counter"
            self._device_class = SensorDeviceClass.DISTANCE
            self._attr_state_class = SensorStateClass.TOTAL
        elif self._itemName == "NextServicePredicted":
            # self._unit = ATTR_LOCATION
            self._icon = "mdi:wrench"
            self._device_class = SensorDeviceClass.DATE
        elif self._itemName == "EVchargePercentage":
            self._unit = PERCENTAGE
            self._icon = "mdi:battery"
            self._device_class = SensorDeviceClass.BATTERY
        elif self._itemName == "EVHVBattTemp":
            self._unit = UnitOfTemperature.CELSIUS
            self._icon = "mdi:thermometer"
            self._device_class = SensorDeviceClass.TEMPERATURE
        elif self._itemName == "Speed":
            self._unit = UnitOfSpeed.KILOMETERS_PER_HOUR
            self._icon = "mdi:speedometer"
            self._device_class = SensorDeviceClass.SPEED
        elif self._itemName == "mileage latest year":
            self._unit = UnitOfLength.KILOMETERS
            self._icon = "mdi:counter"
            self._device_class = SensorDeviceClass.DISTANCE
        elif self._itemName == "mileage latest month":
            self._unit = UnitOfLength.KILOMETERS
            self._icon = "mdi:counter"
            self._device_class = SensorDeviceClass.DISTANCE
        elif self._itemName == "mileage since refuel":
            self._unit = UnitOfLength.KILOMETERS
            self._icon = "mdi:counter"
            self._device_class = SensorDeviceClass.DISTANCE
        elif self._itemName == "fuel economy":
            self._unit = "km/l"
            self._icon = "mdi:gas-station-outline"

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
        return self._state is not None

    @property
    def device_class(self):
        return self._device_class

    @property
    def extra_state_attributes(self):
        """Return state attributes."""
        attributes = dict()
        # attributes['state_class'] = self._state_class
        #        if self._device_class is not None:
        #            attributes['device_class'] = self._device_class
        for key in self._dict:
            attributes[key] = self._dict[key]
        return attributes

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    async def async_update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        # _LOGGER.debug(f"Setting status for {self._name}")

        if self._itemName == "outdoorTemperature":
            self._state = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["outdoorTemperatures", 0, "celsius"]
            )
        if self._itemName == "BatteryVoltage":
            self._state = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["latestBatteryVoltage", "voltage"]
            )
        if self._itemName == "fuelPercentage":
            self._state = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["fuelPercentage", "percent"]
            )
        if self._itemName == "fuelLevel":
            self._state = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["fuelLevel", "liter"]
            )
        if self._itemName == "odometer":
            self._state = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["odometer", "odometer"]
            )
        if self._itemName == "NextServicePredicted":
            self._state = (
                await self._connectedcarsclient.get_next_service_data_predicted(
                    self._vehicle["id"]
                )
            )
        if self._itemName == "Speed":
            self._state = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["position", "speed"]
            )
            self._dict["Direction"] = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["position", "direction"]
            )
            # direction = self._dict["Direction"]
            # _LOGGER.debug(f"Speed: {self._state} km/h, direction: {direction}")
        if self._itemName == "mileage latest year" and (
            self._data_date is None
            or datetime.utcnow() >= self._data_date + timedelta(hours=1)
        ):
            (
                self._state,
                self._dict,
            ) = await self._connectedcarsclient.get_latest_years_mileage(
                self._vehicle["id"], False
            )
            if self._state is not None:
                self._data_date = datetime.utcnow()
        if self._itemName == "mileage latest month" and (
            self._data_date is None
            or datetime.utcnow() >= self._data_date + timedelta(hours=1)
        ):
            (
                self._state,
                self._dict,
            ) = await self._connectedcarsclient.get_latest_years_mileage(
                self._vehicle["id"], True
            )
            if self._state is not None:
                self._data_date = datetime.utcnow()
        if self._itemName == "mileage since refuel":
            self._state = None

            refuel_event_time = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["refuelEvents", 0, "time"]
            )
            if refuel_event_time is not None:
                # Has refuel timestamp changed?
                if (
                    "Refueled at" not in self._dict
                    or self._dict["Refueled at"] is None
                    or refuel_event_time != self._dict["Refueled at"]
                ):
                    _LOGGER.debug("Refuel event detected")
                    self._dict["Refueled at"] = refuel_event_time
                    self._dict["Odometer"] = None

                # Do we have odometer value corresponding to refuel timestamp?
                if "Odometer" not in self._dict or self._dict["Odometer"] is None:
                    trip = await self._connectedcarsclient.get_trip_at_time(
                        self._vehicle["id"], refuel_event_time
                    )
                    if trip is not None and "startOdometer" in trip:
                        _LOGGER.debug(
                            "Got odometer value at refuel event: %s",
                            trip["startOdometer"],
                        )
                        self._dict["Odometer"] = trip["startOdometer"]

                # Subtract refuel odometer from current odometer
                if "Odometer" in self._dict and self._dict["Odometer"] is not None:
                    odometer_current = await self._connectedcarsclient.get_value(
                        self._vehicle["id"], ["odometer", "odometer"]
                    )
                    distance_since_refuel = odometer_current - self._dict["Odometer"]
                    if distance_since_refuel >= 0:
                        self._state = distance_since_refuel

            # ignition = (
            #     str(
            #         await self._connectedcarsclient.get_value(
            #             self._vehicle["id"], ["ignition", "on"]
            #         )
            #     ).lower()
            #     == "true"
            # )
            # try:
            #     ignition_time = datetime.fromisoformat(
            #         str(
            #             await self._connectedcarsclient.get_value(
            #                 self._vehicle["id"], ["ignition", "time"]
            #             )
            #         ).replace("Z", "+00:00")
            #     )
            # except Exception as err:  # pylint: disable=broad-except
            #     _LOGGER.warning("Unable to parse ignition timestamp. Err: %s", err)
            # _LOGGER.debug("ignition: %s, time: %s", ignition, ignition_time)

            # if (
            #     self._data_date is None
            #     or datetime.utcnow() >= self._data_date + timedelta(hours=1)
            #     or (
            #         not ignition
            #         and ignition_time > self._data_date.replace(tzinfo=timezone.utc)
            #     )
            # ):
            #     (
            #         self._state,
            #         self._dict,
            #     ) = await self._connectedcarsclient.get_mileage_since_refuel(
            #         self._vehicle["id"]
            #     )
            #     _LOGGER.debug("5")
            #     if self._state is not None:
            #         self._data_date = datetime.utcnow()

        if self._itemName == "fuel economy":
            self._state = round(
                await self._connectedcarsclient.get_value(
                    self._vehicle["id"], ["fuelEconomy"]
                ),
                1,
            )

        # EV
        if self._itemName == "EVchargePercentage":
            self._state = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["chargePercentage", "pct"]
            )
            batlevel = round(self._state / 10) * 10
            if batlevel == 100:
                self._icon = "mdi:battery"
            elif batlevel == 0:
                self._icon = "mdi:battery-outline"
            else:
                self._icon = f"mdi:battery-{batlevel}"
        if self._itemName == "EVHVBattTemp":
            self._state = await self._connectedcarsclient.get_value(
                self._vehicle["id"], ["highVoltageBatteryTemperature", "celsius"]
            )


class MinVwEntityRestore(MinVwEntity, RestoreSensor):
    """Representation of a restoring sensor."""

    # def __init__(
    #     self, vehicle, itemName, entity_registry_enabled_default, connectedcarsclient
    # ):
    #     """Inherited"""
    #     super().__init__(
    #         vehicle, itemName, entity_registry_enabled_default, connectedcarsclient
    #     )

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        if (
            (last_state := await self.async_get_last_state()) is not None
            # and (extra_data := await self.async_get_last_sensor_data()) is not None
            and last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            # The trigger might have fired already while we waited for stored data,
            # then we should not restore state
            #            and CONF_STATE not in self._rendered
        ):
            _LOGGER.debug(
                "Read previously stored state and attributes for sensor: %s",
                self._unique_id,
            )
            self._state = last_state.state

            for key in last_state.attributes:
                if key not in [
                    "unit_of_measurement",
                    "device_class",
                    "icon",
                    "friendly_name",
                ]:
                    self._dict[key] = last_state.attributes[key]
            _LOGGER.debug("State: %s, Attributes: %s", last_state.state, self._dict)

        await MinVwEntity.async_update(self)
        self.async_write_ha_state()

    # async def async_get_last_sensor_data(self):
    #     """Restore Utility Meter Sensor Extra Stored Data."""
    #     _LOGGER.debug("2")
    #     if (restored_last_extra_data := await self.async_get_last_extra_data()) is None:
    #         return None

    #     _LOGGER.debug("3")
    #     return restored_last_extra_data.as_dict()
