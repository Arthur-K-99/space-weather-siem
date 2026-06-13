"""NASA DONKI coronal mass ejections (CME).

https://api.nasa.gov/DONKI/CME — discrete CME events. Speed comes from the most
accurate analysis in ``cmeAnalyses``. @timestamp is the CME start time. Second
link in the flare -> CME -> storm chain (M5); severity stays 0 (it's a marker).
"""

from __future__ import annotations

import requests

from collector.feeds import donki_common
from collector.schema import (
    NormalizedEvent,
    build_event,
    doc_id,
    num,
    to_utc_iso,
)

FEED = "donki_cme"
GROUP = "donki"
URL = f"{donki_common.DONKI_BASE}/CME"
CATEGORY = "cme"
DATASET = "donki.cme"
OBSERVER = "NASA-DONKI"


def _best_speed(rec: dict) -> float | None:
    analyses = rec.get("cmeAnalyses") or []
    for analysis in analyses:
        if analysis.get("isMostAccurate"):
            return num(analysis.get("speed"))
    return num(analyses[0].get("speed")) if analyses else None


def normalize(records: list[dict]) -> list[NormalizedEvent]:
    events = []
    for rec in records:
        ts = to_utc_iso(rec["startTime"])
        speed = _best_speed(rec)
        metrics = {"speed_km_s": speed} if speed is not None else {}
        doc = build_event(
            timestamp=ts,
            kind="event",
            category=CATEGORY,
            dataset=DATASET,
            severity=0,
            observer=OBSERVER,
            feed=FEED,
            url=URL,
            metrics=metrics,
            raw=rec,
            extra={"cme": {"source_location": rec.get("sourceLocation")}},
        )
        events.append(NormalizedEvent(id=doc_id(FEED, rec["activityID"]), doc=doc))
    return events


def fetch(session: requests.Session) -> list[dict]:
    return donki_common.fetch(session, "CME")
