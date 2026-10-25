"""The login block survives a restart (ADR-Client-015)."""

from typing import Any

from homeassistant.core import HomeAssistant
import httpx
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.wolf_smartset import api
from custom_components.wolf_smartset.api import LoginFailed, PortalUnavailable, WolfClient
from custom_components.wolf_smartset.coordinator import (
    LOGIN_BACKOFF_STORE,
    async_login_backoff_hook,
)


async def test_block_is_persisted_and_restored(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A restart during a portal block does not post the credentials again."""
    requests = 0

    def blocked_portal(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, text="<html>no login form</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(blocked_portal)) as http:
        hook = await async_login_backoff_hook(hass, "User@example.com")
        client = WolfClient(http, "user@example.com", "pw", on_login_backoff=hook)
        with pytest.raises(PortalUnavailable):
            await client.get_systems()
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        stored = hass_storage[LOGIN_BACKOFF_STORE]["data"]
        assert len(stored) == 1
        assert "example" not in next(iter(stored))  # hashed, not the username
        assert next(iter(stored.values()))[1] == 1

        # Restart: process state and the loaded store are gone.
        api._login_backoff.clear()
        hass.data.pop(LOGIN_BACKOFF_STORE)
        sent = requests
        hook = await async_login_backoff_hook(hass, "user@example.com")
        with pytest.raises(LoginFailed):
            await WolfClient(http, "user@example.com", "pw", on_login_backoff=hook).get_systems()
        assert requests == sent
        assert 0 < client.login_blocked_seconds <= api.LOGIN_BACKOFF_SECONDS
