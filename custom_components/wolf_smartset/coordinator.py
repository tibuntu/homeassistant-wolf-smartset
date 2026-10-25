"""One DataUpdateCoordinator per SmartSet system (ADR-Polling-003)."""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.httpx_client import SERVER_SOFTWARE, USER_AGENT
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.ssl import client_context
import httpx

from .api import (
    STATE_ERROR,
    STATE_OK,
    STATE_TIMEOUT,
    AuthError,
    LoginFailed,
    ParameterReadError,
    PortalUnavailable,
    System,
    TooManyRequests,
    Value,
    WolfClient,
    WolfError,
)
from .const import (
    BACKOFF_ISSUE_STEPS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DESCRIPTION_MAX_AGE,
    DOMAIN,
    LOGGER,
    MAX_BACKOFF,
)
from .model import Description, parse_description

if TYPE_CHECKING:
    from .write import WriteManager


def create_http_client() -> httpx.AsyncClient:
    """Own HTTP client with HA's SSL context and user agent.

    HA's shared or created httpx clients must not be closed by integrations, and
    their cookie jars are not ours alone. The login cookies belong to one account,
    so each config entry and each config flow gets its own client and closes it.
    """
    return httpx.AsyncClient(
        verify=client_context(), headers={USER_AGENT: SERVER_SOFTWARE}, timeout=30
    )


@dataclass
class WolfRuntimeData:
    """Shared HTTP client and API client plus one coordinator per selected system."""

    http: httpx.AsyncClient
    client: WolfClient
    coordinators: dict[int, WolfSystemCoordinator]
    writer: WriteManager


type WolfConfigEntry = ConfigEntry[WolfRuntimeData]

# value_id -> raw value string (None = unknown)
type WolfData = dict[int, str | None]


class WolfSystemCoordinator(DataUpdateCoordinator[WolfData]):
    """Poll the values of all enabled entities of one system."""

    config_entry: WolfConfigEntry
    description: Description

    def __init__(
        self, hass: HomeAssistant, entry: WolfConfigEntry, client: WolfClient, system: System
    ) -> None:
        """Interval from the options; entities register their ParameterId as context."""
        self._interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {system.name}",
            update_interval=self._interval,
        )
        self.client = client
        self.system = system
        self.access_level: int | None = None
        self.unreadable: set[int] = set()
        # Value ids read with State OK by the last successful poll.
        self.polled: set[int] = set()
        self.backoff_steps = 0
        self._started_bundles: set[int] = set()
        self._description_loaded = dt_util.utcnow()

    @override
    async def _async_setup(self) -> None:
        try:
            raw = await self.client.get_description(self.system)
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except WolfError as err:
            raise UpdateFailed(f"Cannot load the parameter description: {err}") from err
        self.description = parse_description(raw)
        self._description_loaded = dt_util.utcnow()
        # Values embedded in the description seed the entities until the first poll.
        self.data = {p.value_id: p.value for p in self.description.parameters.values()}

    @override
    async def _async_update_data(self) -> WolfData:
        try:
            data = await self._poll()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (TooManyRequests, PortalUnavailable, LoginFailed) as err:
            self._back_off()
            raise UpdateFailed(f"Wolf SmartSet throttles requests: {err}") from err
        except WolfError as err:
            raise UpdateFailed(f"Error communicating with Wolf SmartSet: {err}") from err
        if self.backoff_steps:
            self.backoff_steps = 0
            self.update_interval = self._interval
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        return data

    async def _poll(self) -> WolfData:
        state = await self.client.get_system_state(self.system)
        if not state.online:
            raise UpdateFailed("The Wolf system is offline")
        self.access_level = state.access_level
        if dt_util.utcnow() - self._description_loaded > DESCRIPTION_MAX_AGE:
            await self._refresh_description()

        parameters = self.description.parameters
        bundles: dict[int, list[int]] = {}
        for parameter_id in set(self.async_contexts()):
            parameter = parameters.get(parameter_id)
            if parameter and parameter.value_id not in self.unreadable:
                bundles.setdefault(parameter.bundle_id, []).append(parameter.value_id)

        data = dict(self.data or {})
        polled: set[int] = set()
        received = False
        for bundle_id, value_ids in bundles.items():
            for value in await self._read_bundle(bundle_id, sorted(value_ids)):
                received = True
                if value.state == STATE_OK and value.value is not None:
                    data[value.value_id] = value.value
                    polled.add(value.value_id)
                elif value.state in (STATE_TIMEOUT, STATE_ERROR):
                    data[value.value_id] = None
        if bundles and not received:
            # ioBroker saw throttling as empty answers rather than errors.
            raise TooManyRequests("all value requests returned empty")
        self.polled = polled
        return data

    async def _read_bundle(self, bundle_id: int, value_ids: list[int]) -> list[Value]:
        first = bundle_id not in self._started_bundles
        try:
            values = await self.client.get_values(self.system, bundle_id, value_ids, first=first)
        except ParameterReadError:
            if len(value_ids) == 1:
                LOGGER.warning(
                    "Value %s of %s cannot be read and is skipped from now on",
                    value_ids[0],
                    self.system.name,
                )
                self.unreadable.add(value_ids[0])
                return []
            isolated: list[Value] = []
            for value_id in value_ids:
                isolated += await self._read_bundle(bundle_id, [value_id])
            return isolated
        self._started_bundles.add(bundle_id)
        return values

    async def _refresh_description(self) -> None:
        """Daily reload; a changed parameter set reloads the config entry."""
        new = parse_description(await self.client.get_description(self.system))
        self._description_loaded = dt_util.utcnow()

        def shape(description: Description) -> set:
            return {
                (p.parameter_id, p.kind, p.bundle_id, p.device)
                for p in description.parameters.values()
            }

        if shape(new) != shape(self.description):
            LOGGER.info("Parameter description of %s changed, reloading", self.system.name)
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        self.description = new
        self._started_bundles.clear()

    @property
    def _issue_id(self) -> str:
        return f"throttled_{self.config_entry.entry_id}_{self.system.id}"

    def _back_off(self) -> None:
        self.backoff_steps += 1
        self.update_interval = min(self._interval * 2**self.backoff_steps, MAX_BACKOFF)
        LOGGER.warning(
            "Wolf SmartSet throttles %s, next poll in %s", self.system.name, self.update_interval
        )
        if self.backoff_steps >= BACKOFF_ISSUE_STEPS:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="throttled",
                translation_placeholders={"system": self.system.name},
            )
