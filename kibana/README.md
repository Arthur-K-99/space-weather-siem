# Kibana dashboards

Four saved dashboards that turn the `space-weather-events` / `space-weather-alerts`
indices into a SOC-style triage view. They are **dashboards as code**: the saved
objects are assembled by [`scripts/build_dashboards.py`](../scripts/build_dashboards.py)
and serialized to [`dashboards.ndjson`](dashboards.ndjson), which
[`scripts/bootstrap.py`](../scripts/bootstrap.py) imports through the Kibana
saved-objects API on every `docker compose up`.

## The dashboards

| Dashboard | URL (`/app/dashboards#/view/…`) | Panels |
|---|---|---|
| **SOC Overview** | `sws-dashboard-overview` | open alerts, highest open severity, peak NOAA G/R/S scales, alerts-by-severity, event volume by category, recent-alerts table |
| **Geomagnetic** | `sws-dashboard-geomagnetic` | peak Kp, Kp history, IMF Bz/Bt, solar wind speed & density |
| **Solar Activity** | `sws-dashboard-solar` | GOES X-ray flux (log), proton flux ≥10 MeV (log), DONKI flare/CME activity, recent solar events |
| **Pipeline Health** | `sws-dashboard-health` | total events, documents per feed, feed last-seen (the feed-down check), ingest by dataset |

Each dashboard restores a `now-7d` time range and registers two data views
(`space-weather-events`, `space-weather-alerts`) so Discover works too. Space
weather is usually quiet, so the alert panels are empty until a rule fires —
that's the *all clear* state, not a broken panel.

## Regenerating

Edit the panels in Python, not the NDJSON:

```sh
python scripts/build_dashboards.py     # rewrites kibana/dashboards.ndjson
```

`tests/test_dashboards.py` fails if the committed NDJSON drifts from the builder
or if any saved-object reference dangles, so the artifact stays honest.

## Importing manually

`bootstrap.py` does this for you, but to (re)import by hand:

```sh
curl -u "elastic:$ELASTIC_PASSWORD" -X POST \
  "$KIBANA_URL/api/saved_objects/_import?overwrite=true" \
  -H "kbn-xsrf: true" -F file=@kibana/dashboards.ndjson
```
