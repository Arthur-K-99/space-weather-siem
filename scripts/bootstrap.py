#!/usr/bin/env python3
"""Bootstrap Elasticsearch for the space-weather SIEM.

Applies, idempotently (PUT overwrites with the repo version):
  1. ILM policy        space-weather-events   (elastic/ilm-policy-events.json)
  2. Index template    space-weather-events   (elastic/template-events.json, data stream)
  3. Index template    space-weather-alerts   (elastic/template-alerts.json)
  4. Creates the space-weather-alerts index if it does not exist yet

Kibana saved-object import (dashboards) is added in M6.

Stdlib only — no pip install needed. Reads ES_URL and ELASTIC_PASSWORD from
the environment, falling back to the repo's .env file.

Usage: python scripts/bootstrap.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from base64 import b64encode
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ELASTIC_DIR = REPO_ROOT / "elastic"

ES_WAIT_TIMEOUT_S = 120


def load_dotenv(path: Path) -> None:
    """Set KEY=VALUE pairs from a .env file, without overriding real env vars."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def request(
    method: str,
    url: str,
    auth: tuple[str, str],
    body: dict | None = None,
) -> tuple[int, dict]:
    """Send one HTTP request; return (status, parsed JSON body)."""
    req = urllib.request.Request(url, method=method)
    token = b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def wait_for_es(es_url: str, auth: tuple[str, str]) -> None:
    deadline = time.monotonic() + ES_WAIT_TIMEOUT_S
    while True:
        try:
            status, body = request("GET", f"{es_url}/_cluster/health", auth)
            if status == 200:
                print(f"Elasticsearch is up (cluster status: {body.get('status')})")
                return
            if status == 401:
                sys.exit("Authentication failed — check ELASTIC_PASSWORD")
        except OSError:
            status = None
        if time.monotonic() > deadline:
            sys.exit(f"Elasticsearch not reachable at {es_url} after {ES_WAIT_TIMEOUT_S}s")
        print(f"Waiting for Elasticsearch at {es_url} ...")
        time.sleep(3)


def put(name: str, url: str, auth: tuple[str, str], body: dict) -> None:
    status, resp = request("PUT", url, auth, body)
    if status not in (200, 201):
        sys.exit(f"FAILED {name}: HTTP {status}\n{json.dumps(resp, indent=2)}")
    print(f"  ok: {name}")


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    es_url = os.environ.get("ES_URL", "http://localhost:9200").rstrip("/")
    password = os.environ.get("ELASTIC_PASSWORD")
    if not password:
        sys.exit("ELASTIC_PASSWORD is not set (env or .env)")
    auth = ("elastic", password)

    wait_for_es(es_url, auth)

    def load(filename: str) -> dict:
        return json.loads((ELASTIC_DIR / filename).read_text())

    print("Applying ILM policy and index templates:")
    put(
        "ILM policy space-weather-events",
        f"{es_url}/_ilm/policy/space-weather-events",
        auth,
        load("ilm-policy-events.json"),
    )
    put(
        "index template space-weather-events",
        f"{es_url}/_index_template/space-weather-events",
        auth,
        load("template-events.json"),
    )
    put(
        "index template space-weather-alerts",
        f"{es_url}/_index_template/space-weather-alerts",
        auth,
        load("template-alerts.json"),
    )

    # The events data stream is auto-created on first collector write; the
    # alerts index is created here so dashboards work before any alert fires.
    status, _ = request("HEAD", f"{es_url}/space-weather-alerts", auth)
    if status == 200:
        print("  ok: index space-weather-alerts (already exists)")
    else:
        put("index space-weather-alerts", f"{es_url}/space-weather-alerts", auth, {})

    print("Bootstrap complete.")


if __name__ == "__main__":
    main()
