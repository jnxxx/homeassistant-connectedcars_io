"""HTTP view serving an interactive map of recent trips.

The page is reachable at /api/connectedcars_io/trips_map/<map_token> without
HA authentication, so it can be embedded in a dashboard Webpage (iframe) card.
The token is a per-config-entry random secret persisted in the entry data; it
grants access to this page only. The LastTrip sensor exposes the URL as its
"Map URL" attribute.
"""

from datetime import UTC, datetime, timedelta
import json
import logging
import secrets

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MAX_COLORED_TRIPS = 8  # categorical palette slots; older trips render neutral

# The core map_tiles proxy (HA 2026.9+) publishes its rotating access token in
# hass.data under its own domain. Looked up rather than imported, so this module
# still loads on older cores, which fall back to OSM directly.
MAP_TILES_DOMAIN = "map_tiles"
MAP_TILES_RASTER_URL = "/api/map_tiles/raster/{z}/{x}/{y}.png?token={token}"
OSM_RASTER_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
# Vector styles the frontend ships next to the proxy. They already point at the
# /api/map_tiles endpoints, so the page only has to add the token.
MAP_STYLE_LIGHT = "/static/map/light.json"
MAP_STYLE_DARK = "/static/map/dark.json"
OSM_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    " contributors"
)
MIN_MAP_ZOOM = 1  # Leaflet zoom 0 drives the MapLibre adapter to -1
MAX_MAP_ZOOM = 20  # MapLibre overzooms the vector source rather than stop at it
MAX_RASTER_ZOOM = 19  # OSM serves no raster past this

# Categorical palette (light/dark mode steps) and status colors for event
# severity. Validated with the dataviz palette validator against the map tile
# surfaces; identity never rides on color alone (legend + letter glyphs).
SERIES_LIGHT = [
    "#2a78d6",
    "#1baf7a",
    "#eda100",
    "#008300",
    "#4a3aa7",
    "#e34948",
    "#e87ba4",
    "#eb6834",
]
SERIES_DARK = [
    "#3987e5",
    "#199e70",
    "#c98500",
    "#008300",
    "#9085e9",
    "#e66767",
    "#d55181",
    "#d95926",
]
NEUTRAL = "#898781"
SEVERITY_COLORS = {"high": "#d03b3b", "medium": "#ec835a", "low": "#fab219"}
EVENT_LETTERS = {
    "acceleration": "A",
    "brake": "B",
    "speeding": "F",
    "turn_left": "S",
    "turn_right": "S",
}
EVENT_NAMES_DA = {
    "acceleration": "Acceleration",
    "brake": "Opbremsning",
    "speeding": "Fartoverskridelse",
    "turn_left": "Sving (venstre)",
    "turn_right": "Sving (højre)",
}
SEVERITY_NAMES_DA = {"high": "kraftig", "medium": "middel", "low": "let"}

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _parse_bool(value, default=True):
    """Query flag to bool; missing or unrecognised falls back to default."""
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default
    
def _parse_ts(value):
    """ISO-8601 string to epoch seconds, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

def _parse_day(value):
    """YYYY-MM-DD string to an aware UTC datetime, or None."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None

def _api_iso(dt):
    """Datetime to the API's ISO-8601 Zulu format."""
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _client_for_token(hass, token):
    """Client of the config entry whose map token matches, or None."""
    if not token.isascii():  # compare_digest rejects non-ASCII input
        return None
    for config in hass.data.get(DOMAIN, {}).values():
        candidate = config.get("map_token")
        if candidate and secrets.compare_digest(candidate, token):
            return config["connectedcarsclient"]
    return None


def _map_tiles_token(hass):
    """Current access token of the core map tiles proxy, or None without one."""
    tokens = hass.data.get(MAP_TILES_DOMAIN)
    if not tokens:
        return None
    try:
        return tokens[-1]
    except (IndexError, KeyError, TypeError):
        return None


