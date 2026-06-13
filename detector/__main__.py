"""Detector entry point: ``python -m detector [--once]``.

Loads rules from RULES_DIR (default: repo ``rules/``), then evaluates them every
DETECTOR_INTERVAL seconds. Reads ES_URL, ELASTIC_PASSWORD from env (or repo .env).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from detector.es_gateway import make_client
from detector.notifier import LogNotifier
from detector.rules import load_rules
from detector.runner import run_cycle

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv() -> None:
    """Load repo-root .env into the environment (no-op in containers)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="detector")
    parser.add_argument(
        "--once",
        action="store_true",
        help="evaluate every rule a single time and exit (default: loop forever)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("detector")

    load_dotenv()
    es_url = os.environ.get("ES_URL", "http://localhost:9200")
    password = os.environ.get("ELASTIC_PASSWORD")
    if not password:
        print("ELASTIC_PASSWORD is not set (env or .env)", file=sys.stderr)
        return 1
    interval = int(os.environ.get("DETECTOR_INTERVAL", "60"))
    rules_dir = os.environ.get("RULES_DIR", str(REPO_ROOT / "rules"))

    rules = load_rules(rules_dir)
    es = make_client(es_url, password)
    notifier = LogNotifier()
    log.info("detector loaded %d rules: %s", len(rules), [r.id for r in rules])

    if args.once:
        fired = run_cycle(es, rules, datetime.now(UTC), notifier)
        log.info("run-once complete: %d new/escalated alerts", fired)
        return 0

    log.info("detector starting; evaluation interval=%ds", interval)
    while True:
        run_cycle(es, rules, datetime.now(UTC), notifier)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
