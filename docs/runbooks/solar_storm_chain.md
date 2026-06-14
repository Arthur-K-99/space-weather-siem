# Solar Storm Chain — runbook

**Rule:** `solar_storm_chain` · **Type:** chain (multi-stage correlation) · **Throttle:** 6h
**Severity:** declared floor 4, raised to the max of the stage severities (a G5 storm → sev 5)
**Trigger (ordered stages, from the DONKI catalog):**
1. `donki.flr` — a flare ≥ M-class (`event.severity ≥ 1`), then
2. `donki.cme` — a CME **within 6h** of the flare, then
3. `donki.gst` — a geomagnetic storm with `metrics.kp_index ≥ 5` **within 3 days** of the CME.

## What it detects
The full Sun-to-Earth sequence linked into **one composite incident**: flare →
CME → geomagnetic storm. This is the space-weather analog of a multi-stage
intrusion (recon → delivery → impact) — individually each stage is routine;
together they confirm a storm's solar origin and attribute it to a specific
flare/CME. The engine anchors on the storm and walks backward, so unrelated
background CMEs between the stages don't break the correlation.

## Why it matters
- **Attribution + confidence:** unlike the single-signal threshold rules, a
  completed chain is high-confidence and tells you *why* the storm happened.
- **Forecasting:** once the flare→CME stages fire, the storm stage is a prediction
  with 1–3 days of lead time (CME transit time).

## Triage
1. Open **Solar Activity** dashboard — locate the originating flare and CME.
2. Open **Geomagnetic** dashboard — confirm the storm (Kp) the chain terminated on.
3. Read the alert `message` — it spells out the three linked stages and times.
4. Expect concurrent [Geomagnetic Storm](geomagnetic_storm.md) and possibly
   [Radio Blackout](radio_blackout.md) / [Radiation Storm](radiation_storm.md)
   alerts from the same event.

## Response / escalation
- Treat as the **primary incident** and correlate the single-signal alerts under it.
- Severity follows the terminal storm — a G4–G5 chain is a major incident: notify
  grid, satellite, aviation, and HF stakeholders.
- Keep open until the geomagnetic storm recovers.

## References
- NASA DONKI: <https://ccmc.gsfc.nasa.gov/tools/DONKI/>
- May 2024 Gannon storm (the replay scenario): the X-class flares of AR3664 → fast
  CMEs → G5 storm on 10–11 May 2024.
