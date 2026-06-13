"""GOES X-ray flux (1-day) — NOAA SWPC.

https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json

The feed reports two energy bands per timestamp: the short 0.05-0.4 nm channel
and the long 0.1-0.8 nm (1-8 Å) channel. NOAA flare class (A/B/C/M/X) and the
R-scale radio-blackout ladder are both defined on the *long* channel, so we keep
only that band and drop the short one. ``flux`` is the electron-corrected value.
"""

from __future__ import annotations

import requests

from collector.schema import (
    SWPC_BASE,
    NormalizedEvent,
    build_event,
    doc_id,
    to_utc_iso,
    xray_to_severity,
)

FEED = "goes_xrays_1day"
URL = f"{SWPC_BASE}/json/goes/primary/xrays-1-day.json"
CATEGORY = "xray"
DATASET = "swpc.goes_xray"
LONG_BAND = "0.1-0.8nm"


def fetch(session: requests.Session) -> list[dict]:
    resp = session.get(URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize(records: list[dict]) -> list[NormalizedEvent]:
    events = []
    for rec in records:
        if rec.get("energy") != LONG_BAND:
            continue
        ts = to_utc_iso(rec["time_tag"])
        flux = float(rec["flux"])
        doc = build_event(
            timestamp=ts,
            kind="metric",
            category=CATEGORY,
            dataset=DATASET,
            severity=xray_to_severity(flux),
            observer=f"GOES-{rec['satellite']}",
            feed=FEED,
            url=URL,
            metrics={"xray_flux": flux},
            raw=rec,
        )
        # Energy band is part of the id so adding the short band later can't collide.
        events.append(NormalizedEvent(id=doc_id(FEED, rec["energy"], ts), doc=doc))
    return events
