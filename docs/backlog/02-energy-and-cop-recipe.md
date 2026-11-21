# 02 – Energy and COP recipe

Status: ready · Size: docs only · Commit type: `docs:` · Rules: [README](README.md#rules-for-every-brief)

## Why

Without an S0 electricity meter the portal reports `Verbrauch`, `JAZ`, `TAZ` and `MAZ` as 0. Issue #23 (COP/JAZ sensors) was closed as blocked because there was "nothing to divide by". The measurement below shows there is: the live power sensor carries real values. A recipe lets users estimate electricity use, feed the Energy dashboard and compute a COP without new code.

## Evidence

Measured on the owner's CHA, 335 hourly statistics rows:

| Entity (translation key) | Observation |
|---|---|
| `power_consumption_wp_ehz` | 0.0 to 3.0 kW in 0.1 kW steps, mean 0.546 kW, about 183 kWh |
| `current_secondary_power` | -15.1 to 15.0 kW (negative during defrost), mean 3.44 kW, about 1153 kWh |
| `energy_amount_htg` | 29044 to 29898 kWh (+854) |
| `energy_amount_dhw` | 11380 to 11520 kWh (+140) |
| `heat_generated_current_year` | +995 kWh |

- COP over the window: 994 kWh heat (Wolf's counters) / 183 kWh electricity (integrated power) = about 5.4.
- Accuracy: integrating the thermal power the same way gives 1153 kWh against 994 kWh on Wolf's own counter, 16 % too high. State the estimate as ±15 to 20 %.

Verified: in Home Assistant 2026.10.4 an individual device in the Energy dashboard needs an energy statistic (`DeviceConsumption.stat_consumption` in `homeassistant/components/energy/data.py`); a power sensor alone is not accepted there.

Reported: the 2026.10 release notes say the Energy configuration can derive energy from a power-only device. Check this in the UI of the minimum version in `hacs.json` and document whichever path exists.

## Deliverable

A section "Examples" in `README.md` with:

1. Electricity estimate: an Integral (Riemann sum) helper on `power_consumption_wp_ehz`, giving a kWh sensor.
2. Energy dashboard: that sensor as an individual device.
3. COP: heat from `energy_amount_htg` + `energy_amount_dhw` divided by the estimated electricity over the same period (for example two daily utility meters and a template sensor).
4. The accuracy statement with a link to the measurement.

Name entities by translation key and Wolf label; entity IDs differ per installation. A built-in derived sensor is out of scope: the helper already does it, and the integration would own the accuracy claim.

## Steps

1. Add a dated section to `docs/phase2-measurements.md` with the table and the two results above. Done when the README's accuracy statement can link to it.
2. Write the README section. Done when each of the four deliverables is present.
3. Validate every YAML snippet once, by loading it in a Home Assistant dev instance or a throwaway test with `async_setup_component`. Done when the pull request description shows the proof for each snippet.
4. Set `docs-examples` and `docs-use-cases` in `custom_components/wolf_smartset/quality_scale.yaml` to `done` once this brief and [03](03-pv-surplus-dhw-blueprint.md) have both landed.

## Done when

The steps are complete and the merge gate is green. Reopening or commenting on issue #23 is the owner's call; propose the text.
