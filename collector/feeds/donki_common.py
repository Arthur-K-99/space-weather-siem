"""Shared NASA DONKI fetch logic.

All four DONKI endpoints (FLR/CME/GST/SEP) share the same auth + date-range query;
only the path and the per-record normalization differ. Each donki_* feed module
delegates fetching here. The API key comes from NASA_API_KEY (DEMO_KEY works but
is heavily rate-limited).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import requests

DONKI_BASE = "https://api.nasa.gov/DONKI"


def fetch(session: requests.Session, endpoint: str) -> list[dict]:
    """Fetch one DONKI endpoint over a recent look-back window."""
    lookback = int(os.environ.get("DONKI_LOOKBACK_DAYS", "3"))
    end = datetime.now(UTC).date()
    start = end - timedelta(days=lookback)
    resp = session.get(
        f"{DONKI_BASE}/{endpoint}",
        params={
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "api_key": os.environ.get("NASA_API_KEY", "DEMO_KEY"),
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
