"""Diagnostics do not leak credentials or identifiers."""

import copy
from dataclasses import asdict, replace
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant.typing import ClientSessionGenerator

from custom_components.wolf_smartset.api import System, Value
from custom_components.wolf_smartset.const import CONF_DRY_RUN, CONF_SYSTEMS, DOMAIN
from custom_components.wolf_smartset.model import parse_description
from custom_components.wolf_smartset.redact import (
    DESCRIPTOR_TEXTS,
    FAKE_IDS,
    SECRET_CONTROL_TYPES,
    SECRET_KEYS,
    redact_description,
    secret_value_ids,
)

from .conftest import FAULTS, FIXTURES, SEED

# One name per alternative of redact.SECRET_PARAMETER, on a non-secret control type (6).
SECRET_NAMES = (
    "ISM Seriennummer",
    "Seriennr.",
    "Serial number",
    "MAC Adresse",
    "IP Adresse",
    "IP-Adresse",
    "IPAdresse",
    "Gateway",
    "DNS Server",
    "Subnetzmaske",
    "Anlagenname",
    "Herstelldatum",
)
SYSTEM_ID, GATEWAY_ID = 731900417, 731900829


async def test_redaction(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Username, password, system and gateway IDs are redacted."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, mock_config_entry)
    text = json.dumps(result)
    for secret in ("user@example.com", "secret", "5678", '"Home"'):
        assert secret not in text
    assert result["systems"][0]["kinds"]["switch"] == 1
    assert result["client"]["login_blocked_seconds"] == 0
    assert result["writes"] == {"dry_run": True, "max_writes_per_hour": 20, "history": []}


async def test_write_response_in_diagnostics_is_redacted(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The last 50 history records, response included, show no identifiers."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={CONF_DRY_RUN: False})
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    mock_client.write_value.return_value = {
        "Values": [{"ValueId": 35000900000, "State": 1}],
        "SystemId": 1234,
        "GatewayId": 5678,
    }
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, "1234_35000900000")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 55}, blocking=True
    )

    result = await get_diagnostics_for_config_entry(hass, hass_client, mock_config_entry)
    record = result["writes"]["history"][-1]
    assert "system_id" not in record
    assert record["response"] == {
        "Values": [{"ValueId": 35000900000, "State": 1}],
        "SystemId": "**REDACTED**",
        "GatewayId": "**REDACTED**",
    }


