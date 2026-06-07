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
import asyncio
import json
import os
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
    ("https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_NOVOSTI", "YLE · Talous"),
    ("https://www.kauppalehti.fi/rss/uusimmat", "Kauppalehti"),
    ("https://www.talouselama.fi/api/feed/latest", "Talouselämä"),
    
    # Major English sources - oil/gas/energy/geopolitics
    ("https://feeds.reuters.com/reuters/businessNews", "Reuters · Business"),
    ("https://feeds.reuters.com/Reuters/worldNews", "Reuters · World"),
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
    ("https://www.bloomberg.com/feed/podcast/bloomberg-commodities-edge.xml", "Bloomberg · Commodities"),
    ("https://www.marketwatch.com/rss/energy", "MarketWatch · Energy"),
    ("https://www.wsj.com/xml/rss/3_7031.xml", "WSJ · Commodities"),
    
    # Energy-specific
    ("https://www.oilprice.com/rss/main", "OilPrice.com"),
    ("https://www.rigzone.com/news/feeds/oil_gas.rss", "Rigzone · Oil & Gas"),
    ("https://www.platts.com/RSS/RSSFeed", "S&P Global Platts"),
    ("https://www.worldoil.com/rss/recent/topics/all", "World Oil"),
]

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
    r"Neste\s+(Oil|Express|huoltoasem)|Teboil|ABC\s+asem|huoltoasem|tankkau|"
    r"pumppu\s*hin|liikennepolttoaine|"
    # English keywords - oil/gas/energy
    r"\boil\s+price|\bcrude\s+oil|\bpetroleum|\bbarrel|"
    r"\bgas\s+price|\bgasoline|\bfuel\s+price|\bdiesel\s+price|"
    r"\bOPEC\+?|\bSaudi\s+Arabia|Russia.*oil|Iran.*oil|Iraq.*oil|"
    r"Venezuela.*oil|Libya.*oil|Nigeria.*oil|"
    r"\benergy\s+crisis|\brefinery|\brefineries|\bpipeline|"
    r"Middle\s+East.*conflict|Ukraine.*war|sanctions.*oil|sanctions.*energy|"
    r"\bdrilling|\bfracking|\bshale\s+oil|"
    r"oil\s+supply|oil\s+demand|oil\s+production|oil\s+output|"
    r"energy\s+security|strategic\s+reserve|"
    r"\bIEA\b|International\s+Energy\s+Agency|"
    r"oil\s+embargo|oil\s+exports|LNG|natural\s+gas|"
    r"commodity.*oil|energy.*sector|fossil\s+fuel"
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


