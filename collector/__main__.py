"""Collector entry point: ``python -m collector [--once]``.

Reads ES_URL, ELASTIC_PASSWORD, and POLL_INTERVAL_REALTIME from the environment
(docker-compose injects them; locally, ``source .env`` first).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import requests

from collector.es_writer import make_client
from collector.poller import run_forever, run_once


def load_dotenv() -> None:
    """Load repo-root .env into the environment (no-op in containers).

    Real env vars win, so docker-compose injection is never overridden.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collector")
    parser.add_argument(
        "--once",
        action="store_true",
        help="poll each feed a single time and exit (default: loop forever)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    load_dotenv()
    es_url = os.environ.get("ES_URL", "http://localhost:9200")
    password = os.environ.get("ELASTIC_PASSWORD")
    if not password:
        print("ELASTIC_PASSWORD is not set (env or .env)", file=sys.stderr)
        return 1
    interval = int(os.environ.get("POLL_INTERVAL_REALTIME", "60"))

    client = make_client(es_url, password)
    session = requests.Session()

    if args.once:
        created, skipped = run_once(client, session)
        logging.getLogger("collector").info(
            "run-once complete: created=%d skipped=%d", created, skipped
        )
    else:
        run_forever(client, session, interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
