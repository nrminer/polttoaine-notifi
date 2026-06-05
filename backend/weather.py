"""
Weather and road condition data for Finnish fuel demand modeling.

**Data sources**:
1. FMI (Finnish Meteorological Institute) Open Data — daily weather observations
   - API: OGC WFS 2.0 (XML-based)
   - Endpoint: https://opendata.fmi.fi/wfs
   - Authentication: None (fully open)
   - License: Creative Commons Attribution 4.0
   - Stored query: fmi::observations::weather::daily::simple

2. Digitraffic — road condition and weather station data
   - API: REST JSON
   - Endpoint: https://tie.digitraffic.fi/api/weathercam/v1/
   - Authentication: None
   - License: CC 4.0

**Status**:
Experimental helper. This module is not currently wired into run_prediction()
or predict_tomorrow(), so API responses and UI labels must not claim
weather-adjusted predictions until that integration exists.

**Caching**: 3-hour cache (weather updates frequently but not minute-by-minute)

Error handling: returns neutral values (None / 1.0) on API failure.
"""
from __future__ import annotations
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from statistics import mean

logger = logging.getLogger("bensavahti.weather")

# Tracked cities (matches tracker.py TRACKED_CITIES)
TRACKED_CITIES = ("Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti")

# FMI FMISID station codes for tracked cities (largest observation station per city)
# Source: https://en.ilmatieteenlaitos.fi/observation-stations (manual lookup)
_FMI_STATIONS = {
    "Helsinki": "100971",  # Helsinki Kaisaniemi
    "Espoo": "101023",     # Espoo Tapiola (closest to Espoo center)
    "Vantaa": "100968",    # Helsinki-Vantaa airport
    "Tampere": "101118",   # Tampere Härmälä
    "Turku": "100949",     # Turku airport
    "Lahti": "101061",     # Lahti Laune
}

# Digitraffic road weather station IDs (closest to each city center)
# Source: https://tie.digitraffic.fi/api/weathercam/v1/stations (manual lookup)
_DIGITRAFFIC_STATIONS = {
    "Helsinki": "1001",    # Helsinki area
    "Espoo": "1002",       # Espoo area
    "Vantaa": "1003",      # Vantaa area (near airport)
    "Tampere": "2001",     # Tampere area
    "Turku": "3001",       # Turku area
    "Lahti": "4001",       # Lahti area
}

HEADERS = {"User-Agent": "Mozilla/5.0 (BensaVahti/2.0; +fuel-price-predictor)"}
TIMEOUT = 15

# Cache: {cache_key: (timestamp, data)}
_cache: Dict[str, tuple[datetime, any]] = {}
CACHE_TTL_SECONDS = 3 * 3600  # 3 hours


def _cache_get(key: str):
    """Return cached value if fresh, else None."""
    if key not in _cache:
        return None
    ts, val = _cache[key]
    if datetime.now(timezone.utc) - ts < timedelta(seconds=CACHE_TTL_SECONDS):
        return val
    del _cache[key]
    return None


def _cache_set(key: str, val):
    """Store value with current timestamp."""
    _cache[key] = (datetime.now(timezone.utc), val)


def _fetch_fmi_weather(fmisid: str, days: int = 1) -> Optional[Dict]:
    """Fetch daily weather observations from FMI WFS API.

    Returns dict with: {temp_mean, temp_min, temp_max, precipitation_sum}
    All temps in Celsius, precipitation in mm. None on failure."""

    cache_key = f"fmi:{fmisid}:{days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        # FMI WFS stored query for daily weather observations
        # Returns last N days of aggregated weather data
        url = "https://opendata.fmi.fi/wfs"
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "getFeature",
            "storedquery_id": "fmi::observations::weather::daily::simple",
            "fmisid": fmisid,
            "parameters": "tday,tmin,tmax,rrday",  # daily mean/min/max temp, precip
            "maxlocations": 1,
            "timestep": 1440,  # daily (minutes)
        }

        r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        r.raise_for_status()

        # Parse XML response (simplified — production would use lxml)
        # Format: <wfs:FeatureCollection><wfs:member><BsWfs:BsWfsElement>...
        # We extract the MOST RECENT observation (last <BsWfs:BsWfsElement>)

        xml = r.text

        # Quick-and-dirty XML parse (robust parser would use lxml.etree)
        # Extract last occurrence of each parameter
        def extract_last(param_name: str) -> Optional[float]:
            tag = f"<BsWfs:{param_name}>"
            end_tag = f"</BsWfs:{param_name}>"
            idx = xml.rfind(tag)
            if idx == -1:
                return None
            end_idx = xml.find(end_tag, idx)
            if end_idx == -1:
                return None
            val_str = xml[idx + len(tag):end_idx].strip()
            try:
                return float(val_str)
            except ValueError:
                return None

        temp_mean = extract_last("tday")
        temp_min = extract_last("tmin")
        temp_max = extract_last("tmax")
        precip = extract_last("rrday")

        result = {
            "temp_mean": temp_mean,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "precipitation_sum": precip if precip is not None else 0.0,
        }

        _cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.warning(f"FMI weather fetch failed for fmisid={fmisid}: {e}")
        return None


