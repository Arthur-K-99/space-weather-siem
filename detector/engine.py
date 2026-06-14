"""Pure rule-evaluation core — no Elasticsearch, fully unit-testable.

``evaluate`` takes a rule, a list of event ``_source`` dicts, and the current
time, and dispatches on ``rule.type`` to a pure evaluator that returns the
alert(s) to upsert. Dedup/throttle is encoded in the deterministic fingerprint
(rule + entity + time bucket): re-evaluating the same bucket yields the same
``_id`` and overwrites in place; a new bucket re-alerts; a higher severity
escalates. The four evaluators share one ``_matches`` helper so a "condition"
means the same thing everywhere.
"""

from __future__ import annotations

import hashlib
import operator
from datetime import UTC, datetime, timedelta

from detector.rules import Condition, Rule

_OPS = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
}
# ops where "worse" means a larger value (so the representative value is the max)
_ASCENDING = {">=", ">"}

# One matched event: the source doc, its numeric value (None for presence-only
# stages), and its parsed timestamp.
Match = tuple[dict, float | None, datetime]


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


def _parse_ts(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)  # handles a trailing 'Z' on 3.11+
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def bucket_id(now: datetime, throttle_s: int) -> int:
    return int(now.timestamp() // throttle_s)


def bucket_start(now: datetime, throttle_s: int) -> datetime:
    return datetime.fromtimestamp(bucket_id(now, throttle_s) * throttle_s, UTC)


def fingerprint(rule_id: str, entity: str, bucket: int) -> str:
    return hashlib.sha1(f"{rule_id}|{entity}|{bucket}".encode()).hexdigest()


def _severity(event: dict) -> int:
    return int(dig(event, "event.severity") or 0)


def _matches(cond: Condition, events: list[dict]) -> list[Match]:
    """Events of ``cond.dataset`` satisfying the condition, with parsed timestamps."""
    out: list[Match] = []
    for event in events:
        if dig(event, "event.dataset") != cond.dataset:
            continue
        if cond.min_severity is not None and _severity(event) < cond.min_severity:
            continue
        value: float | None = None
        if cond.field is not None:
            raw = dig(event, cond.field)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not _OPS[cond.op](value, cond.threshold):
                continue
        ts = _parse_ts(dig(event, "@timestamp"))
        if ts is None:
            continue
        out.append((event, value, ts))
    return out


def _peak(cond: Condition, matches: list[Match]) -> float:
    values = [v for _, v, _ in matches if v is not None]
    return max(values) if cond.op in _ASCENDING else min(values)


def _alert(
    rule: Rule,
    now: datetime,
    *,
    severity: int,
    message: str,
    fp: str,
    first_seen: str,
    last_seen: str,
    count: int,
) -> dict:
    return {
        "@timestamp": iso_z(now),
        "message": message,
        "rule": {"id": rule.id, "name": rule.name},
        "event": {"kind": "alert", "category": rule.category, "severity": severity},
        "alert": {
            "fingerprint": fp,
            "status": "active",
            "first_seen": first_seen,
            "last_seen": last_seen,
            "count": count,
        },
    }


# --- threshold (rules 1-3) -------------------------------------------------


def _eval_threshold(rule: Rule, events: list[dict], now: datetime) -> list[tuple[str, dict]]:
    cond = rule.conditions[0]
    matches = _matches(cond, events)
    if not matches:
        return []
    bucket = bucket_id(now, rule.throttle_s)
    severity = max(_severity(e) for e, _, _ in matches)
    timestamps = sorted(ts for _, _, ts in matches)
    peak = _peak(cond, matches)
    metric = cond.field.rsplit(".", 1)[-1]
    fp = fingerprint(rule.id, "global", bucket)
    alert = _alert(
        rule,
        now,
        severity=severity,
        message=f"{rule.name}: {metric} reached {peak:g} ({rule.scale}{severity})",
        fp=fp,
        first_seen=iso_z(timestamps[0]),
        last_seen=iso_z(timestamps[-1]),
        count=len(matches),
    )
    return [(fp, alert)]


# --- precursor (rule 4) ----------------------------------------------------


def _eval_precursor(rule: Rule, events: list[dict], now: datetime) -> list[tuple[str, dict]]:
    """All conditions must hold; a condition with ``sustain_s`` must persist that long."""
    all_ts: list[datetime] = []
    total = 0
    parts: list[str] = []
    for cond in rule.conditions:
        matches = _matches(cond, events)
        if not matches:
            return []  # AND fails
        note = ""
        if cond.sustain_s is not None:
            span = max(ts for _, _, ts in matches) - min(ts for _, _, ts in matches)
            if span.total_seconds() < cond.sustain_s:
                return []
            note = f" sustained {int(span.total_seconds() // 60)}m"
        total += len(matches)
        all_ts.extend(ts for _, _, ts in matches)
        metric = cond.field.rsplit(".", 1)[-1]
        parts.append(f"{metric} {cond.op} {cond.threshold:g} (peak {_peak(cond, matches):g}{note})")

    severity = rule.severity
    all_ts.sort()
    bucket = bucket_id(now, rule.throttle_s)
    fp = fingerprint(rule.id, "global", bucket)
    alert = _alert(
        rule,
        now,
        severity=severity,
        message=f"{rule.name}: {' & '.join(parts)} ({rule.scale}-precursor sev {severity})",
        fp=fp,
        first_seen=iso_z(all_ts[0]),
        last_seen=iso_z(all_ts[-1]),
        count=total,
    )
    return [(fp, alert)]


# --- chain (rule 5) --------------------------------------------------------


def _stage_label(stage: Condition, match: Match) -> str:
    event, value, ts = match
    name = stage.label or stage.dataset.rsplit(".", 1)[-1]
    flare_class = dig(event, "flare.class")
    if flare_class:
        detail = f" {flare_class}"
    elif value is not None:
        detail = f" {value:g}"
    else:
        detail = ""
    return f"{name}{detail} @ {iso_z(ts)}"


def _find_chain(stages: tuple[Condition, ...], by_stage: list[list[Match]], terminal: Match):
    """Walk backward from a terminal-stage match, choosing for each earlier stage
    the closest preceding match within its ``within_s`` gap that still lets the
    rest of the chain complete. Backtracks, so unrelated events of the same
    dataset sitting between two real stages don't break the link (e.g. background
    CMEs between the chain's flare and its geomagnetic storm). Returns the ordered
    matches, or None."""

    def back(i: int, after: Match):
        if i < 0:
            return []
        gap = stages[i + 1].within_s or 0
        ref = after[2]
        candidates = sorted(
            (m for m in by_stage[i] if m[2] <= ref and (ref - m[2]).total_seconds() <= gap),
            key=lambda m: m[2],
            reverse=True,  # closest preceding first
        )
        for cand in candidates:
            prefix = back(i - 1, cand)
            if prefix is not None:
                return [*prefix, cand]
        return None

    prefix = back(len(stages) - 2, terminal)
    return None if prefix is None else [*prefix, terminal]


def _eval_chain(rule: Rule, events: list[dict], now: datetime) -> list[tuple[str, dict]]:
    """One composite incident per terminal-stage event that completes the chain."""
    stages = rule.conditions
    by_stage = [_matches(stage, events) for stage in stages]
    if any(not stage_matches for stage_matches in by_stage):
        return []

    bucket = bucket_id(now, rule.throttle_s)
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for terminal in by_stage[-1]:
        chain = _find_chain(stages, by_stage, terminal)
        if chain is None:
            continue
        entity = iso_z(terminal[2])  # one incident per terminal storm
        if entity in seen:
            continue
        seen.add(entity)
        severity = max([rule.severity] + [_severity(e) for e, _, _ in chain])
        trail = " -> ".join(_stage_label(stages[i], chain[i]) for i in range(len(stages)))
        fp = fingerprint(rule.id, entity, bucket)
        out.append(
            (
                fp,
                _alert(
                    rule,
                    now,
                    severity=severity,
                    message=f"{rule.name}: {trail} ({rule.scale}{severity})",
                    fp=fp,
                    first_seen=iso_z(chain[0][2]),
                    last_seen=iso_z(chain[-1][2]),
                    count=len(stages),
                ),
            )
        )
    return out


# --- telemetry loss (rule 6) -----------------------------------------------


def _eval_telemetry(rule: Rule, events: list[dict], now: datetime) -> list[tuple[str, dict]]:
    """One alert per monitored feed silent past ``cadence_s * multiplier``."""
    bucket = bucket_id(now, rule.throttle_s)
    window_start = now - timedelta(seconds=rule.lookback_s)
    out: list[tuple[str, dict]] = []
    for mon in rule.monitors:
        seen_ts = [
            ts
            for e in events
            if dig(e, "event.dataset") == mon.dataset
            and (ts := _parse_ts(dig(e, "@timestamp"))) is not None
        ]
        latest = max(seen_ts) if seen_ts else None
        gap = mon.cadence_s * mon.multiplier
        silence = (now - latest) if latest else (now - window_start)
        silence_s = silence.total_seconds()
        if latest is not None and silence_s <= gap:
            continue  # feed is healthy

        if latest is not None:
            seen_part = f"last doc {iso_z(latest)}"
            first_seen = iso_z(latest)
        else:
            seen_part = f"no docs in last {int(silence_s // 60)}m"
            first_seen = iso_z(window_start)
        fp = fingerprint(rule.id, mon.dataset, bucket)
        out.append(
            (
                fp,
                _alert(
                    rule,
                    now,
                    severity=rule.severity,
                    message=(
                        f"{rule.name}: {mon.dataset} silent {int(silence_s // 60)}m "
                        f"({seen_part}, cadence {mon.cadence_s}s x{mon.multiplier})"
                    ),
                    fp=fp,
                    first_seen=first_seen,
                    last_seen=iso_z(now),
                    count=int(silence_s // mon.cadence_s),
                ),
            )
        )
    return out


_EVALUATORS = {
    "threshold": _eval_threshold,
    "precursor": _eval_precursor,
    "chain": _eval_chain,
    "telemetry_loss": _eval_telemetry,
}


def evaluate(rule: Rule, events: list[dict], now: datetime) -> list[tuple[str, dict]]:
    """Return [(alert_id, alert_doc)] for ``rule`` given the events visible at ``now``."""
    return _EVALUATORS[rule.type](rule, events, now)
