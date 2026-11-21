"""Redaction helpers used by the fixture recorder."""

from custom_components.wolf_smartset.redact import (
    REDACTED,
    redact_faults,
    redact_values,
    secret_value_ids,
)

DESCRIPTION = {
    "MenuItems": [
        {
            "TabViews": [
                {
                    "ParameterDescriptors": [
                        {"ValueId": 1, "ControlType": 21, "Name": "IP Adresse"},
                        {"ValueId": 2, "ControlType": 6, "Name": "ISM Seriennummer"},
                        {"ValueId": 3, "ControlType": 6, "Name": "Kesseltemperatur"},
                        {
                            "ValueId": 4,
                            "ControlType": 13,
                            "Name": "Zeitprogramm",
                            "ChildParameterDescriptors": [
                                {"ValueId": 5, "ControlType": 14, "Name": "Mo"}
                            ],
                        },
                    ]
                }
            ]
        }
    ]
}


def test_secret_value_ids() -> None:
    """Text, IP, date and time inputs plus identifying names, children included."""
    assert secret_value_ids(DESCRIPTION) == {1, 2, 5}


def test_redact_faults() -> None:
    """IDs replaced, device labels blanked, fault texts of message entries kept."""
    message = {
        "Id": 77,
        "ErrorCode": 93,
        "Description": "Störung Wärmepumpe",
        "Device": "HG1",
        "OccurTimeLocal": "2026-11-21T08:00:00",
    }
    raw = {
        "LastRead": "2026-11-21T08:01:00",
        "MessagesChanged": True,
        "SystemId": 7,
        "GatewayId": 8,
        "CurrentMessages": [message],
        "HistoryMessages": [],
        "GatewayEvents": [{"EventType": 3, "Payload": "x", "Description": "y"}],
        "CommitFaultMessageEntries": [{"DeviceShortName": "WP", "DeviceIndex": 1}],
        "DeviceFaultMessages": [{"DeviceIndex": 1, "HistoryMessages": [message]}],
    }
    kept = {**message, "Id": 1234, "Device": REDACTED}
    assert redact_faults(raw) == {
        "LastRead": "2026-11-21T08:01:00",
        "MessagesChanged": True,
        "SystemId": 1234,
        "GatewayId": 5678,
        "CurrentMessages": [kept],
        "HistoryMessages": [],
        "GatewayEvents": [{"EventType": 3, "Payload": REDACTED, "Description": REDACTED}],
        "CommitFaultMessageEntries": [{"DeviceShortName": REDACTED, "DeviceIndex": 1}],
        "DeviceFaultMessages": [{"DeviceIndex": 1, "HistoryMessages": [kept]}],
    }


def test_redact_values() -> None:
    """Secret values are blanked, others kept, identifiers replaced."""
    values = {
        "SystemId": 7,
        "Values": [
            {"ValueId": 1, "Value": "10.0.0.1", "State": 1},
            {"ValueId": 3, "Value": "40", "State": 1},
            {"ValueId": 5, "State": 0},
        ],
    }
    assert redact_values(values, {1, 5}) == {
        "SystemId": 1234,
        "Values": [
            {"ValueId": 1, "Value": REDACTED, "State": 1},
            {"ValueId": 3, "Value": "40", "State": 1},
            {"ValueId": 5, "State": 0},
        ],
    }
