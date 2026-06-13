"""Rule schema + YAML loader.

Rules live as ``rules/*.yaml`` (a deliverable). Each is parsed into a frozen
``Rule``; the engine never sees raw YAML. A rule's ``type`` selects how the engine
evaluates it:

- ``threshold``      — one field crosses a threshold (M4 rules 1-3).
- ``precursor``      — several conditions hold together over a window, one of them
  sustained for a minimum duration (rule 4: Bz southward + fast solar wind).
- ``chain``          — ordered stages, each occurring within a gap of the previous
  (rule 5: the flare -> CME -> geomagnetic-storm "attack chain").
- ``telemetry_loss`` — a monitored feed has gone silent past N x its cadence
  (rule 6: the SIEM "log source down" / dead-agent detection).

``threshold``/``precursor``/``chain`` express their matchers as ``Condition``s so
the engine shares one matcher across all three; ``telemetry_loss`` uses
``Monitor``s instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_DURATION = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}

_VALID_OPS = {">=", ">", "<=", "<", "=="}
_VALID_TYPES = {"threshold", "precursor", "chain", "telemetry_loss"}


def parse_duration(text: str | int) -> int:
    """'1h' -> 3600, '15m' -> 900, '30s' -> 30, '2d' -> 172800. Ints pass through."""
    if isinstance(text, (int, float)):
        return int(text)
    match = _DURATION.match(str(text))
    if not match:
        raise ValueError(f"bad duration: {text!r} (use e.g. 30s, 15m, 1h, 2d)")
    return int(match.group(1)) * _UNIT[match.group(2)]


@dataclass(frozen=True)
class Condition:
    """One matcher: events of ``dataset`` where ``field op threshold`` holds.

    ``field``/``threshold`` are optional — a chain stage that only needs an event
    to exist (a flare, a CME) omits them. ``sustain_s`` (precursor) requires the
    matches to span at least that long; ``within_s`` (chain) bounds the gap after
    the previous stage; ``min_severity`` (chain) gates on the stamped severity.
    """

    dataset: str
    field: str | None = None
    op: str = ">="
    threshold: float | None = None
    sustain_s: int | None = None
    within_s: int | None = None
    min_severity: int | None = None
    label: str | None = None


@dataclass(frozen=True)
class Monitor:
    """A feed whose silence past ``cadence_s * multiplier`` is itself an alert."""

    dataset: str
    cadence_s: int
    multiplier: int


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    description: str
    category: str
    scale: str
    type: str
    throttle_s: int
    severity: int | None  # declared floor; None => derive from the matched events
    conditions: tuple[Condition, ...]  # threshold:1, precursor:N, chain:ordered stages
    monitors: tuple[Monitor, ...]  # telemetry_loss only
    datasets: tuple[str, ...]  # every event.dataset the rule reads (for the fetch)
    lookback_s: int  # how far back the runner fetches events for this rule


_COMMON = ("id", "name", "category", "scale", "throttle")


def _condition(data: dict) -> Condition:
    op = data.get("op", ">=")
    if op not in _VALID_OPS:
        raise ValueError(f"invalid op {op!r}")
    threshold = data.get("threshold")
    return Condition(
        dataset=data["dataset"],
        field=data.get("field"),
        op=op,
        threshold=float(threshold) if threshold is not None else None,
        sustain_s=parse_duration(data["sustain"]) if "sustain" in data else None,
        within_s=parse_duration(data["within"]) if "within" in data else None,
        min_severity=data.get("min_severity"),
        label=data.get("name"),
    )


def _monitor(data: dict) -> Monitor:
    return Monitor(
        dataset=data["dataset"],
        cadence_s=parse_duration(data["cadence"]),
        multiplier=int(data["multiplier"]),
    )


def _load_one(path: Path) -> Rule:
    data = yaml.safe_load(path.read_text())
    rtype = data.get("type", "threshold")
    if rtype not in _VALID_TYPES:
        raise ValueError(f"{path.name}: unknown type {rtype!r}")
    missing = [k for k in _COMMON if k not in data]
    if missing:
        raise ValueError(f"{path.name}: missing required keys {missing}")

    conditions: tuple[Condition, ...] = ()
    monitors: tuple[Monitor, ...] = ()
    try:
        if rtype == "threshold":
            conditions = (_condition(data["query"]),)
            lookback_s = parse_duration(data["throttle"])
        elif rtype == "precursor":
            conditions = tuple(_condition(c) for c in data["conditions"])
            lookback_s = parse_duration(data["window"])
        elif rtype == "chain":
            conditions = tuple(_condition(s) for s in data["stages"])
            lookback_s = sum(c.within_s or 0 for c in conditions)
        else:  # telemetry_loss
            monitors = tuple(_monitor(m) for m in data["monitors"])
            lookback_s = int(max(m.cadence_s * m.multiplier for m in monitors) * 3)
    except KeyError as exc:
        raise ValueError(f"{path.name}: missing {exc.args[0]!r} for type {rtype!r}") from exc

    if "lookback" in data:  # explicit override (e.g. widen a chain window for replay)
        lookback_s = parse_duration(data["lookback"])

    severity = data.get("severity")
    if rtype != "threshold" and severity is None:
        raise ValueError(f"{path.name}: type {rtype!r} requires an explicit severity")

    datasets = tuple(
        dict.fromkeys([c.dataset for c in conditions] + [m.dataset for m in monitors])
    )

    return Rule(
        id=data["id"],
        name=data["name"],
        description=data.get("description", "").strip(),
        category=data["category"],
        scale=data["scale"],
        type=rtype,
        throttle_s=parse_duration(data["throttle"]),
        severity=int(severity) if severity is not None else None,
        conditions=conditions,
        monitors=monitors,
        datasets=datasets,
        lookback_s=lookback_s,
    )


def load_rules(rules_dir: str | Path) -> list[Rule]:
    directory = Path(rules_dir)
    rules = [_load_one(p) for p in sorted(directory.glob("*.yaml"))]
    if not rules:
        raise ValueError(f"no rules found in {directory}")
    ids = [r.id for r in rules]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate rule ids: {sorted(dupes)}")
    return rules
