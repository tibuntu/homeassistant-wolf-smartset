# 12 – Polling health sensors (parked)

Status: parked · Rules: [README](README.md#rules-for-every-brief)

## Idea

Diagnostic sensors that show how polling is doing: request count, time of the last successful poll, age of the data. Peer integrations have them where the vendor enforces quotas (reported: the Vaillant integration mypyllant has an API request count sensor; ViCare and Daikin Onecta document daily request limits).

## Why parked

Measured on 0.6.1 over 14 days, there is nothing these sensors would have shown:

- one outage, 4 minutes long (2026-11-11, 03:56);
- no window longer than 20 minutes in which none of the 51 enabled sensors changed, across about 48,900 recorded state changes.

Verified, already in place: the connectivity binary sensor separates "gateway offline" from "portal unreachable"; a repair issue appears after repeated throttling (`coordinator.py`, `_back_off`); the diagnostics carry `login_count`, `last_login` and `login_blocked_seconds`. Wolf limits logins, not requests, so a request counter measures nothing Wolf acts on.

## Revisit when

- a user reports stale values while every entity stays available, or
- the frozen values of `docs/phase2-measurements.md` (section 2026-11-04/05) return, or
- users report blocks that the repair issue and the connectivity sensor did not explain.

## First step then

A stale-data check (polls succeed, yet no value has changed for N polls) that raises a repair issue. It addresses the one failure mode this integration has actually had; counters do not.
