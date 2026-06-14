# Geomagnetic Storm Precursor — runbook

**Rule:** `storm_precursor` · **Type:** precursor (correlation) · **Throttle:** 1h · **Severity:** 3 (declared)
**Trigger (1h window, all must hold):**
- `swpc.solar_wind_mag` — `metrics.bz_gsm ≤ −10 nT` **sustained ≥ 30 min**, AND
- `swpc.solar_wind_plasma` — `metrics.speed_km_s > 600`

## What it detects
The coupling conditions that drive geomagnetic storms, seen at the L1 point
(DSCOVR) **before** Kp itself responds. A sustained southward interplanetary
magnetic field (negative Bz) lets the solar wind dump energy into the
magnetosphere; pair that with a fast wind and a storm is imminent. This is a
correlation rule — the space-weather analog of chaining two weak signals into one
high-confidence early warning.

## Why it matters
- **Lead time:** Bz/speed at L1 lead ground-level Kp by roughly 30–60 minutes —
  enough to pre-position grid and satellite operators before [Geomagnetic
  Storm](geomagnetic_storm.md) fires.
- A true positive here is usually followed by a G-scale alert within the hour.

## Triage
1. Open **Geomagnetic** dashboard — confirm Bz is still strongly southward and
   speed elevated (not a brief excursion).
2. Has [Geomagnetic Storm](geomagnetic_storm.md) fired yet? If not, this is your
   advance warning — expect it soon.
3. Check for an upstream [Solar Storm Chain](solar_storm_chain.md) (a CME en route
   explains the conditions).

## Response / escalation
- Treat as **pre-storm warning (sev 3):** notify operators that a storm is likely
  within ~1 hour. Increase monitoring cadence.
- If conditions persist or deepen (Bz more negative, speed rising), escalate ahead
  of the geomagnetic-storm alert.
- If Bz turns northward and speed falls without a storm, close as a near-miss.

## References
- Solar wind (DSCOVR) mag: `https://services.swpc.noaa.gov/products/solar-wind/mag-6-hour.json`
- Solar wind (DSCOVR) plasma: `https://services.swpc.noaa.gov/products/solar-wind/plasma-6-hour.json`
