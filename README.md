# Wolf SmartSet (read/write) for Home Assistant

Custom integration for Wolf heating systems connected to the Wolf SmartSet cloud. It uses the same unofficial interface as the SmartSet portal. This version (0.1.x) only reads; writing follows in a later release.

Full documentation (German and English, risks, disclaimer, tested systems) follows before the first public release. Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Entities disabled by default

Some parameters exist in every description but only carry data on some installations. There is no generic signal in the Wolf data to tell them apart (see [ADR-Model-008](docs/adr/ADR-Model-008-parameter-model-entity-mapping-and-naming.md)), so these entities start disabled. Enable the ones that apply to your system under Settings › Devices & services › Wolf SmartSet › Entities.

| Group | Example | Why disabled |
|---|---|---|
| Expert (Fachmann) parameters | Sparfaktor, Heizkurve | several hundred values; may need an expert session to stay current |
| Overview schema ports | Verdichterfrequenz, MKP Mischerkreispumpe | duplicate tab values under another ID |
| Statistics that need an S0 electricity meter (WP110) | Verbrauch …, JAZ, TAZ, MAZ | stay 0 without a meter |
| Optional sensor inputs | Raumtemperatur | no value without a room sensor at the control unit |
| Network and identity values | IP-Adresse, MAC-Adresse | diagnostic only |

The setting only applies when an entity is created. Installations that already ran version 0.1.0 keep these entities enabled until you disable them yourself.
