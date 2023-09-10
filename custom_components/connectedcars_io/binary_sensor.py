"""Support for connectedcars.io / Min Volkswagen integration."""

import logging
from datetime import timedelta
import traceback

from homeassistant import config_entries, core
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)  # ,  BinarySensorEntityDescription
from homeassistant.exceptions import PlatformNotReady

from .const import DOMAIN, CONF_HEALTH_SENSITIVITY

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Set up the Connectedcars_io binary_sensor platform."""
    config = hass.data[DOMAIN][config_entry.entry_id]

    _connectedcarsclient = config["connectedcarsclient"]

    try:
        sensors = []
        data = await _connectedcarsclient.get_vehicle_instances()
        for vehicle in data:
            if "Ignition" in vehicle["has"]:
                sensors.append(
                    CcBinaryEntity(
                        vehicle, "Ignition", "", "moving", True, _connectedcarsclient
                    )
                )
            if "Health" in vehicle["has"]:
                sensors.append(
                    CcBinaryEntity(
                        vehicle,
                        "Health",
                        "",
                        "problem",
                        True,
                        _connectedcarsclient,
                        config[CONF_HEALTH_SENSITIVITY],
                    )
                )
            for lampState in vehicle["lampStates"]:
                sensors.append(
                    CcBinaryEntity(
                        vehicle,
                        "Lamp",
                        lampState,
                        "problem",
                        False,
                        _connectedcarsclient,
                    )
                )
        async_add_entities(sensors, update_before_add=True)

    except Exception as err:
        _LOGGER.warning("Failed to add sensors: %s", err)
        _LOGGER.debug("%s", traceback.format_exc())
        raise PlatformNotReady from err


class CcBinaryEntity(BinarySensorEntity):
    """Representation of a BinaryEntity."""

    def __init__(
        self,
        vehicle,
        itemName,
        subitemName,
        device_class,
        entity_registry_enabled_default,
        connectedcarsclient,
        sensitivity=None,
    ) -> None:
        self._vehicle = vehicle
        self._itemName = itemName
        self._subitemName = subitemName
        # self._icon = "mdi:map"
        self._name = f"{self._vehicle['make']} {self._vehicle['model']} {self._itemName}{self._subitemName.capitalize()}"
        self._unique_id = f"{DOMAIN}-{self._vehicle['vin']}-{self._itemName}{self._subitemName.capitalize()}"
        self._device_class = device_class
        self._connectedcarsclient = connectedcarsclient
        self._sensitivity = sensitivity
        self._is_on = None
        self._entity_registry_enabled_default = entity_registry_enabled_default
        self._dict = dict()
        _LOGGER.debug("Adding sensor: %s", self._unique_id)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._vehicle["vin"])},
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
        return self._is_on is not None

    @property
    def device_class(self):
        return self._device_class

    @property
    def extra_state_attributes(self):
        """Return state attributes."""
        attributes = dict()
        for key, value in self._dict.items():
            attributes[key] = value
        return attributes

    async def async_update(self):
        """Update data."""
        self._is_on = None
        try:
            if self._itemName == "Ignition":
                self._is_on = (
                    str(
                        await self._connectedcarsclient.get_value(
                            self._vehicle["id"], ["ignition", "on"]
                        )
                    ).lower()
                    == "true"
                )
            elif self._itemName == "Health":
                # self._is_on = (
                #     str(
                #         await self._connectedcarsclient.get_value(
                #             self._vehicle["id"], ["health", "ok"]
                #         )
                #     ).lower()
                #     != "true"
                # )
                self._dict["Leads"] = await self._connectedcarsclient.get_leads(
                    self._vehicle["id"]
                )
                self._is_on = self.evaluate_health()

            elif self._itemName == "Lamp":
                self._is_on = (
                    str(
                        await self._connectedcarsclient.get_lampstatus(
                            self._vehicle["id"], self._subitemName
                        )
                    ).lower()
                    == "true"
                )

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Unable to get binary state: %s", err)

    def evaluate_health(self):
        ret = False
        for lead in self._dict["Leads"]:
            if "type" in lead and lead["type"] is not None:
                t = lead["type"]
                if self._sensitivity == "high" and t in (
                    "error_code_high",
                    "lamp_engine_lamp",
                ):
                    ret = True
                elif self._sensitivity == "medium" and (
                    t
                    in (
                        "error_code_high",
                        "error_code_medium",
                        "poor_battery",
                    )
                    or t.startswith("lamp_")
                ):
                    ret = True
                elif self._sensitivity == "low" and (
                    t
                    in (
                        "error_code_high",
                        "error_code_medium",
                        "error_code",
                        "poor_battery",
                    )
                    or t.startswith("lamp_")
                ):
                    ret = True
                elif self._sensitivity == "all":
                    ret = True
        return ret
