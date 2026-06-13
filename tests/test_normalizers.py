"""Normalizer tests against recorded SWPC fixtures + severity-ladder unit tests.

The fixtures in tests/fixtures/ are real slices captured from the live feeds, so
these tests pin our parsing to the actual API shape. The severity ladders are
exercised directly at their boundaries, since live data is usually quiet.
"""

import json
from pathlib import Path

import pytest

from collector.feeds import kp_index, xray
from collector.schema import kp_to_severity, xray_to_severity

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


# --- Kp index --------------------------------------------------------------


def test_kp_normalize_shape():
    records = load("planetary_k_index_1m.json")
    events = kp_index.normalize(records)

    assert len(events) == len(records)
    doc = events[0].doc
    assert doc["@timestamp"].endswith("Z")  # naive SWPC time_tag gets a Z
    assert doc["event"]["kind"] == "metric"
    assert doc["event"]["category"] == "geomagnetic"
    assert doc["event"]["dataset"] == "swpc.planetary_k_index"
    assert doc["observer"]["name"] == "NOAA-SWPC"
    assert doc["source"]["feed"] == "planetary_k_index_1m"
    # estimated_kp is the precise value we key severity off, not the rounded int
    assert doc["metrics"]["kp_index"] == float(records[0]["estimated_kp"])
    assert doc["raw"] == records[0]


def test_kp_id_is_deterministic():
    records = load("planetary_k_index_1m.json")
    first = kp_index.normalize(records)
    again = kp_index.normalize(records)
    assert [e.id for e in first] == [e.id for e in again]
    assert len({e.id for e in first}) == len(first)  # unique per timestamp


@pytest.mark.parametrize(
    "kp,severity",
    [
        (0.0, 0),
        (4.67, 0),
        (5.0, 1),  # G1
        (5.67, 1),
        (6.0, 2),  # G2
        (7.0, 3),  # G3
        (8.0, 4),  # G4
        (9.0, 5),  # G5
        (10.0, 5),  # clamps
    ],
)
def test_kp_to_severity(kp, severity):
    assert kp_to_severity(kp) == severity


# --- GOES X-ray ------------------------------------------------------------


def test_xray_keeps_only_long_band():
    records = load("goes_xrays_1day.json")
    bands = {r["energy"] for r in records}
    assert bands == {"0.05-0.4nm", "0.1-0.8nm"}  # fixture has both

    events = xray.normalize(records)
    long_band = [r for r in records if r["energy"] == "0.1-0.8nm"]
    assert len(events) == len(long_band)  # short band dropped


def test_xray_normalize_shape():
    records = load("goes_xrays_1day.json")
    doc = xray.normalize(records)[0].doc

    assert doc["@timestamp"].endswith("Z")
    assert doc["event"]["category"] == "xray"
    assert doc["event"]["dataset"] == "swpc.goes_xray"
    assert doc["observer"]["name"] == "GOES-18"
    assert doc["source"]["feed"] == "goes_xrays_1day"
    long_band = [r for r in records if r["energy"] == "0.1-0.8nm"]
    assert doc["metrics"]["xray_flux"] == float(long_band[0]["flux"])


def test_xray_id_is_deterministic_and_unique():
    records = load("goes_xrays_1day.json")
    events = xray.normalize(records)
    assert [e.id for e in events] == [e.id for e in xray.normalize(records)]
    assert len({e.id for e in events}) == len(events)


@pytest.mark.parametrize(
    "flux,severity",
    [
        (1e-8, 0),  # A/B class, quiet
        (9.9e-6, 0),  # high C-class, still sub-R1
        (1e-5, 1),  # M1 -> R1
        (5e-5, 2),  # M5 -> R2
        (1e-4, 3),  # X1 -> R3
        (1e-3, 4),  # X10 -> R4
        (2e-3, 5),  # X20 -> R5
        (5e-3, 5),  # clamps
    ],
)
def test_xray_to_severity(flux, severity):
    assert xray_to_severity(flux) == severity
