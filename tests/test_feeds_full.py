"""Normalizer tests for the M3 feeds against recorded fixtures + severity ladders.

Fixtures are real slices captured from the live SWPC/DONKI APIs, so these pin our
parsing to the actual payload shapes (array-of-arrays products feeds, multi-band
proton/x-ray feeds, the DONKI catalog).
"""

import json
from pathlib import Path

import pytest

from collector.feeds import (
    donki_cme,
    donki_flr,
    donki_gst,
    donki_sep,
    mag,
    noaa_scales,
    plasma,
    protons,
    swpc_alerts,
)
from collector.schema import flare_class_to_severity, proton_to_severity

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


# --- severity ladders ------------------------------------------------------


@pytest.mark.parametrize(
    "pfu,severity",
    [(1.0, 0), (9.9, 0), (10, 1), (100, 2), (1e3, 3), (1e4, 4), (1e5, 5), (5e5, 5)],
)
def test_proton_to_severity(pfu, severity):
    assert proton_to_severity(pfu) == severity


@pytest.mark.parametrize(
    "cls,severity",
    [
        (None, 0),
        ("C3.1", 0),
        ("M1.0", 1),  # R1
        ("M5.0", 2),  # R2
        ("X1.0", 3),  # R3
        ("X10", 4),  # R4
        ("X20", 5),  # R5
        ("B9.9", 0),
    ],
)
def test_flare_class_to_severity(cls, severity):
    assert flare_class_to_severity(cls) == severity


# --- solar wind (array-of-arrays products feeds) ---------------------------


def test_plasma_normalize():
    events = plasma.normalize(load("solar_wind_plasma.json"))
    assert events  # header row dropped, data rows kept
    doc = events[0].doc
    assert doc["@timestamp"].endswith("Z")
    assert doc["event"]["category"] == "solar_wind"
    assert doc["observer"]["name"] == "DSCOVR"
    assert "speed_km_s" in doc["metrics"]
    assert isinstance(doc["metrics"]["speed_km_s"], float)


def test_mag_normalize():
    events = mag.normalize(load("solar_wind_mag.json"))
    doc = events[0].doc
    assert doc["event"]["dataset"] == "swpc.solar_wind_mag"
    assert "bz_gsm" in doc["metrics"]
    assert "bt" in doc["metrics"]


# --- GOES protons (multi-band) ---------------------------------------------


def test_protons_keep_only_10mev():
    records = load("integral_protons.json")
    events = protons.normalize(records)
    ten_mev = [r for r in records if r["energy"] == ">=10 MeV"]
    assert len(events) == len(ten_mev)  # other bands dropped
    assert events[0].doc["metrics"]["proton_flux_10mev"] == float(ten_mev[0]["flux"])
    assert events[0].doc["event"]["category"] == "solar_radiation"


# --- NOAA scales (current observed only) -----------------------------------


def test_noaa_scales_current_only():
    events = noaa_scales.normalize(load("noaa_scales.json"))
    assert len(events) == 1  # forecasts ignored
    doc = events[0].doc
    assert doc["event"]["category"] == "noaa_scales"
    assert set(doc["metrics"]) <= {"r_scale", "s_scale", "g_scale"}
    assert doc["event"]["severity"] == int(max(doc["metrics"].values()))


# --- SWPC official alerts --------------------------------------------------


def test_swpc_alerts_headline_and_id():
    records = load("swpc_alerts.json")
    events = swpc_alerts.normalize(records)
    assert len(events) == len(records)
    doc = events[0].doc
    assert doc["event"]["kind"] == "alert"
    assert doc["swpc"]["product_id"] == records[0]["product_id"]
    assert doc["message"]  # a headline was extracted


# --- DONKI catalog ---------------------------------------------------------


def test_donki_flr():
    records = load("donki_flr.json")
    events = donki_flr.normalize(records)
    assert len(events) == len(records)
    doc = events[0].doc
    assert doc["event"]["kind"] == "event"
    assert doc["event"]["category"] == "flare"
    assert doc["flare"]["class"] == records[0]["classType"]
    # X1.0 in the Gannon fixture -> R3
    assert doc["event"]["severity"] == flare_class_to_severity(records[0]["classType"])
    assert events[0].id == donki_flr.normalize(records)[0].id  # deterministic


def test_donki_cme_speed():
    events = donki_cme.normalize(load("donki_cme.json"))
    doc = events[0].doc
    assert doc["event"]["category"] == "cme"
    # most-accurate analysis speed surfaced as a metric when present
    if doc["metrics"]:
        assert isinstance(doc["metrics"]["speed_km_s"], float)


def test_donki_gst_peak_kp():
    records = load("donki_gst.json")
    events = donki_gst.normalize(records)
    doc = events[0].doc
    assert doc["event"]["category"] == "geomagnetic"
    peak = max(k["kpIndex"] for k in records[0]["allKpIndex"])
    assert doc["metrics"]["kp_index"] == peak
    assert doc["event"]["severity"] == 5  # Gannon peaked at Kp 9 -> G5


def test_donki_sep():
    events = donki_sep.normalize(load("donki_sep.json"))
    doc = events[0].doc
    assert doc["event"]["category"] == "solar_radiation"
    assert doc["@timestamp"].endswith("Z")
