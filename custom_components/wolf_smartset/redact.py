"""Redaction of portal responses for the fixtures, the diagnostics and the write history.

The diagnostics file is posted in public issues: what is secret in a recorded
fixture is secret there too. One key set covers both, applied two ways: the
fixtures and the diagnostics get consistent fake IDs so they stay usable as test
data, the write history blanks every identifier (its stored format).
"""

import re
from typing import Any

REDACTED = "**REDACTED**"
# IDs are replaced consistently so the fixtures stay usable.
FAKE_IDS = {"Id": 1234, "SystemId": 1234, "GatewayId": 5678, "SystemShareId": 9012}
SECRET_KEYS = {
    "Name", "Description", "Comment", "ContactInformation", "Email", "UserName",
    "Firstname", "Surname", "Street", "City", "ZipCode", "Phone", "SerialNumber",
    "GatewayUsername", "SessionId",
}  # fmt: skip
ID_KEYS = frozenset(FAKE_IDS) | SECRET_KEYS
# Parameter, menu and option texts under MenuItems, needed to parse the description again.
DESCRIPTOR_TEXTS = frozenset({"Name", "Description"})
SECRET_PARAMETER = re.compile(
    r"seriennummer|serial|mac|ip adresse|gateway|dns|subnetz|anlagenname|herstell",
    re.IGNORECASE,
)
# text, IP, URL, password inputs; dates, times and day switch times (presence patterns)
SECRET_CONTROL_TYPES = {9, 10, 14, 20, 21, 22, 23}


def _is_secret(node: dict[str, Any]) -> bool:
    """A descriptor whose value identifies the installation or reveals presence."""
    return "ValueId" in node and bool(
        node.get("ControlType") in SECRET_CONTROL_TYPES
        or SECRET_PARAMETER.search(str(node.get("Name") or ""))
    )


def _redact(data: Any, keep: frozenset[str], blank_values: bool) -> Any:
    if isinstance(data, list):
        return [_redact(item, keep, blank_values) for item in data]
    if not isinstance(data, dict):
        return data
    result = {
        key: FAKE_IDS[key]
        if key in FAKE_IDS and value is not None
        else REDACTED
        if key in SECRET_KEYS and key not in keep and value
        else _redact(value, keep, blank_values)
        for key, value in data.items()
    }
    if blank_values and _is_secret(data):
        result["Value"] = REDACTED if data.get("Value") is not None else None
    return result


def redact_ids(data: Any) -> Any:
    """Replace system/gateway IDs and personal fields of non-descriptor objects."""
    return _redact(data, frozenset(), blank_values=False)


def redact_description(data: dict[str, Any]) -> dict[str, Any]:
    """Blank identifying values (serials, MAC, IP, system name, dates, times) and IDs.

    Descriptor texts under MenuItems stay, everything else gets redact_ids.
    """
    rest = _redact({k: v for k, v in data.items() if k != "MenuItems"}, frozenset(), True)
    return {
        k: _redact(v, DESCRIPTOR_TEXTS, True) if k == "MenuItems" else rest[k]
        for k, v in data.items()
    }


def secret_value_ids(description: Any) -> set[int]:
    """ValueIds whose values identify the installation (serials, addresses, dates, times)."""
    found: set[int] = set()

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if _is_secret(node):
                found.add(node["ValueId"])
            for value in node.values():
                walk(value)

    walk(description)
    return found


def redact_values(values: dict[str, Any], secret_ids: set[int]) -> dict[str, Any]:
    """Redact identifiers and blank the values of secret parameters."""
    result = redact_ids(values)
    for item in result.get("Values") or []:
        if item.get("ValueId") in secret_ids and item.get("Value") is not None:
            item["Value"] = REDACTED
    return result


def redact_response(data: Any) -> Any:
    """Blank every identifier key, falsy values included (format of the write history)."""
    if isinstance(data, list):
        return [redact_response(item) for item in data]
    if isinstance(data, dict):
        return {k: REDACTED if k in ID_KEYS else redact_response(v) for k, v in data.items()}
    return data