async def calculate_relevance_with_ai(items: list[dict], batch_size: int = 10) -> list[dict]:
    """Use AI to calculate fuel price impact relevance for each news item.
    
    Adds three fields to each item:
    - relevance_score (0-100): probability this will affect Finnish fuel prices
    - impact_direction ("up", "down", "neutral"): expected price movement
    - impact_magnitude ("low", "medium", "high"): expected size of impact
    
    Returns items with AI analysis populated. If AI unavailable, returns unchanged.
    """
    key = os.getenv("EMERGENT_LLM_KEY")
    if not key:
        return items
    
    try:
        from emergentintegrations import LlmChat, UserMessage
    except ImportError:
        return items
    
    system_message = (
        "Olet energiamarkkinoiden analyytikko, joka arvioi uutisten vaikutusta "
        "Suomen vähittäispolttoaineiden pumppuhintoihin (95E10 bensiini ja diesel). "
        "Arvioi JOKAINEN uutinen seuraavasti:\n\n"
        "1. RELEVANCE_SCORE (0-100): Kuinka todennäköisesti tämä uutinen vaikuttaa "
        "Suomen pumppuhintoihin seuraavan 1-7 päivän aikana?\n"
        "   - 80-100: Suora vaikutus (OPEC-päätökset, verot, Suomen huoltoasemat)\n"
        "   - 60-79: Vahva epäsuora (raakaöljyhinta, jalostamot, geopolitiikka)\n"
        "   - 40-59: Kohtalainen (energiamarkkinat yleisesti, valuutta)\n"
        "   - 20-39: Heikko (pitkän aikavälin trendit, spekulaatio)\n"
        "   - 0-19: Ei merkitystä (ei liity energiaan tai vain keskustelua)\n\n"
        "2. IMPACT_DIRECTION: Odotettu suunta\n"
        "   - 'up': hinta nousee (tarjonnan väheneminen, kysyntä kasvaa, vero nousee)\n"
        "   - 'down': hinta laskee (tarjonta kasvaa, kysyntä vähenee)\n"
        "   - 'neutral': ei selvää suuntaa tai vastakkaiset voimat\n\n"
        "3. IMPACT_MAGNITUDE: Odotettu vaikutuksen suuruus\n"
        "   - 'high': >5 senttiä/litra (veronkorotus, suuri tarjontahäiriö)\n"
        "   - 'medium': 2-5 senttiä/litra (OPEC-päätökset, geopoliittiset kriisit)\n"
        "   - 'low': <2 senttiä/litra (pienet markkinaliikkeet, trendit)\n\n"
        "Palauta VAIN JSON-array, yksi objekti per uutinen:\n"
        '[{"relevance_score": 85, "impact_direction": "up", "impact_magnitude": "medium", '
        '"reasoning": "OPEC leikkaa tuotantoa"}, ...]'
    )
    
    # Process in batches to avoid token limits
    analyzed_items = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        
        # Build prompt with numbered articles
        prompt_parts = ["Analysoi seuraavat uutiset:\n"]
        for idx, item in enumerate(batch, 1):
            age_str = f"{int(item['age_hours'])}h sitten" if item.get('age_hours') else "?"
            prompt_parts.append(
                f"{idx}. [{age_str}] {item['title']}\n"
                f"   Lähde: {item['source']}\n"
                f"   Kuvaus: {item['description'][:150]}\n"
            )
        prompt = "\n".join(prompt_parts)
        
        try:
            chat = LlmChat(
                api_key=key,
                session_id=f"news-relevance-{datetime.now(timezone.utc).isoformat()}",
                system_message=system_message,
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")  # Fast model for batch analysis
            
            msg = UserMessage(text=prompt)
            response = await chat.send_message(msg)
            
            # Parse JSON response
            raw = response.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
            first = raw.find("[")
            last = raw.rfind("]")
            if first != -1 and last > first:
                raw = raw[first:last + 1]
            
            analyses = json.loads(raw)
            
            # Merge analyses back into items
            for idx, analysis in enumerate(analyses):
                if idx < len(batch):
                    batch[idx]["relevance_score"] = analysis.get("relevance_score", 0)
                    batch[idx]["impact_direction"] = analysis.get("impact_direction", "neutral")
                    batch[idx]["impact_magnitude"] = analysis.get("impact_magnitude", "low")
                    batch[idx]["ai_reasoning"] = analysis.get("reasoning", "")
            
            analyzed_items.extend(batch)
            
        except Exception as e:
            # If AI fails, return items with no relevance scores
            for item in batch:
                item["relevance_score"] = None
                item["impact_direction"] = None
                item["impact_magnitude"] = None
            analyzed_items.extend(batch)
            continue
    
    return analyzed_items


def fetch_news_with_ai_relevance(
    queries=None, 
    max_age_days: int = 14, 
    limit: int = 20,
    min_relevance: int = 40,
    use_ai: bool = True
) -> list[dict]:
    """Fetch news and optionally calculate AI relevance scores.
    
    Args:
        queries: Deprecated, kept for compatibility
        max_age_days: Maximum age of news items
        limit: Maximum number of items to return AFTER filtering by relevance
        min_relevance: Minimum relevance score (0-100) to include
        use_ai: Whether to use AI for relevance scoring (requires EMERGENT_LLM_KEY)
    
    Returns:
        List of news items sorted by relevance_score (if AI used) or age_hours
    """
    # First fetch all matching news
    all_news = fetch_news(queries, max_age_days, limit=100)  # Get more initially
    
    if not use_ai or not os.getenv("EMERGENT_LLM_KEY"):
        # Return without AI analysis
        return all_news[:limit]
    
    # Calculate AI relevance asynchronously
    try:
        analyzed = asyncio.run(calculate_relevance_with_ai(all_news))
        
        # Filter by minimum relevance
        filtered = [
            item for item in analyzed 
            if item.get("relevance_score") is not None 
            and item["relevance_score"] >= min_relevance
        ]
        
        # Sort by relevance score (highest first), then by recency
        filtered.sort(
            key=lambda x: (
                -(x.get("relevance_score") or 0),  # Negative for descending
                x.get("age_hours") or 999
            )
        )
        
        return filtered[:limit]
        
    except Exception:
        # Fallback to non-AI version
        return all_news[:limit]
