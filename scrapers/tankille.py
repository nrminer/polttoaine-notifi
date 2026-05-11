"""
Stub scraper for tankille.fi.

Tankille is primarily a mobile app — the website doesn't expose prices in a
scrapable HTML format. The mobile app talks to an internal API at
api.tankille.fi which has been reverse-engineered by hobbyists but:

  1. It's not officially documented and could change without notice.
  2. The endpoints require a session token obtained via an auth flow.
  3. Hitting it from a script is a grey area — fine for personal use,
     but be respectful (cache, low frequency, identify yourself).

If you want to add this later, search GitHub for "tankille api" — there
are a few community Python/Node clients you can crib from. For now this
returns an empty list and the runner will just skip it.
"""

def fetch_prices() -> list[dict]:
    return []
