# ADR-Model-017: Curated controls without entity category

## Status

Accepted. Adds the entity category rule to the platform mapping of [ADR-Model-011](ADR-Model-011-parameter-model-entity-mapping-and-naming.md).

## Date

2026-11-21

## Context

Up to 0.6.1, `WolfEntity` gave every writable `number` and `select` `EntityCategory.CONFIG`. That includes the eight curated controls people change most: `set_dhw_temperature`, `day_temperature_heating`, `day_temperature_mixer_circuit_1`, `setpoint_correction`, `program_heating`, `program_dhw`, `time_program_heating` and `time_program_dhw`. Only the `one_time_dhw_charge` switch was a primary entity.

Home Assistant treats an entity with a category differently: it is listed under "Configuration" on the device page, left out of auto-generated dashboards, never exposed to voice assistants by default, and skipped by service calls that target a whole area or device.

The only recorded intent is in ADR-Model-002 (superseded): "Writable parameters get `EntityCategory.CONFIG`, except the known use-case parameters, which stay primary entities." ADR-Model-008 and ADR-Model-011 did not restate it, and the code lost the exception.

Existing installations hold `entity_category: config` in their entity registry. Home Assistant 2026.10.4 updates that field on every setup from what the entity reports:

- `helpers/entity_platform.py`, `_async_add_entity`, line 1109 ff.: `entity_registry.async_get_or_create(..., entity_category=entity.entity_category, ...)`; the value is the entity's, `None` included, never `UNDEFINED`.
- `helpers/entity_registry.py`, `async_get_or_create`, line 1563 ff.: for an existing entry it calls `_async_update_entity(entity_id, ..., entity_category=entity_category, ...)`.
- `helpers/entity_registry.py`, `_async_update_entity`, lines 1999 and 2016 ff.: every field that is not `UNDEFINED` and differs from the stored value is written.
- `components/config/entity_registry.py`, lines 159 to 190: the websocket command `config/entity_registry/update` accepts no `entity_category`. The registry has a single category field, it is owned by the integration, and users cannot set it. There is nothing a user chose that this change could overwrite.

## Decision

1. A writable parameter with a translation key ([ADR-Model-016](ADR-Model-016-stable-translation-keys.md)) has no entity category.
2. Writable parameters without a translation key keep `EntityCategory.CONFIG`.
3. No explicit registry migration: Home Assistant clears the stored category on the next setup. A test pins this behaviour with registry entries created with `CONFIG`.

Entity IDs and unique IDs do not change.

## Rationale

The translation key already marks the parameters curated as the ones users build dashboards on. Using it for the category needs no second list and keeps new curated rows primary automatically.

Rule 2 keeps the unreviewed rest of the writable parameters, which are installer-level settings, out of dashboards, voice exposure and area-wide calls.

### Alternatives Considered

**Keep `CONFIG` for every writable parameter**

- Pro: the controls stay out of area-wide service calls; every write goes to the controller's EEPROM.
- Con: the most-used controls are missing from auto-generated dashboards and filed as device configuration, contrary to the original intent of ADR-Model-002. The write pipeline's rate limit and no-op suppression (ADR-Writes-013) already bound the EEPROM risk.

**A separate list of primary controls**

- Pro: category independent of naming.
- Con: a second curated table that has to stay in step with the translation keys.

**Explicit registry update in `async_setup_entry`**

- Pro: does not depend on Home Assistant's update behaviour.
- Con: duplicates what Home Assistant already does on every setup; the test catches a change in that behaviour.

## Consequences

### Positive

- The eight curated controls appear in auto-generated dashboards and in the device page's "Controls" section.
- The category no longer blocks voice exposure. In 2026.10.4 `components/homeassistant/exposed_entities.py`, `_is_default_exposed` (lines 304 ff.), returns `False` for any entity with a category; without one it decides by domain. `number` and `select` are not in `DEFAULT_EXPOSED_DOMAINS` (lines 32 ff.), so the controls are still not exposed automatically; users can expose them like any primary entity.

### Negative

- Dashboards change on existing installations: auto-generated dashboards show the controls.
- Area- and device-wide service calls now reach the controls. `helpers/target.py` line 282 skips entities with a category only for those targets; for example `number.set_value` on a whole area now also sets `set_dhw_temperature`. Every such write still goes through the write pipeline.
- Voice exposure decisions are stored per entity once evaluated (`async_should_expose`, lines 247 ff., writes `should_expose` into the registry options). Existing "not exposed" decisions stay as they are.

### Risks

- If Home Assistant stops updating the category of existing entries, the registry test fails before a release.

## Related Decisions

- [ADR-Model-011: Parameter model, entity mapping and naming (revision 3)](ADR-Model-011-parameter-model-entity-mapping-and-naming.md) — platform mapping extended by this ADR
- [ADR-Model-016: Stable translation keys for curated parameters](ADR-Model-016-stable-translation-keys.md) — the keys that select the curated controls
- [ADR-Model-002: Parameter model and entity mapping](ADR-Model-002-parameter-model-and-entity-mapping.md) — the original intent
- [ADR-Writes-013: Write pipeline with explicit confirmation](ADR-Writes-013-write-pipeline-with-explicit-confirmation.md) — rate limit and no-op suppression
