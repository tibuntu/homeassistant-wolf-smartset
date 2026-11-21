# 04 – Fixture-grade diagnostics

Status: ready · Size: medium · Commit type: `feat:` · Rules: [README](README.md#rules-for-every-brief)

## Why

The integration is in the HACS default store since 2026-11-04 and has been tested on one installation. A bug report from a gas boiler, a second mixer circuit or another control unit has to be reproducible as a test. Today's diagnostics file cannot do that: it holds the parsed model, and mapping bugs live in the raw description. With the raw description in the file, every attached diagnostics download is a ready-made fixture, and new translation keys (for example the `_mixer_circuit_2` rows the README promises "once an installation provides the IDs") can be added from it.

## Evidence (verified)

- `diagnostics.py` writes parsed parameters: no raw description, no values, no list options.
- `coordinator.py` drops the raw description after `parse_description` in `_async_setup` and `_refresh_description`.
- Redaction of raw responses exists only in `scripts/record_fixtures.py` (`redact_ids`, `redact_description`, `secret_value_ids`, `redact_values`). `write.py` has a second `redact_ids` with its own key set.
- `.github/ISSUE_TEMPLATE/bug_report.yml` tells users the file "contains no credentials or system IDs".

## Privacy is the hard part

The diagnostics file is posted in public issues. The redaction in the script already treats these as secret, and the diagnostics must too: identifier keys, personal fields, serial numbers, system name, IP and MAC values, and the values of dates, times and day switch times (control types 9, 10, 14), which reveal when people are home.

## Steps

1. Move the redaction from `scripts/record_fixtures.py` into one module of the package; the script imports it. Fold the `redact_ids` of `write.py` into it if the key sets can be unified without changing the write history format. Done when `grep -rn "def redact_"` shows one implementation of each function.
2. Keep the raw description on the coordinator. Done when both places that parse it also store it.
3. Add per system to the diagnostics: `description` (redacted raw description) and `values` (the coordinator's current values, with the secret value IDs blanked).
4. Leak test: plant a marker string in every field class the redaction covers (each identifier key, each personal field, each secret control type, each parameter name the secret pattern matches, the system and gateway IDs) and assert the serialised diagnostics contain no marker. Done when every class has a planted marker.
5. Round-trip test: `parse_description` on the `description` taken from the diagnostics output yields the same parameter model as on the original fixture (IDs, kinds, bundles, devices, limits, options). This is what "fixture-grade" means.
6. Docs: the "Diagnostics" entry in the README's "Troubleshooting" says what the file now contains; the bug report template's promise still holds.

## Notes

- The description is about 500 KB of JSON, so the diagnostics file grows to roughly 0.5 to 1 MB. That is fine for an issue attachment.
- Diagnostics run without any call to the portal.

## Done when

The merge gate is green including both new tests, and `scripts/check-fixtures.sh` still passes.
