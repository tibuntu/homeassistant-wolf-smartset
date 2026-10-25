"""Shared fixtures."""

from collections.abc import Generator
import copy
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wolf_smartset.api import System, SystemState, Value
from custom_components.wolf_smartset.const import CONF_SYSTEMS, DOMAIN
from custom_components.wolf_smartset.model import parse_description

FIXTURES = Path(__file__).parent / "fixtures"
DESCRIPTION: dict[str, Any] = json.loads(
    (FIXTURES / "description_heatpump.json").read_text(encoding="utf-8")
)
SYSTEM = System(id=1234, gateway_id=5678, name="Home", share_id=None)
# Values the fake portal returns: those embedded in the description, else "0".
SEED = {p.value_id: p.value or "0" for p in parse_description(DESCRIPTION).parameters.values()}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture(autouse=True)
def no_frame_warnings(caplog: pytest.LogCaptureFixture) -> Generator[None]:
    """HA's deprecation and misuse reports must fail the test, not just log."""
    yield
    reports = [
        record.getMessage()
        for when in ("setup", "call")
        for record in caplog.get_records(when)
        if "Detected that custom integration" in record.getMessage()
    ]
    assert not reports


@pytest.fixture
def description() -> dict[str, Any]:
    """Fresh copy of the heat-pump description."""
    return copy.deepcopy(DESCRIPTION)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Config entry for one system."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        unique_id="user@example.com",
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_SYSTEMS: [asdict(SYSTEM)],
        },
    )


@pytest.fixture
def mock_client(description: dict[str, Any]) -> Generator[MagicMock]:
    """WolfClient replaced in the integration and the config flow."""
    with (
        patch("custom_components.wolf_smartset.WolfClient", autospec=True) as cls,
        patch("custom_components.wolf_smartset.config_flow.WolfClient", new=cls),
    ):
        client = cls.return_value
        client.get_systems = AsyncMock(return_value=[SYSTEM])
        client.get_system_state = AsyncMock(return_value=SystemState(True, 4))
        client.get_description = AsyncMock(return_value=description)
        # Every requested value comes back with State OK, like the portal.
        client.get_values = AsyncMock(
            side_effect=lambda system, bundle, ids, first=False: [Value(i, SEED[i], 1) for i in ids]
        )
        client.close = AsyncMock()
        client.write_value = AsyncMock(return_value={})
        client.login_count = 1
        client.last_login = None
        yield client
