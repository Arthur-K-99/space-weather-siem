"""NASA DONKI geomagnetic storms (GST).

https://api.nasa.gov/DONKI/GST — discrete storm events carrying an ``allKpIndex``
series. @timestamp is the storm start time; the metric and severity come from the
peak Kp over the series. Final link in the flare -> CME -> storm chain (M5).
"""

from __future__ import annotations

import requests

from collector.feeds import donki_common
from collector.schema import (
    NormalizedEvent,
    build_event,
    doc_id,
    kp_to_severity,
    num,
    to_utc_iso,
)

FEED = "donki_gst"
GROUP = "donki"
URL = f"{donki_common.DONKI_BASE}/GST"
CATEGORY = "geomagnetic"
DATASET = "donki.gst"
OBSERVER = "NASA-DONKI"


def _peak_kp(rec: dict) -> float | None:
    kps = [num(k.get("kpIndex")) for k in rec.get("allKpIndex") or []]
    kps = [k for k in kps if k is not None]
    return max(kps) if kps else None


def normalize(records: list[dict]) -> list[NormalizedEvent]:
    events = []
    for rec in records:
        ts = to_utc_iso(rec["startTime"])
        peak_kp = _peak_kp(rec)
        metrics = {"kp_index": peak_kp} if peak_kp is not None else {}
        severity = kp_to_severity(peak_kp) if peak_kp is not None else 0
        doc = build_event(
            timestamp=ts,
            kind="event",
            category=CATEGORY,
            dataset=DATASET,
            severity=severity,
            observer=OBSERVER,
            feed=FEED,
            url=URL,
            metrics=metrics,
            raw=rec,
        )
        events.append(NormalizedEvent(id=doc_id(FEED, rec["gstID"]), doc=doc))
    return events


def fetch(session: requests.Session) -> list[dict]:
    return donki_common.fetch(session, "GST")
