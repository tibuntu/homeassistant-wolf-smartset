# Wolf SmartSet (read/write) for Home Assistant

Custom integration for Wolf heating systems connected to the Wolf SmartSet cloud. It uses the same unofficial interface as the SmartSet portal. It reads all parameters and can write settings. Writing is off until you switch off the dry run.

Full documentation (German and English, risks, disclaimer, tested systems) follows before the first public release. Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Entities disabled by default

Some parameters exist in every description but only carry data on some installations. There is no generic signal in the Wolf data to tell them apart (see [ADR-Model-011](docs/adr/ADR-Model-011-parameter-model-entity-mapping-and-naming.md)), so these entities start disabled. Enable the ones that apply to your system under Settings › Devices & services › Wolf SmartSet › Entities.

| Group | Example | Why disabled |
|---|---|---|
| Expert (Fachmann) parameters | Sparfaktor, Heizkurve | several hundred values; may need an expert session to stay current |
| Overview schema ports that duplicate a tab parameter | Ausgang MKP (duplicates Mischerkreispumpe) | same function under another ID |
| Statistics that need an S0 electricity meter (WP110) | Verbrauch …, JAZ, TAZ, MAZ | stay 0 without a meter |
| Optional sensor inputs | Raumtemperatur | no value without a room sensor at the control unit |
| Network and identity values | IP-Adresse, MAC-Adresse | diagnostic only |

The setting only applies when an entity is created. Installations that already ran version 0.1.0 keep these entities enabled until you disable them yourself.

## Writing

Every write ends up in the non-volatile memory (EEPROM) of the Wolf controller. The integration therefore runs every change through one pipeline ([ADR-Writes-013](docs/adr/ADR-Writes-013-write-pipeline-with-explicit-confirmation.md)):

- **Dry run, on by default.** Changes are only logged at INFO with parameter, old and new value. Switch it off under Settings › Devices & services › Wolf SmartSet › Configure.
- **No-op suppression.** A value that is already set is not sent again.
- **Validation** against min, max, step and list options from the Wolf description; read-only parameters and accounts without write access are refused.
- **Rate limit**, 20 writes per hour by default, configurable.
- **One write at a time.**
- **Optimistic state** with confirmation: the new value shows immediately and is kept for 30 s, even if a poll still returns the old value. The first poll after that confirms it (`confirmed: true`) or shows the real value, records `confirmed: false` with the value read back, and logs a warning.
- **History** of the last 200 attempts in `.storage`, the last 50 in the diagnostics; an **Undo last change** button.

Writing uses the same unofficial interface as the SmartSet portal. Wolf does not support third-party access. Wrong settings, in particular expert parameters, can make the system inefficient or uncomfortable. Use at your own risk.
