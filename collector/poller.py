"""Poll loop: for each feed, fetch → normalize → bulk-index, then sleep."""

from __future__ import annotations

import logging
import time

import requests
from elasticsearch import Elasticsearch

from collector import feeds
from collector.es_writer import index_events

log = logging.getLogger("collector")


def run_once(client: Elasticsearch, session: requests.Session) -> tuple[int, int]:
    """Poll every feed once. Returns total (created, skipped) across feeds.

    A failure on one feed is logged and does not stop the others — the same
    fault isolation a real log collector needs.
    """
    total_created = 0
    total_skipped = 0
    for feed in feeds.ALL:
        try:
            records = feed.fetch(session)
            events = feed.normalize(records)
            created, skipped = index_events(client, events)
        except Exception:
            log.exception("feed %s failed", feed.FEED)
            continue
        total_created += created
        total_skipped += skipped
        log.info(
            "feed=%s fetched=%d created=%d skipped=%d",
            feed.FEED,
            len(records),
            created,
            skipped,
        )
    return total_created, total_skipped


def run_forever(client: Elasticsearch, session: requests.Session, interval: int) -> None:
    log.info("collector starting; poll interval=%ds", interval)
    while True:
        run_once(client, session)
        time.sleep(interval)
