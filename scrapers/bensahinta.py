"""
Stub scraper for bensahinta.fi.

bensahinta.fi returns HTTP 403 to plain requests — they actively block
non-browser user agents and likely use Cloudflare or similar. Bypassing
that for personal use is possible (cloudscraper, Playwright with a real
browser context), but it's fragile and gets you into "I'm working around
their anti-bot measures" territory.

If you want this data, the practical options are:

  1. Use Playwright to actually render the page in a headless browser.
     Heavier dependency, slower, but it works.
  2. Skip it — polttoaine.net already covers most of the same stations
     since both sites are crowdsourced and the same users submit to both.

Returning empty for now.
"""

def fetch_prices() -> list[dict]:
    return []
