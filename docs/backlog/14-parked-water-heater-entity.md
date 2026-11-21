# 14 – water_heater entity (parked)

Status: parked · Rules: [README](README.md#rules-for-every-brief)

## Idea

A `water_heater` entity that combines the DHW temperature (`dhw_temperature`), the DHW setpoint (`set_dhw_temperature`) and the DHW program (`program_dhw`), for Home Assistant's native water heater card and for voice control. Peer integrations offer one (reported: ViCare, Luxtronik).

## Why parked

- The owner decided against the sibling `climate` entity, and ADR-Model-002 put both out of scope: "`climate` and `water_heater` entities are explicitly out of scope until the generic platforms work on the owner's system."
- It would duplicate three entities that exist.
- It would hard-code a mapping verified on one installation; other heat generators use other parameter IDs for the same functions (`docs/discovery.md`, section 4.10).

## Cheaper alternative

Reported, not verified: since Home Assistant 2026.11 the Template integration can create `water_heater` entities. A README recipe that wraps the three entities gives users the card and voice control without code in this integration. It belongs in the README section "Examples".

## Revisit when

The owner asks for it, or users request voice or card control of DHW. Start with the template recipe; build an entity only if the recipe proves insufficient.
