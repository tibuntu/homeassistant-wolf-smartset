# 10 – Config entry functions return None

Status: ready, the test pin now brings Home Assistant 2026.11.3; the claim is reported, not verified · Size: small · Rules: [README](README.md#rules-for-every-brief)

## Trigger

The test dependency moved to the Core-maintained `pytest-homeassistant` (2026.11.3, brings Home Assistant 2026.11.3); `pytest-homeassistant-custom-component` stopped at 0.13.375 with 2026.10.4. Start any time.

## Claim (reported)

Home Assistant developer blog, 2026-10-23: the config entry setup, unload and migrate functions are to return `None`. <https://contributors.home-assistant.io/blog/2026/10/23/config-entry-methods-return-none/>

## Affected here (verified)

- `__init__.py`, `async_setup_entry` returns `True`.
- `__init__.py`, `async_unload_entry` returns the result of `async_unload_platforms` and closes the portal session and the HTTP client only when that result is true. The new contract has to say what replaces a `False` return.

## Also reported in the same research; check in the same pass

- Omitting `step_id` in flow results is deprecated and stops working in 2027.5 (`config_flow.py`).
- The device info constants in `homeassistant.const` are deprecated, blog 2026-11-10 (`entity.py`).
- `UNDEFINED` is replaced by `Undefined`, blog 2026-11-01.

## Steps

1. Read the blog posts and the matching source in the bumped environment (`homeassistant/config_entries.py` for the main claim). Done when each of the four claims is marked "confirmed" or "does not apply here", with the source line.
2. Run the test suite on the bumped pin and collect every deprecation warning that names `wolf_smartset`.
3. Adapt the code for the confirmed claims. The minimum version in `hacs.json` must keep working: if the new contract is not accepted there, keep the old form and record until which Home Assistant version, or raise the minimum with the owner's agreement.

## Done when

The merge gate is green on the bumped pin, the test run shows no deprecation warning from this integration, and the pull request description lists the four claims with their outcome.
