"""NASA DONKI solar flares (FLR).

https://api.nasa.gov/DONKI/FLR — discrete flare events with a GOES class
("X1.0"). @timestamp is the flare begin time; severity maps the class to the
R-scale. First link in the flare -> CME -> storm chain (M5).
"""

from __future__ import annotations

import requests

from collector.feeds import donki_common
from collector.schema import (
    NormalizedEvent,
    build_event,
    doc_id,
    flare_class_to_severity,
    to_utc_iso,
)

FEED = "donki_flr"
GROUP = "donki"
URL = f"{donki_common.DONKI_BASE}/FLR"
CATEGORY = "flare"
DATASET = "donki.flr"
OBSERVER = "NASA-DONKI"


def fetch(session: requests.Session) -> list[dict]:
    return donki_common.fetch(session, "FLR")


def normalize(records: list[dict]) -> list[NormalizedEvent]:
    events = []
    for rec in records:
        ts = to_utc_iso(rec["beginTime"])
        doc = build_event(
            timestamp=ts,
            kind="event",
            category=CATEGORY,
            dataset=DATASET,
            severity=flare_class_to_severity(rec.get("classType")),
            observer=OBSERVER,
            feed=FEED,
            url=URL,
            metrics={},
            raw=rec,
            extra={
                "flare": {
                    "class": rec.get("classType"),
                    "source_location": rec.get("sourceLocation"),
                    "active_region": rec.get("activeRegionNum"),
                }
            },
        )
        events.append(NormalizedEvent(id=doc_id(FEED, rec["flrID"]), doc=doc))
    return events
