# Wolf SmartSet (read/write) for Home Assistant

Custom integration for Wolf heating systems connected to the Wolf SmartSet cloud. It uses the same unofficial interface as the SmartSet portal and app. It reads every parameter of the system and can write settings such as the DHW setpoint, the operating mode or "1x Warmwasser". Writing is off until you switch off the dry run.

Wolf does not support third-party access. Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Installation

1. In HACS open *Integrations*, then the three-dot menu, then *Custom repositories*. Add `https://github.com/tibuntu/homeassistant-wolf-smartset` with category *Integration*.
2. Install "Wolf SmartSet (read/write)" and restart Home Assistant.
3. If the core integration "Wolf SmartSet Service" (`wolflink`) is set up for the same account, disable it first: Settings › Devices & services › Wolf SmartSet Service › three-dot menu › *Disable*. Two integrations on one account log in from the same IP address, and Wolf blocks the address for up to an hour after too many logins. The block also hits the SmartSet app.
4. Settings › Devices & services › *Add integration* › "Wolf SmartSet (read/write)".

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

## Removal

Settings › Devices & services › Wolf SmartSet › three-dot menu › *Delete*. This removes the entry, its devices and entities. The write history `.storage/wolf_smartset.<entry_id>.history` stays behind; delete it by hand if you want it gone. Re-enable the core "Wolf SmartSet Service" integration afterwards if you still need it.

## Known limitations

- Time programs, dates, times, party and holiday mode are not mapped yet ([concept](docs/time-programs.md)).
- Entity names are Wolf's German labels, the same as in the SmartSet app and the manuals.
- The interface is unofficial. Wolf changes the login flow several times a year; a broken login shows as "portal unavailable" until a fix is released.
- Only one installation (Wolf CHA heat pump with BM-2 and MM1, Link home gateway) has been tested so far.
- The icon under `brand/` is a neutral placeholder. An entry in [home-assistant/brands](https://github.com/home-assistant/brands) is a follow-up.

## Troubleshooting

- **Repair issue "throttles … or blocks the login"**: the portal answered several polls with throttling or empty responses, or the login is blocked after repeated failures (five minutes, doubling up to an hour). The integration polls less often until the portal answers again. The block also holds across Home Assistant restarts, so restarting does not speed it up. Check that no other client logs in with this account from your network.
- **Repair issue "core integration is active"**: disable the core integration for the same account (see Installation).
- **Re-authentication prompt**: the portal rejected the password. Enter the current one.
- **Diagnostics**: Settings › Devices & services › Wolf SmartSet › three-dot menu › *Download diagnostics*. The file contains the parsed parameter model, the write history and login statistics, with credentials and identifiers redacted.
- **A write shows "not applied"**: the controller reported another value after the write. Expert parameters may need an expert session; user-level parameters may be limited by a dependent setting in the controller.
