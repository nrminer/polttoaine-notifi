"""
Real-time Finnish fuel + global oil news via Google News RSS.

No API key needed. Returns recent headlines with publish date and source.
Used both for displaying in the UI and as context for the AI prediction.
"""
from __future__ import annotations
import re
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BensaVahti/2.0)"}
TIMEOUT = 12


def _parse_rss(xml_text: str) -> list[dict]:
    out = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for it in root.findall(".//item"):
        title = it.findtext("title") or ""
        link = it.findtext("link") or ""
        pub_raw = it.findtext("pubDate") or ""
        source_el = it.find("source")
        source = source_el.text if source_el is not None and source_el.text else ""
        try:
            pub_dt = parsedate_to_datetime(pub_raw).astimezone(timezone.utc)
        except Exception:
            pub_dt = None
        # remove " - SourceName" tail that Google adds
        clean_title = re.sub(r"\s*[-—]\s*[^-—]+$", "", title).strip() if " - " in title else title
        out.append({
            "title": clean_title or title,
            "raw_title": title,
            "source": source,
            "link": link,
            "published": pub_dt.isoformat() if pub_dt else None,
            "age_hours": (
                (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600.0
                if pub_dt else None
            ),
        })
    return out


def fetch_news(queries: list[str] | None = None, max_age_days: int = 14,
               limit: int = 8) -> list[dict]:
    if not queries:
        queries = [
            "polttoaine hinta suomi",
            "bensiini diesel hinta",
            "brent öljy OPEC",
        ]
    all_items: list[dict] = []
    for q in queries:
        is_fi = any(w in q for w in ("polttoaine", "bensiini", "diesel"))
        url = (
            f"https://news.google.com/rss/search?q={q.replace(' ', '+')}"
            f"&hl={'fi' if is_fi else 'en-US'}"
            f"&gl={'FI' if is_fi else 'US'}"
            f"&ceid={'FI:fi' if is_fi else 'US:en'}"
        )
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            items = _parse_rss(r.text)
            for it in items:
                it["query"] = q
            all_items.extend(items)
        except Exception:
            continue

    # filter by age + dedupe by title
    cutoff_h = max_age_days * 24
    seen = set()
    filtered = []
    for it in all_items:
        if it.get("age_hours") is None:
            continue
        if it["age_hours"] > cutoff_h:
            continue
        key = it["title"][:80].lower()
        if key in seen:
            continue
        seen.add(key)
        filtered.append(it)

    # sort newest first
    filtered.sort(key=lambda x: x["age_hours"])
    return filtered[:limit]
