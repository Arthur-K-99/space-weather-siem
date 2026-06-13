"""GOES integral proton flux (1-day) — NOAA SWPC.

https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json

The feed reports many energy bands per timestamp (>=1, >=5, >=10, ... MeV). The
NOAA S-scale (solar radiation storm) is defined on the >=10 MeV integral flux, so
we keep only that band. Feeds the radiation-storm rule (M4).
"""

from __future__ import annotations

import requests

from collector.schema import (
    SWPC_BASE,
    NormalizedEvent,
    build_event,
    doc_id,
    num,
    proton_to_severity,
    to_utc_iso,
)

FEED = "goes_integral_protons_1day"
GROUP = "slow"
URL = f"{SWPC_BASE}/json/goes/primary/integral-protons-1-day.json"
CATEGORY = "solar_radiation"
DATASET = "swpc.goes_protons"
BAND = ">=10 MeV"


def fetch(session: requests.Session) -> list[dict]:
    resp = session.get(URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize(records: list[dict]) -> list[NormalizedEvent]:
    events = []
    for rec in records:
        if rec.get("energy") != BAND:
            continue
        flux = num(rec.get("flux"))
        if flux is None:
            continue
        ts = to_utc_iso(rec["time_tag"])
        doc = build_event(
            timestamp=ts,
            kind="metric",
            category=CATEGORY,
            dataset=DATASET,
            severity=proton_to_severity(flux),
            observer=f"GOES-{rec['satellite']}",
            feed=FEED,
            url=URL,
            metrics={"proton_flux_10mev": flux},
            raw=rec,
        )
        events.append(NormalizedEvent(id=doc_id(FEED, ts), doc=doc))
    return events
