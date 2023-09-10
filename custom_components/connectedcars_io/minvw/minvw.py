"""Wrapper for connectedcars.io."""

import logging
import traceback
import asyncio
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import aiohttp
import json


# import hashlib

# Test
# import random

_LOGGER = logging.getLogger(__name__)


class MinVW:
    """
    Primary exported interface for connectedcars.io API wrapper.
    """

    def __init__(self, email, password, namespace) -> None:
        self._email = email
        self._password = password
        self._namespace = namespace
        self._base_url_auth = "https://auth-api.connectedcars.io/"
        self._base_url_graph = "https://api.connectedcars.io/"
        self._accesstoken = None
        self._at_expires = None
        self._data = None
        self._data_expires = None
        self._lock_update = asyncio.Lock()

    async def get_next_service_data_predicted(self, vehicle_id):
        """Calculate number of days until next service. Prodicted."""
        ret = None
        date_str = await self.get_value(vehicle_id, ["service", "predictedDate"])

        if date_str is not None:
            ret = datetime.strptime(date_str, "%Y-%m-%d").date()
            # ret = (date - datetime.now().date()).days
            # if ret < 0:
            #  ret = 0
        return ret

    async def api_request(self, req_param):
        """Make an API request for data"""
        ret = None

        try:
            async with self._lock_update:
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "x-organization-namespace": f"semler:{self._namespace}",
                    "User-Agent": "ConnectedCars/360 CFNetwork/978.0.7 Darwin/18.7.0",
                    "Authorization": f"Bearer {await self._get_access_token()}",
                }

                req_body = {"query": req_param}
                req_url = self._base_url_graph + "graphql"

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        req_url, json=req_body, headers=headers
                    ) as response:
                        if response.ok:
                            ret = await response.json()
                        else:
                            _LOGGER.warning(
                                "Unexpected response: %s", await response.read()
                            )

        except aiohttp.ClientConnectionError as err:
            _LOGGER.warning("Connection error: %s", str(err))
            _LOGGER.debug("%s", traceback.format_exc())

        return ret

    async def get_latest_years_mileage(self, vehicle_id, latest_month):
        """Get mileage for latest year or month."""
        ret = None
        att = dict()

        req_param = """query YearlyMileage {
  vehicle(id: %s) {

    totalTripStatistics(period: {first: "%sZ", last: "%sZ"} ) {mileageInKm, driveDurationInMinutes, numberTrips, longestMileageInKm}
  }
}
        """

        date = datetime.utcnow()
        time_delta = relativedelta(years=-1)
        if latest_month:
            time_delta = relativedelta(months=-1)

        req_param = req_param % (
            vehicle_id,
            (date + time_delta).isoformat(timespec="milliseconds"),
            date.isoformat(timespec="milliseconds"),
        )

        vehicle_data = await self.api_request(req_param)
        ret = self._get_vehicle_value(
            vehicle_data, ["data", "vehicle", "totalTripStatistics", "mileageInKm"]
        )
        if ret is not None:
            ret = round(ret, 1)

        value = self._get_vehicle_value(
            vehicle_data,
            ["data", "vehicle", "totalTripStatistics", "driveDurationInMinutes"],
        )
        if value is not None:
            value = round(value)
        att["Duration in minutes"] = value

        att["Trips"] = self._get_vehicle_value(
            vehicle_data, ["data", "vehicle", "totalTripStatistics", "numberTrips"]
        )

        value = self._get_vehicle_value(
            vehicle_data,
            ["data", "vehicle", "totalTripStatistics", "longestMileageInKm"],
        )
        if value is not None:
            value = round(value, 1)
        att["Longest trip in km"] = value

        return ret, att

    #     async def get_mileage_since_refuel(self, vehicle_id):
    #         """Calculate distance since last refuel event."""
    #         _LOGGER.warning("get_mileage_since_refuel...")
    #         ret = None
    #         att = dict()

    #         req_param = """query fuel {
    #   vehicle(id: %s) {
    #     refuelEvents(limit: 1) {
    #       time
    #     }
    #     serverCalcGpsOdometers(limit: 1, order: DESC){odometer time}
    #   }
    # }
    #         """
    #         req_param = req_param % (vehicle_id)

    #         vehicle_data = await self.api_request(req_param)

    #         fuelevent = self._get_vehicle_value(
    #             vehicle_data, ["data", "vehicle", "refuelEvents"]
    #         )
    #         odometers = self._get_vehicle_value(
    #             vehicle_data, ["data", "vehicle", "serverCalcGpsOdometers"]
    #         )

    #         if (
    #             fuelevent is not None
    #             and len(fuelevent) == 1
    #             and fuelevent[0]["time"] is not None
    #             and odometers is not None
    #             and len(odometers) == 1
    #             and odometers[0]["odometer"] is not None
    #         ):

    #             odometer_current = odometers[0]["odometer"]
    #             fuel_time = fuelevent[0]["time"]
    #             att["Refueled at"] = fuel_time

    #             odometer_fuel_time = await self.get_odometer_at_time(vehicle_id, fuel_time)
    #             if odometer_fuel_time is not None:
    #                 ret = odometer_current - odometer_fuel_time
    #             else:
    #                 ret = 0

    #         return ret, att

    async def get_trip_at_time(self, vehicle_id, isotime):
        """Get trip at a specific time"""
        trip = None

        req_param = """query fuel {
  vehicle(id: %s) {
    trips(fromTime: "%s", first: 1 ){items{mileage, gpsMileage, odometerMileage, startOdometer, endOdometer, startTime, endTime, time}}
  }}
        """
        req_param = req_param % (vehicle_id, isotime)
        # _LOGGER.warning("req_param: %s", req_param)

        vehicle_data = await self.api_request(req_param)
        # _LOGGER.warning("vehicle_data: %s", vehicle_data)

        trip = self._get_vehicle_value(
            vehicle_data, ["data", "vehicle", "trips", "items", 0]
        )

        return trip

    #     async def get_odometer_at_time(self, vehicle_id, isotime):
    #         """Get calculated odometer value at a specific time"""
    #         odometer = None

    #         req_param = """query fuel {
    #   vehicle(id: %s) {
    #     serverCalcGpsOdometers(first: "%s", limit: 1, order: ASC){odometer time}
    #   }
    # }
    #         """
    #         req_param = req_param % (vehicle_id, isotime)
    #         # _LOGGER.warning("req_param: %s", req_param)

    #         vehicle_data = await self.api_request(req_param)
    #         # _LOGGER.warning("vehicle_data: %s", vehicle_data)

    #         odometers = self._get_vehicle_value(
    #             vehicle_data, ["data", "vehicle", "serverCalcGpsOdometers"]
    #         )

    #         if (
    #             odometers is not None
    #             and len(odometers) == 1
    #             and odometers[0]["odometer"] is not None
    #         ):
    #             odometer = odometers[0]["odometer"]

    #         return odometer

    #     async def get_fuel_economy(self, vehicle_id):
    #         """Calculate distance driven per liter of fuel."""
    #         ret = None
    #         att = dict()

    #         req_param = """query fuel {
    #   vehicle(id: %s) {
    #     refuelEvents(limit: 2, order: DESC) {
    #       litersAfter
    #       litersBefore
    #       time
    #     }
    #     fuelLevel {
    #       time
    #       liter
    #     }
    #   }
    # }
    #         """
    #         req_param = req_param % (vehicle_id)

    #         vehicle_data = await self.api_request(req_param)

    #         fuelevents = self._get_vehicle_value(
    #             vehicle_data, ["data", "vehicle", "refuelEvents"]
    #         )
    #         fuellevel = self._get_vehicle_value(
    #             vehicle_data, ["data", "vehicle", "fuelLevel"]
    #         )

    #         if fuelevents is not None and len(fuelevents) >= 2 and fuellevel is not None:

    #             fuel_used = 0
    #             fuel_used += fuelevents[1]["litersAfter"] - fuelevents[0]["litersBefore"]
    #             fuel_used += fuelevents[0]["litersAfter"] - fuellevel["liter"]
    #             att["Fuel used"] = fuel_used

    #             # Request distance
    #             time_start = fuelevents[1]["time"]
    #             time_end = fuellevel["time"]

    #             req_param = """query fuelDistance {
    #   vehicle(id: %s) {
    #     totalTripStatistics(period: {first: "%s", last: "%s"} ) { mileageInKm }
    #   }
    # }
    #             """
    #             req_param = req_param % (
    #                 vehicle_id,
    #                 time_start,
    #                 time_end,
    #             )

    #             vehicle_data = await self.api_request(req_param)
    #             distance = self._get_vehicle_value(
    #                 vehicle_data, ["data", "vehicle", "totalTripStatistics", "mileageInKm"]
    #             )

    #             if distance is not None:
    #                 att["distance"] = distance
    #                 ret = round(distance / fuel_used, 1)

    #         return ret, att

    def has_value(self, obj, key) -> bool:
        return key in obj.keys() and obj[key] is not None

    def obj_copy_attributes(self, obj_src, obj_dst, keys):
        if obj_src is not None and obj_dst is not None:
            for key in keys:
                if self.has_value(obj_src, key):
                    # obj_dst[keys[key]] = obj_src[key]
                    obj_dst[key] = obj_src[key]
        return obj_dst

    async def get_leads(self, vehicle_id):
        """Find vehicle."""
        ret = []
        data = await self._get_vehicle_data()
        for item in data["data"]["viewer"]["vehicles"]:
            vehicle = item["vehicle"]
            if vehicle["id"] == vehicle_id:
                # j = 0
                for lead in vehicle["leads"]:
                    try:
                        # Basic info
                        element = {
                            "type": lead["type"],
                            "createdTime": lead["createdTime"],
                        }
                        # Optional info
                        element = self.obj_copy_attributes(
                            lead,
                            element,
                            [
                                "updatedTime",
                                "bookingTime",
                                "lastContactedTime",
                                "severityScore",
                            ],
                        )
                        # Value
                        if self.has_value(lead, "value"):
                            element[
                                "value"
                            ] = f"{lead['value']['amount']} {lead['value']['currency']}"

                        # Context - Type specific info
                        if self.has_value(lead, "context"):
                            # Type: service_reminder
                            if lead["type"] == "service_reminder":
                                element["context"] = self.obj_copy_attributes(
                                    lead["context"],
                                    {},
                                    ["serviceDate", "oilEstimateUncertain"],
                                )
                                if lead["context"]["sourceData"] is not None:
                                    for data in lead["context"]["sourceData"]:
                                        if (
                                            data is not None
                                            and data["type"] is not None
                                            and data["value"] is not None
                                        ):
                                            element["context"][data["type"]] = data[
                                                "value"
                                            ]
                            else:
                                if self.has_value(lead, "context"):
                                    element["context"] = lead["context"]

                            # Remove emply values in context
                            remove_keys = []
                            if element["context"] is not None:
                                for key in element["context"].keys():
                                    if element["context"][key] is None:
                                        _LOGGER.debug("Ket to remove: %s", key)
                                        remove_keys.append(key)
                            for key in remove_keys:
                                element["context"].pop(key)

                        ret.append(element)

                        # j = j + 1
                        # if j >= 5:
                        #     break

                    except Exception as err:  # pylint: disable=broad-except
                        _LOGGER.error("Failed to handle lead: %s\n%s", lead, err)

        return ret

    async def get_value_float(self, vehicle_id, selector):
        """Extract a float value from read data"""
        ret = None
        data = await self.get_value(vehicle_id, selector)
        if isinstance(data, str):  # type(data) == str
            ret = float(data)
        # type(data) == float or type(data) == int:
        if isinstance(data, float) or isinstance(data, int):
            ret = data
        return ret

    async def get_value(self, vehicle_id, selector):
        """Find vehicle."""
        ret = None
        data = await self._get_vehicle_data()
        # vehicles = []
        for item in data["data"]["viewer"]["vehicles"]:
            vehicle = item["vehicle"]
            if vehicle["id"] == vehicle_id:
                ret = self._get_vehicle_value(vehicle, selector)
        return ret

    def _get_vehicle_value(self, vehicle, selector):
        """Get selected attribures in vehicle data."""
        ret = None
        obj = vehicle
        for sel in selector:
            if (obj is not None) and (
                sel in obj or (isinstance(obj, list) and sel < len(obj))
            ):
                # print(obj)
                # print(sel)
                obj = obj[sel]
            else:
                # Object does not have specified selector(s)
                obj = None
                break
        ret = obj
        return ret

    async def get_lampstatus(self, vehicle_id, lamptype):
        """Get status of warning lamps."""
        ret = None
        data = await self._get_vehicle_data()
        # vehicles = []
        for item in data["data"]["viewer"]["vehicles"]:
            vehicle = item["vehicle"]
            if vehicle["id"] == vehicle_id:
                obj = vehicle
                for lamp in obj["lampStates"]:
                    # print(lamp)
                    if lamp["type"] == lamptype:
                        ret = lamp["enabled"]
                        break
        return ret

    async def _get_voltage(self, vehicle_id):
        ret = None
        data = await self._get_vehicle_data()
        for item in data["data"]["viewer"]["vehicles"]:
            vehicle = item["vehicle"]
            if vehicle["id"] == vehicle_id:
                ret = vehicle["latestBatteryVoltage"]["voltage"]
        return ret

    async def get_vehicle_instances(self, include_additional_parameters=False):
        """Get vehicle instances and sensor data available."""
        data = await self._get_vehicle_data()
        vehicles = []
        for item in data["data"]["viewer"]["vehicles"]:
            vehicle = item["vehicle"]
            vehicle_id = vehicle["id"]

            # Find lamps for this vehicle
            lampstates = []
            for lamp in vehicle["lampStates"]:
                lampstates.append(lamp["type"])

            # Find data availability for sensors
            has = []
            if (
                self._get_vehicle_value(vehicle, ["outdoorTemperatures", 0, "celsius"])
                is not None
            ):
                has.append("outdoorTemperature")
            if (
                self._get_vehicle_value(vehicle, ["latestBatteryVoltage", "voltage"])
                is not None
            ):
                has.append("BatteryVoltage")
            if (
                self._get_vehicle_value(vehicle, ["fuelPercentage", "percent"])
                is not None
            ):
                has.append("fuelPercentage")
            if self._get_vehicle_value(vehicle, ["fuelLevel", "liter"]) is not None:
                has.append("fuelLevel")
            if self._get_vehicle_value(vehicle, ["fuelEconomy"]) is not None:
                has.append("fuelEconomy")
            if self._get_vehicle_value(vehicle, ["odometer", "odometer"]) is not None:
                has.append("odometer")
            if await self.get_next_service_data_predicted(vehicle_id) is not None:
                has.append("NextServicePredicted")
            if (
                self._get_vehicle_value(vehicle, ["chargePercentage", "pct"])
                is not None
            ):
                has.append("EVchargePercentage")
            if (
                self._get_vehicle_value(
                    vehicle, ["highVoltageBatteryTemperature", "celsius"]
                )
                is not None
            ):
                has.append("EVHVBattTemp")

            if self._get_vehicle_value(vehicle, ["ignition", "on"]) is not None:
                has.append("Ignition")
            if self._get_vehicle_value(vehicle, ["health", "ok"]) is not None:
                has.append("Health")

            if (
                self._get_vehicle_value(vehicle, ["position", "latitude"]) is not None
                and self._get_vehicle_value(vehicle, ["position", "longitude"])
                is not None
            ):
                has.append("GeoLocation")

            if self._get_vehicle_value(vehicle, ["position", "speed"]) is not None:
                has.append("Speed")

            if (
                self._get_vehicle_value(vehicle, ["refuelEvents", 0, "time"])
                is not None
            ):
                has.append("refuelEvents")

            # Request additional parameters
            if include_additional_parameters:
                req_param = """query AdditionalParameters {
vehicle(id: %s) {
    totalTripStatistics(period: {first: "%sZ", last: "%sZ"}) {mileageInKm, driveDurationInMinutes, numberTrips, longestMileageInKm}
    serverCalcGpsOdometers(limit: 1, order: DESC){odometer, time}
    trips(last: 1){items{mileage, gpsMileage, odometerMileage, startOdometer, endOdometer, startTime, endTime, time}}
}}
                """
                #     refuelEvents(limit: 1) {time, litersAfter, litersBefore}

                date = datetime.utcnow()

                req_param = req_param % (
                    vehicle_id,
                    (date + relativedelta(months=-2)).isoformat(
                        timespec="milliseconds"
                    ),
                    date.isoformat(timespec="milliseconds"),
                )

                vehicle_data = await self.api_request(req_param)
                if (
                    self._get_vehicle_value(
                        vehicle_data,
                        ["data", "vehicle", "totalTripStatistics", "mileageInKm"],
                    )
                    is not None
                ):
                    has.append("totalTripStatistics")

                if (
                    self._get_vehicle_value(
                        vehicle_data,
                        ["data", "vehicle", "serverCalcGpsOdometers", 0, "odometer"],
                    )
                    is not None
                ):
                    has.append("serverCalcGpsOdometers")

                if (
                    self._get_vehicle_value(
                        vehicle_data, ["data", "vehicle", "trips", "items", 0, "time"]
                    )
                    is not None
                ):
                    has.append("trips")

            # Add vehicle to array
            vehicles.append(
                {
                    "id": vehicle_id,
                    "vin": vehicle["vin"],
                    "name": vehicle["name"],
                    "make": vehicle["make"],
                    "model": vehicle["model"],
                    "licensePlate": vehicle["licensePlate"],
                    "lampStates": lampstates,
                    "has": has,
                }
            )

        return vehicles

    async def _get_vehicle_data(self):
        """Read data from API."""

        async with self._lock_update:
            if (
                self._data_expires is None
                or self._data is None
                or datetime.utcnow() > self._data_expires
            ):
                self._data_expires = None
                self._data = None

                req_param = """query User {
  viewer {
    vehicles {
      primary
      vehicle {
        odometer {
          odometer
        }
        odometerOffset
        id
        vin
        licensePlate
        name
        brand
        make
        model
        year
        engineSize
        avgCO2EmissionKm
        fuelEconomy
        fuelType
        fuelLevel {
          time
          liter
        }
        refuelEvents(limit: 1) {
          litersAfter
          time
        }
        fuelTankSize(limit: 1)
        fuelPercentage {
          percent
          time
        }
        adblueRemainingKm(limit: 1) {
          km
        }
        chargePercentage {
          pct
          time
        }
        highVoltageBatteryTemperature {
          celsius
          time
        }
        ignition {
          time
          on
        }
        lampStates {
          type
          time
          enabled
          lampDetails {
            title
            subtitle
          }
        }
        outdoorTemperatures(limit: 1) {
          celsius
          time
        }
        position {
          latitude
          longitude
          speed
          direction
        }
        service {
          predictedDate
        }
        latestBatteryVoltage {
          voltage
          time
        }
        health { ok }
        leads(statuses: [open], orderBy: {field: created_at, direction: DESC}) {
          type
          status
          interactions{time, channel}
          severityScore
          value{amount, currency}
          createdTime
          updatedTime
          lastActivityTime
          bookingTime
          lastContactedTime
          context {
            ... on LeadErrorCodeContext {
                errorCode, ecu, provider, errorCodeCount, description, severity, firstErrorCodeTime, lastErrorCodeTime
            }
            ... on LeadLowBatteryVoltageContext {
                sourceMedianVoltage { voltage }
            }
            ... on LeadServiceReminderContext {
                serviceDate, oilEstimateUncertain, sourceData { type, value }
            }
            ... on  LeadConnectivityIssueContext{
                latestVehiclePositionRecordTime
            }
            ... on  LeadEngineLampContext{
                lamps { type, color, title, subtitle, recommendationText, descriptionTitle, descriptionText }
            }
            ... on LeadMainPowerDisconnectContext{
                disconnectionEventTime, disconnectionLatitude, disconnectionLongitude, disconnectionPositionTime, unitConnectionState, lastConnectionEventTime, incidentCount
            }
            ... on LeadDefaultContext{
              context
            }
            ... on LeadRapidBatteryDischargeContext{
               time, durationHours, minVoltage, maxVoltage, voltageDrop
            }
            ... on LeadQuoteContext{
				quote{workshop{name},title,price{amount, currency},expirationDate,status}
            }
            ... on UserReportedLampLeadContext{
				type, color, frequency, source
            }
          }
        }

      }
    }
  }
}
          """
                req_body = {"query": req_param}

                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "x-organization-namespace": f"semler:{self._namespace}",
                    "User-Agent": "ConnectedCars/360 CFNetwork/978.0.7 Darwin/18.7.0",
                    "Authorization": f"Bearer {await self._get_access_token()}",
                }

                req_url = self._base_url_graph + "graphql"

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        req_url, json=req_body, headers=headers
                    ) as response:
                        self._data = await response.json()
                        # self._data = json.loads('')
                        _LOGGER.debug("Got vehicle data: %s", json.dumps(self._data))

                        # Does any car have ignition?
                        expire_time = 4.75
                        for item in self._data["data"]["viewer"]["vehicles"]:
                            vehicle = item["vehicle"]
                            # id = vehicle["id"]
                            ignition = self._get_vehicle_value(
                                vehicle, ["ignition", "on"]
                            )  # Preferred to check this only, but it seems to be delayed
                            speed = self._get_vehicle_value(
                                vehicle, ["position", "speed"]
                            )
                            speed = speed if speed is not None else 0
                            if bool(ignition) is True or speed > 0:  # ignition == True
                                expire_time = (
                                    0.75  # At least one car has ignition/moving
                                )
                                break
                        self._data_expires = datetime.utcnow() + timedelta(
                            minutes=expire_time
                        )

                # result = requests.post(req_url, json = req_body, headers = headers)
                # print(result)
                # result_json = result.json()
                # print(result_json['data']['viewer']['vehicles'])

                # for item in self._data['data']['viewer']['vehicles']:
                #   vehicle = item['vehicle']
                #   print(f"Primary: {item['primary']}")
                #   print(f"Name:    {vehicle['name']}")
                #   print(f"LicPlat: {vehicle['licensePlate']}")

        return self._data

    async def _get_access_token(self):
        """Authenticate to get access token."""

        if (
            self._accesstoken is None
            or self._at_expires is None
            or datetime.utcnow() > self._at_expires
        ):
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-organization-namespace": f"semler:{self._namespace}",
                "User-Agent": "ConnectedCars/360 CFNetwork/978.0.7 Darwin/18.7.0",
            }
            body = {"email": self._email, "password": self._password}

            # Authenticate
            try:
                self._accesstoken = None
                self._at_expires = None
                result_json = None

                _LOGGER.debug("Getting access token...")

                auth_url = self._base_url_auth + "auth/login/email/password"

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        auth_url, json=body, headers=headers
                    ) as response:
                        result_json = await response.json()

                # result = await requests.post(auth_url, json = body, headers = headers)
                # result_json = result.json()
                # print(result_json)

                if (
                    result_json is not None
                    and "token" in result_json
                    and "expires" in result_json
                ):
                    self._accesstoken = result_json["token"]
                    self._at_expires = datetime.utcnow() + timedelta(
                        seconds=int(result_json["expires"]) - 120
                    )
                    _LOGGER.debug("Got access token: %s...", self._accesstoken[:10])
                if (
                    result_json is not None
                    and "error" in result_json
                    and "message" in result_json
                ):
                    raise Exception(result_json["message"])

            except aiohttp.ClientError as client_error:
                _LOGGER.warning("Authentication failed. %s", client_error)
            # except requests.exceptions.Timeout:
            #     _LOGGER.warn("Authentication failed. Timeout")
            # except requests.exceptions.HTTPError as e:
            #     _LOGGER.warn(f"Authentication failed. HTTP error: {e}.")
            # except requests.exceptions.RequestException as e:
            #     _LOGGER.warn(f"Authentication failed: {e}.")

        # print(self._at_expires)

        return self._accesstoken
