# 07 – Registry cleanup on platform change

Status: ready · Size: small · Commit type: `fix:` · Rules: [README](README.md#rules-for-every-brief)

## Why

When a parameter moves to another platform, Home Assistant creates a new entity and keeps the old registry entry as a dead entity. Version 0.6.0 moved all expert numbers and selects to sensors, and the changelog told users to clean up and re-enable by hand. The integration can do both.

## Evidence

Measured in the owner's entity registry on 0.6.1:

- 94 unique IDs are registered on two domains: 67 as `number` and `sensor`, 27 as `select` and `sensor`. The `number` and `select` entries are dead.
- Three dead entries were enabled (Sparfaktor, Sockeltemperatur Heizkurve, Vorlauftemperatur Heizkurve). Their replacement sensors exist and are disabled, so these three values have had no live entity since the update.

Verified: `CHANGELOG.md`, 0.6.0, "BREAKING CHANGES" describes exactly this as a manual step.

## Rule to implement

After the platforms are set up in `async_setup_entry`, for each registry entry of this config entry:

- Its unique ID has the form `<system id>_<parameter id>`, the current model maps that parameter to another platform, and an entry with the same unique ID exists on that platform. Then the entry is stale.
- If the stale entry is enabled and its sibling is disabled by the integration, enable the sibling.
- Remove the stale entry.

Every other entry stays. In particular, an entry whose parameter is missing from the description is kept: a short portal problem must not delete a user's names and settings.

## Steps

1. Tests, with the registry seeded before setup:
   - enabled stale `number` plus disabled `sensor`: the number is gone, the sensor is enabled;
   - disabled stale `select`: gone, the sensor stays disabled;
   - a sibling the user disabled by hand stays disabled;
   - an entry for a parameter missing from the description is untouched;
   - the undo button and the connectivity sensor are untouched.
2. Implement in `__init__.py`. Enabling an entity makes Home Assistant reload the config entry shortly after; assert in a test that setup stays stable through that reload.
3. README: the sentence about entities "no longer provided" in the upgrade notes, if one exists outside the changelog, matches the new behaviour.

## Done when

The merge gate is green. After the release the owner can confirm on the real system: the registry then holds no unique ID of this integration on two domains.

This is not the Gold rule `stale-devices`, which is about devices and stays `todo`.
