
# Connectedcars.io (Min Volkswagen)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

The `Connectedcars.io (Min Volkswagen)` component is a Home Assistant custom component for showing car information for Danish Volkswagens equipped with the hardware to send data to the mobile app "Min Volkswagen". 
Min Skoda, Min Seat and Mit Audi all use the same backend and should work as well, although still not tested.

## Installation
---
### Manual Installation
  1. Copy  `connectedcars_io`  folder into your custom_components folder in your hass configuration directory.
  2. Restart Home Assistant.

### Installation with HACS (Home Assistant Community Store)
  1. Ensure that [HACS](https://hacs.xyz/) is installed.
  2. In HACS / Integrations / Kebab menu / Custom repositories, add the url the this repository.
  3. Search for and install the `Connectedcars.io (Min Volkswagen)` integration.
  4. Restart Home Assistant.


## Configuration

It is configurable through config flow, meaning it will popup a dialog after adding the integration.
  1. Head to Configuration --> Integrations
  2. Add new and search for `Connectedcars.io (Min Volkswagen)` 
  3. Enter credentials and namespace.

#### Currently known namespaces
 - minvolkswagen *(default)*
 - minskoda
 - minseat
 - mitaudi

#### Multiple cars
If you have multiple cars on the same account, they should all appear.  
If you have multiple cars of different brands, add the integration multiple times each with the suitable namespace.  
*So far only tested with a single car*

## State and attributes
A device is created for each car.
For each car the following sensors can be created, but only when data is present. Thus fuel based cars should have fuel level sensors, while EVs should have battery sensors. 

The naming scheme is `{brand} {model} <name>`.  
Sensor names:
* BatteryVoltage (12V battery)
* EVHVBattTemp (EV)
* EVchargePercentage (EV)
* Charging (EV) - binary sensor, on while the car is charging
* ChargingStatus (EV) - average charge speed (kW) while charging; attributes include charged %, time until 80%, kWh/range added (disabled by default)
* EVBatteryCapacity (EV) - current usable battery capacity in kWh (degradation-adjusted); factory spec and energy-available-now as attributes (disabled by default)
* EVBatteryHealth (EV) - battery State of Health in %; predicted SoH and charge cycles as attributes
* EVEfficiency (EV) - average consumption in kWh/100km; km/kWh as attribute (disabled by default)
* PowerDisconnected - binary sensor (problem), on if the OBD device has been unplugged (disabled by default)
* AdBlueRange - remaining AdBlue range in km (diesel)
* DriverScore - driving score out of ten; previous score as attribute (disabled by default)
* fuelLevel
* fuelPercentage
* GeoLocation
* Health (severity threshold configurable)
  * Attribute: Leads array may help to explain the cause
* Ignition
* Lamp *+name* (one sensor per each reported lamp, disabled by default)
* NextServicePredicted (disabled by default)
* odometer
* outdoorTemperature
* Speed
* Fuel economy (disabled by default)
* Mileage latest year (disabled by default)
* Mileage latest month (disabled by default)
* Mileage since refuel (disabled by default)
* LastTrip - distance of the latest completed trip in km; attributes hold the trip details as shown in the app: start/end time and address, duration, fuel/electricity used, and the detected driving events (hard/medium/low accelerations, brakes and turns, speeding), including the individual events with timestamp and g-force

All sensors may not be reported correctedly with all cars.
Among others fuelPercentage is one of those.

## Events
A `connectedcars_io_event` event is fired on the Home Assistant event bus, usable as an automation trigger:
* `charging_started` / `charging_stopped` (EV) — when the car starts or stops charging. Data: `type`, `vin`, `make`, `model`, `license_plate` and `charge_percentage` (state of charge when the event fired).
* `trip_ended` — when a new completed trip is detected. Data: `type`, `vin`, `make`, `model`, `license_plate` and `trip` with the full trip details (times, addresses, mileage, fuel/electricity used, acceleration/brake/turn counters and the individual `events` with type, time and g-force). Since events show up in the Logbook, this also gives a browsable trip history.

```yaml
trigger:
  - platform: event
    event_type: connectedcars_io_event
    event_data:
      type: trip_ended  # or charging_started / charging_stopped
```

Note the API is polled, so events fire up to a few minutes after the fact.

## Services
`connectedcars_io.get_trips` returns the trip history (newest first), for use in scripts or template cards. All fields are optional: `vin` (needed with multiple cars), `from_time` / `to_time` (range filter), `limit` (default 20, max 100) and `include_events` (include the individual driving events per trip).

```yaml
action: connectedcars_io.get_trips
data:
  from_time: "2026-07-01T00:00:00+02:00"
  limit: 50
response_variable: result
```

Try it in Developer tools / Actions to see the response shape.

## Trip map
The integration serves an interactive map of recent trips at `/api/connectedcars_io/trips_map/<token>`, with each trip colour-coded and the detected driving events marked on the route (letter = type, colour = severity; hover for details). The URL is in the LastTrip sensor's `Map URL` attribute — the token is a random per-installation secret so the page can be embedded in a dashboard without HA authentication.

```yaml
type: iframe
url: /api/connectedcars_io/trips_map/<token>?days=7
aspect_ratio: 75%
```

Query parameters: `days` (default 7), `from`/`to` (`YYYY-MM-DD`, a custom date range that overrides `days`), `limit` (default 8, max 200 — the 8 newest trips get distinct colours, older ones render gray), `legend` (`true`/`false` or `1`/`0`, default true — set to false for a clean map with just the routes), `vin` (with multiple cars). The page itself has preset buttons (7/30/90/365 days) and a custom from–to date picker; it shows the total km for the selected span. With `legend=false` the panel and its controls are left out entirely and the map fills the frame, which suits small dashboard cards.

## Debugging
It is possible to debug log the raw response from the API. This is done by setting up logging like below in configuration.yaml in Home Assistant. It is also possible to set the log level through a service call in UI.  

```
logger: 
  default: info
  logs: 
    custom_components.connectedcars_io: debug
```

## Examples

Configuration  
![Config](https://github.com/jnxxx/homeassistant-connectedcars_io/raw/main/images/config.png)  
![Options](https://github.com/jnxxx/homeassistant-connectedcars_io/raw/main/images/options.png)

Device  
![Device](https://github.com/jnxxx/homeassistant-connectedcars_io/raw/main/images/device.png)

Dashboard  
![Dashboard](https://github.com/jnxxx/homeassistant-connectedcars_io/raw/main/images/dashboard.png)

Location state  
![Location state](https://github.com/jnxxx/homeassistant-connectedcars_io/raw/main/images/location_state.png)
