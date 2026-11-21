# 01 – Write-result event entity

Status: ready · Size: small · Commit type: `feat:` · Rules: [README](README.md#rules-for-every-brief)

## Why

A user cannot see in the UI what the write pipeline did with a change.

- Dry run is the default. A change made in dry run snaps back to the old value with no message. The only trace is an INFO log line, and Home Assistant hides INFO unless the user configures logging.
- A write the controller did not apply only logs a warning.
- Automations cannot react to either case.

An `event` entity puts every attempt into the logbook and on the device page, and gives automations a trigger ("notify me when a write was not applied"). It replaces the history view a custom panel would otherwise be built for.

## Evidence (verified)

- `write.py`, `WriteManager.async_write`: the dry-run branch logs at INFO, records the attempt and returns.
- `write.py`, `WriteManager.async_check_pending`: sets `not_applied` and logs a warning.
- `README.md`, section "Writing": "Changes are only logged at INFO."

## Design (proposal, the owner may change it)

- One event entity per system, on the system device, translation key `write`.
- Event types reuse the `RESULT_*` strings of `write.py`, so the history and the events share one vocabulary: `ok` (sent to the portal), `confirmed` (new), `not_applied`, `dry_run`, `rate_limited`, `error`.
- `unchanged` fires no event: an automation that re-asserts a value would fill the logbook.
- Attributes: `label`, `parameter_id`, `old`, `new`, `source`, plus `error` when present. The system ID stays out, as in the diagnostics.

## Where

- `write.py`: `_record()` is the one place every immediate result passes; `async_check_pending()` decides `confirmed` and `not_applied` later. `async_add_listener()` exists but carries no payload (the undo button uses it).
- New `event.py`; add `Platform.EVENT` to `PLATFORMS` in `__init__.py`.
- `strings.json`, `translations/en.json`, `translations/de.json`: entity name and one translated state per event type. `tests/test_translation_keys.py` shows how the three files are pinned to each other.
- `README.md`: the dry-run bullet in "Writing", the "not applied" entry in "Troubleshooting", and one automation example that notifies on `not_applied`.

## Steps

1. Tests in `tests/test_event.py`, following `tests/test_write.py`. Done when there is one test per event type asserting type and attributes, one asserting that `unchanged` fires nothing, and one asserting that no attribute contains the system ID.
2. Implement the entity and the notification from `WriteManager`. Done when the tests of step 1 pass.
3. Translations in all three files. Done when `tests/test_translation_keys.py` passes and the German file has German texts.
4. README. Done when the three places listed above describe the event entity.

## Done when

The merge gate is green, and changing a number entity in dry run produces a `dry_run` event with the old and new value. All of this is testable with dry run on; no real write is needed.
