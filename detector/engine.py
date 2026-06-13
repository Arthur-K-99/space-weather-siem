"""Pure rule-evaluation core — no Elasticsearch, fully unit-testable.

``evaluate`` takes a rule, a list of event ``_source`` dicts, and the current
time, and returns the alert(s) to upsert. All the dedup/throttle behaviour is
encoded in the deterministic fingerprint (rule + entity + time bucket).
"""

from __future__ import annotations

import hashlib
import operator
from datetime import UTC, datetime

from detector.rules import Rule

_OPS = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
}
# ops where "worse" means a larger value (so the representative value is the max)
_ASCENDING = {">=", ">"}


def dig(doc: dict, dotted: str):
    """Read a dotted path (``metrics.kp_index``) from a nested dict, or None."""
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def bucket_id(now: datetime, throttle_s: int) -> int:
    return int(now.timestamp() // throttle_s)


def bucket_start(now: datetime, throttle_s: int) -> datetime:
    return datetime.fromtimestamp(bucket_id(now, throttle_s) * throttle_s, UTC)


def fingerprint(rule_id: str, entity: str, bucket: int) -> str:
    return hashlib.sha1(f"{rule_id}|{entity}|{bucket}".encode()).hexdigest()


def evaluate(rule: Rule, events: list[dict], now: datetime) -> list[tuple[str, dict]]:
    """Return [(alert_id, alert_doc)] for the current throttle bucket (0 or 1 for M4).

    ``events`` are event _source dicts (any dataset; we filter to the rule's).
    """
    compare = _OPS[rule.op]
    matches: list[tuple[dict, float]] = []
    for event in events:
        if dig(event, "event.dataset") != rule.dataset:
            continue
        raw = dig(event, rule.field)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if compare(value, rule.threshold):
            matches.append((event, value))

    if not matches:
        return []

    bucket = bucket_id(now, rule.throttle_s)
    severity = max(int(dig(e, "event.severity") or 0) for e, _ in matches)
    timestamps = sorted(dig(e, "@timestamp") for e, _ in matches)
    values = [v for _, v in matches]
    peak = max(values) if rule.op in _ASCENDING else min(values)
    metric = rule.field.rsplit(".", 1)[-1]
    fp = fingerprint(rule.id, "global", bucket)

    alert = {
        "@timestamp": iso_z(now),
        "message": f"{rule.name}: {metric} reached {peak:g} ({rule.scale}{severity})",
        "rule": {"id": rule.id, "name": rule.name},
        "event": {"kind": "alert", "category": rule.category, "severity": severity},
        "alert": {
            "fingerprint": fp,
            "status": "active",
            "first_seen": timestamps[0],
            "last_seen": timestamps[-1],
            "count": len(matches),
        },
    }
    return [(fp, alert)]
