"""Bulk-index normalized events into the space-weather-events data stream.

Idempotency: every action is an ``op_type=create`` keyed by the event's
deterministic ``_id``. Re-ingesting an already-stored record returns HTTP 409
(version conflict), which we count as a skip rather than an error — so re-running
the collector never duplicates events.
"""

from __future__ import annotations

from collections.abc import Iterable

from elasticsearch import Elasticsearch, helpers

from collector.schema import NormalizedEvent

INDEX = "space-weather-events"


def make_client(es_url: str, password: str, *, user: str = "elastic") -> Elasticsearch:
    return Elasticsearch(es_url, basic_auth=(user, password), request_timeout=30)


def index_events(
    client: Elasticsearch,
    events: Iterable[NormalizedEvent],
    *,
    index: str = INDEX,
) -> tuple[int, int]:
    """Bulk-create events. Returns (created, skipped_duplicates).

    Raises on any failure that is not a 409 version conflict.
    """
    actions = (
        {"_op_type": "create", "_index": index, "_id": e.id, **e.doc} for e in events
    )
    created = 0
    skipped = 0
    for ok, info in helpers.streaming_bulk(
        client, actions, raise_on_error=False, raise_on_exception=False
    ):
        if ok:
            created += 1
            continue
        result = info.get("create", {})
        if result.get("status") == 409:
            skipped += 1
        else:
            raise RuntimeError(f"bulk index error: {result.get('error', info)}")
    return created, skipped
