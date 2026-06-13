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
    assert geo.dataset == "swpc.planetary_k_index"
    assert geo.field == "metrics.kp_index"
    assert geo.threshold == 5
    assert geo.throttle_s == 3600

    # 1.0e-5 must parse as a float, not a string
    assert by_id["radio_blackout"].threshold == pytest.approx(1e-5)


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
