"""Thin async client for the Wolf SmartSet cloud API (no Home Assistant imports).

The login flow follows wolf-comm (https://github.com/janrothkegel/wolf-comm,
Apache-2.0, Copyright Jan Rothkegel and contributors) and the official web
portal: OpenID Connect authorization code with PKCE against the portal's
IdentityServer, then a portal session kept alive with UpdateSession.

See docs/adr/ADR-Client-001-own-thin-api-client.md.
"""

import asyncio
import base64
import contextlib
from dataclasses import dataclass
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

BASE_URL = "https://www.wolf-smartset.com"
AUTH_URL = f"{BASE_URL}/idsrv"
API_URL = f"{BASE_URL}/portal/api/portal"
CLIENT_ID = "smartset.web"
REDIRECT_URI = f"{BASE_URL}/signin-callback.html"
SCOPE = "openid profile api role"

# The portal silently truncates longer passwords (wolf-comm PR #18).
MAX_PASSWORD_LENGTH = 30
SESSION_REFRESH_SECONDS = 60
TOKEN_EXPIRY_MARGIN_SECONDS = 60

# A failed login blocks the next attempt for this long, doubling per failure (ADR-Client-014).
LOGIN_BACKOFF_SECONDS = 300
LOGIN_BACKOFF_MAX_SECONDS = 3600

# Lower-cased username -> (monotonic time until which logins are blocked, consecutive failures).
# ponytail: process-wide dict, one HA instance per process; it must outlive client
# instances so HA's setup retries and the config flow cannot log in again.
_login_backoff: dict[str, tuple[float, int]] = {}

# Values of Declarations.EnParamState in the portal JavaScript.
STATE_OK = 1
STATE_TIMEOUT = 4
STATE_ERROR = 5

_READ_ERROR_MESSAGE = "internal msg: ReadParameterValues error"


class WolfError(Exception):
    """Base class for all client errors."""


class CannotConnect(WolfError):
    """Network error or unexpected response."""


class AuthError(WolfError):
    """The portal rejected the credentials."""


class PortalUnavailable(WolfError):
    """Login page without form: maintenance or a temporary IP block."""


class Maintenance(PortalUnavailable):
    """ErrorCode 6, the portal is in maintenance."""


class LoginFailed(WolfError):
    """Login blocked after earlier failures; no request was made."""


class TooManyRequests(WolfError):
    """The portal throttles this client (HTTP 429 or ErrorCode 10)."""


class SystemOffline(WolfError):
    """The gateway is not connected to the portal."""


class ParameterReadError(WolfError):
    """At least one requested value cannot be read."""


class ApiError(WolfError):
    """Any other error reported by the portal."""

    def __init__(self, code: Any, message: Any) -> None:
        """Keep the portal's error code and message."""
        super().__init__(f"ErrorCode {code}: {message}")
        self.code = code


class _Unauthorized(WolfError):
    """HTTP 401, the token is no longer valid."""


class _InvalidSession(WolfError):
    """ErrorCode 1, the portal session is gone."""


@dataclass(frozen=True)
class System:
    """A SmartSet system (one installation behind one gateway)."""

    id: int
    gateway_id: int
    name: str
    share_id: int | None = None


@dataclass(frozen=True)
class SystemState:
    """Online flag and access level of a system."""

    online: bool
    access_level: int | None


@dataclass(frozen=True)
class Value:
    """One entry of a GetParameterValues response."""

    value_id: int
    value: str | None
    state: int | None


class _TokenParser(HTMLParser):
    """Find the anti-forgery token of the IdentityServer login form."""

    token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if (
            self.token is None
            and tag == "input"
            and values.get("name") == "__RequestVerificationToken"
        ):
            self.token = values.get("value") or None


def extract_verification_token(html: str) -> str | None:
    """Return the login form's anti-forgery token, or None without a form."""
    parser = _TokenParser()
    parser.feed(html)
    return parser.token


