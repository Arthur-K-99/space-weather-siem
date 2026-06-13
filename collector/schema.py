"""Normalized event schema, severity taxonomy, and shared helpers.

Every feed normalizes its raw records into the ECS-inspired document described
in docs/PLAN.md and indexed into the ``space-weather-events`` data stream. The
G/R/S severity ladders live here because they are a property of the measurement
(a Kp=7 reading *is* a G3 event); the detector reuses them in M4.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

SWPC_BASE = "https://services.swpc.noaa.gov"


@dataclass(frozen=True)
class NormalizedEvent:
    """One event ready to index: a deterministic ``_id`` plus the ES document."""

    id: str
    doc: dict


def kp_to_severity(kp: float) -> int:
    """Map a planetary K-index to the NOAA G-scale as severity 0-5.

    Kp < 5 is sub-storm (0); Kp 5..9 maps to G1..G5 = severity 1..5.
    """
    if kp < 5:
        return 0
    return min(int(kp) - 4, 5)


# NOAA R-scale thresholds on the GOES long-band (1-8 Å) flux, in W/m².
# R1=M1 1e-5, R2=M5 5e-5, R3=X1 1e-4, R4=X10 1e-3, R5=X20 2e-3.
_XRAY_LADDER = (
    (2e-3, 5),
    (1e-3, 4),
    (1e-4, 3),
    (5e-5, 2),
    (1e-5, 1),
)


def xray_to_severity(flux: float) -> int:
    """Map GOES long-band X-ray flux (W/m²) to the NOAA R-scale as severity 0-5."""
    for threshold, severity in _XRAY_LADDER:
        if flux >= threshold:
            return severity
    return 0


def to_utc_iso(time_tag: str) -> str:
    """Normalize a SWPC ``time_tag`` to ISO-8601 UTC with a trailing ``Z``.

    SWPC is inconsistent: the Kp feed emits naive UTC ("...:00") while the
    X-ray feed already carries "Z". Both denote UTC.
    """
    t = time_tag.strip().replace(" ", "T")
    if t.endswith("Z"):
        return t
    if t.endswith("+00:00"):
        return t[:-6] + "Z"
    return t + "Z"


def doc_id(*parts: str) -> str:
    """Deterministic document ``_id`` from source + timestamp parts.

    Re-ingesting the same record yields the same id, so a ``create`` op is a
    no-op (409) rather than a duplicate.
    """
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def build_event(
    *,
    timestamp: str,
    kind: str,
    category: str,
    dataset: str,
    severity: int,
    observer: str,
    feed: str,
    url: str,
    metrics: dict,
    raw: dict,
) -> dict:
    """Assemble the common normalized-event document."""
    return {
        "@timestamp": timestamp,
        "event": {
            "kind": kind,
            "category": category,
            "dataset": dataset,
            "severity": severity,
        },
        "observer": {"name": observer},
        "source": {"feed": feed, "url": url},
        "metrics": metrics,
        "raw": raw,
    }
