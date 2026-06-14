"""Replay builds a storm that fires all six rules — verified ES-free.

``build_events`` is pure (no Elasticsearch), so we can normalize the committed
fixtures, then feed the rebased events straight into the detector engine and
assert every rule fires. This is the end-to-end guarantee behind the demo claim
"run replay and all six rules light up".
"""

from datetime import UTC, datetime
from pathlib import Path

from detector.engine import evaluate
from detector.rules import load_rules
from scripts.replay import build_events

RULES = {r.id: r for r in load_rules(Path(__file__).parent.parent / "rules")}
NOW = datetime(2026, 6, 13, 22, 30, 0, tzinfo=UTC)

ALL_RULES = [
    "geomagnetic_storm",
    "radio_blackout",
    "radiation_storm",
    "storm_precursor",
    "solar_storm_chain",
    "telemetry_loss",
]


def _docs() -> list[dict]:
    return [e.doc for e in build_events(NOW)]


def test_replay_covers_every_dataset():
    datasets = {d["event"]["dataset"] for d in _docs()}
    assert {
        "swpc.planetary_k_index",
        "swpc.goes_xray",
        "swpc.goes_protons",
        "swpc.solar_wind_mag",
        "swpc.solar_wind_plasma",
        "donki.flr",
        "donki.cme",
        "donki.gst",
    } <= datasets


def test_replay_rebases_peak_to_now():
    # the latest realtime sample is mapped exactly to `now`
    assert max(d["@timestamp"] for d in _docs()) == "2026-06-13T22:30:00Z"


def test_replay_tags_events():
    assert all(d.get("tags") == ["replay", "gannon-2024"] for d in _docs())


def test_replay_truncates_plasma_for_telemetry_loss():
    plasma = "swpc.solar_wind_plasma"
    plasma_ts = sorted(d["@timestamp"] for d in _docs() if d["event"]["dataset"] == plasma)
    # plasma stops short of now (>= 18 min gap) while other feeds reach now
    assert plasma_ts[-1] <= "2026-06-13T22:12:00Z"


def test_replay_fires_all_six_rules():
    docs = _docs()
    for rule_id in ALL_RULES:
        alerts = evaluate(RULES[rule_id], docs, NOW)
        assert alerts, f"{rule_id} did not fire on the replayed storm"


def test_replay_telemetry_loss_is_the_plasma_feed():
    alerts = evaluate(RULES["telemetry_loss"], _docs(), NOW)
    feeds = [a[1]["message"] for a in alerts]
    assert any("swpc.solar_wind_plasma" in m for m in feeds)
    # the other monitored feeds reach now, so plasma is the only silent one
    assert len(alerts) == 1


def test_replay_chain_is_g5():
    alerts = evaluate(RULES["solar_storm_chain"], _docs(), NOW)
    assert len(alerts) == 1
    assert alerts[0][1]["event"]["severity"] == 5  # peak Kp 9 -> G5