def _tile_config(hass, map_token):
    """Base map source for the page, and where to renew its token.

    With the core proxy the page draws Home Assistant's own vector basemap and
    keeps its raster tiles as the fallback. Without it there is neither, so the
    page loads OpenStreetMap raster tiles directly.
    """
    tile_token = _map_tiles_token(hass)
    return {
        "url": MAP_TILES_RASTER_URL if tile_token else OSM_RASTER_URL,
        "token": tile_token,
        "tokenUrl": f"/api/connectedcars_io/trips_map/{map_token}/tile_token",
        "styleLight": MAP_STYLE_LIGHT if tile_token else None,
        "styleDark": MAP_STYLE_DARK if tile_token else None,
        "attribution": OSM_ATTRIBUTION,
        "minZoom": MIN_MAP_ZOOM,
        "maxZoom": MAX_MAP_ZOOM,
        "rasterMaxZoom": MAX_RASTER_ZOOM,
    }


def _event_positions(trip):
    """Attach coordinates to each detected event by time-interpolating the
    trip's GPS track."""
    track = []
    for pos in trip.get("positions") or []:
        ts = _parse_ts(pos.get("time"))
        if ts is not None and pos.get("latitude") is not None:
            track.append((ts, pos["latitude"], pos["longitude"]))
    track.sort()

    events = []
    for event in trip.get("profilings") or []:
        ts = _parse_ts(event.get("time"))
        if ts is None or not track:
            continue
        after = next((p for p in track if p[0] >= ts), None)
        before = next((p for p in reversed(track) if p[0] <= ts), None)
        if before is None or after is None:
            point = before or after
            lat, lon = point[1], point[2]
        elif after[0] == before[0]:
            lat, lon = before[1], before[2]
        else:
            frac = (ts - before[0]) / (after[0] - before[0])
            lat = before[1] + frac * (after[1] - before[1])
            lon = before[2] + frac * (after[2] - before[2])
        parts = str(event.get("type", "")).rsplit("_", 1)
        kind, severity = parts[0], (parts[1] if len(parts) == 2 else "low")
        events.append(
            {
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "letter": EVENT_LETTERS.get(kind, "?"),
                "name": EVENT_NAMES_DA.get(kind, kind),
                "severity": severity,
                "severityName": SEVERITY_NAMES_DA.get(severity, severity),
                "color": SEVERITY_COLORS.get(severity, NEUTRAL),
                "time": event.get("time"),
                "g": event.get("gForce"),
            }
        )
    return events


def _trip_path(trip):
    """GPS track as [lat, lon] pairs; falls back to the start/end points."""
    path = [
        [round(p["latitude"], 6), round(p["longitude"], 6)]
        for p in (trip.get("positions") or [])
        if p.get("latitude") is not None and p.get("longitude") is not None
    ]
    if not path:
        for key in ("start", "end"):
            lat, lon = trip.get(f"{key}Latitude"), trip.get(f"{key}Longitude")
            if lat is not None and lon is not None:
                path.append([round(lat, 6), round(lon, 6)])
    return path


def build_payload(vehicle, trips, selection, tiles, show_legend=True):
    """JSON-serializable payload embedded in the map page.

    selection is {"days": int|None, "from": "YYYY-MM-DD"|None, "to": ...} —
    either a preset day count or a custom date range.
    """
    out = []
    for idx, trip in enumerate(trips):
        path = _trip_path(trip)
        if len(path) < 2:
            continue
        colored = idx < MAX_COLORED_TRIPS
        out.append(
            {
                "colorLight": SERIES_LIGHT[idx] if colored else NEUTRAL,
                "colorDark": SERIES_DARK[idx] if colored else NEUTRAL,
                "startTime": trip.get("startTime"),
                "distanceKm": trip.get("mileage"),
                "durationMin": trip.get("duration"),
                "fromAddress": trip.get("startAddressString"),
                "toAddress": trip.get("endAddressString"),
                "path": path,
                "events": _event_positions(trip),
            }
        )
    return {
        "vehicle": vehicle.get("name"),
        "selection": selection,
        "showLegend": show_legend,
        "tiles": tiles,
        "trips": out,
    }


def async_ensure_map_token(hass, entry):
    """Make sure the config entry carries a persistent map token.

    Must run before the entry's update listener is registered, so the
    data update does not trigger a reload loop.
    """
    if "map_token" not in entry.data:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "map_token": secrets.token_hex(16)}
        )
    return entry.data["map_token"]


