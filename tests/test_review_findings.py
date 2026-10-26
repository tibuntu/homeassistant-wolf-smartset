"""Reproductions of the findings of the 2026-10-25 review.

See docs/reviews/2026-10-25-write-pipeline.md.

Each test asserts the desired behaviour. An open finding is marked xfail(strict=True); a
fixed finding makes its test pass, which fails the strict xfail: remove the marker in the
same change. All findings are closed since 2026-10-26.
"""

import json
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wolf_smartset.api import (
    AUTH_URL,
    REDIRECT_URI,
    CannotConnect,
    LoginFailed,
    WolfClient,
)
from custom_components.wolf_smartset.const import CONF_DRY_RUN, DOMAIN

from .conftest import FIXTURES

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


async def test_real_write_response_carries_no_state(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Finding 2, closed 2026-10-26: the portal answers `{"Dummy": 0}` to an applied write.

    The body says nothing about the value, so the record stays `ok` with the body kept
    for later comparison, and only the read-back (ADR-Writes-013) confirms the write.
    """
    await _setup_writable(hass, mock_config_entry)
    mock_client.write_value.return_value = json.loads(
        (FIXTURES / "real" / "write_response_0.json").read_text(encoding="utf-8")
    )
    await _set_setpoint(hass, 55)
    record = mock_config_entry.runtime_data.writer.history[-1]
    assert (record["result"], record["response"], record["confirmed"]) == ("ok", {"Dummy": 0}, None)


LOGIN_PAGE = '<form><input type="hidden" name="__RequestVerificationToken" value="tok"/></form>'


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
            with pytest.raises((CannotConnect, LoginFailed)):
                await client.get_systems()
    assert logins == 1
