# Time programs and timed functions – concept (no implementation yet)

Status: analysis for a later phase. Nothing described here is implemented. Source: the recorded description of the owner's CHA heat pump with BM-2 (`tests/fixtures/real/description_0.json`) and the portal JavaScript (`EnControlType`, discovery section 4.3). Example values below are illustrative, not the owner's schedule.

## 1. What is unmapped today

63 of 288 parameters have no entity type:

| ControlType | Name in the portal | Count | Examples |
|---|---|---|---|
| 14 | `DaySwitchTimes` | 42 | "Mo" … "So" of each time program |
| 10 | `TimeInput` | 10 | "Uhrzeit Start/Ende" of party and holiday mode, "Uhrzeit BM2" |
| 9 | `DateInput` | 7 | "Datum Start/Ende" of party and holiday mode, "Datum BM2" |
| 13 | `TimeProgram` | 2 | "Zeitprogramm" (heating circuit, DHW): selects program 1, 2 or 3 |
| 24 | `TimedFunction` | 2 | "Partymodus", "Urlaubsmodus" |

Containers without data point (`ValueId 0`, `NoDataPoint`) such as "Zeitprogramm 1" (`ControlType 19`, `TimeSubProgram`) are already skipped by the model.

## 2. Raw structure

### 2.1 Weekly time programs

```text
Zeitprogramm            ValueId 36001600001  CT 13  ListItems 1/2/3   Value "1"   SubBundleId 400
├─ Zeitprogramm 1       ValueId 0            CT 19  (container)
│  ├─ Mo                ValueId 32006300001  CT 14  Unit "Uhr"  Value "HH:MM-HH:MM;HH:MM-HH:MM;…" (5 slots)
│  ├─ Di … So           ValueId 32006400001 … 32006900001
├─ Zeitprogramm 2       (container, days 32007000001 …)
└─ Zeitprogramm 3       (container, days 32007700001 …)
```

- One selector per circuit (heating circuit 36001600001, DHW 35000400000) chooses which of three weekly programs is active. It is a normal list parameter (`ControlType 13`, writable, list items 1 to 3) and could be a `select` today.
- Each program has seven day parameters, each with its own `ValueId`. The value is one string with **five switching slots**, `start-end` separated by `;`. Unused slots are `00:00-00:00`. Example: `05:00-07:00;16:00-22:00;00:00-00:00;00:00-00:00;00:00-00:00`.
- All day parameters carry `IsReadOnly: false`, `Unit: "Uhr"`, `Group` = weekday abbreviation, and `SubBundleId 0`; the selector and containers use `SubBundleId 400`.
- Programs exist for the heating circuit (MK, prefix 36/32…01) and DHW (prefix 35/32…00). Circulation or ventilation programs exist on other systems ("Zeitprogramm Zirkulation Heizgerät", "Zeitprogramm Lüftung" in the wolf-comm examples).

### 2.2 Timed functions (party and holiday mode)

```text
Partymodus              ValueId 22003400000  CT 24  ListItems 0 Deaktiviert / 1 Aktiviert   SubBundleId 4100
├─ Uhrzeit Ende         ValueId 33000000000  CT 10  "HH:MM"
├─ Datum Ende           ValueId 33000100000  CT 9   "DD.MM.YYYY"
├─ Uhrzeit Start        ValueId 33000200000  CT 10
├─ Datum Start          ValueId 33000300000  CT 9
├─ Uhrzeit BM2          ValueId 33000400000  CT 10  (controller clock)
└─ Datum BM2            ValueId 33000500000  CT 9   (controller clock)
Urlaubsmodus            ValueId 22003500000  CT 24  same structure, ValueIds 33000600000 …, SubBundleId 4200
```

- The parent has `PreloadChilds: true`, `FunctionOnMessage` with placeholders `{0}`/`{1}` for start and end, and `HintDescription`.
- Start and end are separate date and time values in German formats.
- "Uhrzeit/Datum BM2" is the controller's current clock, shown for reference.

## 3. How the portal handles them (from the portal JavaScript)

- Time programs and timed functions open a sub dialog (`DisplayControlType.hasSubDialog`: `TimedFunction`, `TimeProgram`, `TimeProgramDayOrWeek`, …).
- While a sub dialog is open, the portal reads its **sub bundle** (`IsSubBundle: true`, `BundleId` = `SubBundleId`) and calls `DeactivatePushBundle` when the dialog closes. Reading these values through the normal bundle may therefore return stale data; this needs a measurement.
- `WriteParameterValues` takes a **list** of values. The portal sends all changed values of a dialog in one request, for example start date, start time, end date, end time and the activation flag of the party mode. Our client writes exactly one value per request today.

## 4. Options for Home Assistant

| Option | Fit | Effort | Notes |
|---|---|---|---|
| A. `select` for the program selector (CT 13) | good | low | Already a normal list parameter; switching between three predefined programs covers many automations (for example "away" program). |
| B. One `text` entity per day and program, validated against the 5-slot format | poor | low | 42 entities, cryptic strings, easy to break a schedule by a typo. |
| C. A `time_program` entity per program with attributes, written by one service with `dry_run` | medium | medium | Services were discouraged in the Core review but accepted for things that do not fit an entity. |
| D. Sync with a Home Assistant `schedule` helper | good UX | high | HA schedules have unlimited blocks per day; Wolf has five per day and three programs. Needs a lossy mapping and conflict rules. |
| E. Party and holiday mode as `switch` plus `datetime` start/end | good | medium | Needs a multi-value write (all four values plus the flag in one request) and the sub bundle read. |

## 5. Recommendation

1. **Next:** option A for the program selectors. It needs no new write path and no new entity type: map `ControlType 13` to `select` with its list items. The day values stay unmapped.
2. **Later, separately:** option E for party and holiday mode, after a multi-value `write_values` in the client and a measurement of sub-bundle reads.
3. **Not planned:** option B. Options C and D only if there is a concrete use case that A cannot cover.

## 6. Open questions (to measure, read-only first)

1. Do the day values (CT 14) update through the normal bundle 1000, or only through sub bundle 400 with `IsSubBundle: true`?
2. Does writing one day string change only that day, and does the controller accept fewer than five slots?
3. For party mode: must start and end be written together with the activation flag in one request, and in which order does the portal send them?
4. Is "Uhrzeit/Datum BM2" writable from the portal, and should it ever be (clock sync)? Probably no.
5. Does the EEPROM concern apply to time programs the same way (every day string is one write)?
