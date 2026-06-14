# Radio Blackout — runbook

**Rule:** `radio_blackout` · **Type:** threshold · **Throttle:** 1h
**Trigger:** GOES long-band X-ray flux `metrics.xray_flux ≥ 1e-5 W/m²` (M-class) (`swpc.goes_xray`)
**Severity:** NOAA R-scale — M1→R1, M5→R2, X1→R3, X10→R4, X20→R5

## What it detects
A solar flare is emitting enough X-ray flux to ionize the dayside upper
atmosphere. The R-scale is defined on the 0.1–0.8 nm (1–8 Å) long channel, which
is exactly the field this rule thresholds.

## Why it matters
- **HF radio:** shortwave (3–30 MHz) degrades or blacks out on the sunlit side of
  Earth — aviation, maritime, emergency, and amateur comms.
- **Navigation:** low-frequency nav signals (e.g. for aviation) can be degraded.
- A strong flare is often the **first stage** of a flare → CME → storm chain;
  watch for an escalating [Solar Storm Chain](solar_storm_chain.md).

## Triage
1. Open **Solar Activity** dashboard — read the X-ray flux (log scale) and the
   peak class (M vs X). The spike's height is the blackout severity.
2. Note the flare's timing — the dayside hemisphere at flare peak is the affected region.
3. Check **DONKI Flares & CMEs** — did this flare launch a CME? If so a
   geomagnetic storm may follow in 1–3 days.

## Response / escalation
- **R1–R2 (sev 1–2):** minor; brief HF fade-outs on sunlit side. Log it.
- **R3 (sev 3):** wide-area HF blackout for ~tens of minutes; notify HF-dependent ops.
- **R4–R5 (sev 4–5):** escalate; extended blackout. Correlate with the CME/storm chain.

## References
- NOAA space-weather scales: <https://www.swpc.noaa.gov/noaa-scales-explanation>
- GOES X-ray feed: `https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json`
