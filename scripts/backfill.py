#!/usr/bin/env python3
"""One-time historical backfill: SWPC 7-day product windows + a long DONKI lookback.

The live collector only polls short recent windows (6-hour / 1-day) to keep each
poll light, so a fresh stack has little history and the dashboards look bare. This
fills them with real data:

  - SWPC: the ``*-7-day`` product variants of the X-ray, proton, and solar-wind
    feeds — identical JSON shapes to the live feeds, so the collector normalizers
    parse them unchanged (a week of real metrics).
  - DONKI: a long look-back over the flare/CME/storm/SEP catalogs (months of real
    events) — fills the Solar Activity dashboard and can even fire the chain rule
    on a real historical flare -> CME -> storm.

Reuses the collector normalizers and the idempotent bulk indexer, so re-running is
safe: records that overlap what the collector already wrote 409-skip.

Usage:
  python scripts/backfill.py                 # SWPC 7-day + DONKI 90 days
  python scripts/backfill.py --donki-days 30
  python scripts/backfill.py --no-swpc       # DONKI catalog only
  python scripts/backfill.py --no-donki      # SWPC metrics only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))  # allow `python scripts/backfill.py` to import collector/

from collector.es_writer import index_events, make_client  # noqa: E402
from collector.feeds import (  # noqa: E402
    donki_cme,
    donki_flr,
    donki_gst,
    donki_sep,
    mag,
    plasma,
    protons,
    xray,
)
from collector.schema import SWPC_BASE  # noqa: E402

# SWPC long-window variants — same JSON shapes as the live feeds (verified), so the
# existing normalizers parse them unchanged. (No Kp: the planetary_k_index_1m feed
# is recent-only and has no 7-day variant.)
SWPC_7DAY = (
    (xray, f"{SWPC_BASE}/json/goes/primary/xrays-7-day.json"),
    (protons, f"{SWPC_BASE}/json/goes/primary/integral-protons-7-day.json"),
    (mag, f"{SWPC_BASE}/products/solar-wind/mag-7-day.json"),
    (plasma, f"{SWPC_BASE}/products/solar-wind/plasma-7-day.json"),
)
DONKI = (donki_flr, donki_cme, donki_gst, donki_sep)


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


def _fetch_json(url: str):
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    # Some SWPC payloads carry trailing NUL padding; strip it before parsing.
    return json.loads(resp.text.replace("\x00", "").strip())


def backfill_swpc(client) -> None:
    print("SWPC 7-day backfill:")
    for module, url in SWPC_7DAY:
        events = module.normalize(_fetch_json(url))
        created, skipped = index_events(client, events)
        src = url.rsplit("/", 1)[-1]
        print(f"  {module.DATASET:26} created={created:5} skipped={skipped:6} ({src})")


def backfill_donki(client, days: int) -> None:
    print(f"DONKI backfill (last {days} days):")
    os.environ["DONKI_LOOKBACK_DAYS"] = str(days)
    session = requests.Session()
    for module in DONKI:
        events = module.normalize(module.fetch(session))
        created, skipped = index_events(client, events)
        print(f"  {module.DATASET:26} created={created:5} skipped={skipped:6}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backfill", description="Backfill historical data.")
    parser.add_argument(
        "--donki-days", type=int, default=90, help="DONKI look-back window in days (default 90)"
    )
    parser.add_argument("--no-swpc", action="store_true", help="skip the SWPC 7-day backfill")
    parser.add_argument("--no-donki", action="store_true", help="skip the DONKI backfill")
    args = parser.parse_args(argv)

    load_dotenv()
    es_url = os.environ.get("ES_URL", "http://localhost:9200")
    password = os.environ.get("ELASTIC_PASSWORD")
    if not password:
        print("ELASTIC_PASSWORD is not set (env or .env)", file=sys.stderr)
        return 1

    client = make_client(es_url, password)
    if not args.no_swpc:
        backfill_swpc(client)
    if not args.no_donki:
        backfill_donki(client, args.donki_days)
    print("Backfill complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
