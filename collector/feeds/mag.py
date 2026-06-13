"""Solar wind magnetometer (DSCOVR, 6-hour window) — NOAA SWPC.

https://services.swpc.noaa.gov/products/solar-wind/mag-6-hour.json

Array-of-arrays with a header row. ``bz_gsm`` (southward IMF) is the key driver of
geomagnetic coupling and feeds the storm-precursor rule (M5).
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

FEED = "solar_wind_mag"
GROUP = "realtime"
URL = f"{SWPC_BASE}/products/solar-wind/mag-6-hour.json"
CATEGORY = "solar_wind"
DATASET = "swpc.solar_wind_mag"
OBSERVER = "DSCOVR"


def fetch(session: requests.Session) -> list[list]:
    resp = session.get(URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize(payload: list[list]) -> list[NormalizedEvent]:
    events = []
    for rec in zip_header(payload):
        bz = num(rec.get("bz_gsm"))
        if bz is None:  # data gap
            continue
        ts = to_utc_iso(rec["time_tag"])
        metrics = {
            "bz_gsm": bz,
            "bt": num(rec.get("bt")),
            "bx_gsm": num(rec.get("bx_gsm")),
            "by_gsm": num(rec.get("by_gsm")),
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
