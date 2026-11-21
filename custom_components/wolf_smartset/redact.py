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
    "Name", "SystemName", "Description", "Comment", "ContactInformation", "Email", "UserName",
    "Firstname", "Surname", "Street", "City", "ZipCode", "Phone", "SerialNumber",
    "GatewayUsername", "SessionId", "MacAddress", "IpAddress",
}  # fmt: skip
# Keys are matched case-insensitively: the portal mixes PascalCase and camelCase DTOs.
_FAKE = {key.casefold(): value for key, value in FAKE_IDS.items()}
_SECRET = frozenset(key.casefold() for key in SECRET_KEYS)
_ID = frozenset(_FAKE) | _SECRET
# Parameter, menu and option texts under MenuItems, needed to parse the description again.
DESCRIPTOR_TEXTS = frozenset({"name", "description"})
SECRET_PARAMETER = re.compile(
    r"seriennummer|seriennr|serial|mac|ip[ -]?adresse|gateway|dns|subnetz|anlagenname|herstell",
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


def _redact(data: Any, keep: frozenset[str], secret: set[int] | None) -> Any:
    """Fake IDs, blank personal keys; with secret, blank Value of every node with such a ValueId."""
    if isinstance(data, list):
        return [_redact(item, keep, secret) for item in data]
    if not isinstance(data, dict):
        return data
    result: dict[str, Any] = {}
    for key, value in data.items():
        folded = key.casefold()
        if folded in _FAKE and value is not None:
            result[key] = _FAKE[folded]
        elif folded in _SECRET and folded not in keep and value:
            result[key] = REDACTED
        else:
            result[key] = _redact(value, keep, secret)
    if secret is not None:
        if data.get("ValueId") in secret:
            result["Value"] = REDACTED if data.get("Value") is not None else None
        # A group title the user can edit is free text ("Wohnung Mueller").
        if data.get("IsTitleEditable") and data.get("GroupName"):
            result["GroupName"] = REDACTED
    return result


def redact_ids(data: Any) -> Any:
    """Replace system/gateway IDs and personal fields of non-descriptor objects."""
    return _redact(data, frozenset(), None)


def redact_description(data: dict[str, Any]) -> dict[str, Any]:
    """Blank identifying values (serials, MAC, IP, system name, dates, times) and IDs.

    A secret ValueId is blanked in every descriptor that carries it, hidden duplicates
    included. Descriptor texts under MenuItems stay, everything else gets redact_ids.
    """
    secret = secret_value_ids(data)
    rest = _redact({k: v for k, v in data.items() if k != "MenuItems"}, frozenset(), secret)
    return {
        k: _redact(v, DESCRIPTOR_TEXTS, secret) if k == "MenuItems" else rest[k]
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


# Wolf's fault texts and codes ("Description", "ErrorCode") describe the fault, not the
# installation, and are the point of the recording. "Description" is in SECRET_KEYS, so
# it is kept only inside these message lists. Device labels and the gateway event
# payload are of unknown content and are blanked.
FAULT_MESSAGE_LISTS = {"CurrentMessages", "HistoryMessages"}
FAULT_SECRET_KEYS = {"Device", "DeviceName", "DeviceShortName", "Payload"}


def redact_faults(data: Any, in_message: bool = False) -> Any:
    """Redact a ReadFaultMessages response, keeping the fault texts of message entries."""
    if isinstance(data, list):
        return [redact_faults(item, in_message) for item in data]
    if not isinstance(data, dict):
        return data
    result: dict[str, Any] = {}
    for key, value in data.items():
        if in_message and key == "Description":
            result[key] = value
        elif key.casefold() in _FAKE and value is not None:
            result[key] = _FAKE[key.casefold()]
        elif (key.casefold() in _SECRET or key in FAULT_SECRET_KEYS) and value:
            result[key] = REDACTED
        else:
            result[key] = redact_faults(value, key in FAULT_MESSAGE_LISTS)
    return result


def redact_response(data: Any) -> Any:
    """Blank every identifier key, falsy values included (format of the write history)."""
    if isinstance(data, list):
        return [redact_response(item) for item in data]
    if isinstance(data, dict):
        return {k: REDACTED if k.casefold() in _ID else redact_response(v) for k, v in data.items()}
    return data
