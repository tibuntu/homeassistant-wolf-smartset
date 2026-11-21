# 05 – Primary controls out of "Configuration"

Status: needs owner decision (step 1) · Size: one condition plus an ADR · Commit type: `feat:` · Rules: [README](README.md#rules-for-every-brief)

## Why

The settings people change most are filed as device configuration. Home Assistant treats an entity with a category differently: it is listed under "Configuration" on the device page, left out of auto-generated dashboards, not exposed to voice assistants by default, and skipped by service calls that target a whole area or device.

## Evidence (verified)

- `entity.py`, `WolfEntity.__init__`: every writable `number` and `select` gets `EntityCategory.CONFIG`.
- That includes all eight curated controls: `set_dhw_temperature`, `day_temperature_heating`, `day_temperature_mixer_circuit_1`, `setpoint_correction`, `program_heating`, `program_dhw`, `time_program_heating`, `time_program_dhw`. Only the `one_time_dhw_charge` switch is a primary entity.
- The only ADR text on categories is in ADR-Model-002 (superseded): "Writable parameters get `EntityCategory.CONFIG`, except the known use-case parameters, which stay primary entities." ADR-Model-008 and ADR-Model-011 do not restate it, so the code differs from the last recorded intent.

## Proposal

A writable parameter with a translation key has no category. Writable parameters without a key keep `CONFIG`.

Argument for keeping today's behaviour, for the owner to weigh: the category keeps the controls out of area-wide service calls and out of default voice exposure, and every write goes to the controller's EEPROM. The write pipeline's rate limit and no-op suppression already bound that risk.

## Steps

1. Ask the owner: proposal, or keep as is. If "keep", record that in an ADR and close this brief.
2. Record the decision as a new ADR in `docs/adr/` (next free number, format of the existing ones, referencing ADR-Model-011).
3. Tests: category is `None` for each of the eight keys and `CONFIG` for a writable parameter without a key.
4. Existing installations: a test with a registry entry that already has `CONFIG` shows what the registry holds after setup. Done when existing entries end up without a category, with an explicit registry update if Home Assistant does not do it on its own.
5. Make the change in `entity.py`.

## Done when

The merge gate is green and the ADR is merged with the change. Entity IDs and unique IDs stay the same; say in the commit body that dashboards and voice exposure change.
