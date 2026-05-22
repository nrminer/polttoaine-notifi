"""
"Self-training" -kerros: lue aiemmat ennusteet + toteutuneet hinnat
suoraan tietokannasta ja kokoa menetelmäkohtainen track record, jota
sekä fundamental_anchor (numeerinen bias-korjaus) että AI-promppi
(kielellinen itsekalibrointi) käyttävät.

Mikään tästä EI ole synteettistä — vertailupohja on aina
`daily_tracker.actual_cheapest` (myöhäisin capture/päivä), sama
totuuslähde kuin /api/accuracy:lla ja `realized_method_mae`:lla.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone


_METHODS = ("moving_average", "linear_regression", "exp_smoothing",
            "fundamental_anchor", "ai_llm")


def _stats(signed_errors: list[float]) -> dict:
    """{n, mae, bias, rmse}. bias = signed mean (pred − actual); positiivinen
    = malli yliennustaa systemaattisesti."""
    if not signed_errors:
        return {"n": 0, "mae": None, "bias": None, "rmse": None}
    n = len(signed_errors)
    abs_sum = sum(abs(x) for x in signed_errors)
    sq_sum = sum(x * x for x in signed_errors)
    return {
        "n": n,
        "mae": round(abs_sum / n, 5),
        "bias": round(sum(signed_errors) / n, 5),
        "rmse": round((sq_sum / n) ** 0.5, 5),
    }


async def track_record(db, fuel: str, region: str = "Suomi",
                       days: int = 30,
                       methods: tuple[str, ...] = _METHODS) -> dict:
    """Lue viimeisen `days` päivän tallennetut ennusteet ja kelaa läpi
    jokainen menetelmä + ensemble vs. tallennettu toteutuma.

    Palauttaa:
        {
          "rows": [
             {"date","actual","methods":{m:pred},"signed":{m:pred-actual}},
             …
          ],
          "stats": {
             "<method>": {"n","mae","bias","rmse"},
             "ensemble":  {…},
          },
          "n_total": <vertailtuja päiviä>,
          "days_window": days,
        }

    Käyttäjät:
      - `predict.fundamental_anchor` lukee `stats['fundamental_anchor']['bias']`
        ja vähentää siitä vaimennetun korjauksen (sample-koolla skaalattu).
      - `predict.ai_llm_predict` näyttää rivit ja statistiikan AI:lle, jotta
        se voi havaita oman systemaattisen vinoumansa.
    """
    cutoff_date = (datetime.now(timezone.utc).date()
                   - timedelta(days=days)).isoformat()

    preds = await db.predictions.find(
        {"fuel": fuel, "region": region, "target_date": {"$gte": cutoff_date}},
        {"_id": 0, "target_date": 1, "methods": 1, "ensemble": 1,
         "ensemble_full": 1, "generated_at": 1},
    ).sort("target_date", 1).to_list(length=days + 20)

    keys = list(methods) + ["ensemble"]
    signed: dict[str, list[float]] = {k: [] for k in keys}
    rows: list[dict] = []

    for p in preds:
        target = p.get("target_date")
        if not target:
            continue
        actual_doc = await db.daily_tracker.find_one(
            {"fuel": fuel, "region": region, "date": target,
             "actual_cheapest": {"$ne": None}},
            {"_id": 0, "actual_cheapest": 1},
            sort=[("hour", -1)],
        )
        actual = actual_doc.get("actual_cheapest") if actual_doc else None
        if actual is None:
            continue

        row = {"date": target, "actual": float(actual),
               "methods": {}, "signed": {}}

        for m, v in (p.get("methods") or {}).items():
            if m in signed and v is not None:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                row["methods"][m] = round(fv, 4)
                row["signed"][m] = round(fv - actual, 5)
                signed[m].append(fv - actual)

        # `db.predictions` tallennusmuoto: `ensemble` on FLOAT (uloskaivettu
        # arvo) ja `ensemble_full` on koko dict. Tue molempia muotoja
        # varovaisesti — vanha legacy-data saattaa myös tallentaa dictinä.
        ens_raw = p.get("ensemble_full")
        if not isinstance(ens_raw, dict):
            ens_raw = p.get("ensemble")
        if isinstance(ens_raw, dict):
            ens_v = ens_raw.get("value")
        elif isinstance(ens_raw, (int, float)):
            ens_v = float(ens_raw)
        else:
            ens_v = None
        if ens_v is not None:
            try:
                fv = float(ens_v)
                row["methods"]["ensemble"] = round(fv, 4)
                row["signed"]["ensemble"] = round(fv - actual, 5)
                signed["ensemble"].append(fv - actual)
            except (TypeError, ValueError):
                pass

        rows.append(row)

    stats = {k: _stats(v) for k, v in signed.items()}
    return {
        "rows": rows,
        "stats": stats,
        "n_total": len(rows),
        "days_window": days,
    }
