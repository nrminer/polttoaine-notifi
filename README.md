# gas-alert

Bensiinin (95E10) hintavahti Suomeen. Sends a free push notification via
[ntfy.sh](https://ntfy.sh) when the cheapest 95E10 in your chosen area
drops to or below a price you set.

## How it works

1. A GitHub Action runs every 2 hours.
2. It scrapes `polttoaine.net` (the "20 cheapest 95E10" list).
3. Filters to your chosen cities (optional).
4. If the cheapest station is at or below your threshold and you haven't
   already been alerted at that price, it sends a push notification.
5. State is committed back to the repo so re-alerts are debounced.

## Run it locally first

```bash
pip install -r requirements.txt

export NTFY_TOPIC="pick-something-unguessable-here-xyz789"
export PRICE_THRESHOLD="1.90"
export CITIES="Espoo,Helsinki,Vantaa,Kauniainen"   # optional

python check_prices.py
```

On your phone, install the ntfy.sh app and subscribe to the same topic
name. **The topic is your password** — anyone who knows it can send you
notifications, so make it random and unguessable. Don't commit it.

To test without waiting for a real price drop, set `PRICE_THRESHOLD=99`
and you should get an alert immediately.

## Deploy on GitHub Actions

1. Push this repo to GitHub.
2. In your repo: **Settings → Secrets and variables → Actions**.
3. Add a **secret** named `NTFY_TOPIC` with your ntfy topic.
4. Add **variables** (not secrets) named `PRICE_THRESHOLD` (e.g. `1.85`)
   and optionally `CITIES` (e.g. `Espoo,Helsinki,Vantaa`).
5. **Settings → Actions → General → Workflow permissions** → enable
   *Read and write permissions* (so the bot can commit `state.json`).
6. Trigger the workflow manually once from the **Actions** tab to verify
   it runs cleanly.

That's it. It'll run every 2 hours from then on.

## Data sources

| Source           | Status   | Notes |
|------------------|----------|-------|
| polttoaine.net   | ✅ works  | Crowdsourced, latin1-encoded HTML table. Reliable. |
| tankille.fi      | stub     | No public web prices; needs unofficial mobile API. |
| bensahinta.fi    | stub     | Blocks bots; needs a headless browser to scrape. |

polttoaine.net alone covers most of the country because the same users
report prices to both sites. Adding the other two is genuinely diminishing
returns unless you find a station that only appears on one of them.

## Tuning

- **Re-alert behaviour**: see `RE_ALERT_DELTA` in `check_prices.py`. After
  alerting, you won't get pinged again until the price drops at least
  3 cents further, or climbs back above the threshold and then dips again.
- **Cron frequency**: every 2 hours is plenty. polttoaine.net is updated
  manually by users, so faster polling won't see fresher data and may get
  you rate-limited.
- **Multiple thresholds**: easiest path is to run the workflow twice
  with different env values, into different ntfy topics.
