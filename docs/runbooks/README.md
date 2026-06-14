# Alert runbooks

One runbook per detection rule — the triage/response playbook a SOC analyst
reaches for when the alert fires. Each maps the space-weather event to its
real-world impact and a concrete response, the same way a security runbook maps a
detection to an investigation.

| Severity | Alert | Rule |
|---|---|---|
| Geomagnetic | [Geomagnetic Storm](geomagnetic_storm.md) | `geomagnetic_storm` |
| Radio | [Radio Blackout](radio_blackout.md) | `radio_blackout` |
| Radiation | [Solar Radiation Storm](radiation_storm.md) | `radiation_storm` |
| Correlation | [Geomagnetic Storm Precursor](storm_precursor.md) | `storm_precursor` |
| Correlation | [Solar Storm Chain](solar_storm_chain.md) | `solar_storm_chain` |
| Health | [Telemetry Loss](telemetry_loss.md) | `telemetry_loss` |

Severity throughout is the NOAA 0–5 scale the collector stamps on each event
(G/R/S), surfaced on the alert as `event.severity`. See [`rules/`](../../rules/)
for the rule definitions and [`docs/PLAN.md`](../PLAN.md) for the architecture.

> Demo: [`scripts/replay.py`](../../scripts/replay.py) replays the May 2024
> Gannon G5 storm so these alerts fire on demand — see the
> [README quickstart](../../README.md#replay-the-may-2024-g5-storm).