class ConnectedCarsTripsMapView(HomeAssistantView):
    """Serve the trips map page."""

    url = "/api/connectedcars_io/trips_map/{token}"
    name = "api:connectedcars_io:trips_map"
    requires_auth = False

    def __init__(self, hass) -> None:
        """Initialize."""
        self.hass = hass

    async def get(self, request, token):
        """Render the map page."""
        client = _client_for_token(self.hass, token)
        if client is None:
            return web.Response(status=404, text="Unknown map token")

        try:
            days = min(max(int(request.query.get("days", 7)), 1), 365)
            limit = min(max(int(request.query.get("limit", 8)), 1), 200)
        except ValueError:
            return web.Response(status=400, text="Bad days/limit")
        vin = request.query.get("vin")
        show_legend = _parse_bool(request.query.get("legend"), True)

        # A from/to date range takes precedence over the days preset.
        from_q = request.query.get("from")
        to_q = request.query.get("to")
        to_iso = None
        if from_q:
            start = _parse_day(from_q)
            end = _parse_day(to_q) if to_q else None
            if start is None or (to_q and end is None):
                return web.Response(status=400, text="Bad from/to date")
            if end is not None and end < start:
                start, end = end, start
                from_q, to_q = to_q, from_q
            from_iso = _api_iso(start)
            if end is not None:
                # inclusive end date
                to_iso = _api_iso(end + timedelta(days=1))
            selection = {"days": None, "from": from_q, "to": to_q}
        else:
            from_iso = _api_iso(datetime.now(UTC) - timedelta(days=days))
            selection = {"days": days, "from": None, "to": None}

        vehicles = await client.get_vehicle_instances()
        vehicle = next(
            (v for v in vehicles if vin is None or v["vin"] == vin), None
        )
        if vehicle is None:
            return web.Response(status=404, text="Unknown VIN")

        trips = (
            await client.get_trips(
                vehicle["id"],
                from_iso=from_iso,
                to_iso=to_iso,
                limit=limit,
                include_events=True,
                include_positions=True,
            )
            or []
        )
        payload = build_payload(
            vehicle, trips, selection, _tile_config(self.hass, token), show_legend
        )
        return web.Response(
            text=render_map_html(payload),
            content_type="text/html",
            headers={"Cache-Control": "no-store"},
        )


class ConnectedCarsMapTileTokenView(HomeAssistantView):
    """Hand the map page a current base map token.

    The core rotates it every 30 minutes and a dashboard stays open far longer,
    so the page renews it here instead of reloading itself. It takes the same
    map token that grants the page, and gives out nothing beyond the tiles that
    page already draws.
    """

    url = "/api/connectedcars_io/trips_map/{token}/tile_token"
    name = "api:connectedcars_io:trips_map:tile_token"
    requires_auth = False

    def __init__(self, hass) -> None:
        """Initialize."""
        self.hass = hass

    async def get(self, request, token):
        """Return the current base map token."""
        if _client_for_token(self.hass, token) is None:
            return web.Response(status=404, text="Unknown map token")
        return web.json_response(
            {"token": _map_tiles_token(self.hass)},
            headers={"Cache-Control": "no-store"},
        )


def render_map_html(payload):
    """Self-contained Leaflet page; payload is inlined as JSON."""
    return _MAP_HTML.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))


