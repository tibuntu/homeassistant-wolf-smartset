"""API client against a fake portal (httpx.MockTransport)."""

from collections.abc import Callable
import json
import time
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from custom_components.wolf_smartset.api import (
    API_URL,
    AUTH_URL,
    LOGIN_BACKOFF_MAX_SECONDS,
    LOGIN_BACKOFF_SECONDS,
    REDIRECT_URI,
    ApiError,
    AuthError,
    CannotConnect,
    LoginFailed,
    Maintenance,
    ParameterReadError,
    PortalUnavailable,
    System,
    TooManyRequests,
    Value,
    WolfClient,
    _login_backoff,
    extract_verification_token,
)

SYSTEM = System(1, 2, "Home")
LOGIN_PAGE = (
    '<form><input name="Input.Username"/>'
    '<input type="hidden" name="__RequestVerificationToken" value="tok"/></form>'
)


class FakePortal:
    """Minimal IdentityServer plus portal API."""

    def __init__(self) -> None:
        self.password = "secret"
        self.logins = 0
        self.calls: list[str] = []
        self.api: dict[str, Callable[[httpx.Request], httpx.Response]] = {}
        self.login_page = LOGIN_PAGE
        self.state = ""
        self.token_status = 200
        self.token_body: dict[str, Any] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(f"{AUTH_URL}/connect/authorize"):
            self.state = request.url.params["state"]
            return httpx.Response(
                302, headers={"Location": f"{AUTH_URL}/Account/Login?ReturnUrl=x"}
            )
        if url.startswith(f"{AUTH_URL}/Account/Login") and request.method == "GET":
            return httpx.Response(200, text=self.login_page)
        if url.startswith(f"{AUTH_URL}/Account/Login"):
            form = parse_qs(request.content.decode())
            assert form["__RequestVerificationToken"] == ["tok"]
            if form["Input.Password"] != [self.password]:
                return httpx.Response(200, text=LOGIN_PAGE)
            self.logins += 1
            return httpx.Response(
                302, headers={"Location": f"{REDIRECT_URI}?code=c{self.logins}&state={self.state}"}
            )
        if url.startswith(REDIRECT_URI):
            return httpx.Response(200, text="ok")
        if url == f"{AUTH_URL}/connect/token":
            if self.token_status != 200:
                return httpx.Response(self.token_status, text="<html>error</html>")
            form = parse_qs(request.content.decode())
            assert form["code_verifier"] and form["grant_type"] == ["authorization_code"]
            body = self.token_body or {"access_token": f"t{self.logins}", "expires_in": 3600}
            return httpx.Response(200, json=body)
        path = url.removeprefix(f"{API_URL}/").split("?")[0]
        self.calls.append(path)
        if path == "CreateSession2":
            return httpx.Response(200, json={"BrowserSessionId": 42})
        return self.api[path](request)


@pytest.fixture
def portal() -> FakePortal:
    """Fresh fake portal."""
    return FakePortal()


@pytest.fixture
async def client(portal: FakePortal):
    """Client wired to the fake portal."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        yield WolfClient(http, "user", portal.password)


async def test_login_session_and_system_list(client: WolfClient, portal: FakePortal) -> None:
    """One login, one session, bearer token and session id on JSON calls."""
    portal.api["GetSystemList"] = lambda r: httpx.Response(
        200, json=[{"Id": 1, "GatewayId": 2, "Name": "Home", "SystemShareId": None}]
    )

    def state(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer t1"
        assert json.loads(request.content)["SessionId"] == 42
        return httpx.Response(200, json=[{"GatewayState": {"IsOnline": True}, "AccessLevel": 4}])

    portal.api["GetSystemStateList"] = state
    assert await client.get_systems() == [SYSTEM]
    assert (await client.get_system_state(SYSTEM)).access_level == 4
    assert (portal.logins, client.login_count) == (1, 1)
    assert portal.calls == ["CreateSession2", "GetSystemList", "GetSystemStateList"]


async def test_wrong_password(portal: FakePortal) -> None:
    """The login form shown again means invalid credentials."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        with pytest.raises(AuthError):
            await WolfClient(http, "user", "wrong").get_systems()


async def test_login_page_without_form(client: WolfClient, portal: FakePortal) -> None:
    """Maintenance or IP block: credentials are never sent."""
    portal.login_page = "<html>Der Portal-Server reagiert nicht.</html>"
    with pytest.raises(PortalUnavailable):
        await client.get_systems()
    assert portal.logins == 0


async def test_unauthorized_relogs_once(client: WolfClient, portal: FakePortal) -> None:
    """HTTP 401 triggers exactly one new login and a retry."""
    answers = iter([httpx.Response(401), httpx.Response(200, json=[])])
    portal.api["GetSystemList"] = lambda r: next(answers)
    assert await client.get_systems() == []
    assert portal.logins == 2


