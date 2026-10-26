"""Parameter model against the heat-pump description (ADR-Model-011, ADR-Model-010)."""

import logging
from typing import Any

import pytest

from custom_components.wolf_smartset.model import Kind, parse_description, slugify


def test_one_time_dhw_is_a_switch(description: dict[str, Any]) -> None:
    """'1x Warmwasser' maps to the known switch on the system device."""
    p = parse_description(description).parameters[22004200000]
    assert (p.kind, p.writable, p.bundle_id, p.device, p.expert) == (
        Kind.SWITCH,
        True,
        1000,
        None,  # no submenu, ProtGrp or schema evidence: system device (ADR-Model-010)
        False,
    )
    assert p.options == {"0": "Aus", "1": "Ein"}


def test_writable_duplicate_wins(description: dict[str, Any]) -> None:
    """Sparfaktor is read-only under MM1 but writable under BM-2 settings (bundle 6300)."""
    p = parse_description(description).parameters[36000600001]
    assert {o.read_only for o in p.occurrences} == {True, False}
    assert (p.kind, p.bundle_id, p.device) == (Kind.NUMBER, 6300, "bedienmodul_bm_2_0")
    assert (p.minimum, p.maximum, p.step) == (0.0, 10.0, 0.5)
    assert p.expert


def test_overview_measurement_is_never_writable(description: dict[str, Any]) -> None:
    """ControlType 0 carries IsReadOnly false but is a measurement."""
    p = parse_description(description).parameters[27000600001]
    assert any(o.control_type == 0 and not o.read_only for o in p.occurrences)
    assert (p.kind, p.writable, p.unit, p.device) == (Kind.SENSOR, False, "°C", "heizgerat")


def test_hidden_duplicates_and_placeholders_are_skipped(description: dict[str, Any]) -> None:
    """ControlType 31 copies and ValueId 0 containers produce no parameter."""
    parameters = parse_description(description).parameters
    assert 36005800001 not in parameters  # hidden 'Programmwahl'
    assert all(p.value_id > 0 for p in parameters.values())


def test_select_and_labels(description: dict[str, Any]) -> None:
    """Both 'Programmwahl' parameters get the tab as distinguishing label."""
    parameters = parse_description(description).parameters
    heating, dhw = parameters[36005100001], parameters[35001200000]
    assert (heating.kind, dhw.kind) == (Kind.SELECT, Kind.SELECT)
    assert (heating.label, dhw.label) == ("Programmwahl (Heizung)", "Programmwahl (Warmwasser)")
    assert list(heating.options.values())[:3] == ["Standby", "Auto", "Permanent"]
    mapped = [p for p in parameters.values() if p.kind]
    assert len({(p.device, p.label) for p in mapped}) == len(mapped)


def test_time_program_selector_is_a_select(description: dict[str, Any]) -> None:
    """ControlType 13 chooses weekly program 1, 2 or 3; the day strings stay unmapped."""
    parameters = parse_description(description).parameters
    heating, dhw = parameters[36001600001], parameters[35000400000]
    assert (heating.kind, dhw.kind) == (Kind.SELECT, Kind.SELECT)
    assert (heating.label, dhw.label) == ("Zeitprogramm (Heizung)", "Zeitprogramm (Warmwasser)")
    assert heating.selectable == ["1", "2", "3"]
    assert parameters[32006300001].kind is None  # "Mo" of Zeitprogramm 1


def test_devices_from_expert_submenus(description: dict[str, Any]) -> None:
    """Every expert submenu is a device; user-only parameters stay on the system."""
    desc = parse_description(description)
    assert desc.devices == {
        "heizgerat": "Heizgerät",
        "bedienmodul_bm_2_0": "Bedienmodul BM-2 0",
        "mischermodul_mm1": "Mischermodul MM1",
        "ism": "ISM",
    }
    assert desc.parameters[35000900000].device is None  # DHW setpoint, user level only


def test_value_and_unknown_units_are_kept(description: dict[str, Any]) -> None:
    """Embedded current values seed entities; units wolf-comm drops survive."""
    parameters = parse_description(description).parameters
    assert parameters[35000900000].value == "50"
    assert parameters[27008700001].unit == "min"


def test_slugify() -> None:
    """Device keys are ASCII."""
    assert slugify("Bedienmodul BM-2 0") == "bedienmodul_bm_2_0"
    assert slugify("Heizgerät") == "heizgerat"


def test_device_needs_data_evidence(description: dict[str, Any]) -> None:
    """Schema configuration ports give a device; no ValueId-prefix guessing."""
    parameters = parse_description(description).parameters
    assert parameters[27004800001].device == "heizgerat"  # Verdichterfrequenz
    assert parameters[4000100001].device == "mischermodul_mm1"  # Ausgang MKP
    for system_level in (22004200000, 36005100001, 36002900001, 4007000001, 35000900000):
        assert parameters[system_level].device is None


def test_schema_ports_get_list_items_and_duplicates(description: dict[str, Any]) -> None:
    """Overview ports take list items from the schema configuration."""
    parameters = parse_description(description).parameters
    motor, pump = parameters[4000200001], parameters[4000100001]
    assert (motor.kind, motor.options) == (Kind.ENUM, {"0": "Aus", "1": "Zu", "2": "Auf"})
    assert (pump.kind, pump.port_function, pump.duplicate_of) == (
        Kind.ENUM,
        "Mischerkreispumpe",
        4007000001,
    )
    assert not pump.writable and not motor.writable


def test_enabled_by_default(description: dict[str, Any]) -> None:
    """Expert, schema-only, meter-dependent and optional-input values start disabled."""
    parameters = parse_description(description).parameters
    disabled = {p.label for p in parameters.values() if p.kind and not p.enabled_by_default}
    assert {
        "Ausgang MKP",
        "Verbrauch Vortag",
        "JAZ aktuelles Jahr",
        "TAZ Vortag",
        "MAZ aktueller Monat",
        "Raumtemperatur",
    } <= disabled
    for kept in (
        "Erzeugte Wärmemenge Vortag",
        "Mischerkreispumpe",
        "1x Warmwasser",
        "Verdichterfrequenz",
        "Mischermotor",
    ):
        assert kept not in disabled


def _descriptors(description: dict[str, Any], value_id: int) -> list[dict[str, Any]]:
    """Every descriptor of a ValueId anywhere in the description."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("ValueId") == value_id:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(description)
    return found


def test_number_needs_a_step(description: dict[str, Any]) -> None:
    """Without StepWidth a numeric input cannot be validated, so it stays a sensor."""
    for descriptor in _descriptors(description, 35000900000):
        descriptor.pop("StepWidth", None)
    assert parse_description(description).parameters[35000900000].kind is Kind.SENSOR


def test_tab_without_bundle_id_is_skipped(
    description: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Polling an invented bundle id can lock the account; such tabs contribute nothing."""
    for tab in description["MenuItems"][0]["TabViews"]:
        if tab["TabName"] == "Warmwasser":
            del tab["BundleId"]
    with caplog.at_level(logging.WARNING):
        parameters = parse_description(description).parameters
    assert 35000900000 not in parameters
    assert "Warmwasser" in caplog.text


def test_known_switch_needs_write_access(description: dict[str, Any]) -> None:
    """A read-only '1x Warmwasser' is an enum sensor, not a switch that always fails."""
    for descriptor in _descriptors(description, 22004200000):
        descriptor["IsReadOnly"] = True
    assert parse_description(description).parameters[22004200000].kind is Kind.ENUM