_MAP_HTML = """<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ture</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {
    --surface-1: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --border: rgba(11,11,11,0.10);
    --ring: #ffffff;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --surface-1: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --border: rgba(255,255,255,0.10);
      --ring: #1a1a19;
    }
  }
  html, body { margin: 0; height: 100%; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  #map { height: 100%; }
  .legend {
    position: absolute; top: 10px; left: 10px; z-index: 1000;
    background: var(--surface-1); color: var(--text-primary);
    border: 1px solid var(--border); border-radius: 10px;
    padding: 8px 10px; max-height: 55%; overflow: auto;
    font-size: 12px; line-height: 1.45; max-width: 46%;
    box-shadow: 0 1px 4px rgba(0,0,0,0.15);
    opacity: 1;
    transition: max-height 0.3s ease-in-out, opacity 0.2s ease-in-out;
  }
  .legend h1 { font-size: 12px; margin: 0 0 5px; font-weight: 600; cursor: pointer; }
  #legend.collapsed {
    max-height: 1.2em !important;
    opacity: 0.95;
  }
  #legend.preload, #legend.preload * {
    transition: none !important;
  }
  #legend h1 #idCollapse {
    display: inline-block;
    user-select: none;
    margin-right: 6px;
    transition: transform 0.3s ease-in-out; /* Smooth rotation */
  }
  #legend.collapsed h1 #idCollapse {
    transform: rotate(-90deg); /* Rotates ▼ to point right (▶) */
  }
  .ranges, .custom { display: flex; align-items: center; gap: 4px; margin: 0 0 6px; }
  .ranges button, .custom button {
    font: inherit; font-size: 11px; color: var(--text-secondary);
    background: transparent; border: 1px solid var(--border);
    border-radius: 6px; padding: 2px 7px; cursor: pointer;
  }
  .ranges button:hover, .custom button:hover { color: var(--text-primary); }
  .ranges button.active {
    color: var(--text-primary); font-weight: 600;
    border-color: var(--text-secondary);
  }
  .custom { border-top: 1px solid var(--border); padding-top: 6px; }
  .custom input {
    font: inherit; font-size: 11px; color: var(--text-primary);
    background: transparent; border: 1px solid var(--border);
    border-radius: 6px; padding: 1px 4px; color-scheme: light dark;
  }
  .legend .trip { display: flex; align-items: center; gap: 6px; cursor: pointer; white-space: nowrap; }
  .legend .trip:hover { text-decoration: underline; }
  .legend .chip { width: 10px; height: 10px; border-radius: 3px; flex: none; }
  .legend .muted { color: var(--text-secondary); }
  .legend .total { font-weight: 600; margin: 0 0 4px; }
  .legend .empty { color: var(--text-secondary); }
  .ev-icon {
    display: flex; align-items: center; justify-content: center;
    width: 16px; height: 16px; border-radius: 50%;
    border: 2px solid var(--ring);
    color: #0b0b0b; font-size: 9px; font-weight: 700;
    box-sizing: border-box;
  }
  .start-icon {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--ring); border: 3px solid #000; box-sizing: border-box;
  }
  .leaflet-tooltip { font-family: inherit; }
  /* Only the raster fallback needs this: OpenStreetMap ships one raster
     style, so dark mode filters it, exactly as Home Assistant does. The vector
     base map has its own dark style, and its canvas is not a .leaflet-tile. */
  @media (prefers-color-scheme: dark) {
    .leaflet-tile-pane .leaflet-tile {
      filter: invert(0.9) hue-rotate(170deg) brightness(1.5) contrast(1.2) saturate(0.3);
    }
  }
  .leaflet-container .leaflet-control-attribution {
    background: var(--surface-1);
    color: var(--text-secondary);
    border-radius: 6px 0 0 0;
  }
  .leaflet-container .leaflet-control-attribution a { color: var(--text-secondary); }
</style>
</head>
<body>
<div id="map"></div>
<div class="legend" id="legend"></div>
<script>
"use strict";
const DATA = __PAYLOAD__;
const darkQuery = window.matchMedia
  ? window.matchMedia("(prefers-color-scheme: dark)")
  : null;
let dark = Boolean(darkQuery && darkQuery.matches);
let ring = dark ? "#1a1a19" : "#ffffff";
const showLegend = DATA.showLegend !== false;
const tileConfig = DATA.tiles;

const map = L.map("map", {
  zoomControl: !showLegend,
  minZoom: tileConfig.minZoom,
  maxZoom: tileConfig.maxZoom,
});
map.attributionControl.setPrefix("");
if (showLegend) L.control.zoom({ position: 'topright' }).addTo(map);

// --- Base map --------------------------------------------------------------
// The one Home Assistant itself draws: MapLibre over the vector tiles its
// map_tiles proxy serves, falling back to that proxy's raster tiles where
// WebGL2 is missing. Follows the frontend's own src/common/map/base-layer.ts,
// including its version pins.
const MAPLIBRE = "https://unpkg.com/maplibre-gl@5.24.0/dist/";
const MAPLIBRE_LEAFLET =
  "https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.4/leaflet-maplibre-gl.js";
// Without it Arabic and Hebrew labels render reversed. MapLibre's worker loads
// it, hence a URL rather than a script tag.
const RTL_TEXT_PLUGIN = "/static/map/mapbox-gl-rtl-text.js";
// Browsers keep about 16 live WebGL contexts and drop the oldest, which a
// dashboard full of maps hits. A transient loss is restored, hence the grace.
const CONTEXT_RESTORE_GRACE = 2000;
const RECOVERY_THROTTLE = 30000;

let token = tileConfig.token || "";
let rasterLayer = null;
let vectorLayer = null;
let renewPending = false;
let lastRenew = 0;
let lastRecovery = 0;
let refused = false;
// Replaced once a base layer is up. Raster has no dark variant of its own, so
// there it stays a no-op and the CSS filter does the work.
let setDarkMode = () => {};
let onTokenChange = () => {};

// MapLibre's worker fetches tiles and Leaflet asks for raster ones with an
// <img>. Neither can set a header, so the token has to ride in the URL.
function withToken(url) {
  try {
    const parsed = new URL(url, window.location.href);
    if (parsed.origin === window.location.origin &&
        parsed.pathname.indexOf("/api/map_tiles/") === 0) {
      parsed.searchParams.set("token", token);
      return parsed.href;
    }
  } catch (err) {
    // Nothing we can rewrite, so hand it back untouched.
  }
  return url;
}

function loadAsset(tag, props) {
  return new Promise((resolve, reject) => {
    const el = Object.assign(document.createElement(tag), props);
    el.onload = resolve;
    el.onerror = () => reject(new Error(props.src || props.href));
    document.head.appendChild(el);
  });
}

// Rules out iOS below 15, older Android tablets and blocklisted drivers.
function supportsWebGL2() {
  try {
    const gl = document.createElement("canvas").getContext("webgl2");
    if (!gl) return false;
    // Contexts are scarce; the probe must not keep one.
    const lose = gl.getExtension("WEBGL_lose_context");
    if (lose) lose.loseContext();
    return true;
  } catch (err) {
    return false;
  }
}

async function loadStyle(wantDark) {
  const res = await fetch(wantDark ? tileConfig.styleDark : tileConfig.styleLight);
  if (!res.ok) throw new Error("style " + res.status);
  const style = await res.json();
  // MapLibre rejects a relative sprite URL. Not the glyph URL: resolving that
  // one would mangle its {fontstack} and {range} placeholders.
  const absolute = (u) => (u.charAt(0) === "/" ? window.location.origin + u : u);
  if (typeof style.sprite === "string") {
    style.sprite = absolute(style.sprite);
  } else if (Array.isArray(style.sprite)) {
    style.sprite = style.sprite.map(
      (sprite) => Object.assign({}, sprite, { url: absolute(sprite.url) })
    );
  }
  return style;
}

function addRaster() {
  rasterLayer = L.tileLayer(tileConfig.url, {
    attribution: tileConfig.attribution,
    maxZoom: tileConfig.maxZoom,
    // OSM's raster stops at 19 and the proxy refuses higher, so Leaflet scales
    // that level up rather than asking for tiles which are not there.
    maxNativeZoom: tileConfig.rasterMaxZoom,
    // Leaflet substitutes any layer option into the URL template.
    token: token,
  }).addTo(map);
  if (tileConfig.token) rasterLayer.on("tileerror", renewToken);
}

async function addVector() {
  // Only loaded on the vector path, so the raster fallback stays as light as
  // it was.
  await loadAsset("link", {
    rel: "stylesheet",
    href: MAPLIBRE + "maplibre-gl.css",
  }).catch(() => {});
  await loadAsset("script", { src: MAPLIBRE + "maplibre-gl.js" });
  await loadAsset("script", { src: MAPLIBRE_LEAFLET });

  try {
    const rtl = window.maplibregl.setRTLTextPlugin(
      new URL(RTL_TEXT_PLUGIN, window.location.href).href, true
    );
    if (rtl && rtl.catch) rtl.catch(() => {});
  } catch (err) {
    // Already requested, or unavailable. Those scripts read reversed; the rest
    // of the map still renders.
  }

  const layer = L.maplibreGL({
    style: await loadStyle(dark),
    // Absolute, or the worker fetching tiles cannot resolve them.
    transformRequest: (url) => ({ url: withToken(url) }),
    // Draws CJK with the device's own fonts instead of fetching glyphs for it.
    localIdeographFontFamily: "sans-serif",
  });
  // The adapter builds the MapLibre map in onAdd, so a refused context or a
  // blocked worker throws here rather than earlier.
  layer.addTo(map);
  vectorLayer = layer;
  watchVector(layer.getMaplibreMap());
}

function watchVector(glMap) {
  let contextLost = false;
  let fallbackTimer = null;
  // Tracked apart so a failed style request rolls back to what is displayed,
  // not to the opposite of what it asked for.
  let applied = dark;
  let requested = dark;
  let latest = 0;

  function onVisibility() {
    if (contextLost) scheduleSwap();
  }

  function swapToRaster() {
    if (!vectorLayer) return;
    document.removeEventListener("visibilitychange", onVisibility);
    try {
      vectorLayer.remove();
    } catch (err) {
      // May never have finished being added.
    }
    vectorLayer = null;
    setDarkMode = () => {};
    addRaster();
  }

  function scheduleSwap() {
    clearTimeout(fallbackTimer);
    // Backgrounding drops the context too, and there it comes back on return.
    if (!vectorLayer || document.hidden) return;
    fallbackTimer = setTimeout(swapToRaster, CONTEXT_RESTORE_GRACE);
  }

  function applyStyle(wantDark, rebuild) {
    // Styles are fetched, so only the newest request may touch the map.
    const request = ++latest;
    loadStyle(wantDark)
      .then((style) => {
        if (request !== latest) return;
        applied = wantDark;
        const gl = vectorLayer && vectorLayer.getMaplibreMap();
        if (!gl) return;
        // A recovery re-applies the style it already has, and MapLibre would
        // diff that down to no change at all, leaving the refused source just
        // as dead. Only a full reload rebuilds it. A theme change needs no
        // such thing: those two styles differ, so the diff does the work and
        // keeps the map on screen while it swaps.
        gl.setStyle(style, rebuild ? { diff: false } : undefined);
      })
      .catch(() => {
        if (request === latest) requested = applied;
      });
  }

  glMap.on("webglcontextlost", () => {
    contextLost = true;
    scheduleSwap();
  });
  glMap.on("webglcontextrestored", () => {
    contextLost = false;
    clearTimeout(fallbackTimer);
  });
  document.addEventListener("visibilitychange", onVisibility);
  map.on("unload", () => {
    clearTimeout(fallbackTimer);
    document.removeEventListener("visibilitychange", onVisibility);
  });

  glMap.on("error", (event) => {
    const status = event.error && event.error.status;
    // 403 is a lapsed token, 404 a proxy not registered yet, and no status at
    // all a network failure. All three recover the same way. Throttled, or a
    // proxy refusing for another reason loops.
    if (status !== undefined && status !== 403 && status !== 404) return;
    if (Date.now() - lastRecovery < RECOVERY_THROTTLE) return;
    lastRecovery = Date.now();
    refused = true;
    renewToken();
  });

  setDarkMode = (wantDark) => {
    if (!vectorLayer || wantDark === requested) return;
    requested = wantDark;
    applyStyle(wantDark);
  };
  // A refused request leaves the source dead: the TileJSON is fetched once and
  // never retried, so only a new token can revive it.
  onTokenChange = () => {
    if (vectorLayer && refused) {
      refused = false;
      applyStyle(requested, true);
    }
  };
}

function renewToken() {
  if (!tileConfig.token || renewPending) return;
  if (Date.now() - lastRenew < RECOVERY_THROTTLE) return;
  renewPending = true;
  fetch(tileConfig.tokenUrl, { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : null))
    .then((body) => {
      if (!body || !body.token || body.token === token) return;
      token = body.token;
      if (rasterLayer) {
        rasterLayer.options.token = token;
        rasterLayer.redraw(); // refused tiles are cached as failures
      }
      onTokenChange();
    })
    .catch(() => {})
    .finally(() => {
      renewPending = false;
      lastRenew = Date.now();
    });
}

if (tileConfig.styleLight && token && supportsWebGL2()) {
  addVector().catch(() => {
    // No style, no script or no context, but still a map.
    if (vectorLayer) {
      try {
        vectorLayer.remove();
      } catch (err) {
        // Never finished being added.
      }
      vectorLayer = null;
    }
    addRaster();
  });
} else {
  addRaster();
}

// The core rotates the token every 30 minutes and a dashboard stays open far
// longer, so renew ahead of that as well as on a refusal.
if (tileConfig.token) setInterval(renewToken, 10 * 60 * 1000);
const fmt = (iso, withDate) => {
  const d = new Date(iso);
  const opts = withDate
    ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }
    : { hour: "2-digit", minute: "2-digit" };
  return d.toLocaleString("da-DK", opts);
};

const sel = DATA.selection;
const fmtDay = (s) => new Date(s + "T00:00:00").toLocaleDateString("da-DK",
  { day: "2-digit", month: "2-digit", year: "numeric" });
const headline = sel.days != null
  ? "ture, seneste " + sel.days + " dage"
  : "ture, " + fmtDay(sel.from) + " – " + (sel.to ? fmtDay(sel.to) : "nu");
const legend = document.getElementById("legend");
legend.classList.add('preload');
if (!showLegend) legend.remove();

const collapseBtn = document.createElement('span');
collapseBtn.id = 'idCollapse';
collapseBtn.style.userSelect = 'none';

// Check stored state
const CollapseStorageKey = 'connectedcars_trips_map_legend_collapsed';
const isCollapsed = localStorage.getItem(CollapseStorageKey) === 'true';
collapseBtn.textContent = '▼';
if (isCollapsed) legend.classList.add('collapsed');

// Create text node for title
const vehicle = DATA.vehicle || "Bil";
const titleText = document.createTextNode(` ${vehicle} · ${headline}`);
const legendh1 = document.createElement('h1');
legendh1.addEventListener('click', function() {
  const isCollapsed = legend.classList.toggle('collapsed');
  localStorage.setItem(CollapseStorageKey, isCollapsed ? 'true' : 'false');
});
legendh1.appendChild(collapseBtn);
legendh1.appendChild(titleText);
legend.appendChild(legendh1);


const ranges = document.createElement("div");
ranges.className = "ranges";
[[7, "7 dage"], [30, "30 dage"], [90, "90 dage"], [365, "1 år"]].forEach(([days, label]) => {
  const btn = document.createElement("button");
  btn.textContent = label;
  if (days === sel.days) btn.className = "active";
  btn.addEventListener("click", () => {
    const url = new URL(window.location);
    url.searchParams.set("days", days);
    url.searchParams.delete("from");
    url.searchParams.delete("to");
    window.location = url;
  });
  ranges.appendChild(btn);
});
legend.appendChild(ranges);

// custom interval: from/to date inputs override the presets
const custom = document.createElement("div");
custom.className = "custom";
const fromInput = document.createElement("input");
fromInput.type = "date";
fromInput.value = sel.from || "";
const toInput = document.createElement("input");
toInput.type = "date";
toInput.value = sel.to || "";
const apply = document.createElement("button");
apply.textContent = "Vis";
apply.addEventListener("click", () => {
  if (!fromInput.value) { fromInput.focus(); return; }
  const url = new URL(window.location);
  url.searchParams.delete("days");
  url.searchParams.set("from", fromInput.value);
  if (toInput.value) url.searchParams.set("to", toInput.value);
  else url.searchParams.delete("to");
  window.location = url;
});
custom.append(fromInput, document.createTextNode("–"), toInput, apply);
legend.appendChild(custom);

const totalKm = DATA.trips.reduce((sum, t) => sum + (t.distanceKm || 0), 0);
const total = document.createElement("div");
total.className = "total";
total.textContent = "I alt " +
  totalKm.toLocaleString("da-DK", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) +
  " km · " + DATA.trips.length + (DATA.trips.length === 1 ? " tur" : " ture");
legend.appendChild(total);

const allBounds = [];
const themed = [];  // repainted when the OS theme flips, as the base map is
DATA.trips.forEach((trip) => {
  const color = dark ? trip.colorDark : trip.colorLight;
  const label = fmt(trip.startTime, true) + " · " +
    (trip.distanceKm != null ? trip.distanceKm.toFixed(1) : "?") + " km" +
    (trip.durationMin != null ? " · " + trip.durationMin + " min" : "");

  // white/dark casing under the line separates overlapping trips
  const casing = L.polyline(trip.path, { color: ring, weight: 7, opacity: 0.8, interactive: false }).addTo(map);
  const line = L.polyline(trip.path, { color: color, weight: 3 }).addTo(map);
  line.bindTooltip(label, { sticky: true });
  line.on("mouseover", () => line.setStyle({ weight: 5 }));
  line.on("mouseout", () => line.setStyle({ weight: 3 }));

  const start = L.marker(trip.path[0], {
    icon: L.divIcon({
      className: "",
      html: '<div class="start-icon" style="border-color:' + color + '"></div>',
      iconSize: [10, 10], iconAnchor: [5, 5],
    }),
    interactive: false,
  }).addTo(map);

  trip.events.forEach((ev) => {
    const marker = L.marker([ev.lat, ev.lon], {
      icon: L.divIcon({
        className: "",
        html: '<div class="ev-icon" style="background:' + ev.color + '">' + ev.letter + "</div>",
        iconSize: [16, 16], iconAnchor: [8, 8],
      }),
    }).addTo(map);
    marker.bindTooltip(
      ev.name + " (" + ev.severityName + ") · " + fmt(ev.time, false) +
      (ev.g != null ? " · " + ev.g + " g" : "")
    );
  });

  const row = document.createElement("div");
  row.className = "trip";
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.style.background = color;
  const rowLabel = document.createElement("span");
  rowLabel.textContent = label;
  row.append(chip, rowLabel);
  row.title = (trip.fromAddress || "?") + " → " + (trip.toAddress || "?");
  row.addEventListener("click", () => map.fitBounds(line.getBounds(), { padding: [30, 30] }));
  row.addEventListener("mouseenter", () => line.setStyle({ weight: 6 }));
  row.addEventListener("mouseleave", () => line.setStyle({ weight: 3 }));
  legend.appendChild(row);

  allBounds.push(line.getBounds());
  themed.push({ trip: trip, casing: casing, line: line, start: start, chip: chip });
});

// The base map restyles itself on a theme change, so the routes drawn over it
// have to keep up; leaving one half of the page on the old palette is worse
// than not following at all.
if (darkQuery && darkQuery.addEventListener) {
  darkQuery.addEventListener("change", (event) => {
    dark = event.matches;
    ring = dark ? "#1a1a19" : "#ffffff";
    themed.forEach((item) => {
      const color = dark ? item.trip.colorDark : item.trip.colorLight;
      item.casing.setStyle({ color: ring });
      item.line.setStyle({ color: color });
      item.chip.style.background = color;
      const icon = item.start.getElement();
      const dot = icon && icon.querySelector(".start-icon");
      if (dot) dot.style.borderColor = color;
    });
    setDarkMode(dark);
  });
}

if (allBounds.length) {
  const bounds = allBounds.reduce((acc, b) => acc.extend(b), L.latLngBounds(allBounds[0]));
  map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
} else {
  legend.innerHTML += '<div class="empty">Ingen ture i perioden.</div>';
  map.setView([56.0, 10.5], 6);
}
const note = document.createElement("div");
note.className = "muted";
note.textContent = "A: acceleration · B: opbremsning · F: fart · S: sving";
legend.appendChild(note);

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    legend.classList.remove('preload');
  });
});
</script>
</body>
</html>
"""
