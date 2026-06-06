"""
Real-time Finnish fuel + oil news via direct publisher RSS feeds.

We pull from publishers directly (Iltalehti, Helsingin Sanomat, Ilta-Sanomat)
so links are canonical — no Google News opaque redirect tokens — and they
open the actual article when clicked.

We filter by fuel/oil keywords client-side.

ENHANCED: Now includes English-language oil/gas/war RSS feeds for global events
that can impact fuel prices (OPEC decisions, Middle East conflicts, sanctions, etc.)
"""
from __future__ import annotations
import re
import html
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from defusedxml.ElementTree import fromstring

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BensaVahti/2.0)"}
TIMEOUT = 12

# Lähde-feedit + kanavanimet näytettäväksi UI:ssa
FEEDS = [
    # Finnish sources
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
    # English sources - oil/gas/energy
    ("https://feeds.reuters.com/reuters/businessNews", "Reuters · Business"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "BBC · Business"),
    ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera"),
    ("https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "NYT · World"),
]

# Avainsanat: polttoaine, raakaöljy-hinta, vero, OPEC, Brent, asemaketjut
# (riittävän tiukka jotta ei matchaa esim. liikenneonnettomuus-uutisia)
KEYWORDS = re.compile(
    r"("
    r"polttoaine|"
    r"bensiini|bensii?nin|95E10|"
    r"\bdiesel|dieselin|dieselöljy|"
    r"raakaöljy|öljyn\s+hin|öljymarkkin|"
    r"polttoaineverot|valmistevero|"
    r"\bOPEC|\bBrent\b|"
    r"Neste\s+(Oil|Express|huoltoasem)|Teboil|huoltoasem|tankkau|"
    # English keywords
    r"\boil\s+price|\bcrude\s+oil|\bpetroleum|"
    r"\bgas\s+price|\bgasoline|\bfuel\s+price|"
    r"\bOPEC\+|Saudi\s+Arabia|Russia.*oil|Iran.*oil|"
    r"\benergy\s+crisis|\brefinery|\bpipeline|"
    r"Middle\s+East.*conflict|Ukraine.*war|sanctions.*oil"
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
    r"refinery.*explosion|refinery.*fire.*shutdown|refinery.*closed|"
    r"pipeline.*attack|pipeline.*sabotage|pipeline.*shut|"
    r"supply.*disruption|production.*halt|"
    # Geopolitical escalations (WAR/ATTACK only, not threats)
    r"\bwar\s+declared|\bwar\s+breaks|military.*strike.*oil|invasion.*oil|"
    r"attack.*oil.*facility|attack.*tanker|missile.*strike.*refinery|"
    r"Iran.*attack.*Israel|Israel.*strike.*Iran|"
    r"Russia.*halt.*export|embargo.*imposed|blockade.*oil|"
    # Major market-moving announcements (DECISIONS not discussions)
    r"sanctions.*approved|emergency.*reserve.*release|"
    r"price.*surge.*percent|oil.*spike|crude.*jump|"
    r"shortage.*declared|rationing.*begins|"
    # Finnish specific (TAX INCREASE CONFIRMED)
    r"valmistevero.*korotus.*hyväksytty|bensiinivero.*nousee|polttoainevero.*vahvistettu"
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
    if any(word in text for word in ["war declared", "invasion", "explosion", "attack on"]):
        score += 3
    if any(word in text for word in ["million barrel", "production cut", "emergency meeting"]):
        score += 3
    
    # Major events (+2 each)
    if any(word in text for word in ["strike", "shutdown", "halt", "closed"]):
        score += 2
    if any(word in text for word in ["sanctions approved", "embargo", "blockade"]):
        score += 2
    
    # Material indicators (+1 each)
    if any(word in text for word in ["surge", "spike", "jump"]):
        score += 1
    if any(word in text for word in ["shortage", "disruption"]):
        score += 1
    
    # Recency boost (fresher = more severe)
    # This is set during item creation
    
    return min(score, 10)


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
        })
    return out


def fetch_news(queries=None, max_age_days: int = 14, limit: int = 8) -> list[dict]:
    """queries argumentti säilytetään allekirjoituksen yhteensopivuuden vuoksi
    mutta filtteröinti tehdään aina KEYWORDS-patternilla.
    
    Returns list of news items with 'breaking' field indicating breaking news.
    """
    all_items: list[dict] = []
    for url, label in FEEDS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            all_items.extend(_parse_rss(r.text, label))
        except Exception:
            continue

    cutoff_h = max_age_days * 24
    seen = set()
    matched = []
    for it in all_items:
        if it.get("age_hours") is None or it["age_hours"] > cutoff_h:
            continue
        # match VAIN otsikkoa vasten — kuvaukset usein matchaavat aiheeseen
        # vain väljästi (esim. "huoltoaseman lähellä kolari")
        if not KEYWORDS.search(it["title"]):
            continue
        key = it["title"][:80].lower()
        if key in seen:
            continue
        seen.add(key)
        matched.append(it)

    matched.sort(key=lambda x: x["age_hours"])
    return matched[:limit]


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
