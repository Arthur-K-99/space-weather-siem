"""Elasticsearch I/O for the detector: read events, upsert alerts.

Kept thin so the evaluation logic in engine.py stays pure. Alerts are written to
a plain index (not a data stream) by deterministic ``_id``, so re-evaluating a
throttle bucket overwrites in place rather than duplicating.
"""

from __future__ import annotations

from elasticsearch import Elasticsearch, NotFoundError

from detector.rules import Rule

EVENTS_INDEX = "space-weather-events"
ALERTS_INDEX = "space-weather-alerts"


def make_client(url: str, password: str, *, user: str = "elastic") -> Elasticsearch:
    return Elasticsearch(url, basic_auth=(user, password), request_timeout=30)


def fetch_events(es: Elasticsearch, rule: Rule, start_iso: str, end_iso: str) -> list[dict]:
    """Events of the rule's dataset in [start, end]. Threshold is applied in engine."""
    try:
        resp = es.search(
            index=EVENTS_INDEX,
            size=10000,
            query={
                "bool": {
                    "filter": [
                        {"range": {"@timestamp": {"gte": start_iso, "lte": end_iso}}},
                        {"term": {"event.dataset": rule.dataset}},
                    ]
                }
            },
        )
    except NotFoundError:  # events data stream not created yet
        return []
    return [hit["_source"] for hit in resp["hits"]["hits"]]


def upsert_alert(es: Elasticsearch, alert_id: str, alert: dict) -> tuple[bool, int | None]:
    """Write the alert by id (overwrite). Returns (is_new, prior_severity)."""
    is_new = True
    prior_severity = None
    try:
        prior = es.get(index=ALERTS_INDEX, id=alert_id)
        is_new = False
        prior_severity = prior["_source"].get("event", {}).get("severity")
    except NotFoundError:
        pass
    es.index(index=ALERTS_INDEX, id=alert_id, document=alert)
    return is_new, prior_severity
