"""Reproductions of the open findings of the 2026-10-25 review.

See docs/reviews/2026-10-25-write-pipeline.md.

Each test asserts the desired behaviour and is marked xfail(strict=True) until the finding
is fixed. A fixed finding makes its test pass, which fails the strict xfail: remove the marker
in the same change.
"""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wolf_smartset.api import (
    AUTH_URL,
    REDIRECT_URI,
    CannotConnect,
    Value,
    WolfClient,
)
from custom_components.wolf_smartset.const import CONF_DRY_RUN, DOMAIN

from .conftest import SEED

DHW_SETPOINT = 35000900000  # "Warmwassersolltemperatur eingestellt", 25-65 °C, step 1, value 50


def _entity_id(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"1234_{DHW_SETPOINT}")
    assert entity_id
    return entity_id


async def _setup_writable(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={CONF_DRY_RUN: False})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _set_setpoint(hass: HomeAssistant, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value", {"entity_id": _entity_id(hass), "value": value}, blocking=True
    )


async def test_poll_shortly_after_write_keeps_optimistic_value(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The gateway still reports the old value while the controller applies the write."""
    await _setup_writable(hass, mock_config_entry)
    await _set_setpoint(hass, 55)
    assert hass.states.get(_entity_id(hass)).state == "55.0"

    freezer.tick(timedelta(seconds=10))
    await mock_config_entry.runtime_data.coordinators[1234].async_refresh()  # reads 50
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id(hass)).state == "55.0"

    # An automation that re-sends the same value must not reach the EEPROM again.
    await _set_setpoint(hass, 55)
    assert mock_client.write_value.await_count == 1


async def test_in_flight_poll_does_not_overwrite_write(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The poll copies coordinator.data, waits on the network, then stores the stale copy."""
    await _setup_writable(hass, mock_config_entry)
    gate = asyncio.Event()

    async def slow_values(system: Any, bundle: int, ids: list[int], first: bool = False) -> list:
        await gate.wait()
        return [Value(i, SEED[i], 1) for i in ids]

    mock_client.get_values.side_effect = slow_values
    poll = asyncio.create_task(mock_config_entry.runtime_data.coordinators[1234].async_refresh())
    await asyncio.sleep(0)  # the poll is waiting on the network
    await _set_setpoint(hass, 55)
    gate.set()
    await poll
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id(hass)).state == "55.0"


@pytest.mark.xfail(
    strict=True,
    reason="Finding 2: the WriteParameterValues response body is never inspected; "
    "the shape of a real response is still unrecorded, this body is a placeholder",
)
async def test_write_response_reporting_an_error_is_not_ok(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A response that reports State 5 (Error) for the written value must not count as applied."""
    await _setup_writable(hass, mock_config_entry)
    mock_client.write_value.return_value = {"Values": [{"ValueId": DHW_SETPOINT, "State": 5}]}
    await _set_setpoint(hass, 55)
    assert mock_config_entry.runtime_data.writer.history[-1]["result"] != "ok"


LOGIN_PAGE = '<form><input type="hidden" name="__RequestVerificationToken" value="tok"/></form>'


@pytest.mark.xfail(
    strict=True,
    reason="Finding 3: a failed token exchange leaves the token empty, and every later call "
    "posts the credentials again without any backoff",
)
async def test_failed_token_exchange_does_not_relogin_on_every_call() -> None:
    """Five calls against a broken token endpoint must not post the credentials five times."""
    logins = 0
    state = ""

    def portal(request: httpx.Request) -> httpx.Response:
        nonlocal logins, state
        url = str(request.url)
        if url.startswith(f"{AUTH_URL}/connect/authorize"):
            state = request.url.params["state"]
            return httpx.Response(
                302, headers={"Location": f"{AUTH_URL}/Account/Login?ReturnUrl=x"}
            )
        if url.startswith(f"{AUTH_URL}/Account/Login") and request.method == "GET":
            return httpx.Response(200, text=LOGIN_PAGE)
        if url.startswith(f"{AUTH_URL}/Account/Login"):
            logins += 1
            return httpx.Response(302, headers={"Location": f"{REDIRECT_URI}?code=c&state={state}"})
        if url.startswith(REDIRECT_URI):
            return httpx.Response(200, text="ok")
        if url == f"{AUTH_URL}/connect/token":
            return httpx.Response(502, text="<html>bad gateway</html>")
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        client = WolfClient(http, "user", "pw")
        for _ in range(5):
            with pytest.raises(CannotConnect):
                await client.get_systems()
    assert logins < 5
