"""Rule schema + YAML loader.

Rules live as ``rules/*.yaml`` (a deliverable). Each is parsed into a frozen
``Rule``; the engine never sees raw YAML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_DURATION = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}

_VALID_OPS = {">=", ">", "<=", "<", "=="}


def parse_duration(text: str | int) -> int:
    """'1h' -> 3600, '15m' -> 900, '30s' -> 30, '2d' -> 172800. Ints pass through."""
    if isinstance(text, (int, float)):
        return int(text)
    match = _DURATION.match(str(text))
    if not match:
        raise ValueError(f"bad duration: {text!r} (use e.g. 30s, 15m, 1h, 2d)")
    return int(match.group(1)) * _UNIT[match.group(2)]


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    description: str
    category: str
    scale: str
    dataset: str
    field: str
    op: str
    threshold: float
    throttle_s: int


_REQUIRED = ("id", "name", "category", "scale", "query", "throttle")


def _load_one(path: Path) -> Rule:
    data = yaml.safe_load(path.read_text())
    missing = [k for k in _REQUIRED if k not in data]
    if missing:
        raise ValueError(f"{path.name}: missing required keys {missing}")
    q = data["query"]
    op = q.get("op", ">=")
    if op not in _VALID_OPS:
        raise ValueError(f"{path.name}: invalid op {op!r}")
    return Rule(
        id=data["id"],
        name=data["name"],
        description=data.get("description", "").strip(),
        category=data["category"],
        scale=data["scale"],
        dataset=q["dataset"],
        field=q["field"],
        op=op,
        threshold=float(q["threshold"]),
        throttle_s=parse_duration(data["throttle"]),
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
