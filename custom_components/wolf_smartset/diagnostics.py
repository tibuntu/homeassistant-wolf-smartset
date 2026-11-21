"""Diagnostics with credentials and identifiers redacted."""

from collections import Counter
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import WolfConfigEntry, WolfSystemCoordinator
from .redact import REDACTED, redact_description, secret_value_ids

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "id", "gateway_id", "name", "share_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WolfConfigEntry
) -> dict[str, Any]:
    """Login statistics, write history, and per system the model, description and values."""
    runtime = entry.runtime_data
    return {
        "entry": async_redact_data(
            {"title": entry.title, "data": dict(entry.data), "options": dict(entry.options)},
            TO_REDACT,
        ),
        "client": {
            "login_count": runtime.client.login_count,
            "last_login": runtime.client.last_login and runtime.client.last_login.isoformat(),
            "login_blocked_seconds": runtime.client.login_blocked_seconds,
        },
        "writes": {
            "dry_run": runtime.writer.dry_run,
            "max_writes_per_hour": runtime.writer.max_writes_per_hour,
            # Last 50 attempts; the system id is dropped like everywhere else.
            "history": [
                {k: v for k, v in record.items() if k != "system_id"}
                for record in runtime.writer.history[-50:]
            ],
        },
        "systems": [
            {
                "access_level": c.access_level,
                "update_interval": c.update_interval and c.update_interval.total_seconds(),
                "last_update_success": c.last_update_success,
                "backoff_steps": c.backoff_steps,
                "unreadable_value_ids": sorted(c.unreadable),
                "active_parameter_ids": sorted(set(c.async_contexts())),
                "kinds": Counter(str(p.kind) for p in c.description.parameters.values()),
                "devices": sorted(c.description.devices.values()),
                "parameters": [
                    {
                        "parameter_id": p.parameter_id,
                        "label": p.label,
                        "kind": p.kind,
                        "control_type": p.control_type,
                        "writable": p.writable,
                        "expert": p.expert,
                        "bundle_id": p.bundle_id,
                        "device": p.device,
                        "unit": p.unit,
                        "limits": [p.minimum, p.maximum, p.step],
                    }
                    for p in c.description.parameters.values()
                ],
                # Fixture-grade: tests/fixtures/real/description_<n>.json and values.
                "description": redact_description(c.raw_description),
                "values": _values(c),
            }
            for c in runtime.coordinators.values()
        ],
    }


def _values(coordinator: WolfSystemCoordinator) -> dict[int, str | None]:
    """Current values by ValueId; serials, addresses, dates and times blanked."""
    secret = secret_value_ids(coordinator.raw_description)
    return {
        value_id: REDACTED if value_id in secret and value is not None else value
        for value_id, value in (coordinator.data or {}).items()
    }
