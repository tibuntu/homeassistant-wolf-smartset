# Wolf SmartSet (read/write) for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/tibuntu/homeassistant-wolf-smartset)](https://github.com/tibuntu/homeassistant-wolf-smartset/releases/latest)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tibuntu&repository=homeassistant-wolf-smartset&category=integration)

Custom integration for Wolf heating systems connected to the Wolf SmartSet cloud. It uses the same unofficial interface as the SmartSet portal and app. It reads every parameter of the system and can write settings such as the DHW setpoint, the operating mode or "1x Warmwasser". Writing is off until you switch off the dry run.

Wolf does not support third-party access. Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Installation

### HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. Search for "Wolf SmartSet (read/write)" in HACS and download it, or use the button above.
3. Restart Home Assistant.

### Manual installation

1. Download `wolf_smartset.zip` from the [latest release](https://github.com/tibuntu/homeassistant-wolf-smartset/releases/latest).
2. Extract it into `config/custom_components/wolf_smartset/`.
3. Restart Home Assistant.

### Add the integration

1. If the core integration "Wolf SmartSet Service" (`wolflink`) is set up for the same account, disable it first: Settings › Devices & services › Wolf SmartSet Service › three-dot menu › *Disable*. Two integrations on one account log in from the same IP address, and Wolf blocks the address for up to an hour after too many logins. The block also hits the SmartSet app.
2. Settings › Devices & services › *Add integration* › "Wolf SmartSet (read/write)".

The Wolf icon and logo ship with the integration in `brand/`; Home Assistant shows local brand images since 2026.3. [home-assistant/brands](https://github.com/home-assistant/brands) no longer takes custom integrations, and the images are the Wolf set from that repository (`custom_integrations/wolf`).

## Configuration

The integration asks for the username and password of your Wolf SmartSet account (the password has at most 30 characters, the portal silently truncates longer ones). It lists the systems of the account; with more than one you choose which to add. One entry per account; a second account is a second entry.

To change the selection later, use *Reconfigure* in the entry's menu. Systems that stay selected keep their entity IDs and history; devices and entities of deselected systems are removed.

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

## Fault entities

Each system device has two entities fed by the portal's fault list, read every 10 minutes (fixed, separate from the value poll; [ADR-Polling-019](docs/adr/ADR-Polling-019-fault-messages-read.md)):

- *Fault* (binary sensor, device class `problem`, translation key `fault`): on while the portal lists a current fault.
- *Fault code* (sensor, translation key `fault_code`): Wolf's error code of the newest current fault, unknown without one. Attributes `description` and `occurred` give Wolf's fault text and the time it came in.

Faults often last only one to three minutes, shorter than the 10-minute read. The fault code sensor therefore also carries the newest entry of the portal's fault history as `last_fault_code`, `last_fault_description`, `last_fault_occurred` and `last_fault_ended`, so a fault that came and went between two reads still shows up. Times are the portal's local times as sent; `occurred` can be empty when the portal leaves it out. If a fault read fails, only these two entities become unavailable.

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
| `time_program_dhw` | Zeitprogramm (Warmwasser) | select | System | 35000400000 |
| `time_program_heating` | Zeitprogramm (Heizung) | select | System | 36001600001 |
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

- **Dry run, on by default.** Nothing is sent; the entity snaps back to the old value, the *Write result* event entity fires `dry_run` with the old and new value, and an INFO line is logged. Switch it off under *Configure* when you have checked the events and want real writes.
- **No-op suppression.** A value that is already set is not sent again.
- **Validation** against min, max, step and list options from the Wolf description; read-only parameters and accounts without write access are refused.
- **Rate limit**, 20 writes per hour by default, configurable.
- **One write at a time.**
- **Optimistic state with confirmation.** The new value shows immediately. The first poll at least 30 s after the write that reads the new value confirms it (`confirmed: true` in the history). The portal can show some values minutes late, so another value only counts once the settle window has passed: one poll interval plus 30 s, at least 5 minutes (5 minutes at the default 120 s interval). After a revert or Undo while the first write is still unconfirmed, a read of the original value also waits for the window, because a late portal shows that value too. The first poll after that restores the value the controller reports (`confirmed: false`, a warning in the log); until then the written value stays.
- **Write result event.** The *Write result* event entity on the system device fires for every attempt: `dry_run`, `rate_limited` or `error` once; a real write fires `ok` when it is sent to the portal and later one `confirmed` or `not_applied` (see above for when). A restart of Home Assistant or a reload of the entry, which every options change causes, drops the checks still pending; those writes fire no second event and stay `confirmed: false` with no read-back value in the history. A write replaced by a newer write to the same parameter before it was checked fires no second event either. Each event has the attributes `label`, `parameter_id`, `old`, `new`, `source` (`entity` or `undo`) and `error` when present. A value that is already set fires nothing. Every event shows in the logbook and can trigger an automation.
- **History** of the last 200 attempts in `.storage/wolf_smartset.<entry_id>.history`, the last 50 in the diagnostics; an **Undo last change** button.
- **Login backoff.** After a failed login the integration waits five minutes, doubling up to an hour, before it logs in again. The block is stored and survives Home Assistant restarts ([ADR-Client-015](docs/adr/ADR-Client-015-login-backoff-survives-restarts.md)). A wrong password is exempt: it opens the re-authentication prompt instead.

Expert (Fachmann) parameters are read-only. There is no evidence from a real installation yet that the controller applies them without an expert login, and every write would end up in the EEPROM. Wrong user-level settings can still make the system inefficient or uncomfortable. Use at your own risk.

The integration never writes on its own. Writes come from your actions in the UI, from automations and from the undo button.

Example: notify when the controller did not apply a write (replace the entity ID with yours). `not_from` keeps a restart or reload, which restores the last event, from sending the notification again:

```yaml
automation:
  - alias: Wolf write not applied
    triggers:
      - trigger: state
        entity_id: event.home_write_result
        not_from: [unavailable, unknown]
    conditions:
      - condition: state
        entity_id: event.home_write_result
        attribute: event_type
        state: not_applied
    actions:
      - action: notify.notify
        data:
          message: >-
            {{ state_attr('event.home_write_result', 'label') }} was written as
            {{ state_attr('event.home_write_result', 'new') }} but the controller did not apply it.
```

**Automations.** Let the controller's weekly time programs do the daily switching between comfort and eco, and use Home Assistant for exceptions: "Programmwahl" to *Sparen* while nobody is home, "Zeitprogramm" 2 or 3 for holidays, "1x Warmwasser" on PV surplus, back to *Auto* afterwards. Rebuilding a schedule with automations works, but every switch is a write to the controller, and if Home Assistant or the cloud is down at the switching time the heating stays in the last written mode. The controller's own program keeps running without either.

## Examples

### Electricity use, Energy dashboard and COP without an electricity meter

Without an S0 electricity meter the portal reports "Verbrauch", "JAZ", "TAZ" and "MAZ" as 0. The live power sensor "Leistungsaufnahme (WP + EHZ)" (`power_consumption_wp_ehz`) still carries real values, so Home Assistant can integrate it into kWh.

**Accuracy.** The result is an estimate of ±15 to 20 %: the controller reports power in 0.1 kW steps and Home Assistant samples it at the poll interval. As a check, integrating "Aktuelle Sekundärleistung" the same way gave 16 % more heat than Wolf's own counter over 14 days. See the [measurement](docs/phase2-measurements.md#2026-11-20--electricity-estimate-and-cop-without-an-s0-meter-recorder-read-only). Do not use it for billing.

Entity IDs differ per installation: replace the `sensor.wolf_*` IDs below with the IDs of your entities (find them by the Wolf label or the [translation key](#translation-keys)). Put the YAML into `configuration.yaml` (or a package) and restart. The "Integral" and "Utility Meter" helpers under Settings › Devices & services › Helpers give the same result without YAML.

**1. Electricity estimate** from "Leistungsaufnahme (WP + EHZ)" (`power_consumption_wp_ehz`, kW):

```yaml
sensor:
  - platform: integration
    source: sensor.wolf_power_consumption_hp_ehz
    name: Wolf electricity estimate
    unique_id: wolf_electricity_estimate
    unit_time: h
    round: 3
    max_sub_interval: "00:10:00"
```

The source is in kW and the time unit is hours, so the result is in kWh. `max_sub_interval` keeps the sum growing while the power value does not change.

**2. Energy dashboard.** Settings › Dashboards › Energy › *Individual devices* › *Add device*, then pick `sensor.wolf_electricity_estimate`. Home Assistant 2026.10 accepts an individual device only with an energy sensor (`stat_consumption`); a power sensor alone is not enough, which is why step 1 comes first. Optionally the device entry also takes the power sensor for live power.

**3. COP** = heat from "Energiemenge HZ" (`energy_amount_htg`) plus "Energiemenge WW" (`energy_amount_dhw`) divided by the estimated electricity over the same period. Two daily utility meters take the heat difference and the electricity, a template sensor divides them:

```yaml
utility_meter:
  wolf_electricity_daily:
    source: sensor.wolf_electricity_estimate
    cycle: daily
  wolf_heat_htg_daily:
    source: sensor.wolf_energy_amount_htg
    cycle: daily
  wolf_heat_dhw_daily:
    source: sensor.wolf_energy_amount_dhw
    cycle: daily

template:
  - sensor:
      - name: Wolf COP (daily)
        unique_id: wolf_cop_daily
        state_class: measurement
        availability: "{{ states('sensor.wolf_electricity_daily') | float(0) > 0.5 }}"
        state: >
          {{ ((states('sensor.wolf_heat_htg_daily') | float(0)
               + states('sensor.wolf_heat_dhw_daily') | float(0))
              / states('sensor.wolf_electricity_daily') | float(1)) | round(2) }}
```

The sensor is unavailable until the day's estimate passes 0.5 kWh. A daily value is noisy; use `cycle: weekly` or `monthly` for a steadier number. In the 14-day measurement the COP was about 5.4.

### Dashboard section with built-in cards

A "Wolf heating" section for a [sections view](https://www.home-assistant.io/dashboards/sections/), made only of built-in `heading` and `tile` cards. Open the dashboard, switch to *Edit* › the three-dots menu › *Raw configuration editor*, and paste the section into the `sections:` list of a view with `type: sections`.

Replace the `*.wolf_*` entity IDs with the IDs of your entities (find them by the Wolf label or the [translation key](#translation-keys)); the comments name both.

```yaml
- type: grid
  cards:
    - type: heading
      heading: Wolf heating
      heading_style: title
      icon: mdi:heat-pump
    # Warmwassertemperatur, dhw_temperature
    - type: tile
      entity: sensor.wolf_dhw_temperature
      name: Hot water
    # Warmwassersolltemperatur eingestellt, set_dhw_temperature (number, writes)
    - type: tile
      entity: number.wolf_set_dhw_temperature
      name: Hot water setpoint
    # 1x Warmwasser, one_time_dhw_charge (switch, writes)
    - type: tile
      entity: switch.wolf_one_time_dhw_charge
      name: One-time hot water charge
    # Programmwahl (Heizung), program_heating (select, writes)
    - type: tile
      entity: select.wolf_program_heating
      name: Heating program
    # Außentemperatur (Heizung), outside_temperature
    - type: tile
      entity: sensor.wolf_outside_temperature
      name: Outside
    # Vorlauftemperatur, flow_temperature
    - type: tile
      entity: sensor.wolf_flow_temperature
      name: Flow
```

A card whose entity does not exist on your installation shows "Entity not found"; delete that card. The number, switch and select tiles write to the controller's EEPROM like any other write ([Writing](#writing)).

### Blueprint: hot water charge on PV surplus

The blueprint turns on "1x Warmwasser" (`one_time_dhw_charge`) once per PV surplus episode. It never turns the switch off: the controller ends the charge itself, in the measurement after about 16 minutes ([discovery](docs/discovery.md), sections 14 and 15). The controller's weekly program stays the baseline; this is an exception on top of it.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Ftibuntu%2Fhomeassistant-wolf-smartset%2Fmain%2Fblueprints%2Fautomation%2Fwolf_smartset%2Fdhw_charge_on_pv_surplus.yaml)

HACS installs only the integration, so import the blueprint with the badge. The automation starts when the surplus has stayed above the threshold for the hold time (one start per crossing) and then checks the conditions below. Inputs:

| Input | Default | Meaning |
|---|---|---|
| PV surplus power | none | Power sensor in W, positive when power is fed into the grid. |
| Surplus threshold | 1500 W | Surplus that starts the charge. |
| Hold time | 10 min | How long the surplus must stay above the threshold. |
| Hot water temperature | none | Temperature sensor of the tank. |
| Hot water temperature limit | 45 °C | No charge at or above this temperature. |
| Cooldown | 180 min | Minimum time since the last run of the automation. |
| One-time hot water charge switch | none | The "1x Warmwasser" switch (only switches of this integration are offered). |

The conditions are: hot water temperature below the limit, the switch is off, and the last run is longer ago than the cooldown. Every run is a write to the controller ([Writing](#writing)); with dry run on, the default, the automation runs, nothing reaches the heat pump and the switch snaps back. Switch dry run off only when you want real charges.

The automation fires when the surplus crosses the threshold. If a condition blocks it at that moment (warm tank, cooldown, switch already on), it waits for the next crossing. The surplus sensor and the threshold must use the same unit (W by default); with a kW sensor, set the threshold in kW.

## Removal

Settings › Devices & services › Wolf SmartSet › three-dot menu › *Delete*. This removes the entry, its devices and entities. The write history `.storage/wolf_smartset.<entry_id>.history` stays behind; delete it by hand if you want it gone. Re-enable the core "Wolf SmartSet Service" integration afterwards if you still need it.

## Known limitations

- Time programs: the selector of the active weekly program (1, 2 or 3) is a `select`. The day schedules, dates, times, party and holiday mode are not mapped yet ([concept](docs/time-programs.md)).
- Entity names are Wolf's German labels, the same as in the SmartSet app and the manuals. Curated parameters (see [Translation keys](#translation-keys)) are translated and show English names on non-German systems.
- The interface is unofficial. Wolf changes the login flow several times a year; a broken login shows as "portal unavailable" until a fix is released.
- Only one installation (Wolf CHA heat pump with BM-2 and MM1, Link home gateway) has been tested so far.
- Every poll re-activates its bundles (`GuiIdChanged: true`). Without that, the gateway froze user-level values for about 70 minutes after many restarts and expert (Fachmann) values until the next daily description refresh. Since 0.6.1 both update every poll ([measurement](docs/phase2-measurements.md)).

## Troubleshooting

- **Repair issue "throttles … or blocks the login"**: the portal answered several polls with throttling or empty responses, or the login is blocked after repeated failures (five minutes, doubling up to an hour). The integration polls less often until the portal answers again. The block also holds across Home Assistant restarts, so restarting does not speed it up. Check that no other client logs in with this account from your network.
- **All entities unavailable**: check the *Connectivity* diagnostic sensor on the system device. `off` means the gateway is offline (power, network at home); `unavailable` means the portal itself did not answer (throttling, login, maintenance).
- **Repair issue "core integration is active"**: disable the core integration for the same account (see Installation).
- **Re-authentication prompt**: the portal rejected the password. Enter the current one.
- **Diagnostics**: Settings › Devices & services › Wolf SmartSet › three-dot menu › *Download diagnostics*. The file contains login statistics, the write history and, per system, the parsed parameter model, the raw parameter description and the current values (about 0.7 MB). Credentials, system and gateway IDs, the system name and personal fields are redacted; the values of serial numbers, IP and MAC addresses, dates, times and switch times are blanked. A maintainer can turn the file into a test fixture for your installation.
- **A write shows "not applied"**: the controller still reported another value when the settle window (one poll interval plus 30 s, at least 5 minutes) had passed; the *Write result* event entity fires `not_applied` and a warning is logged. A dependent setting in the controller may limit the parameter.
