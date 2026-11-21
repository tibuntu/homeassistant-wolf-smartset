# 09 – Dashboard section strategy

Status: step 1 done (PR #53); needs owner decision (step 2) · Rules: [README](README.md#rules-for-every-brief)

## Context

The integration ships no frontend code. The research verdict of 2026-11-20 is to build no sidebar panel: the write history fits the write-result event entity (`event.py`) and all settings fit the options flow.

The frontend users have today is the third-party [Heat Pump Hydraulic Card](https://github.com/Sturmi77/heatpump-hydraulic-card). Its `wolf` preset finds this integration's entities by translation key (reported: card pull request 91, merged 2026-10-26). Gaps of that preset, as reported from the pull request text:

| Gap in the card | What would feed it |
|---|---|
| Fault codes (`errors` stays empty) | [brief 08](08-fault-message-endpoints.md) |
| Electricity counters (0 without an S0 meter) | README section "Examples"; a user-made helper has no translation key, so the card needs manual configuration |
| Heating circuits beyond the first | [brief 04](04-fixture-grade-diagnostics.md), which brings IDs from other installations |
| Room temperature | exists as `room_temperature`, disabled by default by design |
| Buffer temperature | nothing; manual in the card |

## Idea

Reported: Home Assistant 2026.11 adds custom section strategies (`strategyType: "section"`, element `ll-strategy-section-<name>`), offered under "Community sections" in the dashboard editor. A small JavaScript module could generate a "Wolf heating" section from built-in tile cards and resolve the entities by translation key, with no build step and no custom card.

Sources to check: <https://contributors.home-assistant.io/blog/2026/10/28/custom-section-strategies-in-the-dashboard-editor/> and <https://contributors.home-assistant.io/docs/frontend/custom-ui/custom-strategy>.

## Steps

1. Verify the claim on the two pages and in the frontend source of the target version. Note the minimum Home Assistant version; `hacs.json` currently requires 2026.10.0. Done when this file states what was confirmed, with links.
2. Ask the owner to choose: build the strategy, add a dashboard YAML example to the README instead (no JavaScript), or drop the idea.
3. If "build": write a design first (which tiles, which translation keys, what happens when a key is missing on an installation) and get it approved. Mechanics as reported, each to be verified in the Home Assistant source: serve the file with `hass.http.async_register_static_paths`, registered once per Home Assistant run; load it with `frontend.add_extra_js_url` and a `?v=<manifest version>` suffix against stale browser caches; add `http` and `frontend` to the manifest dependencies.

## Done when

Step 1 is written into this file and the owner's choice is recorded. Building is a separate plan.

## Step 1 result (2026-11-21)

Checked against the Home Assistant 2026.11.0 release. Core tag [`2026.11.0`](https://github.com/home-assistant/core/tree/2026.11.0) pins `home-assistant-frontend==20261028.4` ([frontend manifest](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/frontend/manifest.json)); the frontend source below is read at that tag, [`20261028.4`](https://github.com/home-assistant/frontend/tree/20261028.4). Core 2026.10.0 pins `20260930.2`.

| Claim | Result | Evidence |
|---|---|---|
| HA 2026.11 adds custom section strategies, registered with `strategyType: "section"` | confirmed | Blog 2026-10-28: "Push an entry to `window.customStrategies`, with `strategyType: "section"`". Code: [`lovelace_custom_strategies.ts`](https://github.com/home-assistant/frontend/blob/20261028.4/src/data/lovelace_custom_strategies.ts) (`strategyType: LovelaceStrategyConfigType`, which is `"dashboard" \| "view" \| "section"`). Entry fields per the [docs page](https://contributors.home-assistant.io/docs/frontend/custom-ui/custom-strategy): `type` (name without `custom:`), `strategyType`, `name`, `description`, `documentationURL`. |
| Element name `ll-strategy-section-<name>` | confirmed | [`get-strategy.ts`](https://github.com/home-assistant/frontend/blob/20261028.4/src/panels/lovelace/strategies/get-strategy.ts): ``tag: `ll-strategy-${configType}-${name}` ``. A legacy tag `ll-strategy-<name>` is also accepted. The element needs a static `generate(config, hass)`; the frontend waits at most 5 s for it to be defined. |
| Offered under "Community sections" in the dashboard editor | confirmed | Blog: "`Automatic section` lists the built-in section strategies, and the registered ones under `Community sections`". Code: [`hui-dialog-select-section-strategy.ts`](https://github.com/home-assistant/frontend/blob/20261028.4/src/panels/lovelace/editor/section-editor/hui-dialog-select-section-strategy.ts) lists `getCustomStrategiesForType("section")`; string `"custom": "Community sections"` in [`en.json`](https://github.com/home-assistant/frontend/blob/20261028.4/src/translations/en.json) under `select_section_strategy`. |
| Preview and editor are optional | confirmed (extra) | Without a static `getStubConfig(hass)` the tile has no preview; without `getConfigElement()` the user gets only the YAML editor. |

**Minimum version for the picker: Home Assistant 2026.11.0.** The dialog file does not exist in frontend `20260930.2` (HTTP 404 at that tag, i.e. core 2026.10.0) and exists in `20261028.0`, the first 2026.11 frontend release. `hacs.json` requires 2026.10.0, so the picker needs a bump of `homeassistant` to 2026.11.0 (this would drop 2026.10 users); the integration code itself would still load on 2026.10.

**Differs from the brief (changes the options):** the picker is new in 2026.11, but a section strategy used from YAML is not. At `20260930.2` (2026.10.0) `get-strategy.ts` already has the `section` strategy type and the `custom:` tag lookup `ll-strategy-section-<name>`, and `section.ts` already has `LovelaceStrategySectionConfig` / `isStrategySection`. So `sections: - strategy: {type: custom:<name>}` should render on 2026.10 as well, only without the editor dialog. Read from source, not run in a browser. The docs page shows this YAML form: `views: - type: sections, sections: - strategy: {type: custom:my-domain, domain: light}`.

Step 3 mechanics, against core `2026.11.0`:

| Claim | Result | Evidence |
|---|---|---|
| `hass.http.async_register_static_paths` | confirmed | [`http/server.py`](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/http/server.py): `async def async_register_static_paths(self, configs: Collection[StaticPathConfig]) -> None`; it is a coroutine. `StaticPathConfig` is a dataclass with `url_path: str`, `path: str`, `cache_headers: bool = True`, re-exported from `homeassistant.components.http`. `_make_static_resources` returns `None` for a `path` that is not a directory, so a single file is handled by the file-serving branch, not as a folder resource. |
| "Registered once per Home Assistant run" | not checked | Behaviour on a second registration of the same `url_path` (for example a config entry reload) was not read in aiohttp or core. Check this before building. |
| `frontend.add_extra_js_url` | confirmed, signature differs slightly | [`frontend/__init__.py`](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/frontend/__init__.py): `def add_extra_js_url(hass: HomeAssistant, url: str, es5: bool = False) -> None`, synchronous, adds to `hass.data[DATA_EXTRA_MODULE_URL]`. It does not interpret the URL, so a `?v=<manifest version>` suffix is passed through as written. |
| `http` and `frontend` as manifest dependencies | confirmed (names) | `frontend` itself depends on `http` and `lovelace`; `hass.data[DATA_EXTRA_MODULE_URL]` exists only once `frontend` is set up, so the `frontend` dependency is needed. |

Not verified in step 1: whether a built-in `tile` card resolves entities as the idea expects, and the translation-key lookup (needs `hass.entities` to expose `translation_key`, to be read in the design of step 3).
