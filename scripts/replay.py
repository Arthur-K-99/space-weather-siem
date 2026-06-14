#!/usr/bin/env python3
"""Replay the May 2024 Gannon G5 storm so every detection rule fires on demand.

Space weather is quiet most of the time, so the rules rarely trigger on live
data. This backfills committed storm fixtures (``replay/*.json``) — the real
Gannon DONKI flare -> CME -> storm chain plus storm-magnitude SWPC realtime feeds
— through the *same normalizers the collector uses*, with timestamps rebased to
``now`` so the detector sees a live G5 storm. It is the space-weather analog of a
purple-team / attack-simulation exercise: a deterministic incident you can summon
for demos, after which all six rules light up on the dashboards.

Rebasing (default; pass ``--no-rebase`` to load at the original 2024 timestamps):
  - the latest fixture sample maps to ``now``; every record shifts by the same
    delta, preserving the flare -> CME -> storm spacing so the chain rule fires;
  - the solar-wind plasma feed is truncated a few minutes short of ``now`` to
    simulate a DSCOVR dropout during the storm, so telemetry-loss fires too.

Replayed events are tagged ``["replay", "gannon-2024"]`` so they are easy to
spot or filter out in Kibana. Each rebased run injects a fresh storm at the
current time (deterministic ids within a run; new ids across runs).

Usage:
  python scripts/replay.py                 # inject a live G5 storm at now
  python scripts/replay.py --no-rebase     # load the historical storm as-is
  python -m detector --once                # then evaluate — all six rules fire
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))  # allow `python scripts/replay.py` to import collector/

from collector.es_writer import index_events, make_client  # noqa: E402
from collector.feeds import (  # noqa: E402
    donki_cme,
    donki_flr,
    donki_gst,
    kp_index,
    mag,
    noaa_scales,
    plasma,
    protons,
    xray,
)
from collector.schema import NormalizedEvent, doc_id  # noqa: E402

FIXTURES = REPO_ROOT / "replay"

# The five SWPC realtime feeds drive the rebase anchor (their latest sample is
# the storm peak) and the telemetry-loss check.
REALTIME = (
    (kp_index, "kp_index.json"),
    (xray, "xray.json"),
    (protons, "protons.json"),
    (mag, "mag.json"),
    (plasma, "plasma.json"),
    (noaa_scales, "noaa_scales.json"),  # current G/R/S scales -> SOC Overview tiles
)
# The DONKI catalog events feed the flare -> CME -> storm chain rule; they keep
# their (days-apart) spacing relative to the realtime peak.
DONKI = (
    (donki_flr, "donki_flr.json"),
    (donki_cme, "donki_cme.json"),
    (donki_gst, "donki_gst.json"),
)

# Hold the plasma feed this far short of `now` so telemetry-loss (silent > 10x a
# 1-min cadence) fires for it — a realistic storm-time solar-wind dropout.
PLASMA_GAP = timedelta(minutes=18)
TAGS = ["replay", "gannon-2024"]


def load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _load(module, filename: str) -> list[NormalizedEvent]:
    raw = json.loads((FIXTURES / filename).read_text())
    return module.normalize(raw)


def build_events(now: datetime, *, rebase: bool = True) -> list[NormalizedEvent]:
    """Normalize the storm fixtures and (by default) rebase their timestamps to
    ``now``. Pure — no Elasticsearch — so the replay is unit-testable."""
    realtime, other = [], []
    for module, filename in REALTIME:
        for ev in _load(module, filename):
            realtime.append((module, ev, _parse(ev.doc["@timestamp"])))
    for module, filename in DONKI:
        for ev in _load(module, filename):
            other.append((module, ev, _parse(ev.doc["@timestamp"])))

    anchor = max(ts for _, _, ts in realtime)  # storm peak -> now
    delta = (now - anchor) if rebase else timedelta(0)

    events: list[NormalizedEvent] = []
    for module, ev, ts in [*realtime, *other]:
        new_ts = ts + delta
        if rebase and module is plasma and new_ts > now - PLASMA_GAP:
            continue  # truncate the plasma tail -> telemetry-loss fires for it
        stamp = new_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        doc = dict(ev.doc)
        doc["@timestamp"] = stamp
        doc["tags"] = TAGS
        new_id = doc_id("replay", ev.id, stamp) if rebase else ev.id
        events.append(NormalizedEvent(id=new_id, doc=doc))
    return events


def _summary(events: list[NormalizedEvent]) -> str:
    by_ds: dict[str, int] = {}
    for ev in events:
        ds = ev.doc["event"]["dataset"]
        by_ds[ds] = by_ds.get(ds, 0) + 1
    stamps = sorted(ev.doc["@timestamp"] for ev in events)
    lines = [f"  {ds:28} {n}" for ds, n in sorted(by_ds.items())]
    return f"window {stamps[0]} .. {stamps[-1]}\n" + "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="replay", description="Replay the Gannon G5 storm.")
    parser.add_argument(
        "--no-rebase",
        action="store_true",
        help="keep the original 2024 timestamps (historical load; rules won't fire)",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    es_url = os.environ.get("ES_URL", "http://localhost:9200")
    password = os.environ.get("ELASTIC_PASSWORD")
    if not password:
        print("ELASTIC_PASSWORD is not set (env or .env)", file=sys.stderr)
        return 1

    now = datetime.now(UTC)
    events = build_events(now, rebase=not args.no_rebase)
    mode = "rebased to now" if not args.no_rebase else "historical"
    print(f"Replaying {len(events)} storm events ({mode}):")
    print(_summary(events))

    client = make_client(es_url, password)
    created, skipped = index_events(client, events)
    print(f"Indexed: created={created} skipped(duplicate)={skipped}")
    if not args.no_rebase:
        print("Storm is live. Run `python -m detector --once` to fire all six rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
