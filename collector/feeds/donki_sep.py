"""NASA DONKI solar energetic particle events (SEP).

https://api.nasa.gov/DONKI/SEP — discrete SEP onsets. @timestamp is the event
time. Context for the radiation-storm picture; severity stays 0 (the GOES proton
feed carries the S-scale value).
"""

from __future__ import annotations

import requests

from collector.feeds import donki_common
from collector.schema import (
    NormalizedEvent,
    build_event,
    doc_id,
    to_utc_iso,
)

FEED = "donki_sep"
GROUP = "donki"
URL = f"{donki_common.DONKI_BASE}/SEP"
CATEGORY = "solar_radiation"
DATASET = "donki.sep"
OBSERVER = "NASA-DONKI"


def normalize(records: list[dict]) -> list[NormalizedEvent]:
    events = []
    for rec in records:
        ts = to_utc_iso(rec["eventTime"])
        doc = build_event(
            timestamp=ts,
            kind="event",
            category=CATEGORY,
            dataset=DATASET,
            severity=0,
            observer=OBSERVER,
            feed=FEED,
            url=URL,
            metrics={},
            raw=rec,
        )
        events.append(NormalizedEvent(id=doc_id(FEED, rec["sepID"]), doc=doc))
    return events


def fetch(session: requests.Session) -> list[dict]:
    return donki_common.fetch(session, "SEP")
