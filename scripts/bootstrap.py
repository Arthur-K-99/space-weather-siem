#!/usr/bin/env python3
"""Bootstrap Elasticsearch + Kibana for the space-weather SIEM.

Applies, idempotently (PUT/import overwrites with the repo version):
  1. ILM policy        space-weather-events   (elastic/ilm-policy-events.json)
  2. Index template    space-weather-events   (elastic/template-events.json, data stream)
  3. Index template    space-weather-alerts   (elastic/template-alerts.json)
  4. Creates the space-weather-alerts index if it does not exist yet
  5. Imports the Kibana dashboards (kibana/dashboards.ndjson) — data views + the
     four saved dashboards — via the saved-objects API (overwrite=true)

Stdlib only — no pip install needed. Reads ES_URL, ELASTIC_PASSWORD, and
KIBANA_URL from the environment, falling back to the repo's .env file. The Kibana
step is skipped with a warning if Kibana is unreachable (so the ES bootstrap
still works in Elasticsearch-only contexts).

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
KIBANA_DIR = REPO_ROOT / "kibana"

ES_WAIT_TIMEOUT_S = 120
KIBANA_WAIT_TIMEOUT_S = 180


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


def wait_for_kibana(kb_url: str, auth: tuple[str, str]) -> bool:
    """Poll Kibana until it reports available. Returns False if it never comes up."""
    deadline = time.monotonic() + KIBANA_WAIT_TIMEOUT_S
    while True:
        try:
            status, body = request("GET", f"{kb_url}/api/status", auth)
            level = body.get("status", {}).get("overall", {}).get("level")
            if status == 200 and level in (None, "available"):
                print(f"Kibana is up ({kb_url})")
                return True
        except OSError:
            pass
        if time.monotonic() > deadline:
            return False
        print(f"Waiting for Kibana at {kb_url} ...")
        time.sleep(3)


def import_dashboards(kb_url: str, auth: tuple[str, str], ndjson: Path) -> None:
    """Upload kibana/dashboards.ndjson to the saved-objects _import API."""
    boundary = "----swsBootstrapBoundary7f3a9c1e"
    payload = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="dashboards.ndjson"\r\n'
        "Content-Type: application/ndjson\r\n\r\n"
    ).encode() + ndjson.read_bytes() + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{kb_url}/api/saved_objects/_import?overwrite=true", method="POST", data=payload
    )
    token = b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("kbn-xsrf", "true")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"FAILED dashboard import: HTTP {e.code}\n{e.read().decode(errors='replace')}")

    if not body.get("success"):
        errors = json.dumps(body.get("errors"), indent=2)
        sys.exit(f"FAILED dashboard import:\n{errors}")
    print(f"  ok: imported {body.get('successCount')} Kibana saved objects")


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

    # Kibana dashboards. Skipped (non-fatal) if Kibana is unreachable, so the ES
    # bootstrap still works in Elasticsearch-only setups.
    ndjson = KIBANA_DIR / "dashboards.ndjson"
    kb_url = os.environ.get("KIBANA_URL", "http://localhost:5601").rstrip("/")
    if not ndjson.is_file():
        print(f"Skipping Kibana import: {ndjson} not found")
    else:
        print(f"Importing Kibana dashboards into {kb_url}:")
        if wait_for_kibana(kb_url, auth):
            import_dashboards(kb_url, auth, ndjson)
        else:
            print(f"  WARNING: Kibana not reachable at {kb_url} after "
                  f"{KIBANA_WAIT_TIMEOUT_S}s — skipped dashboard import")

    print("Bootstrap complete.")


if __name__ == "__main__":
    main()
