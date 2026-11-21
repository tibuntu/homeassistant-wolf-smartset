# 11 – Manifest categories

Status: ready · Size: one manifest key · Commit type: `fix:` (the manifest ships to users, so it needs a release) · Rules: [README](README.md#rules-for-every-brief)

## Why

The HACS validation already warns on every run that the manifest declares no categories.

## Evidence

Verified, HACS workflow run of 2026-11-20 on the default branch (`.github/workflows/hacs.yaml`):

```text
##[warning] <Integration …> The integration manifest has no categories, see https://contributors.home-assistant.io/core/integrations/categories/
```

Reported: `categories` is a list in `manifest.json` with dotted values such as `energy.ev_charging`; it is optional for custom integrations; the HACS action fails on a value it does not know. The allowed values were not confirmed. Background: <https://contributors.home-assistant.io/blog/2026/10/20/integration-categories/>

## Steps

1. Read the page linked in the warning and take the allowed values from it. Choose the value or values for a heating system and heat pump. Done when the choice is backed by a quote from that page.
2. Add `categories` to `custom_components/wolf_smartset/manifest.json`.
3. Open the pull request and read both validation logs.

## Done when

The hassfest and HACS workflows are green on the pull request and the HACS log no longer contains the categories warning.
