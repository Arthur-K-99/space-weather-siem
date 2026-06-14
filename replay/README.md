# Replay fixtures — May 2024 Gannon G5 storm

Committed storm fixtures replayed by [`scripts/replay.py`](../scripts/replay.py)
so every detection rule fires on demand. They reconstruct the **May 2024 Gannon
storm** (the AR3664 X-class flares → fast CMEs → G5 geomagnetic storm of 10–11 May
2024 — the strongest in two decades).

Each file is a raw feed payload in the **same shape as the live source**, so the
replay runs them through the real collector normalizers — the storm takes the
exact same ingest path as live data.

| File | Feed / shape | Drives |
|---|---|---|
| `kp_index.json` | planetary K-index (objects) — ramps to Kp 9 | geomagnetic storm (G5) |
| `xray.json` | GOES X-ray long band (objects) — peaks X10 | radio blackout (R3+) |
| `protons.json` | GOES ≥10 MeV protons (objects) — crosses 10 pfu | radiation storm (S1+) |
| `mag.json` | DSCOVR magnetometer (array-of-arrays) — Bz to −50 nT | storm precursor |
| `plasma.json` | DSCOVR plasma (array-of-arrays) — speed to 900 km/s | storm precursor + telemetry loss |
| `donki_flr.json` | DONKI flare (X1.0, AR3664) | chain stage 1 |
| `donki_cme.json` | DONKI CME (fast halo) | chain stage 2 |
| `donki_gst.json` | DONKI storm (peak Kp 9) | chain stage 3 (G5) |

## How the rebasing works

`replay.py` maps the latest realtime sample to **now** and shifts every record by
the same delta, so the flare → CME → storm spacing (days apart) is preserved and
the chain rule fires. The plasma feed is held ~18 min short of now to simulate a
DSCOVR dropout, so telemetry-loss fires too (see that
[runbook](../docs/runbooks/telemetry_loss.md) for the live-collector caveat).

`tests/test_replay.py` normalizes these fixtures and asserts all six rules fire on
the result — the guarantee behind the demo.
