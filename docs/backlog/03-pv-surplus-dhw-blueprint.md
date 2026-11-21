# 03 – PV-surplus DHW blueprint

Status: ready · Size: small · Commit type: `feat:` · Rules: [README](README.md#rules-for-every-brief)

## Why

The README recommends "1x Warmwasser on PV surplus" in one sentence and gives no example. A blueprint makes the most common automation for this integration a two-minute setup and covers the Gold rules `docs-examples` and `docs-use-cases` together with the energy and COP recipe (landed, README "Examples").

## Facts about the switch (verified, `docs/discovery.md` sections 14 and 15)

- `one_time_dhw_charge` (ParameterId 22004200000) starts a DHW charge within one poll interval.
- The controller switches it off by itself. In the test this happened after about 16 minutes and before the setpoint was reached.
- Writing "off" cancels a running charge.
- Every switch action is a write to the controller. The rate limit defaults to 20 writes per hour, and dry run is on by default.

## Design

- The blueprint only turns the switch on; the controller ends the charge.
- One write per surplus episode: trigger when surplus stays above a threshold for a hold time, with the conditions "DHW temperature below a limit", "switch is off" and "last run longer ago than a cooldown".
- Inputs: surplus power sensor, threshold, hold time, DHW temperature sensor, temperature limit, cooldown, and the switch (entity selector filtered to integration `wolf_smartset`, domain `switch`).
- File: `blueprints/automation/wolf_smartset/dhw_charge_on_pv_surplus.yaml`.

## Gotchas

- HACS installs only `custom_components/wolf_smartset` (`zip_release` in `hacs.json`). Users import the blueprint by URL, so the README needs an import badge (`my.home-assistant.io/redirect/blueprint_import/`) pointing at the raw file on the default branch.
- The `check-yaml` hook in `.pre-commit-config.yaml` rejects the `!input` tag. Exclude the blueprint folder from that hook or give it `--unsafe` for that folder.
- With dry run on, the automation runs and nothing happens at the heat pump. Say so next to the badge.

## Steps

1. One test that loads the blueprint with Home Assistant's blueprint schema (`homeassistant.components.blueprint`). Done when a schema error in the file fails the test.
2. Write the blueprint. Done when the test passes and each design point above is in the file.
3. README: a short subsection under "Examples" (the section exists since the energy and COP recipe landed) with what the blueprint does, the inputs, the badge and the dry-run note.
4. Set `docs-examples` and `docs-use-cases` in `custom_components/wolf_smartset/quality_scale.yaml` to `done` (carried over from brief 02, which has landed).

## Done when

The merge gate and pre-commit are green. Trying the blueprint on the real heat pump is a real write: it needs the owner's go, and the owner runs it.
