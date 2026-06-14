# Geomagnetic Storm — runbook

**Rule:** `geomagnetic_storm` · **Type:** threshold · **Throttle:** 1h
**Trigger:** planetary K-index `metrics.kp_index ≥ 5` (`swpc.planetary_k_index`)
**Severity:** NOAA G-scale — Kp 5→G1 (sev 1) … Kp 9→G5 (sev 5)

## What it detects
Earth's magnetic field is being driven into storm conditions. Kp ≥ 5 is the G1
threshold; the alert severity tracks the peak Kp in the throttle window.

## Why it matters
- **Power grids:** geomagnetically induced currents (GICs) can saturate
  transformers — the failure mode behind the 1989 Québec blackout. G4–G5 is grid-operator territory.
- **GPS/GNSS:** ionospheric disturbance degrades positioning accuracy.
- **Satellites:** increased atmospheric drag in LEO; surface charging.
- **Aurora** visible to much lower latitudes than usual.

## Triage
1. Open **Geomagnetic** dashboard — is Kp still climbing or recovering?
2. Cross-check **IMF Bz** (should be strongly southward) and **solar wind speed**.
3. Check for a preceding [Storm Precursor](storm_precursor.md) or
   [Solar Storm Chain](solar_storm_chain.md) alert — was this storm predicted?
4. Confirm against the live NOAA scale on the **SOC Overview** dashboard.

## Response / escalation
- **G1–G2 (sev 1–2):** informational. Note in the shift log; aurora watchers / HF
  operators may notice effects.
- **G3 (sev 3):** notify satellite operators (drag/charging); watch GNSS-dependent ops.
- **G4–G5 (sev 4–5):** escalate to grid and satellite operators; expect GIC and
  GNSS impact. Track until Kp falls below 5 for a sustained period.

## References
- NOAA space-weather scales: <https://www.swpc.noaa.gov/noaa-scales-explanation>
- Planetary K-index feed: `https://services.swpc.noaa.gov/json/planetary_k_index_1m.json`
