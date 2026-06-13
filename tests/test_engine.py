"""Engine evaluation against synthetic event sets (the core M4 deliverable)."""

from datetime import UTC, datetime
from pathlib import Path

from detector.engine import bucket_id, evaluate, fingerprint
from detector.rules import load_rules

RULES = {r.id: r for r in load_rules(Path(__file__).parent.parent / "rules")}
NOW = datetime(2026, 6, 13, 22, 30, 0, tzinfo=UTC)


def ev(dataset: str, field_path: str, value, severity: int, ts: str) -> dict:
    metric = field_path.rsplit(".", 1)[-1]
    return {
        "@timestamp": ts,
        "event": {"kind": "metric", "dataset": dataset, "severity": severity},
        "metrics": {metric: value},
    }


def kp(value, severity, ts):
    return ev("swpc.planetary_k_index", "metrics.kp_index", value, severity, ts)


# --- firing + aggregation --------------------------------------------------


def test_geomagnetic_fires_and_aggregates():
    rule = RULES["geomagnetic_storm"]
    events = [
        kp(4, 0, "2026-06-13T22:01:00Z"),  # below threshold, ignored
        kp(5, 1, "2026-06-13T22:05:00Z"),
        kp(6, 2, "2026-06-13T22:20:00Z"),
    ]
    alerts = evaluate(rule, events, NOW)
    assert len(alerts) == 1
    alert_id, doc = alerts[0]

    assert doc["event"]["severity"] == 2  # max of the matching events
    assert doc["event"]["category"] == "geomagnetic"
    assert doc["event"]["kind"] == "alert"
    assert doc["alert"]["count"] == 2  # the kp 5 and kp 6 readings
    assert doc["alert"]["first_seen"] == "2026-06-13T22:05:00Z"
    assert doc["alert"]["last_seen"] == "2026-06-13T22:20:00Z"
    assert doc["rule"]["id"] == "geomagnetic_storm"
    assert "G2" in doc["message"]
    assert alert_id == doc["alert"]["fingerprint"]


def test_no_alert_below_threshold():
    rule = RULES["geomagnetic_storm"]
    events = [kp(2, 0, "2026-06-13T22:01:00Z"), kp(4, 0, "2026-06-13T22:10:00Z")]
    assert evaluate(rule, events, NOW) == []


def test_other_datasets_ignored():
    rule = RULES["geomagnetic_storm"]
    events = [
        ev("swpc.goes_xray", "metrics.xray_flux", 1e-3, 4, "2026-06-13T22:05:00Z"),
        kp(7, 3, "2026-06-13T22:06:00Z"),
    ]
    alerts = evaluate(rule, events, NOW)
    assert len(alerts) == 1
    assert alerts[0][1]["alert"]["count"] == 1  # only the Kp event counted


def test_radio_blackout_fires_on_xray():
    rule = RULES["radio_blackout"]
    events = [
        ev("swpc.goes_xray", "metrics.xray_flux", 2e-6, 0, "2026-06-13T22:02:00Z"),  # C, sub-R1
        ev("swpc.goes_xray", "metrics.xray_flux", 1.2e-4, 3, "2026-06-13T22:09:00Z"),  # X1, R3
    ]
    alerts = evaluate(rule, events, NOW)
    assert len(alerts) == 1
    doc = alerts[0][1]
    assert doc["event"]["severity"] == 3
    assert doc["event"]["category"] == "radio_blackout"
    assert "R3" in doc["message"]


def test_radiation_storm_fires_on_protons():
    rule = RULES["radiation_storm"]
    events = [
        ev("swpc.goes_protons", "metrics.proton_flux_10mev", 5, 0, "2026-06-13T22:03:00Z"),
        ev("swpc.goes_protons", "metrics.proton_flux_10mev", 150, 2, "2026-06-13T22:08:00Z"),
    ]
    alerts = evaluate(rule, events, NOW)
    doc = alerts[0][1]
    assert doc["event"]["severity"] == 2
    assert "S2" in doc["message"]


# --- dedup / throttle fingerprint ------------------------------------------


def test_fingerprint_stable_within_bucket_changes_across():
    rule = RULES["geomagnetic_storm"]
    events = [kp(6, 2, "2026-06-13T22:05:00Z")]
    id_now = evaluate(rule, events, NOW)[0][0]
    # same throttle bucket (1h) -> same id (dedup/throttle: update in place)
    later_same_bucket = datetime(2026, 6, 13, 22, 59, 0, tzinfo=UTC)
    assert evaluate(rule, events, later_same_bucket)[0][0] == id_now
    # next hour -> new bucket -> new id (re-alert)
    next_bucket = datetime(2026, 6, 13, 23, 30, 0, tzinfo=UTC)
    assert evaluate(rule, events, next_bucket)[0][0] != id_now


def test_fingerprint_differs_by_rule():
    bucket = bucket_id(NOW, 3600)
    assert fingerprint("geomagnetic_storm", "global", bucket) != fingerprint(
        "radio_blackout", "global", bucket
    )
