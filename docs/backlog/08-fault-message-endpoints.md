# 08 – Fault-message endpoints

Status: needs the owner's go at step 3 · Size: investigation, no entity code · Rules: [README](README.md#rules-for-every-brief)

## Why

Issue #25 (a `problem` binary sensor for faults and maintenance) is parked because the parameter description offers no verified fault signal: `Sub-Störcode` is a hidden data point of unknown behaviour, `Wartungsmeldung` is a setting, and `DynFaultMessageDevices` is an empty list. The plan was to wait for a real fault.

The portal has a separate fault-message feature. `docs/discovery.md`, section 2.5, lists "Störmeldungen" among the endpoints the portal JavaScript knows and that Phase 0 set aside. If it returns a fault history, the real fault record exists already. The same data would fill the `errors` list of the Heat Pump Hydraulic Card's `wolf` preset, which is empty today.

Unknown so far: the endpoint names, their payloads, what they return, and whether they are read-only.

## Steps

1. **Static analysis.** Fetch the portal's public JavaScript bundle (an unauthenticated static asset, the source used in discovery section 1; the file name changes with each build, take the current one from the portal start page). Extract every fault-message function: HTTP method, path, payload fields, and where the portal calls it. Include how `DynFaultMessageDevices` is used. Done when each fault-related endpoint is listed with method, path, payload and calling context, each quoted from the bundle.
2. **Write it down** as a dated addendum ("Nachtrag") in `docs/discovery.md`, in German like the rest of that file, with its evidence labels (`[Code]`, `[Offen]`).
3. **Stop and ask.** Show the owner the exact request or requests you would send and wait for a go. These are endpoints the integration has never called, and rule 3 applies. Propose only calls that read.
4. **With a go:** send each approved request once, through an extension of `scripts/record_fixtures.py`, and store the redacted response under `tests/fixtures/real/`. Done when `scripts/check-fixtures.sh` passes and the addendum describes the response.
5. **Recommend.** State whether a field can drive a `problem` binary sensor and a fault-code sensor with a translation key, with the evidence. Building them is a new brief; reopening #25 is the owner's call.

## Done when

The addendum holds the endpoint facts, the recorded response if the owner gave a go, and the recommendation.
