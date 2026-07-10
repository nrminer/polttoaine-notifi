"""
Real-time Finnish fuel + oil news via direct publisher RSS feeds.

We pull from publishers directly (Iltalehti, Helsingin Sanomat, Ilta-Sanomat)
so links are canonical — no Google News opaque redirect tokens — and they
open the actual article when clicked.

We filter by fuel/oil keywords client-side.

ENHANCED: Now includes English-language oil/gas/war RSS feeds for global events
that can impact fuel prices (OPEC decisions, Middle East conflicts, sanctions, etc.)

ENHANCED v2: AI-powered relevance scoring to calculate fuel price impact probability.
"""
from __future__ import annotations
import re
import html
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from defusedxml.ElementTree import fromstring

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BensaVahti/2.0)"}
TIMEOUT = 12

# Lähde-feedit + kanavanimet näytettäväksi UI:ssa
FEEDS = [
    # Finnish sources - MAJOR broadcasters
    ("https://www.iltalehti.fi/rss/uutiset.xml", "Iltalehti"),
    ("https://www.iltalehti.fi/rss/talous.xml", "Iltalehti · Talous"),
    ("https://www.iltalehti.fi/rss/autot.xml", "Iltalehti · Autot"),
    ("https://www.iltalehti.fi/rss/kotimaa.xml", "Iltalehti · Kotimaa"),
    ("https://www.hs.fi/rss/tuoreimmat.xml", "Helsingin Sanomat"),
    ("https://www.hs.fi/rss/talous.xml", "HS · Talous"),
    ("https://www.is.fi/rss/tuoreimmat.xml", "Ilta-Sanomat"),
    ("https://www.is.fi/rss/taloussanomat.xml", "Taloussanomat"),
    ("https://www.is.fi/rss/autot.xml", "IS · Autot"),
    ("https://www.mtvuutiset.fi/api/feed/rss/uutiset_uusimmat", "MTV Uutiset"),
    ("https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_UUTISET", "YLE Uutiset"),
    # HUOM: YLE_NOVOSTI poistettu — se on YLEn venäjänkielinen palvelu,
    # ei talousfeed; venäjänkieliset otsikot eivät osu FI/EN-suodattimiin.
    ("https://www.kauppalehti.fi/rss/uusimmat", "Kauppalehti"),
    ("https://www.talouselama.fi/api/feed/latest", "Talouselämä"),

    # Major English sources - oil/gas/energy/geopolitics
    # HUOM: feeds.reuters.com poistettu — Reuters lopetti julkiset
    # RSS-syötteet 2020, domain ei enää edes resolvoidu.
    ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "NYT · World"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "NYT · Business"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "BBC · Business"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC · World"),
    ("https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "BBC · Middle East"),
    ("https://www.theguardian.com/world/rss", "The Guardian · World"),
    ("https://www.theguardian.com/business/rss", "The Guardian · Business"),
    
    # Financial/Energy specialized
    ("https://www.ft.com/rss/world", "Financial Times · World"),
    ("https://www.cnbc.com/id/100727362/device/rss/rss.html", "CNBC · Energy"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC · Commodities"),
    # HUOM: Bloombergin podcast-feed poistettu — jaksonimet eivät ole
    # uutisotsikoita; platts.com-RSS poistettu — domain on eläköitynyt
    # (S&P Global siirsi sisällön spglobal.comiin ilman julkista RSS:ää).
    ("https://www.marketwatch.com/rss/energy", "MarketWatch · Energy"),
    ("https://www.wsj.com/xml/rss/3_7031.xml", "WSJ · Commodities"),

    # Energy-specific
    ("https://oilprice.com/rss/main", "OilPrice.com"),
    ("https://www.rigzone.com/news/feeds/oil_gas.rss", "Rigzone · Oil & Gas"),
    ("https://www.worldoil.com/rss/recent/topics/all", "World Oil"),
]

# Per-feed health: päivitetään jokaisella fetch_news-ajolla. Kuolleet feedit
# näkyvät tästä (/api/news → feed_health) sen sijaan että ne katoaisivat
# hiljaa uutiskatteesta.
_FEED_HEALTH: dict[str, dict] = {}

# Breaking/important market news should stay available to the predictor and UI
# for a full day even when a busy RSS feed pushes it below the normal limit.
IMPORTANT_NEWS_HOLD_HOURS = 24.0
IMPORTANT_NEWS_MIN_SEVERITY = 4
_IMPORTANT_NEWS_CACHE: dict[str, dict] = {}
_IMPORTANT_NEWS_CACHE_LOCK = Lock()


def feed_health() -> dict:
    """Viimeisimmän haun per-feed-tila: {label: {ok, status, items, checked_at}}."""
    return dict(_FEED_HEALTH)

# Avainsanat: polttoaine, raakaöljy-hinta, vero, OPEC, Brent, asemaketjut
# (riittävän tiukka jotta ei matchaa esim. liikenneonnettomuus-uutisia)
KEYWORDS = re.compile(
    r"("
    # Finnish keywords - fuel/oil
    r"polttoaine|"
    r"bensiini|bensii?nin|95E10|98E5|"
    r"\bdiesel|dieselin|dieselöljy|"
    r"raakaöljy|öljyn\s+hin|öljymarkkin|öljyn?\s+tuotant|"
    r"polttoaineverot|valmistevero|polttoainevero|"
    r"\bOPEC|\bBrent\b|\bWTI\b|"
    r"pumppu\s*hin|liikennepolttoaine|"
    # English keywords - oil/gas/energy
    r"\boil\s+price|\bcrude\s+oil|\bpetroleum|\bbarrel|"
    r"\bgas\s+price|\bgasoline|\bfuel\s+price|\bdiesel\s+price|"
    r"\bOPEC\+?|\bSaudi\s+Arabia|Russia.*oil|Iran.*oil|Iraq.*oil|"
    r"Venezuela.*oil|Libya.*oil|Nigeria.*oil|"
    r"\benergy\s+crisis|\brefinery|\brefineries|\bpipeline|"
    r"Middle\s+East.*conflict|Ukraine.*war|sanctions.*oil|sanctions.*energy|"
    r"\bshale\s+oil|"
    r"oil\s+supply|oil\s+demand|oil\s+production|oil\s+output|"
    r"strategic\s+reserve|"
    r"\bIEA\b|International\s+Energy\s+Agency|"
    r"oil\s+embargo|oil\s+exports|"
    r"commodity.*oil|shale\s+oil"
    r")",
    re.IGNORECASE,
)

# Breaking news patterns - events that can cause significant price spikes
# Calibrated to avoid over-reaction: only MAJOR supply/geopolitical events
# that have historically moved oil markets by >5%
BREAKING_NEWS_PATTERNS = re.compile(
    r"("
    # Supply disruptions (MAJOR only - actual cuts/shutdowns)
    r"OPEC.*cut.*million|OPEC.*emergency.*meeting|OPEC.*production.*cut|"
    r"OPEC\+.*agrees.*cut|OPEC.*reduces.*output|"
    r"refinery.*explosion|refinery.*fire.*shutdown|refinery.*closed|"
    r"pipeline.*attack|pipeline.*sabotage|pipeline.*shut|pipeline.*damaged|"
    r"supply.*disruption|production.*halt|output.*cut|drilling.*suspended|"
    r"oil.*facility.*shut|platform.*evacuated|"
    # Geopolitical escalations (WAR/ATTACK only, not threats)
    r"\bwar\s+declared|\bwar\s+breaks|military.*strike.*oil|invasion.*oil|"
    r"attack.*oil.*facility|attack.*tanker|attack.*refinery|missile.*strike.*refinery|"
    r"Iran.*attack.*Israel|Israel.*strike.*Iran|Iran.*strike|"
    r"Russia.*halt.*export|Russia.*cuts.*supply|embargo.*imposed|blockade.*oil|"
    r"conflict.*escalate|military.*intervention|troops.*deployed.*oil|"
    # Major market-moving announcements (DECISIONS not discussions)
    r"sanctions.*approved|sanctions.*imposed.*oil|emergency.*reserve.*release|"
    r"strategic.*reserve.*tap|IEA.*release|"
    r"price.*surge.*percent|oil.*spike|crude.*jump|crude.*soar|"
    r"barrel.*above.*\$\d+|oil.*hit.*high|"
    r"shortage.*declared|rationing.*begins|fuel.*shortage|supply.*crisis|"
    # Finnish specific (TAX INCREASE CONFIRMED)
    r"valmistevero.*korotus.*hyväksytty|bensiinivero.*nousee|polttoainevero.*vahvistettu|"
    r"hallitus.*hyväksyi.*polttoainevero|eduskunta.*hyväksyi.*vero"
    r")",
    re.IGNORECASE,
)

# Filter out non-material news (discussions, proposals, threats that don't materialize)
IGNORE_PATTERNS = re.compile(
    r"("
    r"could|might|may|plan.*to|consider|discuss|proposal|threat|warning|"
    r"analyst.*predict|forecast|expect|possible|potential|risk.*of"
    r")",
    re.IGNORECASE,
)

PRICE_SIGNAL_KEYWORDS = re.compile(
    r"("
    r"hinta|halpa|kallis|vero|valmistevero|"
    r"polttoaine|bensiini|\bdiesel|raaka|Ã¶ljy|OPEC|Brent|WTI|"
    r"oil|crude|barrel|fuel price|gas price|gasoline|petroleum|"
    r"refinery|pipeline|supply|production|output|exports|sanctions|shale oil"
    r")",
    re.IGNORECASE,
)

LOCAL_STATION_NON_MARKET_PATTERNS = re.compile(
    r"("
    r"katto\s+(sortui|romaht)|romahtanut|rakennustarkastaja|"
    r"ovet\s+(kiinni|aukea)|autioitui|omistaja\s+kuoli|"
    r"huoltoasema.*(katto|romaht|aukea|kiinni|autioitui)"
    r")",
    re.IGNORECASE,
)


def _title_is_price_relevant(title: str) -> bool:
    """Return True when a title is plausibly useful for fuel-price context."""
    if not KEYWORDS.search(title):
        return False
    if LOCAL_STATION_NON_MARKET_PATTERNS.search(title) and not PRICE_SIGNAL_KEYWORDS.search(title):
        return False
    return True


def _calculate_severity(title: str, desc: str) -> int:
    """Calculate severity score (0-10) for breaking news.
    
    Used to calibrate the price clamp multiplier:
    - 7-10: Critical (±0.15 EUR/L)
    - 4-6: Major (±0.10 EUR/L)
    - 1-3: Moderate (±0.08 EUR/L)
    """
    score = 0
    text = f"{title} {desc}".lower()
    
    # Critical events (+3 each)
    if any(word in text for word in ["war declared", "invasion", "explosion", "attack on", "missile strike"]):
        score += 3
    if any(word in text for word in ["million barrel", "production cut", "emergency meeting", "output cut"]):
        score += 3
    if any(word in text for word in ["refinery closed", "pipeline shut", "supply crisis"]):
        score += 3
    
    # Major events (+2 each)
    if any(word in text for word in ["strike", "shutdown", "halt", "closed", "suspended"]):
        score += 2
    if any(word in text for word in ["sanctions approved", "sanctions imposed", "embargo", "blockade"]):
        score += 2
    if any(word in text for word in ["escalate", "intervention", "troops deployed"]):
        score += 2
    
    # Material indicators (+1 each)
    if any(word in text for word in ["surge", "spike", "jump", "soar"]):
        score += 1
    if any(word in text for word in ["shortage", "disruption", "rationing"]):
        score += 1
    if any(word in text for word in ["$100", "$110", "$120", "$130"]):  # High oil prices
        score += 1
    
    # Recency boost (fresher = more severe)
    # This is set during item creation
    
    return min(score, 10)


def _parse_iso_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_hours(item: dict) -> float | None:
    age = item.get("age_hours")
    try:
        if age is not None:
            return float(age)
    except (TypeError, ValueError):
        pass
    published = _parse_iso_dt(item.get("published"))
    if not published:
        return None
    return (datetime.now(timezone.utc) - published).total_seconds() / 3600.0


def _news_key(item: dict) -> str:
    raw = item.get("link") or item.get("title") or ""
    return re.sub(r"\s+", " ", str(raw)).strip().lower()[:220]


def is_important_news_item(
    item: dict,
    max_age_hours: float = IMPORTANT_NEWS_HOLD_HOURS,
    min_severity: int = IMPORTANT_NEWS_MIN_SEVERITY,
) -> bool:
    """Breaking or high-severity items remain pinned for the hold window."""
    age = _age_hours(item)
    if age is None or age > max_age_hours:
        return False
    severity = int(item.get("severity") or 0)
    return bool(item.get("breaking")) or severity >= min_severity


def _with_current_age(item: dict) -> dict:
    out = dict(item)
    age = _age_hours(out)
    if age is not None:
        out["age_hours"] = age
    return out


def _public_news_item(item: dict) -> dict:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _purge_important_cache_locked(now: datetime) -> None:
    expired_keys = []
    for key, item in _IMPORTANT_NEWS_CACHE.items():
        until = _parse_iso_dt(item.get("important_until"))
        if until is None:
            seen_at = _parse_iso_dt(item.get("_important_cached_at")) or now
            until = seen_at + timedelta(hours=IMPORTANT_NEWS_HOLD_HOURS)
        if until <= now:
            expired_keys.append(key)
    for key in expired_keys:
        _IMPORTANT_NEWS_CACHE.pop(key, None)


def _refresh_important_news_cache(items: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    with _IMPORTANT_NEWS_CACHE_LOCK:
        _purge_important_cache_locked(now)
        for item in items:
            current = _with_current_age(item)
            if not is_important_news_item(current):
                continue
            key = _news_key(current)
            if not key:
                continue
            published = _parse_iso_dt(current.get("published"))
            important_until = (published or now) + timedelta(hours=IMPORTANT_NEWS_HOLD_HOURS)
            if important_until <= now:
                continue
            cached = dict(current)
            cached["pinned_important"] = True
            cached["important_until"] = important_until.isoformat()
            cached["_important_cached_at"] = now.isoformat()
            _IMPORTANT_NEWS_CACHE[key] = cached


def _cached_important_news_items() -> list[dict]:
    now = datetime.now(timezone.utc)
    with _IMPORTANT_NEWS_CACHE_LOCK:
        _purge_important_cache_locked(now)
        return [_public_news_item(_with_current_age(item)) for item in _IMPORTANT_NEWS_CACHE.values()]


def _prioritized_news_with_retention(items: list[dict], limit: int) -> list[dict]:
    _refresh_important_news_cache(items)
    combined = []
    seen = set()
    for item in [*items, *_cached_important_news_items()]:
        current = _public_news_item(_with_current_age(item))
        key = _news_key(current)
        if not key or key in seen:
            continue
        seen.add(key)
        combined.append(current)

    def sort_key(item: dict):
        age = _age_hours(item)
        safe_age = age if age is not None else 999999.0
        important = is_important_news_item(item)
        return (
            0 if important else 1,
            -int(item.get("severity") or 0),
            safe_age,
            str(item.get("title") or ""),
        )

    combined.sort(key=sort_key)
    return combined[:max(0, int(limit or 0))]


def _sanitize_text(text: str) -> str:
    """Remove control characters and escape HTML to prevent prompt injection."""
    # Remove control characters, keep only printable
    text = "".join(c for c in text if c.isprintable() or c.isspace())
    # Escape HTML entities
    text = html.escape(text)
    # Limit length
    return text[:200]


def _parse_rss(xml_text: str, source_label: str) -> list[dict]:
    out = []
    try:
        root = fromstring(xml_text)
    except Exception:
        return out
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        pub_raw = (it.findtext("pubDate") or "").strip()

        # Sanitize title to prevent prompt injection
        title = _sanitize_text(title)

        try:
            pub_dt = parsedate_to_datetime(pub_raw).astimezone(timezone.utc)
        except Exception:
            pub_dt = None
        
        # Check if this is breaking news
        # First: must match BREAKING pattern
        # Second: must NOT match IGNORE pattern (filters speculation/proposals)
        title_desc = f"{title} {desc}"
        is_breaking = (
            bool(BREAKING_NEWS_PATTERNS.search(title_desc)) and
            not bool(IGNORE_PATTERNS.search(title_desc))
        )
        
        # Calculate severity score for breaking news
        severity = _calculate_severity(title, desc) if is_breaking else 0
        
        # Recency boost: <1h = +2, <3h = +1
        if is_breaking and pub_dt:
            age_h = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600.0
            if age_h < 1:
                severity = min(severity + 2, 10)
            elif age_h < 3:
                severity = min(severity + 1, 10)
        
        out.append({
            "title": title,
            "description": re.sub(r"<[^>]+>", "", desc)[:240],
            "link": link,
            "source": source_label,
            "published": pub_dt.isoformat() if pub_dt else None,
            "age_hours": (
                (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600.0
                if pub_dt else None
            ),
            "breaking": is_breaking,
            "severity": severity,
            "relevance_score": None,  # Will be populated by AI if enabled
            "impact_direction": None,  # "up", "down", "neutral"
            "impact_magnitude": None,  # "low", "medium", "high"
        })
    return out


def fetch_news(queries=None, max_age_days: int = 14, limit: int = 15) -> list[dict]:
    """queries argumentti säilytetään allekirjoituksen yhteensopivuuden vuoksi
    mutta filtteröinti tehdään aina KEYWORDS-patternilla.
    
    Returns list of news items with 'breaking' field indicating breaking news.
    """
    def _fetch_one(url: str, label: str) -> list[dict]:
        """Fetch and parse a single RSS feed.
        
        SECURITY: Validates URL to prevent SSRF attacks.
        """
        from urllib.parse import urlparse
        
        # SECURITY: Validate URL scheme and prevent internal network access
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                logger.error("Invalid URL scheme for feed %s: %s", label, parsed.scheme)
                return []
            if parsed.hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                logger.error("Blocked internal network access: %s", url)
                return []
        except Exception as e:
            logger.error("URL validation failed for %s: %s", label, e)
            return []
        
        checked = datetime.now(timezone.utc).isoformat()
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code != 200:
                _FEED_HEALTH[label] = {"ok": False, "status": r.status_code,
                                       "items": 0, "checked_at": checked}
                return []
            items = _parse_rss(r.text, label)
            _FEED_HEALTH[label] = {"ok": True, "status": 200,
                                   "items": len(items), "checked_at": checked}
            return items
        except Exception as e:
            _FEED_HEALTH[label] = {"ok": False, "status": type(e).__name__,
                                   "items": 0, "checked_at": checked}
            return []

    # Rinnakkainen haku: ~25 feedin sarjallinen läpikäynti 12 s timeoutilla
    # kestäisi pahimmillaan minuutteja; rinnakkain koko kierros on ≤ TIMEOUT.
    all_items: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for items in pool.map(lambda f: _fetch_one(*f), FEEDS):
            all_items.extend(items)

    cutoff_h = max_age_days * 24
    seen = set()
    matched = []
    for it in all_items:
        if it.get("age_hours") is None or it["age_hours"] > cutoff_h:
            continue
        # match VAIN otsikkoa vasten — kuvaukset usein matchaavat aiheeseen
        # vain väljästi (esim. "huoltoaseman lähellä kolari")
        if not _title_is_price_relevant(it["title"]):
            continue
        key = it["title"][:80].lower()
        if key in seen:
            continue
        seen.add(key)
        matched.append(it)

    return _prioritized_news_with_retention(matched, limit)


def has_breaking_news(items: list[dict], max_age_hours: float = 6.0, min_severity: int = 4) -> bool:
    """Check if there are any breaking news items within the last N hours with sufficient severity.
    
    Used by tracker to determine if predictor should run with relaxed limits.
    min_severity: 4-6 = Major, 7-10 = Critical (default: 4 = Major+)
    """
    if not items:
        return False
    for item in items:
        if (item.get("breaking") and 
            (item.get("age_hours") or 999) <= max_age_hours and
            (item.get("severity", 0) >= min_severity)):
            return True
    return False


def get_breaking_news_items(items: list[dict], max_age_hours: float = 6.0) -> list[dict]:
    """Return only breaking news items within the last N hours."""
    return [
        item for item in items
        if item.get("breaking") and (item.get("age_hours") or 999) <= max_age_hours
    ]


def get_max_severity(items: list[dict], max_age_hours: float = 6.0) -> int:
    """Get the maximum severity score from recent breaking news.
    
    Returns 0 if no breaking news, 1-10 otherwise.
    Used to calibrate the price clamp multiplier.
    """
    breaking = get_breaking_news_items(items, max_age_hours)
    if not breaking:
        return 0
    return max(item.get("severity", 0) for item in breaking)
