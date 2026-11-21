# 13 – Two-speed polling (parked)

Status: parked · Rules: [README](README.md#rules-for-every-brief)

## Idea

Poll fast-changing values (temperatures, statuses) every interval and slow ones (counters, settings) less often. Peers do this (reported: the ioBroker adapter has a short and a long poll cycle; Daikin Onecta has day and night intervals).

## Why parked

Verified in `coordinator.py`, `_poll`: the integration sends one `GetParameterValues` request per bundle, and every user-level parameter is in bundle 1000. Splitting user-level values by speed would send the same number of requests. Only enabled expert tabs add requests: one per expert bundle and poll, each re-activating its bundle (`GuiIdChanged: true`) since 0.6.1.

Measured: one 4-minute outage in the 14 days observed, which is a single failed poll at most. The recorder cannot show whether that poll was throttled; the log and the diagnostics (`backoff_steps`) can.

## Revisit when

- a user with several expert tabs enabled reports the `throttled` repair issue, or
- diagnostics from the field show `backoff_steps` above 0 on a regular basis.

Reported background: the ioBroker maintainer's rule "the more values, the longer the interval" and an HTTP 400 after about 20 hours of expert polling (`docs/discovery.md`, section 3.3).

## First step then

Poll expert bundles every Nth cycle. Measure before shipping: expert bundles froze without re-activation (`docs/phase2-measurements.md`, section 2026-10-27), so check on a real system that values stay fresh at the slower rate.
