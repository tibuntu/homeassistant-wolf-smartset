"""Redaction helpers of the fixture recorder."""

from scripts.record_fixtures import REDACTED, redact_values, secret_value_ids

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
