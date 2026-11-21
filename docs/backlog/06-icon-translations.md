# 06 – Icon translations

Status: ready · Size: JSON plus one test · Commit type: `feat:` · Rules: [README](README.md#rules-for-every-brief)

## Why

Entities without a device class show a generic icon: the status and valve sensors, pumps, the program selects, the "1x Warmwasser" switch and the undo button. `quality_scale.yaml` lists `icon-translations` as `todo` ("No icons.json").

## Work

Add `custom_components/wolf_smartset/icons.json`, keyed by platform and translation key (`translation_keys.py`, plus `undo`, plus the event entity `write` if [brief 01](01-write-result-event-entity.md) has landed).

Scope: every curated key whose entity has no device class. Temperature, power, energy, pressure, duration, flow and frequency sensors already get an icon from their device class (`UNITS` in `sensor.py`).

## Gotcha to check first

State-specific icons need the state string as key. The states of the enum sensors and selects here are Wolf's display texts ("Heizbetrieb", "AT/RT Abschaltung"), which are not slugs. Whether hassfest accepts such keys is unverified, and hassfest is not part of the local environment: the workflow `.github/workflows/hassfest.yaml` on the pull request is the judge.

- If hassfest accepts them: add state icons where they carry meaning (compressor status, DHW status, valve position).
- If it rejects them: ship default icons only. On/off states of the switch are plain slugs and work either way.

## Steps

1. A test that pins `icons.json` to `TRANSLATION_KEYS`, in the style of `tests/test_translation_keys.py`: every icon key exists as a translation key on that platform, and every curated key without a device class has a default icon. Done when removing an icon or misspelling a key fails the test.
2. Write `icons.json` with Material Design Icons (`mdi:` names). Done when the test passes.
3. Push and read the hassfest result; settle the state-icon question from it.
4. Set `icon-translations` to `done` in `quality_scale.yaml`.

## Done when

The merge gate and the hassfest workflow are green.
