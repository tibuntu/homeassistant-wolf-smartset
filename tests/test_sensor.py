"""Sensor mapping rules (ADR-Model-011)."""

import json

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
import pytest

from custom_components.wolf_smartset.model import parse_description
from custom_components.wolf_smartset.sensor import unit_mapping

from .conftest import FIXTURES

PARAMETERS = {
    p.label: p
    for p in parse_description(
        json.loads((FIXTURES / "real" / "description_0.json").read_text(encoding="utf-8"))
    ).parameters.values()
    if p.kind
}


@pytest.mark.parametrize(
    ("label", "state_class"),
    [
        ("Verbrauch Vortag", None),
        ("Erzeugte Wärmemenge Vortag", None),
        ("Verbrauch Vorjahr", None),
        ("Erzeugte Wärmemenge Vorjahr", None),
        ("Verbrauch Vorvorjahr", None),
        ("Erzeugte Wärmemenge Vorvorjahr", None),
        ("Verbrauch aktueller Monat", SensorStateClass.TOTAL_INCREASING),
        ("Erzeugte Wärmemenge aktueller Monat", SensorStateClass.TOTAL_INCREASING),
        ("Verbrauch aktuelles Jahr", SensorStateClass.TOTAL_INCREASING),
        ("Erzeugte Wärmemenge aktuelles Jahr", SensorStateClass.TOTAL_INCREASING),
        ("Energiemenge HZ", SensorStateClass.TOTAL_INCREASING),
        ("Energiemenge WW", SensorStateClass.TOTAL_INCREASING),
        ("Energiemenge Kühl.", SensorStateClass.TOTAL_INCREASING),
        ("Betriebsstunden Verdichter", SensorStateClass.TOTAL_INCREASING),
        ("Betriebsstunden E-Heizung", SensorStateClass.TOTAL_INCREASING),
    ],
)
def test_state_class_of_energy_and_hours(label: str, state_class: SensorStateClass | None) -> None:
    """Closed periods are snapshots; running totals stay total_increasing."""
    device_class, _, actual = unit_mapping(PARAMETERS[label])
    assert actual == state_class
    assert device_class in (SensorDeviceClass.ENERGY, SensorDeviceClass.DURATION)
