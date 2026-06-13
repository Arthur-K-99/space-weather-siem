"""Official SWPC alerts / watches / warnings — NOAA SWPC.

https://services.swpc.noaa.gov/products/alerts.json

NOAA's own products (the analog of vendor IDS signatures alongside our own
detection rules). The body is free text; we surface the headline line and the
product id, and keep the full message in ``raw``. Severity is left at 0 — these
carry NOAA's classification, not ours.
"""

from __future__ import annotations

import requests

from collector.schema import (
    SWPC_BASE,
    NormalizedEvent,
    build_event,
    doc_id,
    to_utc_iso,
)

FEED = "swpc_alerts"
GROUP = "slow"
URL = f"{SWPC_BASE}/products/alerts.json"
CATEGORY = "swpc_alert"
DATASET = "swpc.alerts"
OBSERVER = "NOAA-SWPC"

_HEADLINE_PREFIXES = ("ALERT:", "WARNING:", "WATCH:", "SUMMARY:", "EXTENDED WARNING:")


def _headline(message: str) -> str:
    """First ALERT/WARNING/WATCH line, else the first non-empty line."""
    lines = [ln.strip() for ln in message.replace("\r", "\n").split("\n")]
    lines = [ln for ln in lines if ln]
    for ln in lines:
        if ln.upper().startswith(_HEADLINE_PREFIXES):
            return ln
    return lines[0] if lines else ""


def normalize(records: list[dict]) -> list[NormalizedEvent]:
    events = []
    for rec in records:
        ts = to_utc_iso(rec["issue_datetime"])
        product_id = rec.get("product_id", "")
        doc = build_event(
            timestamp=ts,
            kind="alert",
            category=CATEGORY,
            dataset=DATASET,
            severity=0,
            observer=OBSERVER,
            feed=FEED,
            url=URL,
            metrics={},
            raw=rec,
            extra={
                "message": _headline(rec.get("message", "")),
                "swpc": {"product_id": product_id},
            },
        )
        events.append(NormalizedEvent(id=doc_id(FEED, product_id, ts), doc=doc))
    return events


def fetch(session: requests.Session) -> list[dict]:
    resp = session.get(URL, timeout=30)
    resp.raise_for_status()
    return resp.json()