def _fetch_digitraffic_road(station_id: str) -> Optional[Dict]:
    """Fetch road condition from Digitraffic road weather API.

    Returns dict with: {road_temp, road_condition, severity}
    road_condition: "dry" | "wet" | "icy" | "snowy" | "unknown"
    severity: 0.0 (dry) to 1.0 (severe ice/snow)
    None on failure."""

    cache_key = f"digitraffic:{station_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        # Digitraffic weather station API
        # Note: actual endpoint structure may differ; adjust based on API docs
        url = f"https://tie.digitraffic.fi/api/weathercam/v1/stations/{station_id}/data"

        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()

        # Extract road surface condition (schema depends on actual API)
        # Placeholder parsing — adjust to real JSON structure
        road_temp = data.get("roadTemperature")
        condition_code = data.get("roadCondition", "unknown")

        # Map condition code to severity
        severity_map = {
            "dry": 0.0,
            "moist": 0.1,
            "wet": 0.2,
            "slush": 0.5,
            "icy": 0.8,
            "snowy": 0.9,
            "frost": 0.7,
            "unknown": 0.3,  # neutral
        }

        severity = severity_map.get(condition_code.lower(), 0.3)

        result = {
            "road_temp": road_temp,
            "road_condition": condition_code.lower(),
            "severity": severity,
        }

        _cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.warning(f"Digitraffic road condition fetch failed for station={station_id}: {e}")
        return None


def fetch_weather_conditions(cities: List[str] = None) -> Dict[str, Dict]:
    """Fetch current weather and road conditions for tracked cities.

    Args:
        cities: List of city names. Defaults to TRACKED_CITIES.

    Returns:
        Dict mapping city name to:
        {
            "temp_celsius": float | None,
            "precipitation_mm": float | None,
            "road_condition": str ("dry" | "wet" | "icy" | "snowy" | "unknown"),
            "severity": float (0.0–1.0),
        }

        Returns empty dict on total failure (no cities available).

    Example:
        >>> conditions = fetch_weather_conditions(["Helsinki", "Tampere"])
        >>> conditions["Helsinki"]["temp_celsius"]
        -5.2
        >>> conditions["Helsinki"]["road_condition"]
        'icy'
    """
    if cities is None:
        cities = TRACKED_CITIES

    result = {}

    for city in cities:
        fmisid = _FMI_STATIONS.get(city)
        road_station = _DIGITRAFFIC_STATIONS.get(city)

        if not fmisid:
            logger.warning(f"No FMI station mapped for city: {city}")
            continue

        # Fetch FMI weather
        weather = _fetch_fmi_weather(fmisid)
        temp = weather["temp_mean"] if weather else None
        precip = weather["precipitation_sum"] if weather else None

        # Fetch Digitraffic road condition
        road = _fetch_digitraffic_road(road_station) if road_station else None
        road_condition = road["road_condition"] if road else "unknown"
        severity = road["severity"] if road else 0.3  # neutral default

        result[city] = {
            "temp_celsius": temp,
            "precipitation_mm": precip,
            "road_condition": road_condition,
            "severity": severity,
        }

    return result


