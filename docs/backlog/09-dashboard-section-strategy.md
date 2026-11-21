# 09 – Dashboard section strategy

Status: needs owner decision (step 2); the platform claim is reported, not verified · Rules: [README](README.md#rules-for-every-brief)

## Context

The integration ships no frontend code. The research verdict of 2026-11-20 is to build no sidebar panel: the write history fits an event entity ([brief 01](01-write-result-event-entity.md)) and all settings fit the options flow.

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
