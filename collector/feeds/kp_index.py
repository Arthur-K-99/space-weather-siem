"""Planetary K-index (1-minute) — NOAA SWPC.

https://services.swpc.noaa.gov/json/planetary_k_index_1m.json

Each record carries both ``kp_index`` (rounded int) and ``estimated_kp`` (the
precise real-time estimate). We key the geomagnetic severity off ``estimated_kp``
so the G-scale ladder sees the true value.
"""

from __future__ import annotations

import requests

from collector.schema import (
    SWPC_BASE,
    NormalizedEvent,
    build_event,
    doc_id,
    kp_to_severity,
    to_utc_iso,
)

FEED = "planetary_k_index_1m"
GROUP = "realtime"
URL = f"{SWPC_BASE}/json/planetary_k_index_1m.json"
CATEGORY = "geomagnetic"
DATASET = "swpc.planetary_k_index"
# The planetary Kp is a globally derived index, not a single instrument reading.
OBSERVER = "NOAA-SWPC"


def fetch(session: requests.Session) -> list[dict]:
    resp = session.get(URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize(records: list[dict]) -> list[NormalizedEvent]:
    events = []
    for rec in records:
        ts = to_utc_iso(rec["time_tag"])
        kp = float(rec["estimated_kp"])
        doc = build_event(
            timestamp=ts,
            kind="metric",
            category=CATEGORY,
            dataset=DATASET,
            severity=kp_to_severity(kp),
            observer=OBSERVER,
            feed=FEED,
            url=URL,
            metrics={"kp_index": kp},
            raw=rec,
        )
        events.append(NormalizedEvent(id=doc_id(FEED, ts), doc=doc))
    return events
