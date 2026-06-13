"""Glue one evaluation cycle together: fetch → evaluate → upsert → notify."""

from __future__ import annotations

from datetime import datetime, timedelta

from elasticsearch import Elasticsearch

from detector.engine import bucket_start, evaluate, iso_z
from detector.es_gateway import fetch_events, upsert_alert
from detector.notifier import Notifier
from detector.rules import Rule


def run_cycle(
    es: Elasticsearch,
    rules: list[Rule],
    now: datetime,
    notifier: Notifier,
) -> int:
    """Evaluate every rule once. Returns the number of new/escalated alerts."""
    fired = 0
    for rule in rules:
        # Threshold rules evaluate the current (aligned) throttle bucket; correlation
        # and health rules need a rolling look-back to see across time and feeds.
        if rule.type == "threshold":
            start = bucket_start(now, rule.throttle_s)
        else:
            start = now - timedelta(seconds=rule.lookback_s)
        events = fetch_events(es, rule.datasets, iso_z(start), iso_z(now))
        for alert_id, alert in evaluate(rule, events, now):
            is_new, prior_severity = upsert_alert(es, alert_id, alert)
            severity = alert["event"]["severity"]
            if is_new:
                notifier.notify("new", alert)
                fired += 1
            elif prior_severity is not None and severity > prior_severity:
                notifier.notify("escalated", alert)
                fired += 1
    return fired