async def test_no_planted_marker_leaks(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: MagicMock,
    description: dict[str, Any],
) -> None:
    """A marker in every field class the redaction covers; none reaches the file.

    Classes: each identifier key (fake-ID keys and personal fields), as listed and in
    camelCase, lower and upper case, at the top level of the description, in its fault
    device list, in a tab under MenuItems (where only the descriptor texts Name and
    Description stay) and in a write response; an editable group title; each secret
    control type; each name the secret pattern matches; the system and gateway IDs, the
    share ID and the system name; username and password.
    """
    markers: list[str] = []
    numbers: list[int] = [SYSTEM_ID, GATEWAY_ID]

    def mark(field_class: str) -> str:
        markers.append(f"LEAK-{field_class}")
        return markers[-1]

    def number() -> int:
        numbers.append(731901000 + len(numbers))
        return numbers[-1]

    def identifiers(where: str, keep: frozenset[str] = frozenset()) -> dict[str, Any]:
        # Each key as listed, in camelCase, lower and upper case: the portal mixes DTO styles.
        def casings(key: str) -> set[str]:
            return {key, key[0].lower() + key[1:], key.lower(), key.upper()}

        return {k: number() for key in FAKE_IDS for k in casings(key)} | {
            k: mark(f"{where}-{k}")
            for key in SECRET_KEYS
            for k in casings(key)
            if k.casefold() not in keep
        }

    description.update(identifiers("top"))
    description["DynFaultMessageDevices"] = [identifiers("fault-device")]
    tab = description["MenuItems"][0]["TabViews"][0]
    tab.update(identifiers("tab", keep=DESCRIPTOR_TEXTS))
    tab.setdefault("TabViewGroups", []).append(
        {"GroupName": mark("editable-group-title"), "IsTitleEditable": True}
    )

    planted: dict[int, str] = {}

    def descriptor(control_type: int, name: str, field_class: str) -> dict[str, Any]:
        value_id = 990000000001 + len(planted)
        planted[value_id] = mark(field_class)
        return {
            "ValueId": value_id,
            "ParameterId": value_id,
            "Name": name,
            "Group": "Test",
            "ControlType": control_type,
            "IsReadOnly": True,
            "Value": planted[value_id],
        }

    tab["ParameterDescriptors"] += [
        descriptor(ct, f"Feld {ct}", f"control-type-{ct}") for ct in sorted(SECRET_CONTROL_TYPES)
    ] + [descriptor(6, name, f"name-{name}") for name in SECRET_NAMES]
    # The fault response: identifiers at the top level and in a current fault entry, whose
    # Wolf text (Description) is kept on purpose; device labels and gateway payloads.
    faults = copy.deepcopy(FAULTS) | identifiers("fault-top")
    faults["CurrentMessages"] = [
        {"ErrorCode": 107, "Description": "Druck Heizkreis", "Device": mark("fault-entry-device")}
        | identifiers("fault-entry", keep=frozenset({"description"}))
    ]
    faults["HistoryMessages"][0]["Device"] = mark("fault-history-device")
    faults["CommitFaultMessageEntries"] = [{"DeviceShortName": mark("fault-commit-device")}]
    faults["GatewayEvents"] = [{"EventType": 1, "Payload": mark("fault-gateway-payload")}]
    mock_client.read_fault_messages = AsyncMock(return_value=faults)
    # Polls return the markers too, not only the values embedded in the description.
    mock_client.get_values = AsyncMock(
        side_effect=lambda system, bundle, ids, first=False: [
            Value(i, planted.get(i) or SEED[i], 1) for i in ids
        ]
    )
    system = System(SYSTEM_ID, GATEWAY_ID, mark("system-name"), number())
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=mark("title"),
        data={
            CONF_USERNAME: mark("username"),
            CONF_PASSWORD: mark("password"),
            CONF_SYSTEMS: [asdict(system)],
        },
        options={CONF_DRY_RUN: False},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # The model drops embedded dates and times and no entity polls them; a future one might.
    next(iter(entry.runtime_data.coordinators.values())).data.update(planted)
    mock_client.write_value.return_value = {
        "Values": [{"ValueId": 35000900000, "State": 1} | identifiers("write-value")],
        **identifiers("write-response"),
    }
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{SYSTEM_ID}_35000900000")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 55}, blocking=True
    )

    result = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = json.dumps(result)
    assert [m for m in markers if m in text] == []
    assert [n for n in numbers if str(n) in text] == []
    # The planted parameters did reach the file, blanked.
    values = result["systems"][0]["values"]
    assert {values[str(value_id)] for value_id in planted} == {"**REDACTED**"}
    assert result["writes"]["history"][-1]["response"]["SystemId"] == "**REDACTED**"
    # The fault response did reach the file, with Wolf's fault text.
    assert result["systems"][0]["faults"]["CurrentMessages"][0]["Description"] == "Druck Heizkreis"
    assert result["systems"][0]["faults"]["SystemName"] == "**REDACTED**"


async def test_description_round_trip(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The description from the file parses to the same model as the recorded fixture."""
    original = json.loads((FIXTURES / "real" / "description_0.json").read_text(encoding="utf-8"))
    mock_client.get_description.return_value = original
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, mock_config_entry)
    before = parse_description(original)
    after = parse_description(result["systems"][0]["description"])
    secret = secret_value_ids(original)

    def comparable(model: Any) -> dict[int, Any]:
        # IDs, kinds, bundles, devices, limits, options, occurrences; secret values blanked.
        return {
            pid: replace(p, value=None) if p.value_id in secret else p
            for pid, p in model.parameters.items()
        }

    assert comparable(after) == comparable(before)
    assert after.devices == before.devices
    assert len(before.parameters) > 250


def test_secret_value_is_blanked_in_every_duplicate() -> None:
    """A hidden copy (control type 31) of the real date descriptor leaks nothing.

    The real description repeats ValueIds across descriptors (36008500001 as 6 and 31).
    """
    description = json.loads((FIXTURES / "real" / "description_0.json").read_text(encoding="utf-8"))

    def lists(node: Any) -> Any:
        if isinstance(node, list):
            yield node
            for item in node:
                yield from lists(item)
        elif isinstance(node, dict):
            for value in node.values():
                yield from lists(value)

    siblings, date = next(
        (items, d)
        for items in lists(description["MenuItems"])
        for d in items
        if isinstance(d, dict) and d.get("ControlType") == 9 and d.get("Name") == "Datum"
    )
    siblings.append(
        {"ValueId": date["ValueId"], "Name": "Datum", "ControlType": 31, "Value": "LEAK-dup"}
    )
    assert "LEAK-dup" not in json.dumps(redact_description(description))
