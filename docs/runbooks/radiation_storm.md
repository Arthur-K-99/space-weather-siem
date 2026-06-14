# Solar Radiation Storm — runbook

**Rule:** `radiation_storm` · **Type:** threshold · **Throttle:** 1h
**Trigger:** GOES ≥10 MeV integral proton flux `metrics.proton_flux_10mev ≥ 10 pfu` (`swpc.goes_protons`)
**Severity:** NOAA S-scale — 10→S1, 100→S2, 1e3→S3, 1e4→S4, 1e5→S5

## What it detects
Solar energetic protons are elevated past the S1 threshold (10 pfu at ≥10 MeV).
These arrive minutes-to-hours after a flare/CME and can persist for days.

## Why it matters
- **Satellites:** single-event upsets, memory bit-flips, solar-panel degradation.
- **Aviation:** elevated radiation on polar routes — airlines reroute at S3+.
- **Human spaceflight:** radiation-exposure risk to astronauts (EVA holds).
- **Polar HF:** polar-cap absorption blacks out HF through the polar regions.

## Triage
1. Open **Solar Activity** dashboard — read the proton flux (log scale) and trend.
2. Correlate with a recent [Radio Blackout](radio_blackout.md) — proton storms
   usually follow a strong flare from the same active region.
3. Check whether the source region is well-connected to Earth (western hemisphere
   flares ramp protons fastest).

## Response / escalation
- **S1 (sev 1):** minor; possible small effects on polar HF. Log it.
- **S2–S3 (sev 2–3):** notify satellite operators and polar-route aviation; watch trend.
- **S4–S5 (sev 4–5):** escalate; real risk to satellites and astronauts, polar
  routes likely rerouted. Track until flux falls below 10 pfu.

## References
- NOAA space-weather scales: <https://www.swpc.noaa.gov/noaa-scales-explanation>
- GOES proton feed: `https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json`