def pkce_pair() -> tuple[str, str]:
    """Return a PKCE code verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _raise_for_body(data: Any) -> None:
    if not isinstance(data, dict) or not ("ErrorCode" in data or "ErrorType" in data):
        return
    code, message = data.get("ErrorCode"), data.get("Message")
    if message == _READ_ERROR_MESSAGE:
        raise ParameterReadError(message)
    match code:
        case 1:
            raise _InvalidSession(message)
        case 3:
            raise AuthError(message)
        case 4:
            raise SystemOffline(message)
        case 6:
            raise Maintenance(message)
        case 10:
            raise TooManyRequests(message)
    raise ApiError(code, message)


class WolfClient:
    """One login and one portal session per account, shared by all systems."""

    def __init__(self, http: httpx.AsyncClient, username: str, password: str) -> None:
        """Use the given HTTP client; its cookie jar holds the login cookies."""
        self._http = http
        self._username = username
        self._password = password
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self._token_expires = 0.0
        self._session_id: int | None = None
        self._session_refreshed = 0.0
        self.login_count = 0
        self.last_login: datetime | None = None

    async def _login(self) -> None:
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(16)
        query = urlencode(
            {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": SCOPE,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "response_mode": "query",
            }
        )
        self.login_count += 1
        self.last_login = datetime.now().astimezone()
        try:
            page = await self._http.get(
                f"{AUTH_URL}/connect/authorize?{query}", follow_redirects=True
            )
            if page.status_code == 429:
                raise TooManyRequests("login page")
            token = extract_verification_token(page.text)
            if token is None:
                raise PortalUnavailable("login page without form")
            result = await self._http.post(
                page.url,
                data={
                    "Input.Username": self._username,
                    "Input.Password": self._password,
                    "__RequestVerificationToken": token,
                },
                follow_redirects=True,
            )
            if result.status_code == 429:
                raise TooManyRequests("login")
            code = result.url.params.get("code")
            if code is None:
                if extract_verification_token(result.text) is not None:
                    raise AuthError("login form shown again")
                raise PortalUnavailable("no authorization code")
            if result.url.params.get("state") != state:
                raise CannotConnect("state mismatch")
            response = await self._http.post(
                f"{AUTH_URL}/connect/token",
                data={
                    "client_id": CLIENT_ID,
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "code_verifier": verifier,
                    "grant_type": "authorization_code",
                },
            )
            if response.status_code == 429:
                raise TooManyRequests("token")
            data = response.json()
        except httpx.HTTPError as err:
            raise CannotConnect(str(err)) from err
        except ValueError as err:
            raise CannotConnect("token response is not JSON") from err
        if not isinstance(data, dict) or "access_token" not in data:
            error = data.get("error") if isinstance(data, dict) else None
            raise ApiError(response.status_code, error)
        self._token = data["access_token"]
        lifetime = float(data.get("expires_in") or 3600)
        self._token_expires = time.monotonic() + lifetime - TOKEN_EXPIRY_MARGIN_SECONDS
        self._session_id = None

    async def _call(self, method: str, path: str, *, json: Any = None, params: Any = None) -> Any:
        try:
            response = await self._http.request(
                method,
                f"{API_URL}/{path}",
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except httpx.HTTPError as err:
            raise CannotConnect(str(err)) from err
        if response.status_code == 429:
            raise TooManyRequests(path)
        if response.status_code == 401:
            raise _Unauthorized(path)
        try:
            data = response.json()
        except ValueError:
            data = None
        _raise_for_body(data)
        if response.status_code >= 400 or data is None:
            raise ApiError(response.status_code, path)
        return data

    async def _login_with_backoff(self, now: float) -> None:
        """Log in unless an earlier failure still blocks this account."""
        key = self._username.lower()
        blocked_until, failures = _login_backoff.get(key, (0.0, 0))
        if now < blocked_until:
            raise LoginFailed(
                f"login blocked for {int(blocked_until - now)} s after {failures} failed attempts"
            )
        try:
            await self._login()
        except AuthError:
            raise
        except WolfError:
            self._record_login_failure(now)
            raise
        _login_backoff.pop(key, None)

    def _record_login_failure(self, now: float) -> None:
        """Block the next login attempt for this account, doubling per consecutive failure."""
        key = self._username.lower()
        _, failures = _login_backoff.get(key, (0.0, 0))
        delay = min(LOGIN_BACKOFF_SECONDS * 2**failures, LOGIN_BACKOFF_MAX_SECONDS)
        _login_backoff[key] = (now + delay, failures + 1)

    @property
    def login_blocked_seconds(self) -> int:
        """Seconds until the next login attempt is allowed, 0 when not blocked."""
        blocked_until, _ = _login_backoff.get(self._username.lower(), (0.0, 0))
        return max(0, int(blocked_until - time.monotonic()))

    async def _ensure_session(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._token is None or now >= self._token_expires:
                await self._login_with_backoff(now)
            if self._session_id is None:
                data = await self._call(
                    "POST",
                    "CreateSession2",
                    json={"Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                )
                self._session_id = int(data["BrowserSessionId"])
                self._session_refreshed = now
            elif now - self._session_refreshed >= SESSION_REFRESH_SECONDS:
                await self._call("POST", "UpdateSession", json={"SessionId": self._session_id})
                self._session_refreshed = now

    async def _request(
        self, method: str, path: str, *, json: Any = None, params: Any = None
    ) -> Any:
        """Read request: one transparent retry after token or session loss."""
        for attempt in range(2):
            await self._ensure_session()
            if isinstance(json, dict):
                json["SessionId"] = self._session_id
            try:
                return await self._call(method, path, json=json, params=params)
            except _Unauthorized:
                if attempt:
                    self._record_login_failure(time.monotonic())
                    raise ApiError(401, path) from None
                self._token = None
            except _InvalidSession:
                if attempt:
                    raise ApiError(1, path) from None
                self._session_id = None
        raise AssertionError("unreachable")

    async def get_systems(self) -> list[System]:
        """Return all systems of the account, own and shared."""
        data = await self._request("GET", "GetSystemList")
        return [
            System(s["Id"], s["GatewayId"], s.get("Name") or str(s["Id"]), s.get("SystemShareId"))
            for s in data
        ]

    async def get_system_state(self, system: System) -> SystemState:
        """Return the gateway's online flag and the account's access level."""
        entry: dict[str, Any] = {"SystemId": system.id, "GatewayId": system.gateway_id}
        if system.share_id is not None:
            entry["SystemShareId"] = system.share_id
        data = await self._request("POST", "GetSystemStateList", json={"SystemList": [entry]})
        item = data[0]
        return SystemState(bool(item["GatewayState"]["IsOnline"]), item.get("AccessLevel"))

    async def get_description(self, system: System) -> dict[str, Any]:
        """Return the raw GetGuiDescriptionForGateway response."""
        return await self._request(
            "GET",
            "GetGuiDescriptionForGateway",
            params={"GatewayId": system.gateway_id, "SystemId": system.id},
        )

    async def get_values(
        self, system: System, bundle_id: int, value_ids: list[int], *, first: bool = False
    ) -> list[Value]:
        """Read values of one bundle; `first` asks the gateway for a full list."""
        data = await self._request(
            "POST",
            "GetParameterValues",
            json={
                "BundleId": bundle_id,
                "IsSubBundle": False,
                "ValueIdList": value_ids,
                "GatewayId": system.gateway_id,
                "SystemId": system.id,
                "LastAccess": None,
                "GuiIdChanged": first,
            },
        )
        return [
            Value(v["ValueId"], None if v.get("Value") is None else str(v["Value"]), v.get("State"))
            for v in data.get("Values") or []
        ]

    async def write_value(
        self, system: System, bundle_id: int, value_id: int, value: str, name: str
    ) -> Any:
        """Write one value like the web portal does. Never retried.

        A repeated request after a timeout or 5xx could write the EEPROM twice,
        so every failure is raised to the caller (ADR-Writes-012).
        """
        await self._ensure_session()
        payload = {
            "WriteParameterValues": [{"ValueId": value_id, "Value": value, "ParameterName": name}],
            "SystemId": system.id,
            "GatewayId": system.gateway_id,
            "BundleId": bundle_id,
            "SessionId": self._session_id,
        }
        try:
            return await self._call("POST", "WriteParameterValues", json=payload)
        except _Unauthorized:
            self._token = None
            raise ApiError(401, "WriteParameterValues") from None
        except _InvalidSession:
            self._session_id = None
            raise ApiError(1, "WriteParameterValues") from None

    async def close(self) -> None:
        """Release the portal session; errors are irrelevant at this point."""
        if self._session_id is None:
            return
        with contextlib.suppress(WolfError):
            await self._call("POST", "CloseSystem", json={"SessionId": self._session_id})
        self._session_id = None
