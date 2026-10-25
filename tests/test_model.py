"""Parameter model against the heat-pump description (ADR-Model-008, ADR-Model-009)."""

from typing import Any

from custom_components.wolf_smartset.model import Kind, parse_description, slugify


def test_one_time_dhw_is_a_switch(description: dict[str, Any]) -> None:
    """'1x Warmwasser' maps to the known switch on the system device."""
    p = parse_description(description).parameters[22004200000]
    assert (p.kind, p.writable, p.bundle_id, p.device, p.expert) == (
        Kind.SWITCH,
        True,
        1000,
        "bedienmodul_bm_2_0",  # ValueId prefix 22, see ADR-Model-009
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


def test_device_by_value_id_prefix(description: dict[str, Any]) -> None:
    """Prefixes with unanimous evidence get a device; prefix 35 (DHW) has none."""
    parameters = parse_description(description).parameters
    assert parameters[36005100001].device == "bedienmodul_bm_2_0"  # Programmwahl Heizung
    assert parameters[36002900001].device == "bedienmodul_bm_2_0"  # Sollwertkorrektur
    assert parameters[27004800001].device == "heizgerat"  # Verdichterfrequenz
    assert parameters[4000100001].device == "mischermodul_mm1"  # MKP Mischerkreispumpe
    for dhw in (35000900000, 35001200000, 35000100000):
        assert parameters[dhw].device is None  # system device


def test_enabled_by_default(description: dict[str, Any]) -> None:
    """Expert, schema-only, meter-dependent and optional-input values start disabled."""
    parameters = parse_description(description).parameters
    disabled = {p.label for p in parameters.values() if p.kind and not p.enabled_by_default}
    assert {
        "Verdichterfrequenz",
        "MKP Mischerkreispumpe",
        "Mischermotor MM",
        "Verbrauch Vortag",
        "JAZ aktuelles Jahr",
        "TAZ Vortag",
        "MAZ aktueller Monat",
        "Raumtemperatur",
    } <= disabled
    for kept in ("Erzeugte Wärmemenge Vortag", "Mischerkreispumpe", "1x Warmwasser"):
        assert kept not in disabled