def winter_severity_index(cities: List[str] = None) -> float:
    """Calculate composite winter severity index across tracked cities.

    Combines:
    - Temperature (below 0°C increases severity)
    - Precipitation (rain/snow increases severity)
    - Road ice/snow (from Digitraffic severity)

    Args:
        cities: List of city names. Defaults to TRACKED_CITIES.

    Returns:
        Float 0.0–1.0:
        - 0.0 = mild conditions (>10°C, dry roads)
        - 0.5 = moderate winter (0–5°C, wet roads)
        - 1.0 = severe winter (<−15°C, icy roads, heavy precipitation)

        Returns 0.5 (neutral) on API failure.

    Example:
        >>> winter_severity_index(["Helsinki"])
        0.72  # cold + icy roads
    """
    conditions = fetch_weather_conditions(cities)

    if not conditions:
        logger.warning("No weather data available for winter severity calculation")
        return 0.5  # neutral default

    severity_scores = []

    for city, data in conditions.items():
        temp = data["temp_celsius"]
        precip = data["precipitation_mm"]
        road_severity = data["severity"]

        # Temperature component (0.0 at +10°C, 1.0 at −15°C)
        if temp is None:
            temp_score = 0.5
        elif temp >= 10:
            temp_score = 0.0
        elif temp <= -15:
            temp_score = 1.0
        else:
            # Linear interpolation between +10 and −15
            temp_score = (10 - temp) / 25.0

        # Precipitation component (0.0 at 0mm, 1.0 at 20mm+)
        if precip is None:
            precip_score = 0.0
        else:
            precip_score = min(precip / 20.0, 1.0)

        # Road condition component (directly from Digitraffic severity)
        road_score = road_severity

        # Composite: weighted average (temp most important for diesel heating)
        city_severity = 0.5 * temp_score + 0.2 * precip_score + 0.3 * road_score
        severity_scores.append(city_severity)

    # National average severity
    if not severity_scores:
        return 0.5

    return mean(severity_scores)


def forecast_demand_adjustment() -> float:
    """Calculate tomorrow's weather impact on fuel demand.

    Logic:
    - Harsh winter (severity > 0.7) → +1–2% demand (diesel heating, idling)
    - Moderate winter (severity 0.4–0.7) → 0–1% demand
    - Mild conditions (severity < 0.4) → −0.5% demand

    Returns:
        Float multiplier: 0.98–1.02
        - 1.0 = neutral (no weather impact)
        - 1.02 = +2% demand (severe winter)
        - 0.98 = −2% demand (mild conditions, reduced consumption)

        Returns 1.0 (neutral) on API failure.

    Example:
        >>> forecast_demand_adjustment()
        1.015  # +1.5% demand from cold weather
    """
    try:
        severity = winter_severity_index()

        # Map severity to demand multiplier
        if severity >= 0.7:
            # Severe winter: +1–2% demand
            adjustment = 1.0 + 0.01 + (severity - 0.7) / 0.3 * 0.01
        elif severity >= 0.4:
            # Moderate winter: 0–1% demand
            adjustment = 1.0 + (severity - 0.4) / 0.3 * 0.01
        else:
            # Mild conditions: −0.5% demand
            adjustment = 1.0 - (0.4 - severity) / 0.4 * 0.005

        # Clamp to reasonable bounds
        return max(0.98, min(1.02, adjustment))

    except Exception as e:
        logger.warning(f"Weather demand adjustment calculation failed: {e}")
        return 1.0  # neutral default


def get_weather_summary() -> str:
    """Human-readable weather summary for logging/debugging.

    Returns:
        String like: "Helsinki: −2°C icy (0.8), Tampere: 3°C wet (0.4) | severity: 0.62"
    """
    try:
        conditions = fetch_weather_conditions()
        if not conditions:
            return "Weather data unavailable"

        city_parts = []
        for city, data in conditions.items():
            temp = data["temp_celsius"]
            temp_str = f"{temp:.1f}°C" if temp is not None else "N/A"
            condition = data["road_condition"]
            severity = data["severity"]
            city_parts.append(f"{city}: {temp_str} {condition} ({severity:.2f})")

        overall_severity = winter_severity_index()
        city_summary = ", ".join(city_parts)

        return f"{city_summary} | severity: {overall_severity:.2f}"

    except Exception as e:
        return f"Weather summary failed: {e}"


if __name__ == "__main__":
    # Smoke test
    logging.basicConfig(level=logging.INFO)

    print("=== Weather Conditions ===")
    conditions = fetch_weather_conditions(["Helsinki", "Tampere"])
    for city, data in conditions.items():
        print(f"{city}: {data}")

    print("\n=== Winter Severity Index ===")
    severity = winter_severity_index()
    print(f"Severity: {severity:.3f}")

    print("\n=== Demand Adjustment ===")
    adjustment = forecast_demand_adjustment()
    print(f"Multiplier: {adjustment:.4f} ({(adjustment - 1) * 100:+.2f}%)")

    print("\n=== Summary ===")
    print(get_weather_summary())
