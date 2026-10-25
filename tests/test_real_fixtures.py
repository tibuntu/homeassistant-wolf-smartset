"""The owner's installation, recorded with scripts/record_fixtures.py (redacted)."""

import json

from custom_components.wolf_smartset.model import Kind, parse_description

from .conftest import DESCRIPTION, FIXTURES

REAL = FIXTURES / "real"


def _load(name: str):
    return json.loads((REAL / name).read_text(encoding="utf-8"))


def test_real_description_matches_example_model() -> None:
    """Same parameters, platforms, bundles and devices as the test fixture."""
    real = parse_description(_load("description_0.json")).parameters
    example = parse_description(DESCRIPTION).parameters

    def shape(p):
        return (p.kind, p.writable, p.bundle_id, p.device, p.label)

    assert {k: shape(p) for k, p in real.items()} == {k: shape(p) for k, p in example.items()}
    assert real[22004200000].kind is Kind.SWITCH


def test_access_level_and_online_flag() -> None:
    """GetSystemStateList carries AccessLevel next to GatewayState."""
    state = _load("system_state_0.json")[0]
    assert (state["GatewayState"]["IsOnline"], state["AccessLevel"]) == (True, 4)


def test_every_requested_user_value_is_returned() -> None:
    """All user-level values come back with State OK; one may lack a value."""
    values = _load("values_0.json")["Values"]
    real = parse_description(_load("description_0.json")).parameters
    requested = {p.value_id for p in real.values() if p.kind and p.bundle_id == 1000}
    assert {v["ValueId"] for v in values} == requested
    assert {v["State"] for v in values} == {1}
