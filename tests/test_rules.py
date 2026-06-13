"""Rule loader + duration parsing tests, including the shipped rules/ files."""

from pathlib import Path

import pytest

from detector.rules import Rule, load_rules, parse_duration

RULES_DIR = Path(__file__).parent.parent / "rules"


@pytest.mark.parametrize(
    "text,seconds",
    [("30s", 30), ("15m", 900), ("1h", 3600), ("2d", 172800), (45, 45)],
)
def test_parse_duration(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("bad", ["", "5", "1hour", "h", "-3m"])
def test_parse_duration_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)


def test_load_shipped_rules():
    rules = load_rules(RULES_DIR)
    by_id = {r.id: r for r in rules}
    # the three M4 threshold rules
    assert {"geomagnetic_storm", "radio_blackout", "radiation_storm"} <= set(by_id)

    geo = by_id["geomagnetic_storm"]
    assert isinstance(geo, Rule)
    assert geo.type == "threshold"  # default when unset
    cond = geo.conditions[0]
    assert cond.dataset == "swpc.planetary_k_index"
    assert cond.field == "metrics.kp_index"
    assert cond.threshold == 5
    assert geo.throttle_s == 3600
    assert geo.datasets == ("swpc.planetary_k_index",)

    # 1.0e-5 must parse as a float, not a string
    assert by_id["radio_blackout"].conditions[0].threshold == pytest.approx(1e-5)


def test_load_precursor_rule():
    by_id = {r.id: r for r in load_rules(RULES_DIR)}
    rule = by_id["storm_precursor"]
    assert rule.type == "precursor"
    assert rule.severity == 3
    assert rule.lookback_s == 3600  # the 1h window
    assert {c.dataset for c in rule.conditions} == {
        "swpc.solar_wind_mag",
        "swpc.solar_wind_plasma",
    }
    bz = next(c for c in rule.conditions if c.field == "metrics.bz_gsm")
    assert bz.op == "<=" and bz.threshold == -10 and bz.sustain_s == 1800


def test_load_chain_rule():
    by_id = {r.id: r for r in load_rules(RULES_DIR)}
    rule = by_id["solar_storm_chain"]
    assert rule.type == "chain"
    assert rule.severity == 4
    assert rule.lookback_s == parse_duration("4d")  # explicit override
    assert rule.datasets == ("donki.flr", "donki.cme", "donki.gst")
    flare, cme, storm = rule.conditions
    assert flare.min_severity == 1 and flare.within_s is None
    assert cme.within_s == parse_duration("6h")
    assert storm.field == "metrics.kp_index" and storm.within_s == parse_duration("3d")


def test_load_telemetry_rule():
    by_id = {r.id: r for r in load_rules(RULES_DIR)}
    rule = by_id["telemetry_loss"]
    assert rule.type == "telemetry_loss"
    assert rule.severity == 2
    assert len(rule.monitors) == 4
    mon = rule.monitors[0]
    assert mon.cadence_s == 60 and mon.multiplier == 10
    # look-back is a few x the largest silence threshold so a healthy feed's last
    # doc is in-window for an exact silence reading
    assert rule.lookback_s == 60 * 10 * 3


def test_non_threshold_requires_severity(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "id: x\nname: X\ncategory: c\nscale: G\ntype: precursor\nwindow: 1h\n"
        "conditions: [{dataset: d, field: f, op: '>=', threshold: 1}]\nthrottle: 1h\n"
    )
    with pytest.raises(ValueError, match="requires an explicit severity"):
        load_rules(tmp_path)


def test_unknown_type_rejected(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "id: x\nname: X\ncategory: c\nscale: G\ntype: bogus\nthrottle: 1h\n"
    )
    with pytest.raises(ValueError, match="unknown type"):
        load_rules(tmp_path)


def test_load_rules_empty_dir(tmp_path):
    with pytest.raises(ValueError, match="no rules"):
        load_rules(tmp_path)


def test_load_rules_rejects_bad_op(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "id: x\nname: X\ncategory: c\nscale: G\n"
        "query: {dataset: d, field: f, op: '~=', threshold: 1}\nthrottle: 1h\n"
    )
    with pytest.raises(ValueError, match="invalid op"):
        load_rules(tmp_path)
