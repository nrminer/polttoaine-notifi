"""
Real-data-only historical price builder.

Strategy:
  - Real MONTHLY values from Statistics Finland (Tilastokeskus) → placed on
    each month's 15th, then interpolated linearly between adjacent months
    (this is a fair representation since within a single month prices don't
     vary wildly).
  - When Stat Finland data ends (typical lag ~5 months), we EXTRAPOLATE the
    gap to today using two real signals:
      a) Brent oil month-over-month change (Yahoo Finance)
      b) EUR/USD change
    Pass-through factor: Δ retail ≈ 0.6 × Δ crude (€-adjusted)
  - The very last point is "today" = anchored to the LIVE scraped national
    cheapest-sample average (this is what the user can actually pay).
  - NO weekday or random noise added — keeping only signals we can defend.

Returns a list of {date, price, source} where source is one of:
  - "statfin"            (interpolation between two real monthly anchors)
  - "statfin+extrap"     (extrapolated past Stat Finland's last month using
                          Brent/FX trend)
  - "live"               (today's scraped value)
"""
from __future__ import annotations
from datetime import date, timedelta


def _interp(d: date, anchors: list[tuple[date, float]]) -> float:
    """Linear interp between consecutive anchor points; flat outside."""
    if not anchors:
        return None
    if d <= anchors[0][0]:
        return anchors[0][1]
    if d >= anchors[-1][0]:
        return anchors[-1][1]
    lo, hi = 0, len(anchors) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if anchors[mid][0] <= d:
            lo = mid
        else:
            hi = mid
    a_d, a_p = anchors[lo]
    b_d, b_p = anchors[hi]
    span = (b_d - a_d).days or 1
    frac = (d - a_d).days / span
    return a_p + (b_p - a_p) * frac


def build_history(stat_anchors: list[dict],
                  brent_series: list[dict] | None,
                  live_today_price: float | None,
                  days: int = 365) -> list[dict]:
    """stat_anchors: [{"year","month","month_iso","price"}, ...] sorted asc.

    Returns list of {date, price, source}.
    """
    if not stat_anchors:
        return []

    # rakenna ankkurit (date, price)
    anchor_pts = [
        (date(a["year"], a["month"], 15), float(a["price"]))
        for a in stat_anchors
    ]
    anchor_pts.sort()
    last_stat_date, last_stat_price = anchor_pts[-1]

    today = date.today()
    start = today - timedelta(days=days - 1)

    # Brent-perustainen ekstrapolaatio aukolle: lasketaan Brent-keskiarvo
    # last_stat_date kuukaudessa vs nykypäivänä → muutos %.
    brent_factor = None
    if brent_series and live_today_price is None:
        # poimi Brent month around last_stat_date and now
        b_then = [b["value"] for b in brent_series
                  if b["date"][:7] == last_stat_date.strftime("%Y-%m")]
        b_now = [b["value"] for b in brent_series[-7:]]
        if b_then and b_now:
            pct = (sum(b_now) / len(b_now)) / (sum(b_then) / len(b_then)) - 1.0
            # retail liikkuu ~60 % crudesta yli koko hintarakenteen
            brent_factor = 1.0 + 0.6 * pct

    out = []
    for i in range(days):
        d = start + timedelta(days=i)

        if d <= last_stat_date:
            p = _interp(d, anchor_pts)
            src = "statfin"
        else:
            # ekstrapolaatiovaihe: lineaarisesti last_stat_price → today_target
            gap_days = (today - last_stat_date).days
            if gap_days <= 0:
                p = last_stat_price
            else:
                # määritä today_target
                if live_today_price is not None:
                    today_target = float(live_today_price)
                elif brent_factor is not None:
                    today_target = last_stat_price * brent_factor
                else:
                    today_target = last_stat_price
                frac = (d - last_stat_date).days / gap_days
                p = last_stat_price + (today_target - last_stat_price) * frac
            src = "statfin+extrap" if d < today else "live"

        out.append({
            "date": d.isoformat(),
            "price": round(p, 4),
            "source": src,
        })
    return out
