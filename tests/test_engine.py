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


# --- M5: correlation + health rules ----------------------------------------


def mk(dataset: str, ts: str, *, severity: int = 0, metrics: dict | None = None, **extra) -> dict:
    doc = {
        "@timestamp": ts,
        "event": {"kind": "metric", "dataset": dataset, "severity": severity},
        "metrics": metrics or {},
    }
    doc.update(extra)
    return doc


def mag(bz, ts):
    return mk("swpc.solar_wind_mag", ts, metrics={"bz_gsm": bz})


def plasma(speed, ts):
    return mk("swpc.solar_wind_plasma", ts, metrics={"speed_km_s": speed})


# precursor (rule 4) --------------------------------------------------------


def test_precursor_fires_on_sustained_bz_and_fast_wind():
    rule = RULES["storm_precursor"]
    events = [
        mag(-12, "2026-06-13T21:50:00Z"),  # Bz <= -10 spanning 35 min (>= 30 min)
        mag(-14, "2026-06-13T22:05:00Z"),
        mag(-11, "2026-06-13T22:25:00Z"),
        plasma(720, "2026-06-13T22:06:00Z"),  # speed > 600
        plasma(500, "2026-06-13T22:10:00Z"),  # below, ignored
    ]
    alerts = evaluate(rule, events, NOW)
    assert len(alerts) == 1
    alert_id, doc = alerts[0]
    assert doc["event"]["severity"] == 3  # declared (solar-wind events are sev 0)
    assert doc["event"]["category"] == "solar_wind"
    assert doc["alert"]["count"] == 4  # 3 Bz + 1 speed matches
    assert doc["alert"]["first_seen"] == "2026-06-13T21:50:00Z"
    assert "precursor" in doc["message"]
    assert alert_id == doc["alert"]["fingerprint"]


def test_precursor_needs_sustained_bz():
    rule = RULES["storm_precursor"]
    events = [
        mag(-12, "2026-06-13T22:10:00Z"),  # only 15 min of southward Bz
        mag(-13, "2026-06-13T22:25:00Z"),
        plasma(720, "2026-06-13T22:06:00Z"),
    ]
    assert evaluate(rule, events, NOW) == []


def test_precursor_needs_all_conditions():
    rule = RULES["storm_precursor"]
    events = [  # Bz sustained, but the solar wind never exceeds 600 km/s
        mag(-12, "2026-06-13T21:50:00Z"),
        mag(-14, "2026-06-13T22:25:00Z"),
        plasma(450, "2026-06-13T22:06:00Z"),
    ]
    assert evaluate(rule, events, NOW) == []


# chain (rule 5) ------------------------------------------------------------


def flare(severity, ts, cls="M3.0"):
    return mk("donki.flr", ts, severity=severity, flare={"class": cls})


def cme(ts):
    return mk("donki.cme", ts)


def gst(kp, severity, ts):
    return mk("donki.gst", ts, severity=severity, metrics={"kp_index": kp})


def test_chain_links_flare_cme_storm():
    rule = RULES["solar_storm_chain"]
    events = [
        flare(3, "2026-06-10T00:00:00Z"),
        cme("2026-06-10T04:00:00Z"),  # within 6h of the flare
        gst(7, 5, "2026-06-12T00:00:00Z"),  # Kp 7, within 3d of the CME
    ]
    alerts = evaluate(rule, events, NOW)
    assert len(alerts) == 1
    alert_id, doc = alerts[0]
    assert doc["event"]["severity"] == 5  # max(floor 4, flare 3, storm 5)
    assert doc["event"]["category"] == "geomagnetic"
    assert doc["alert"]["count"] == 3  # three stages
    assert doc["alert"]["first_seen"] == "2026-06-10T00:00:00Z"  # the flare
    assert doc["alert"]["last_seen"] == "2026-06-12T00:00:00Z"  # the storm
    assert "G5" in doc["message"] and "->" in doc["message"]
    assert alert_id == doc["alert"]["fingerprint"]


