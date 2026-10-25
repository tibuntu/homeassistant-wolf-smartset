"""API client against a fake portal (httpx.MockTransport)."""

from collections.abc import Callable
import json
from urllib.parse import parse_qs

import httpx
import pytest

from custom_components.wolf_smartset.api import (
    API_URL,
    AUTH_URL,
    REDIRECT_URI,
    ApiError,
    AuthError,
    ParameterReadError,
    PortalUnavailable,
    System,
    TooManyRequests,
    WolfClient,
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
            form = parse_qs(request.content.decode())
            assert form["code_verifier"] and form["grant_type"] == ["authorization_code"]
            return httpx.Response(200, json={"access_token": f"t{self.logins}", "expires_in": 3600})
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
