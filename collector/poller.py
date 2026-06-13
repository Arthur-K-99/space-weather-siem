"""Poll loop with per-feed cadence: fetch → normalize → bulk-index.

``run_once`` polls every feed a single time (used by ``--once`` and tests).
``run_forever`` schedules each feed on its own interval (config.interval_for),
so the 1-min feeds, the 5-min feeds, and the 15-min DONKI catalog each poll at
their own rate instead of all hammering every cycle.
"""

from __future__ import annotations

import logging
import time

import requests
from elasticsearch import Elasticsearch

from collector import feeds
from collector.config import interval_for
from collector.es_writer import index_events

log = logging.getLogger("collector")


def poll_feed(client: Elasticsearch, session: requests.Session, feed) -> tuple[int, int]:
    records = feed.fetch(session)
    events = feed.normalize(records)
    created, skipped = index_events(client, events)
    fetched = len(records) if hasattr(records, "__len__") else 0
    log.info(
        "feed=%s fetched=%d created=%d skipped=%d",
        feed.FEED,
        fetched,
        created,
        skipped,
    )
    return created, skipped


def run_once(client: Elasticsearch, session: requests.Session) -> tuple[int, int]:
    """Poll every feed once. A feed failure is logged and does not stop the rest."""
    total_created = 0
    total_skipped = 0
    for feed in feeds.ALL:
        try:
            created, skipped = poll_feed(client, session, feed)
        except Exception:
            log.exception("feed %s failed", feed.FEED)
            continue
        total_created += created
        total_skipped += skipped
    return total_created, total_skipped


def run_forever(client: Elasticsearch, session: requests.Session) -> None:
    intervals = {feed.FEED: interval_for(feed) for feed in feeds.ALL}
    next_due = {feed.FEED: 0.0 for feed in feeds.ALL}  # all due immediately on start
    log.info("collector starting; intervals(s)=%s", intervals)
    while True:
        now = time.monotonic()
        for feed in feeds.ALL:
            if now < next_due[feed.FEED]:
                continue
            try:
                poll_feed(client, session, feed)
            except Exception:
                log.exception("feed %s failed", feed.FEED)
            next_due[feed.FEED] = time.monotonic() + intervals[feed.FEED]
        time.sleep(max(1.0, min(next_due.values()) - time.monotonic()))
