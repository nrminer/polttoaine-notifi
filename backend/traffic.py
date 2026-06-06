"""
Fintraffic Digitraffic -liikennemäärädata polttoaineen kysynnän proxyyn.

Digitraffic on Fintrafficin (ent. Väylävirasto) ylläpitämä avoimen
liikenteen datajärjestelmä. Käytämme tieliikenteen LAM-pisteiden
(Liikenteen Automaattinen Mittaus) ajomääräaggregaatteja kansallisen
liikenneindeksin laskemiseen.

API: https://tie.digitraffic.fi/api/tms/v1/
Dokumentaatio: https://www.digitraffic.fi/tieliikenne/

Liikenneindeksi on kysyntäsignaali:
- Korkeampi liikenne → korkeampi polttoaineen kysyntä → nousupaineita hintaan
- traffic_demand_proxy() palauttaa suhdeluvun: nykyviikon ka / 4 viikon ka

Jos verkko ei ole käytettävissä tai API rajaa, palautetaan None.
Status: experimental helper. This module is not currently wired into
run_prediction() or predict_tomorrow(), so API responses and UI labels must not
claim traffic-adjusted predictions until that integration exists.
"""
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (BensaVahti/2.0)"}
TIMEOUT = 15
BASE_URL = "https://tie.digitraffic.fi/api/tms/v1"

# Cache: 6 tuntia (liikennedata päivittyy hitaasti, aggregaatit laskettava)
_cache = {"data": None, "expires": None}
CACHE_SECONDS = 6 * 3600


def _is_cache_valid() -> bool:
    """Tarkista onko välimuisti vielä voimassa."""
    if _cache["expires"] is None:
        return False
    return datetime.now(timezone.utc) < _cache["expires"]


def fetch_traffic_index(days: int = 7) -> List[Tuple[str, float]] | None:
    """Hae normalisoitu kansallinen liikenneindeksi viimeiseltä N päivältä.

    Palauttaa listan (date_str, normalized_index) -tupleja, missä
    normalized_index on 0.0–1.0 välillä (1.0 = huippuliikenne jakson aikana).

    Aggregoidaan LAM-pisteiden ajomäärät päivittäin ja normalisoidaan.

    Args:
        days: Haettavien päivien määrä (oletus 7)

    Returns:
        Lista (date_iso, float) tupleja tai None jos API pettää.
    """
    # Tarkista cache
    if _is_cache_valid() and _cache["data"] is not None:
        cached = _cache["data"]
        # Palauta haluttu määrä päiviä cachesta
        return cached[-days:] if len(cached) >= days else cached

    try:
        # Hae LAM-asemien data viimeiseltä 30 päivältä (max varmuusmarginaali)
        # Digitraffic TMS (Traffic Measurement System) data endpoint
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=max(30, days))

        # Hae LAM-pisteiden lista ensin
        stations_url = f"{BASE_URL}/stations"
        stations_resp = requests.get(stations_url, headers=HEADERS, timeout=TIMEOUT)
        stations_resp.raise_for_status()
        stations_data = stations_resp.json()

        # Kerää liikennemääriä kaikilta aktiivisilta LAM-pisteiltä
        # Käytämme data-endpointtia, joka palauttaa mittausdataa
        daily_totals = {}  # date_str -> total_volume

        # Digitraffic API: hae sensorien mittaukset
        # Käytämme historiadata-endpointtia aggregaatteihin
        data_url = f"{BASE_URL}/history"
        params = {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
        }

        # Vaihtoehtoinen lähestymistapa: käytä nykyistä dataa + yksinkertainen aggregointi
        # Koska historiadatan hakeminen voi olla monimutkaista, käytämme
        # sensordata-endpointtia ja aggregoimme itse

        # Yksinkertaistettu toteutus: hae viimeisimmät mittaukset ja tee päiväaggregaatit
        # Tämä on placeholder-toteutus; tuotannossa tarvitaan tarkempi aggregointi
        data_url = f"{BASE_URL}/data"
        data_resp = requests.get(data_url, headers=HEADERS, timeout=TIMEOUT)
        data_resp.raise_for_status()
        data_json = data_resp.json()

        # Käsittele TMS-stationien data
        # Digitraffic API palauttaa stations-arrayn, jossa kullakin on sensors
        stations = data_json.get("stations", [])

        for station in stations:
            # Tarkista onko asema aktiivinen ja sisältääkö liikennemäärädataa
            sensor_values = station.get("sensorValues", [])
            measured_time = station.get("measuredTime")

            if not measured_time:
                continue

            # Parseta päivämäärä
            try:
                dt = datetime.fromisoformat(measured_time.replace("Z", "+00:00"))
                date_key = dt.date().isoformat()
            except Exception:
                continue

            # Etsi liikennemäärä (traffic volume) sensoreista
            # Sensorityyppi: OHITUS (passing vehicles) on yleisin
            for sensor in sensor_values:
                sensor_id = sensor.get("id", 0)
                sensor_value = sensor.get("value")

                # LAM-pisteiden sensorit: 5122 = OHITUS_5MIN (5 min liikenne)
                # Yksinkertaistetaan: kerää kaikki numeeriset arvot
                if sensor_value is not None and isinstance(sensor_value, (int, float)):
                    if date_key not in daily_totals:
                        daily_totals[date_key] = 0
                    daily_totals[date_key] += float(sensor_value)

        # Jos ei dataa, palauta None
        if not daily_totals:
            logger.warning("Digitraffic: ei liikennemääräaggregaatteja")
            return None

        # Normalisoi 0–1 välille (1.0 = maksimi)
        dates_sorted = sorted(daily_totals.keys())
        volumes = [daily_totals[d] for d in dates_sorted]

        if not volumes:
            return None

        max_vol = max(volumes)
        if max_vol == 0:
            return None

        normalized = [(d, daily_totals[d] / max_vol) for d in dates_sorted]

        # Tallenna cacheen
        _cache["data"] = normalized
        _cache["expires"] = datetime.now(timezone.utc) + timedelta(seconds=CACHE_SECONDS)

        # Palauta haluttu määrä päiviä
        return normalized[-days:] if len(normalized) >= days else normalized

    except requests.exceptions.Timeout:
        logger.warning("Digitraffic API timeout (15s)")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Digitraffic API request failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Digitraffic data processing error: {e}")
        return None


def traffic_demand_proxy() -> float | None:
    """Laske kysyntäsignaali liikenteestä: nykyviikon ka / 4 viikon ka.

    Korkeampi arvo (> 1.0) → tavallista vilkkaampi liikenne → kysyntäpaine.
    Matalampi arvo (< 1.0) → hiljainen viikko → kysyntä heikkoa.

    Returns:
        Suhdeluku (float) tai None jos dataa ei saatavilla.
    """
    data = fetch_traffic_index(days=28)  # 4 viikkoa
    if not data or len(data) < 7:
        return None

    # Jaa viimeiseen 7 päivään ja edelliseen 21 päivään
    recent_week = data[-7:]
    prev_weeks = data[-28:-7] if len(data) >= 28 else data[:-7]

    if not recent_week or not prev_weeks:
        return None

    recent_avg = sum(v for _, v in recent_week) / len(recent_week)
    baseline_avg = sum(v for _, v in prev_weeks) / len(prev_weeks)

    if baseline_avg == 0:
        return None

    return recent_avg / baseline_avg


def latest_traffic_index() -> float | None:
    """Hae viimeisin liikenneindeksi (0.0–1.0).

    Returns:
        Viimeisin normalisoitu indeksi tai None.
    """
    data = fetch_traffic_index(days=7)
    if not data:
        return None
    return data[-1][1]
