"""Config flow: credentials, system selection, reauth and options."""

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, override

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import probatio

from .api import (
    MAX_PASSWORD_LENGTH,
    AuthError,
    LoginFailed,
    PortalUnavailable,
    System,
    TooManyRequests,
    WolfClient,
    WolfError,
)
from .const import (
    CONF_DRY_RUN,
    CONF_MAX_WRITES_PER_HOUR,
    CONF_SCAN_INTERVAL,
    CONF_SYSTEMS,
    DEFAULT_DRY_RUN,
    DEFAULT_MAX_WRITES_PER_HOUR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_SCAN_INTERVAL,
)
from .coordinator import create_http_client

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        probatio.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
REAUTH_SCHEMA = probatio.Schema({probatio.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


async def _fetch_systems(username: str, password: str) -> list[System]:
    """Log in once, list the systems, release the session."""
    http = create_http_client()
    client = WolfClient(http, username, password)
    try:
        return await client.get_systems()
    finally:
        await client.close()
        await http.aclose()


async def _validate(
    hass: HomeAssistant, username: str, password: str, errors: dict[str, str]
) -> list[System] | None:
    if len(password) > MAX_PASSWORD_LENGTH:
        errors[CONF_PASSWORD] = "password_too_long"
        return None
    try:
        return await _fetch_systems(username, password)
    except AuthError:
        errors["base"] = "invalid_auth"
    except TooManyRequests, PortalUnavailable, LoginFailed:
        errors["base"] = "portal_unavailable"
    except WolfError:
        errors["base"] = "cannot_connect"
    except Exception:
        LOGGER.exception("Unexpected error during login")
        errors["base"] = "unknown"
    return None


class WolfSmartsetConfigFlow(ConfigFlow, domain=DOMAIN):
    """One config entry per SmartSet account (one login, ADR-Integration-000)."""

    VERSION = 1

    def __init__(self) -> None:
        """Keep credentials and systems between steps."""
        self._credentials: dict[str, str] = {}
        self._systems: dict[int, System] = {}

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for credentials and list the account's systems."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()
            systems = await _validate(self.hass, username, user_input[CONF_PASSWORD], errors)
            if systems is not None:
                if not systems:
                    return self.async_abort(reason="no_systems")
                self._credentials = {
                    CONF_USERNAME: username,
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                self._systems = {s.id: s for s in systems}
                if len(systems) == 1:
                    return self._create(systems)
                return await self.async_step_systems()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_systems(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick the systems to add."""
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = [self._systems[int(i)] for i in user_input[CONF_SYSTEMS]]
            if chosen:
                return self._create(chosen)
            errors["base"] = "no_system_selected"
        options = [SelectOptionDict(value=str(s.id), label=s.name) for s in self._systems.values()]
        schema = probatio.Schema(
            {
                probatio.Required(CONF_SYSTEMS, default=[o["value"] for o in options]): (
                    SelectSelector(SelectSelectorConfig(options=options, multiple=True))
                )
            }
        )
        return self.async_show_form(step_id="systems", data_schema=schema, errors=errors)

    def _create(self, systems: list[System]) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._credentials[CONF_USERNAME],
            data={**self._credentials, CONF_SYSTEMS: [asdict(s) for s in systems]},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The portal rejected the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password of the same account."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            if await _validate(self.hass, entry.data[CONF_USERNAME], password, errors) is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={CONF_USERNAME: entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> WolfSmartsetOptionsFlow:
        """Poll interval option."""
        return WolfSmartsetOptionsFlow()


class WolfSmartsetOptionsFlow(OptionsFlowWithReload):
    """Poll interval (ADR-Polling-003), dry run and write rate limit (ADR-Writes-012)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_DRY_RUN: bool(user_input[CONF_DRY_RUN]),
                    CONF_MAX_WRITES_PER_HOUR: int(user_input[CONF_MAX_WRITES_PER_HOUR]),
                }
            )
        options = self.config_entry.options
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=3600,
                        step=10,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                probatio.Required(
                    CONF_DRY_RUN, default=options.get(CONF_DRY_RUN, DEFAULT_DRY_RUN)
                ): BooleanSelector(),
                probatio.Required(
                    CONF_MAX_WRITES_PER_HOUR,
                    default=options.get(CONF_MAX_WRITES_PER_HOUR, DEFAULT_MAX_WRITES_PER_HOUR),
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=60, step=1, mode=NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
