"""Solar wind plasma (DSCOVR, 6-hour window) — NOAA SWPC.

https://services.swpc.noaa.gov/products/solar-wind/plasma-6-hour.json

A "products" feed: array-of-arrays with a header row. We poll the 6-hour window
(not 7-day) so each frequent poll stays small; idempotent ids dedup the overlap.
Speed feeds the storm-precursor correlation rule (M5).
"""

from __future__ import annotations

import requests

from collector.schema import (
    SWPC_BASE,
    NormalizedEvent,
    build_event,
    doc_id,
    num,
    to_utc_iso,
    zip_header,
)

FEED = "solar_wind_plasma"
GROUP = "realtime"
URL = f"{SWPC_BASE}/products/solar-wind/plasma-6-hour.json"
CATEGORY = "solar_wind"
DATASET = "swpc.solar_wind_plasma"
OBSERVER = "DSCOVR"


def fetch(session: requests.Session) -> list[list]:
    resp = session.get(URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize(payload: list[list]) -> list[NormalizedEvent]:
    events = []
    for rec in zip_header(payload):
        speed = num(rec.get("speed"))
        if speed is None:  # data gap — skip rather than index a hollow doc
            continue
        ts = to_utc_iso(rec["time_tag"])
        metrics = {
            "speed_km_s": speed,
            "density": num(rec.get("density")),
            "temperature": num(rec.get("temperature")),
        }
        metrics = {k: v for k, v in metrics.items() if v is not None}
        doc = build_event(
            timestamp=ts,
            kind="metric",
            category=CATEGORY,
            dataset=DATASET,
            severity=0,
            observer=OBSERVER,
            feed=FEED,
            url=URL,
            metrics=metrics,
            raw=rec,
        )
        events.append(NormalizedEvent(id=doc_id(FEED, ts), doc=doc))
    return events