def test_chain_breaks_when_cme_too_late():
    rule = RULES["solar_storm_chain"]
    events = [
        flare(3, "2026-06-10T00:00:00Z"),
        cme("2026-06-10T12:00:00Z"),  # 12h after the flare (> 6h gap)
        gst(7, 5, "2026-06-12T00:00:00Z"),
    ]
    assert evaluate(rule, events, NOW) == []


def test_chain_ignores_subthreshold_flare():
    rule = RULES["solar_storm_chain"]
    events = [
        flare(0, "2026-06-10T00:00:00Z", cls="B1.0"),  # below min_severity 1
        cme("2026-06-10T04:00:00Z"),
        gst(7, 5, "2026-06-12T00:00:00Z"),
    ]
    assert evaluate(rule, events, NOW) == []


def test_chain_one_incident_per_storm_picks_closest_flare():
    rule = RULES["solar_storm_chain"]
    events = [
        flare(2, "2026-06-10T00:00:00Z"),  # earlier qualifying flare
        flare(3, "2026-06-10T03:00:00Z"),  # closer to the CME — should be chosen
        cme("2026-06-10T04:00:00Z"),
        gst(7, 5, "2026-06-12T00:00:00Z"),
    ]
    alerts = evaluate(rule, events, NOW)
    assert len(alerts) == 1  # one composite incident, not one per flare
    assert alerts[0][1]["alert"]["first_seen"] == "2026-06-10T03:00:00Z"


# telemetry loss (rule 6) ---------------------------------------------------


def test_telemetry_fires_for_silent_feed_only():
    rule = RULES["telemetry_loss"]  # gap = 60s x10 = 10 min; look-back 30 min
    events = [
        mk("swpc.planetary_k_index", "2026-06-13T22:26:00Z"),  # 4 min ago, healthy
        mk("swpc.goes_xray", "2026-06-13T22:10:00Z"),  # 20 min ago, silent
        mk("swpc.solar_wind_mag", "2026-06-13T22:28:00Z"),  # healthy
        mk("swpc.solar_wind_plasma", "2026-06-13T22:27:00Z"),  # healthy
    ]
    alerts = evaluate(rule, events, NOW)
    assert len(alerts) == 1
    alert_id, doc = alerts[0]
    assert doc["event"]["severity"] == 2
    assert doc["event"]["category"] == "pipeline_health"
    assert "swpc.goes_xray" in doc["message"] and "silent 20m" in doc["message"]
    assert doc["alert"]["count"] == 20  # 20 min / 60s cadence
    assert doc["alert"]["last_seen"] == "2026-06-13T22:30:00Z"  # now
    # entity is the feed, so a different feed would get a distinct fingerprint
    assert alert_id == fingerprint("telemetry_loss", "swpc.goes_xray", bucket_id(NOW, 3600))


def test_telemetry_silent_when_all_feeds_healthy():
    rule = RULES["telemetry_loss"]
    events = [
        mk("swpc.planetary_k_index", "2026-06-13T22:26:00Z"),
        mk("swpc.goes_xray", "2026-06-13T22:25:00Z"),
        mk("swpc.solar_wind_mag", "2026-06-13T22:28:00Z"),
        mk("swpc.solar_wind_plasma", "2026-06-13T22:27:00Z"),
    ]
    assert evaluate(rule, events, NOW) == []


def test_telemetry_feed_absent_entirely():
    rule = RULES["telemetry_loss"]
    events = [  # three healthy feeds; planetary_k_index has no docs at all
        mk("swpc.goes_xray", "2026-06-13T22:25:00Z"),
        mk("swpc.solar_wind_mag", "2026-06-13T22:28:00Z"),
        mk("swpc.solar_wind_plasma", "2026-06-13T22:27:00Z"),
    ]
    alerts = evaluate(rule, events, NOW)
    assert len(alerts) == 1
    doc = alerts[0][1]
    assert "swpc.planetary_k_index" in doc["message"]
    assert "no docs in last 30m" in doc["message"]
    assert doc["alert"]["first_seen"] == "2026-06-13T22:00:00Z"  # window start