@pytest.mark.parametrize(
    ("body", "status", "error"),
    [
        ({"ErrorCode": 10, "Message": "x"}, 200, TooManyRequests),
        ({}, 429, TooManyRequests),
        (
            {"ErrorCode": 5, "Message": "internal msg: ReadParameterValues error"},
            200,
            ParameterReadError,
        ),
        ({"ErrorCode": 6, "Message": "x"}, 200, Maintenance),
        ({"ErrorCode": 7, "Message": "x"}, 400, ApiError),
    ],
)
async def test_error_mapping(
    client: WolfClient, portal: FakePortal, body: dict, status: int, error: type[Exception]
) -> None:
    """Portal error codes become typed exceptions."""
    portal.api["GetParameterValues"] = lambda r: httpx.Response(status, json=body)
    with pytest.raises(error):
        await client.get_values(SYSTEM, 1000, [1])


async def test_get_values_payload(client: WolfClient, portal: FakePortal) -> None:
    """Request shape as used by the portal."""

    def values(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload == {
            "BundleId": 6300,
            "IsSubBundle": False,
            "ValueIdList": [7, 8],
            "GatewayId": 2,
            "SystemId": 1,
            "LastAccess": None,
            "GuiIdChanged": True,
            "SessionId": 42,
        }
        return httpx.Response(
            200, json={"LastAccess": "x", "Values": [{"ValueId": 7, "Value": "4", "State": 1}]}
        )

    portal.api["GetParameterValues"] = values
    result = await client.get_values(SYSTEM, 6300, [7, 8], first=True)
    assert [(v.value_id, v.value, v.state) for v in result] == [(7, "4", 1)]


def test_token_parser() -> None:
    """Token found by name, not position."""
    assert extract_verification_token(LOGIN_PAGE) == "tok"
    assert extract_verification_token("<html></html>") is None


async def test_write_value_payload(client: WolfClient, portal: FakePortal) -> None:
    """Same payload as the portal; the value is always a string."""

    def write(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {
            "WriteParameterValues": [
                {"ValueId": 22004200000, "Value": "1", "ParameterName": "1x Warmwasser"}
            ],
            "SystemId": 1,
            "GatewayId": 2,
            "BundleId": 1000,
            "SessionId": 42,
        }
        return httpx.Response(200, json={})

    portal.api["WriteParameterValues"] = write
    await client.write_value(SYSTEM, 1000, 22004200000, "1", "1x Warmwasser")
    assert portal.calls.count("WriteParameterValues") == 1


@pytest.mark.parametrize("status", [401, 500, 503])
async def test_write_value_is_never_retried(
    client: WolfClient, portal: FakePortal, status: int
) -> None:
    """A failed write is reported, not repeated (EEPROM, ADR-Writes-012)."""
    portal.api["WriteParameterValues"] = lambda r: httpx.Response(status, json={})
    with pytest.raises(ApiError):
        await client.write_value(SYSTEM, 1000, 22004200000, "1", "1x Warmwasser")
    assert portal.calls.count("WriteParameterValues") == 1
    assert portal.logins == 1


async def test_failed_login_blocks_further_attempts(client: WolfClient, portal: FakePortal) -> None:
    """One credential POST, then LoginFailed without any request until the block ends."""
    portal.token_status = 502
    with pytest.raises(CannotConnect):
        await client.get_systems()
    for _ in range(4):
        with pytest.raises(LoginFailed):
            await client.get_systems()
    assert portal.logins == 1
    assert portal.calls == []
    assert 0 < client.login_blocked_seconds <= LOGIN_BACKOFF_SECONDS
    assert _login_backoff["user"][1] == 1


async def test_backoff_doubles_and_resets(client: WolfClient, portal: FakePortal) -> None:
    """Each consecutive failure doubles the block; a successful login clears it."""
    portal.token_status = 502
    with pytest.raises(CannotConnect):
        await client.get_systems()
    _login_backoff["user"] = (time.monotonic() - 1, 1)  # the first block has ended
    with pytest.raises(CannotConnect):
        await client.get_systems()
    assert portal.logins == 2
    assert _login_backoff["user"][1] == 2
    assert client.login_blocked_seconds > LOGIN_BACKOFF_SECONDS

    _login_backoff["user"] = (time.monotonic() - 1, 2)
    portal.token_status = 200
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    assert await client.get_systems() == []
    assert "user" not in _login_backoff
    assert client.login_blocked_seconds == 0


async def test_backoff_is_capped(client: WolfClient, portal: FakePortal) -> None:
    """After many failures the block stays at the cap."""
    portal.token_status = 502
    _login_backoff["user"] = (0.0, 10)
    with pytest.raises(CannotConnect):
        await client.get_systems()
    assert (
        LOGIN_BACKOFF_MAX_SECONDS - 2 <= client.login_blocked_seconds <= LOGIN_BACKOFF_MAX_SECONDS
    )


async def test_backoff_key_ignores_case(portal: FakePortal) -> None:
    """Clients for 'User' and 'user' share one block."""
    portal.token_status = 502
    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        with pytest.raises(CannotConnect):
            await WolfClient(http, "User", portal.password).get_systems()
        with pytest.raises(LoginFailed):
            await WolfClient(http, "user", portal.password).get_systems()
    assert portal.logins == 1


async def test_wrong_password_sets_no_block(portal: FakePortal) -> None:
    """Invalid credentials go to reauth; retries are the user's."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(portal)) as http:
        client = WolfClient(http, "user", "wrong")
        for _ in range(2):
            with pytest.raises(AuthError):
                await client.get_systems()
    assert "user" not in _login_backoff


async def test_token_response_without_token(client: WolfClient, portal: FakePortal) -> None:
    """A JSON error from the token endpoint is an ApiError and counts as a failed login."""
    portal.token_body = {"error": "invalid_grant"}
    with pytest.raises(ApiError):
        await client.get_systems()
    assert _login_backoff["user"][1] == 1


def test_maintenance_is_portal_unavailable() -> None:
    """The coordinator's backoff tuple catches Maintenance through its base class."""
    assert issubclass(Maintenance, PortalUnavailable)


@pytest.mark.parametrize(
    ("step", "method"),
    [
        ("connect/authorize", "GET"),
        ("Account/Login", "GET"),
        ("Account/Login", "POST"),
        ("connect/token", "POST"),
    ],
)
async def test_429_during_login(portal: FakePortal, step: str, method: str) -> None:
    """HTTP 429 on every login request (page, form post, token) is throttling."""

    def throttled(request: httpx.Request) -> httpx.Response:
        if step in str(request.url) and request.method == method:
            return httpx.Response(429)
        return portal(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(throttled)) as http:
        with pytest.raises(TooManyRequests):
            await WolfClient(http, "user", portal.password).get_systems()


async def test_session_is_refreshed_after_60_seconds(
    client: WolfClient, portal: FakePortal
) -> None:
    """UpdateSession runs before a request once the session is older than 60 s."""
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    portal.api["UpdateSession"] = lambda r: httpx.Response(200, json={"Maintenance": 0})
    await client.get_systems()
    client._session_refreshed -= 61
    await client.get_systems()
    assert portal.calls == ["CreateSession2", "GetSystemList", "UpdateSession", "GetSystemList"]


async def test_second_unauthorized_is_an_error(client: WolfClient, portal: FakePortal) -> None:
    """Only one relogin per request."""
    portal.api["GetSystemList"] = lambda r: httpx.Response(401)
    with pytest.raises(ApiError):
        await client.get_systems()
    assert portal.logins == 2


async def test_invalid_session_creates_a_new_session(
    client: WolfClient, portal: FakePortal
) -> None:
    """ErrorCode 1 once: new session and retry; twice: error."""
    answers = iter([{"ErrorCode": 1, "Message": "x"}, []])
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=next(answers))
    assert await client.get_systems() == []
    assert portal.calls.count("CreateSession2") == 2

    portal.api["GetSystemList"] = lambda r: httpx.Response(
        200, json={"ErrorCode": 1, "Message": "x"}
    )
    with pytest.raises(ApiError):
        await client.get_systems()


async def test_write_with_lost_session_is_not_retried(
    client: WolfClient, portal: FakePortal
) -> None:
    """A write answered with InvalidSession raises; the next call opens a new session."""
    portal.api["WriteParameterValues"] = lambda r: httpx.Response(
        200, json={"ErrorCode": 1, "Message": "x"}
    )
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    with pytest.raises(ApiError):
        await client.write_value(SYSTEM, 1000, 22004200000, "1", "1x Warmwasser")
    assert portal.calls.count("WriteParameterValues") == 1
    await client.get_systems()
    assert portal.calls.count("CreateSession2") == 2


async def test_write_value_non_json_body(client: WolfClient, portal: FakePortal) -> None:
    """HTTP 200 with an HTML body (login page) is an error, never a silent success."""
    portal.api["WriteParameterValues"] = lambda r: httpx.Response(200, text="<html>login</html>")
    with pytest.raises(ApiError):
        await client.write_value(SYSTEM, 1000, 22004200000, "1", "1x Warmwasser")


async def test_close_releases_the_session(client: WolfClient, portal: FakePortal) -> None:
    """CloseSystem is called once per session; errors are swallowed; no session, no call."""
    await client.close()
    assert "CloseSystem" not in portal.calls
    portal.api["GetSystemList"] = lambda r: httpx.Response(200, json=[])
    portal.api["CloseSystem"] = lambda r: httpx.Response(500)
    await client.get_systems()
    await client.close()
    await client.close()
    assert portal.calls.count("CloseSystem") == 1


async def test_shared_system_state_request(client: WolfClient, portal: FakePortal) -> None:
    """Shared systems send their SystemShareId; values without State or Value are kept."""

    def state(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["SystemList"] == [{"SystemId": 1, "GatewayId": 2, "SystemShareId": 7}]
        assert payload["SessionId"] == 42
        return httpx.Response(200, json=[{"GatewayState": {"IsOnline": False}}])

    portal.api["GetSystemStateList"] = state
    result = await client.get_system_state(System(1, 2, "Home", 7))
    assert (result.online, result.access_level) == (False, None)

    portal.api["GetParameterValues"] = lambda r: httpx.Response(
        200, json={"Values": [{"ValueId": 7, "State": 0}]}
    )
    assert await client.get_values(SYSTEM, 1000, [7]) == [Value(7, None, 0)]
