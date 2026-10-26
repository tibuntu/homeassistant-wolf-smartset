# Wolf SmartSet (read/write) for Home Assistant

Custom integration for Wolf heating systems connected to the Wolf SmartSet cloud. It uses the same unofficial interface as the SmartSet portal and app. It reads every parameter of the system and can write settings such as the DHW setpoint, the operating mode or "1x Warmwasser". Writing is off until you switch off the dry run.

Wolf does not support third-party access. Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Installation

1. In HACS open *Integrations*, then the three-dot menu, then *Custom repositories*. Add `https://github.com/tibuntu/homeassistant-wolf-smartset` with category *Integration*.
2. Install "Wolf SmartSet (read/write)" and restart Home Assistant.
3. If the core integration "Wolf SmartSet Service" (`wolflink`) is set up for the same account, disable it first: Settings › Devices & services › Wolf SmartSet Service › three-dot menu › *Disable*. Two integrations on one account log in from the same IP address, and Wolf blocks the address for up to an hour after too many logins. The block also hits the SmartSet app.
4. Settings › Devices & services › *Add integration* › "Wolf SmartSet (read/write)".

The Wolf icon and logo ship with the integration in `brand/`; Home Assistant shows local brand images since 2026.3. [home-assistant/brands](https://github.com/home-assistant/brands) no longer takes custom integrations, and the images are the Wolf set from that repository (`custom_integrations/wolf`).

## Configuration

The integration asks for the username and password of your Wolf SmartSet account (the password has at most 30 characters, the portal silently truncates longer ones). It lists the systems of the account; with more than one you choose which to add. One entry per account; a second account is a second entry.

When the portal rejects the password later, Home Assistant shows a re-authentication prompt for the entry.

## Options

Settings › Devices & services › Wolf SmartSet › *Configure*:

| Option | Default | Meaning |
|---|---|---|
| Poll interval | 120 s | Seconds between polls, 60 to 3600. Wolf allows at most one poll per minute. |
| Dry run | on | While on, changes are only logged at INFO with parameter, old and new value; nothing is sent to the heating system. |
| Maximum writes per hour | 20 | Rolling limit for real write attempts, 1 to 60. Failed writes count; skipped writes (value already set) and dry runs do not. |

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

## Translation keys

Curated parameters carry a fixed, language-independent `translation_key` ([ADR-Model-016](docs/adr/ADR-Model-016-stable-translation-keys.md)). Dashboards and cards can find an entity through it regardless of entity ID, device name and Home Assistant language, for example with a template over the entity registry or the `wolf` preset of the Heat Pump Hydraulic Card. The keys are a public interface: they only change additively, a key is never renamed or reassigned.

The table below is the complete list. Keys follow the English entity-ID suffixes of the core `wolflink` integration where the same value exists there. The Wolf parameter column is the German label the entity shows on a German system; English systems show an English name. Entity IDs, unique IDs and state values do not change with this feature. Parameters outside the table behave as before (Wolf label, no key).

| Key | Wolf parameter | Platform | Device | ParameterId |
|---|---|---|---|---|
| `day_temperature_heating` | Tagtemperatur (Heizung) (Gemeinsame Einstellungen) | number | Bedienmodul BM-2 | 36006800001 |
| `day_temperature_mixer_circuit_1` | Tagtemperatur (Heizung) (Mischerkreis 1) | number | Bedienmodul BM-2 | 36008400001 |
| `set_dhw_temperature` | Warmwassersolltemperatur eingestellt | number | System | 35000900000 |
| `setpoint_correction` | Sollwertkorrektur | number | System | 36002900001 |
| `program_dhw` | Programmwahl (Warmwasser) | select | System | 35001200000 |
| `program_heating` | Programmwahl (Heizung) | select | System | 36005100001 |
| `3_way_diverter_valve_htg_clg` | 3-Wege-Umschaltventil HZ/K | sensor | Heizgerät | 27001400001 |
| `3_way_diverter_valve_htg_dhw` | 3-Wege-Umschaltventil HZ/WW | sensor | Heizgerät | 27001300001 |
| `average_outside_temperature` | Gemittelte Außentemperatur | sensor | Bedienmodul BM-2 | 36000100001 |
| `boiler_water_temperature` | Kesseltemperatur | sensor | Heizgerät | 27000600001 |
| `clg_energy_amount` | Energiemenge Kühl. | sensor | Heizgerät | 27006100001 |
| `compressor_frequency` | Verdichterfrequenz | sensor | Heizgerät | 27004800001 |
| `compressor_operating_hours` | Betriebsstunden Verdichter | sensor | Heizgerät | 27002700001 |
| `compressor_status` | Verdichterstatus | sensor | Heizgerät | 27005100001 |
| `consumption_current_month` | Verbrauch aktueller Monat | sensor | Heizgerät | 27016200001 |
| `consumption_current_year` | Verbrauch aktuelles Jahr | sensor | Heizgerät | 27016400001 |
| `consumption_previous_day` | Verbrauch Vortag | sensor | Heizgerät | 27017500001 |
| `consumption_previous_year` | Verbrauch Vorjahr | sensor | Heizgerät | 27016600001 |
| `consumption_year_before_last` | Verbrauch Vorvorjahr | sensor | Heizgerät | 27016800001 |
| `current_capacity_specification_compressor` | Aktuelle Leistungsvorgabe Verdichter | sensor | Heizgerät | 27001000001 |
| `current_secondary_power` | Aktuelle Sekundärleistung | sensor | Heizgerät | 27005800001 |
| `dhw_status` | Warmwasser Status | sensor | System | 35000100000 |
| `dhw_temperature` | Warmwassertemperatur | sensor | Heizgerät | 27000700001 |
| `e_heating_operating_hours` | Betriebsstunden E-Heizung | sensor | Heizgerät | 27003800001 |
| `electric_booster_heater` | E-Heizung | sensor | Heizgerät | 27001600001 |
| `energy_amount_dhw` | Energiemenge WW | sensor | Heizgerät | 27006000001 |
| `energy_amount_htg` | Energiemenge HZ | sensor | Heizgerät | 27005900001 |
| `feed_heating_circuit_pump` | Zubringer-/Heizkreispumpe | sensor | Heizgerät | 27001200001 |
| `flow_temperature` | Vorlauftemperatur | sensor | Bedienmodul BM-2 | 36001100001 |
| `hc_flow_rate` | Heizkreisdurchfluss | sensor | Heizgerät | 27002800001 |
| `header_temperature` | Sammlertemperatur | sensor | Heizgerät | 27002900001 |
| `heat_generated_current_month` | Erzeugte Wärmemenge aktueller Monat | sensor | Heizgerät | 27016300001 |
| `heat_generated_current_year` | Erzeugte Wärmemenge aktuelles Jahr | sensor | Heizgerät | 27016500001 |
| `heat_generated_previous_day` | Erzeugte Wärmemenge Vortag | sensor | Heizgerät | 27017600001 |
| `heat_generated_previous_year` | Erzeugte Wärmemenge Vorjahr | sensor | Heizgerät | 27016700001 |
| `heat_generated_year_before_last` | Erzeugte Wärmemenge Vorvorjahr | sensor | Heizgerät | 27016900001 |
| `heating_circuit_pump` | Heizkreispumpe | sensor | Heizgerät | 27001100001 |
| `jaz_current_year` | JAZ aktuelles Jahr | sensor | Heizgerät | 27017200001 |
| `jaz_previous_year` | JAZ Vorjahr | sensor | Heizgerät | 27017300001 |
| `jaz_year_before_last` | JAZ Vorvorjahr | sensor | Heizgerät | 27017400001 |
| `maz_current_month` | MAZ aktueller Monat | sensor | Heizgerät | 27017100001 |
| `mixer_circuit_demand` | Anforderung Mischerkreis | sensor | Bedienmodul BM-2 | 36000400001 |
| `mixer_circuit_pump` | Mischerkreispumpe | sensor | System | 4007000001 |
| `mixer_circuit_status` | Mischerkreis Status | sensor | Bedienmodul BM-2 | 36000500001 |
| `mixer_flow_sensor_vf` | MI72 Analogeingang Vorlauffühler VF | sensor | Mischermodul MM1 | 4002700001 |
| `mixer_motor` | Mischermotor | sensor | Mischermodul MM1 | 4000200001 |
| `mkp_mixer_circuit_pump` | Ausgang MKP | sensor | Mischermodul MM1 | 4000100001 |
| `operating_mode_heater` | Betriebsart Heizgerät | sensor | Heizgerät | 27005000001 |
| `outside_temperature` | Außentemperatur (Heizung) | sensor | Heizgerät | 27000500001 |
| `power_consumption_wp_ehz` | Leistungsaufnahme (WP + EHZ) | sensor | Heizgerät | 27004900001 |
| `return_temperature` | Rücklauftemperatur | sensor | Heizgerät | 27000900001 |
| `room_temperature` | Raumtemperatur | sensor | Bedienmodul BM-2 | 36000000001 |
| `set_boiler_temperature` | Kesselsolltemperatur | sensor | Heizgerät | 27000400001 |
| `set_dhw_temperature_adjusted` | Warmwassersolltemperatur | sensor | Heizgerät | 27000800001 |
| `system_pressure` | Anlagendruck | sensor | Heizgerät | 27003000001 |
| `taz_previous_day` | TAZ Vortag | sensor | Heizgerät | 27017700001 |
| `one_time_dhw_charge` | 1x Warmwasser | switch | System | 22004200000 |

The table covers a CHA heat pump with BM-2 and MM1 (one mixer circuit). A second mixer circuit or module gets its own rows with a `_mixer_circuit_2` suffix once an installation provides the IDs. A key applies only on the platform listed here; when the same parameter maps to another platform on an installation (for example a read-only "1x Warmwasser" becomes a sensor), the entity keeps the Wolf label and has no key.

## Writing

Every write ends up in the non-volatile memory (EEPROM) of the Wolf controller. The integration therefore runs every change through one pipeline ([ADR-Writes-013](docs/adr/ADR-Writes-013-write-pipeline-with-explicit-confirmation.md)):

- **Dry run, on by default.** Changes are only logged at INFO. Switch it off under *Configure* when you have checked the log and want real writes.
- **No-op suppression.** A value that is already set is not sent again.
- **Validation** against min, max, step and list options from the Wolf description; read-only parameters and accounts without write access are refused.
- **Rate limit**, 20 writes per hour by default, configurable.
- **One write at a time.**
- **Optimistic state with confirmation.** The new value shows immediately. The first poll at least 30 s after the write confirms it (`confirmed: true` in the history) or restores the value the controller reports (`confirmed: false`, a warning in the log).
- **History** of the last 200 attempts in `.storage/wolf_smartset.<entry_id>.history`, the last 50 in the diagnostics; an **Undo last change** button.
- **Login backoff.** After a failed login the integration waits five minutes, doubling up to an hour, before it logs in again. The block is stored and survives Home Assistant restarts ([ADR-Client-015](docs/adr/ADR-Client-015-login-backoff-survives-restarts.md)). A wrong password is exempt: it opens the re-authentication prompt instead.

Expert (Fachmann) parameters are written without an expert login. Whether the controller applies them is unproven; the history shows `confirmed: false` when it does not. Wrong settings, in particular expert parameters, can make the system inefficient or uncomfortable. Use at your own risk.

The integration never writes on its own. Writes come from your actions in the UI, from automations and from the undo button.

**Automations.** Let the controller's weekly time programs do the daily switching between comfort and eco, and use Home Assistant for exceptions: "Programmwahl" to *Sparen* while nobody is home, "Zeitprogramm" 2 or 3 for holidays, "1x Warmwasser" on PV surplus, back to *Auto* afterwards. Rebuilding a schedule with automations works, but every switch is a write to the controller, and if Home Assistant or the cloud is down at the switching time the heating stays in the last written mode. The controller's own program keeps running without either.

## Removal

Settings › Devices & services › Wolf SmartSet › three-dot menu › *Delete*. This removes the entry, its devices and entities. The write history `.storage/wolf_smartset.<entry_id>.history` stays behind; delete it by hand if you want it gone. Re-enable the core "Wolf SmartSet Service" integration afterwards if you still need it.

## Known limitations

- Time programs: the selector of the active weekly program (1, 2 or 3) is a `select`. The day schedules, dates, times, party and holiday mode are not mapped yet ([concept](docs/time-programs.md)).
- Entity names are Wolf's German labels, the same as in the SmartSet app and the manuals. Curated parameters (see [Translation keys](#translation-keys)) are translated and show English names on non-German systems.
- The interface is unofficial. Wolf changes the login flow several times a year; a broken login shows as "portal unavailable" until a fix is released.
- Only one installation (Wolf CHA heat pump with BM-2 and MM1, Link home gateway) has been tested so far.

## Troubleshooting

- **Repair issue "throttles … or blocks the login"**: the portal answered several polls with throttling or empty responses, or the login is blocked after repeated failures (five minutes, doubling up to an hour). The integration polls less often until the portal answers again. The block also holds across Home Assistant restarts, so restarting does not speed it up. Check that no other client logs in with this account from your network.
- **Repair issue "core integration is active"**: disable the core integration for the same account (see Installation).
- **Re-authentication prompt**: the portal rejected the password. Enter the current one.
- **Diagnostics**: Settings › Devices & services › Wolf SmartSet › three-dot menu › *Download diagnostics*. The file contains the parsed parameter model, the write history and login statistics, with credentials and identifiers redacted.
- **A write shows "not applied"**: the controller reported another value after the write. Expert parameters may need an expert session; user-level parameters may be limited by a dependent setting in the controller.
