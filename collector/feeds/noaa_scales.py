"""Current NOAA space-weather scales (R/S/G) — NOAA SWPC.

https://services.swpc.noaa.gov/products/noaa-scales.json

A dict keyed "0" (current observed) plus "1"/"2"/"3"/"-1" (forecasts). We ingest
only the current observed snapshot — it drives the SOC-overview "current scales"
panel. Event severity is the max of the three scales.
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
)

FEED = "noaa_scales"
GROUP = "slow"
URL = f"{SWPC_BASE}/products/noaa-scales.json"
CATEGORY = "noaa_scales"
DATASET = "swpc.noaa_scales"
OBSERVER = "NOAA-SWPC"


def fetch(session: requests.Session) -> dict:
    resp = session.get(URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize(payload: dict) -> list[NormalizedEvent]:
    current = payload.get("0")
    if not current:
        return []
    ts = to_utc_iso(f"{current['DateStamp']} {current['TimeStamp']}")
    scales = {
        "r_scale": num(current.get("R", {}).get("Scale")),
        "s_scale": num(current.get("S", {}).get("Scale")),
        "g_scale": num(current.get("G", {}).get("Scale")),
    }
    metrics = {k: v for k, v in scales.items() if v is not None}
    severity = int(max(metrics.values(), default=0))
    doc = build_event(
        timestamp=ts,
        kind="metric",
        category=CATEGORY,
        dataset=DATASET,
        severity=severity,
        observer=OBSERVER,
        feed=FEED,
        url=URL,
        metrics=metrics,
        raw=current,
    )
    return [NormalizedEvent(id=doc_id(FEED, ts), doc=doc)]
