# ioBroker.wolf-smartset (v2.1.2, master @ 24790aa 2026-10-13) – Wolf SmartSet API behaviour as implemented

Source root: clone of `iobroker-community-adapters/ioBroker.wolf-smartset` at commit `24790aa` (2026-10-13). All `file:line` refs are relative to it. Written by a research agent during Phase 0; key claims cross-checked against the source.
Two files matter: `lib/wss.js` (HTTP/API client) and `main.js` (adapter: GUI-description parsing, polling, writes). `lib/tools.js` is unrelated (translation helpers only).

Base URL: `https://www.wolf-smartset.com` (`lib/wss.js:8-9`). All endpoint constants: `lib/wss.js:7-31`.

---

## 1. Auth (OpenID Connect, authorization code + PKCE, scraped login form)

| Item | Value | Ref |
|---|---|---|
| Discovery | `GET /idsrv/.well-known/openid-configuration` via `openid-client` `Issuer.discover()` (5 s timeout) | `lib/wss.js:12,185,194-196` |
| client_id | `smartset.web` (public client, `token_endpoint_auth_method: 'none'`, no secret) | `lib/wss.js:66,187,191` |
| redirect_uri | `https://www.wolf-smartset.com/signin-callback.html` | `lib/wss.js:13,188,320` |
| response_type | `code` | `lib/wss.js:189` |
| scope | `openid profile api role` | `lib/wss.js:237,389` |
| PKCE | yes, `S256`; `codeVerifier`/`codeChallenge`/`state` from `openid-client.generators`, verifier kept in `openIdStore[state]` | `lib/wss.js:223-229,239-240` |
| Token endpoint | `POST /idsrv/connect/token` (form-urlencoded) | `lib/wss.js:14,331-336` |
| Authorization endpoint | not hard-coded; taken from discovery doc (`openIdClient.authorizationUrl()`) | `lib/wss.js:236-241` |
| Unused constants | `/portal/connect/token`, `/portal/api/portal/Init`, `/idsrv/connect/userinfo` | `lib/wss.js:10,11,15` |

Login flow `_getAuthToken()` (`lib/wss.js:219-363`):
1. `GET <authorizationUrl>` with Firefox-like browser headers (`lib/wss.js:89-100`), follow redirects; final URL = login page (`loginUrl = loginPage.request.res.responseUrl`, `:251`).
2. Scrape hidden `__RequestVerificationToken` with regex `/<input name="__RequestVerificationToken" type="hidden" value="(.*)" \/>/` (`:253-255`) and collect `set-cookie` (name=value only) (`:257`).
3. `POST loginUrl` form-urlencoded: `Input.Username`, `Input.Password`, `__RequestVerificationToken` (`:261-265`) + `Origin`, `Referer: loginUrl`, `Sec-Fetch-User: ?1`, `Cookie` (`:272-276`), `maxRedirects: 0`, **expects HTTP 302** (`:283-286`).
4. `GET WEBSERVER + Location` with accumulated cookies (`:289-298`); final `responseUrl` is the callback URL carrying `code`+`state`, parsed via `openIdClient.callbackParams()` (`:304-314`).
5. Token exchange body: `{client_id, code, redirect_uri, code_verifier, grant_type:'authorization_code'}` (`:317-323`). Response (`tokenSet.data`) is used as-is: `access_token`, `token_type`, `expires_in`, `id_token` (`:342,373,111`). Adapter adds `idCookie` (= cookie starting with `idsrv.session=`), `allCookies`, `headers` to it (`:350-352`).
   - Note: the whole token set is logged at **info** level (`:338-340`).

API requests then use `Authorization: <token_type> <access_token>` plus `User-Agent: ioBroker.wolfsmartset`, `Host`, `Connection: keep-alive`, `Cache-control: no-cache`, joke header `X-Pect: The Spanish Inquisition` (`lib/wss.js:108-119`).

Token lifetime / refresh:
- No hard-coded lifetime. `refreshTimeout = setTimeout(_refreshAuthToken, expires_in * 1000)` – refresh is scheduled **at** expiry, not before (`lib/wss.js:342-349`, again `:452-459`). README says re-auth happens "only every hour" (`README.md:108`) → `expires_in` is observed to be 3600 s.
- `_refreshAuthToken()` (`lib/wss.js:368-477`) is **not** a `refresh_token` grant. It is a silent re-authorization: new PKCE pair, `authorizationUrl(...)` + `&prompt=none&response_mode=query&id_token_hint=<id_token>` (`:388-397`), sent with the stored idsrv cookies (`:402`), follow redirect → callback `code` → same token exchange (`:426-446`). Cookies/headers carried over from the first login (`:460-462`).
- If `auth.id_token` missing → full `_getAuthToken()` (`:373-376`). If error message contains `login_required` → `auth = {}` and full `init()` (`:469-475`) (new login + new portal session). Other refresh errors are only logged at info (`:470`).
- No disk caching of tokens any more (commented out, `lib/wss.js:75-83,151-159,199-213`; `CHANGELOG_OLD.md:14`).
- Logout on unload: `GET <end_session_endpoint>&id_token_hint=<id_token>&post_logout_redirect_uri=https://www.wolf-smartset.com/index.html` with cookies, expects 200 (`lib/wss.js:482-535`, called from `stop()` `:786`).

## 2. Session handling (portal session on top of the OIDC token)

- **CreateSession**: `POST /portal/api/portal/CreateSession2` body `{ "Timestamp": "YYYY-MM-DD HH:mm:ss" }` (local time, no TZ; `lib/wss.js:124-133,562-570`). Commented-out optional fields `ClientSideIdentifier: '0001-01-01T00:00:00'`, `AppVersion: '3.0.29'` (`:564-565`). Extra headers: `Cookie: idsrv.session=…`, `Origin`, `X-Requested-With: XMLHttpRequest`, `Sec-Fetch-Dest: empty`, `Sec-Fetch-Mode: cors`, (typo) `SSec-Fetch-Site`, `TE: trailers` (`:547-554`). Response: `{ BrowserSessionId: … }` → `this.SessionId` (`:574-576,733`).
- **UpdateSession (keep-alive)**: `POST /portal/api/portal/UpdateSession` body `{ "SessionId": <id> }` every **60 s** (`_API_INTERVAL_SESSION_UPDATE = 60000`, `lib/wss.js:35,56`; timer `:613-616`, first armed in `init()` `:767-770`). Response only logged (`:601`).
- **Expiry handling**: on UpdateSession error with HTTP **400 or 401** and an existing SessionId → `_createSession()` again; if still no SessionId → full `init()` (`:605-610`). Timer is re-armed regardless (`:613`). No session lifetime is assumed anywhere; keep-alive is the only mechanism. No DeleteSession/logout of the portal session exists; `stop()` only ends the OIDC session (`:782-788`).
- **Where SessionId is sent**: in the JSON body of `GetParameterValues` (`:908`), `parameters/write` (`:988`) and `UpdateSession` (`:591`). Not sent to `GetGuiDescriptionForGateway`, `systemstate`, `GetSystemList`, `ExpertLogin`, `CurrentUserLoadDataSlim` (bearer token only).
- Every `init()` (initial, every 2 h in expert mode, after `login_required`, after keep-alive failure, after IP change / 10 empty polls) creates a **new** session without closing the old one (`:733`).
- `adminGetDevicelist()` (admin UI device picker) also logs in and creates a session before `GetSystemList` (`:794-819`).

## 3. API endpoints used

| Purpose | Method + path | Request | Response as parsed | Ref |
|---|---|---|---|---|
| List systems | `GET /portal/api/portal/GetSystemList?_=<Date.now()>` | bearer only | JSON array; adapter uses `[].Name`, `[].Id` (→ SystemId), `[].GatewayId`; other fields (e.g. `ContactInformation`, `Description`, `Comment`) may contain line breaks | `lib/wss.js:19,641-658`; `main.js:736-741,772-785,809-813`; `README.md:149` |
| (unused alt.) | `GET /portal/api/portal/systems/50` → `response.data.Systems` | | | `lib/wss.js:18,621-635` (commented) |
| User info / limits | `POST /portal/api/portal/CurrentUserLoadDataSlim` (no body) | | `{IsPasswordReset, UserName, UserSalutationType, Firstname, Surname, CultureInfoCode, TwoLetterCountryCode, Email, MaxSystemBusSamplingRateSec:60}` – only `MaxSystemBusSamplingRateSec` used (warn if poll interval below it) | `lib/wss.js:16,660-692,738-744` |
| GUI / parameter description | `GET /portal/api/portal/GetGuiDescriptionForGateway?GatewayId=<gw>&SystemId=<sys>` | | tree, see §5 | `lib/wss.js:20,28-29,827-847` |
| (unused alt.) | `GET /portal/api/portal/GetGuiDescriptionForAppGateway2` ("App data") | | | `lib/wss.js:21,833` |
| System state | `GET /portal/api/portal/systemstate/<SystemId>` | | `{AccessLevel:4, IsSystemShareDeleted, IsSystemDeleted, IsOnline, IsLocked, MaintenanceState:{Mode,Progress,CWLFilterMaintenancePending}, RequestDate, LastDisconnect}`; only `IsOnline` used → `info.connection` | `lib/wss.js:27,849-884`; `main.js:548-559` |
| Read values (bulk) | `POST /portal/api/portal/GetParameterValues` | `{BundleId, IsSubBundle:false, ValueIdList:[…], GatewayId, SystemId, LastAccess:<string|null>, GuiIdChanged:<bool>, SessionId}` | `{LastAccess:<string>, Values:[{ValueId, Value, State, …}]}`; `State == 1` ⇒ value present | `lib/wss.js:22,894-977` |
| Write values | `POST /portal/api/portal/parameters/write` | see §4 | `{Values:[…]}` (same shape as read) | `lib/wss.js:23,986-1014` |
| (unused old) | `POST /portal/api/portal/WriteParameterValues` | | | `lib/wss.js:24,1003` |
| Expert login | `GET /portal/api/portal/ExpertLogin?Password=<pw>` | see §7 | status only | `lib/wss.js:17,30,699-719` |
| Session | `CreateSession2`, `UpdateSession` | see §2 | | |
| (external) public IP | `GET https://api.ipify.org?format=json` → `{ip}` | | | `main.js:8,49-62` |

## 4. Write path

Trigger: ioBroker `stateChange` with `ack === false` (`main.js:862-863`). The adapter looks up the object's `native.ParameterId`, finds the matching descriptor in `ParamObjList` by **ParameterId** to get its `ValueId` (`main.js:865-867,874`).

Exact payload (`lib/wss.js:986-995` + item built in `main.js:872-879`):

```json
{
  "SessionId": "<BrowserSessionId>",
  "BundleId": 1000,
  "GatewayId": <GatewayId>,
  "SystemId": <SystemId>,
  "WriteParameterValues": [
    {
      "ValueId": <descriptor.ValueId>,
      "ParameterId": <descriptor.ParameterId>,
      "Value": "<String(state.val)>",
      "ParameterName": "<object common.name>"
    }
  ],
  "WaitForResponseTimeout": null,
  "GuiId": null
}
```

- `BundleId` is **hard-coded 1000** for writes; `GuiId` is sent as `null` even though the TabView `GuiId` is known (`main.js:92`). `WaitForResponseTimeout: null`.
- One HTTP call per state change, array always has exactly one item; no batching.
- Value encoding: always `String(state.val)` (`main.js:876`):
  - numbers → `"21.5"`, `"3"` (no rounding to `Decimals`/`StepWidth` – not applied);
  - list items (ControlType 1/35) → the numeric `ListItems[].Value` as string (ioBroker `states` map is keyed by `ListItems.Value`, `main.js:276-282`);
  - booleans (ControlType 5) → `"true"`/`"false"` (JS `String(true)`), whereas the **read** path expects `"True"` (`main.js:479`) – case mismatch, untested whether the server is case-insensitive;
  - strings (9/10/14/20/21) → as typed.
- Response: `response.data` returned raw (`lib/wss.js:1010`). Verification is **optimistic + response-driven**: if `answer.Values !== undefined` the adapter (a) acks the state with the requested value and (b) runs `_SetStatesArray(answer)` which applies `Values[].{ValueId, Value}` to all objects whose `native.ParameterId` matches the descriptor found by `ValueId` (`main.js:880-886,588-616`). No separate re-read; the next poll (with `LastAccess`) picks up server-side changes.
- Errors: HTTP error → warn log, returns `undefined` → `answer.Values` throws TypeError → caught, logged as error; state remains un-acked (`lib/wss.js:1011-1013`, `main.js:887-889`).
- Quirks/constraints: **none** – no retries, no delay, no debounce, no "write once", no min/max clamping before send, no readonly check (write flag on the ioBroker object `common.write = !IsReadOnly` is the only guard, `main.js:220`). A write response with empty `Values` counts toward the "10 consecutive empty responses ⇒ full restart" counter (`main.js:589-600`).

## 5. Parameter description structure (GetGuiDescriptionForGateway) and mapping

Tree walked in `main.js:64-193` (`_getParamsWebGui`):

```
MenuItems[]                      .Name                          (main.js:70-71)
 ├─ TabViews[]                   "Benutzer" level               (:73-74)
 │    .TabName .BundleId .GuiId                                 (:75-78)
 │    .ParameterDescriptors[]                                   (:80)
 │         .Group (optional, → sub-channel)                     (:82-83)
 │         .ChildParameterDescriptors[] (time programs etc.)    (:106-107)
 │              .NoDataPoint, .ParameterId, .Name                (:112-113,108)
 │              .ChildParameterDescriptors[] (3rd level)         (:128-131)
 └─ SubMenuEntries[]             "Fachmann" (expert) level      (:156-158)
      .Name
      .TabViews[] (same shape as above)                         (:159-163)
```

Descriptor fields read (`main.js`):
`ParameterId` (:89), `ValueId` (:313,874), `Name` (:215), `NamePrefix` (prefixed `"A1: "`, :213-214), `IsReadOnly` (:220,243), `ControlType` (:240-250,315,320), `Unit` (:254), `MinValue`/`MaxValue` (:260-261,266-267), `MinValueCondition`/`MaxValueCondition` (strings, `parseFloat`, **override** Min/MaxValue because Min/MaxValue "might be wrong in case of floats", :258-271), `StepWidth` → `common.step` (:273-275), `ListItems[].Value` / `.DisplayText` → `common.states` (:276-282), `Value` (initial value shipped inside the description, written to the state at object creation, :320), `Group` (:82), `NoDataPoint` (:112), `ChildParameterDescriptors` (:106,128). `Decimals` is only mentioned in a comment (:229), not used. No `BundleId`/`GuiId` on the descriptor itself – they are inherited from the enclosing `TabView` and attached by the adapter (:76-78,91-92).

Filters: only `ParameterId > 0` (:89,113,133,174); children additionally `NoDataPoint == false` (:112). Comments: "ignore pseudo or intermediate/complex parameters (e.g. list of time programs)" (:88,110).

ControlType table (adapter comment `main.js:225-238`, duplicate at :462-475):

| ControlType | Meaning (per comment) | ioBroker type/role | value parse |
|---|---|---|---|
| 0 | Unknown | number/value | `parseFloat` |
| 1 | Enum w/ ListItems (simple) | number/value + `states` | `parseFloat` |
| 5 | Bool | boolean; role `indicator` if read-only else `switch` | `value === 'True'` |
| 6 | Number; `Decimals` = decimal places | number/value (+unit/min/max/step) | `parseFloat` |
| 9 | Date | string/text | `toString()` |
| 10 | Time | string/text | `toString()` |
| 13 | list of time programs (1,2,3) – not a value | (filtered: no ParameterId / NoDataPoint) | – |
| 14 | list of time ranges | string/text | `toString()` |
| 19 | time program Mon–Sun – not a value | (filtered) | – |
| 20 | Name, SerialNo, MacAddr, SW/HW-Version | string/text | `toString()` |
| 21 | IPv4 addr or netmask | string/text | `toString()` |
| 31 | Number of any kind | number/value | `parseFloat` |
| 35 | Enum w/ ListItems (w/ Image, Description, …) | number/value + `states` | `parseFloat` |

Mapping rules (`main.js:240-283`): type 5 → boolean; 9/10/14/20/21 → string; everything else → number with unit/min/max/step/states. **Writable = `!IsReadOnly` only** (:220); ControlType never affects writability. Expert-ness is purely structural (under `SubMenuEntries` = "Fachmann" subtree, :156; `README.md:73`); no per-parameter expert flag is read; `systemstate.AccessLevel` is ignored.

Object id: `<MenuItem.Name>.<TabName>[.<Group>].<ParameterId>` (expert: `<MenuItem.Name>.<SubMenuEntry.Name>.<TabName>[.<Group>].<ParameterId>`), spaces replaced by `_` (only the first space – `.replace(' ', '_')`, :83,123,144,160,168). `native` stores `{ValueId, ParameterId, ControlType}` (:312-316). Channel name shows the BundleId: `"<tab> (Bundle: <BundleId>)"` (:339).

Duplicates: de-duplicated by **ParameterId, first occurrence wins** (`param.find(e => e.ParameterId === paramInfo.ParameterId)`, :95-102,120-125,139-146,180-185). Because `TabViews` (user) are processed before `SubMenuEntries` (expert), a parameter present in both trees keeps the user-level TabName/BundleId/GuiId. ValueId is not used for dedup. (`_CreateBundleValuesLists` has a second, ineffective dedup – it tests `array[ParameterId]` as an index, :398-403 – harmless since input is already unique.) Objects that disappear from the description are marked `common.desc = 'obsoleted'`, present ones `'active'` (:305,323-334).

**Quirk worth verifying:** the `ValueIdList` sent to `GetParameterValues` is filled with **ParameterId**s (`main.js:399-402,408,416,424` → `lib/wss.js:899`), while responses are matched on `Values[].ValueId` against descriptor `ValueId` (`main.js:606`). Writes send both `ValueId` and `ParameterId`. Either the server accepts ParameterIds in `ValueIdList`, or ValueId == ParameterId for the parameters that matter; the code works in the field either way.

## 6. Polling

Defaults (`io-package.json:183-191`): `pollIntervalShort: 120` s, `pollIntervalLong: 60` min, `doPollAllParams: true`, `doPubIpCheck: true`, `doApiProfile: false`, `bundleIdRequestedShort/Long: "Default"`. Admin UI bounds: short min 60 s step 15 (`admin/jsonConfig.json:172-182`), long min 15 min (`:183-194`). Known BundleIds listed: 1000, 3100, 3500, 4300, 6300, 6500, 7100, 7300, 7600, 8000, 8100, 8200, 10000, 10700, 14000, 14700, 15600, 15700, 15800 (`admin/jsonConfig.json:252-273`, `io-package.json:192-288`).

Server minimum: `MaxSystemBusSamplingRateSec` (60) from `CurrentUserLoadDataSlim`; adapter only **warns** if the short interval is below it (`lib/wss.js:738-744`). README: going below "will not respond in the expected way or may even disconnect your session" (`README.md:56`).

Cycles:
- Short: `_ShortPollValueList` → `GetParameterValues` → `setTimeout(pollIntervalShort*1000)` (`main.js:530-568`). Every 5th short cycle (`onlinePoll > 4`, initial value 4 so the first run does it immediately, `:535-537,805`): public-IP check via ipify (IP change ⇒ `_mainloop()` = full re-login) and `systemstate` → `info.connection` (`:538-559`).
- Long: `_LongPollValueList` → `setTimeout(pollIntervalLong*60*1000 + 5000)` – 5 s offset "to avoid parallel execution" with the short cycle (`main.js:574-586`). Only started if the long ValueId list is non-empty (`:674-676`).
- BundleId per request: with `doPollAllParams` the full ParameterId list is sent with `BundleId: 1000` (`main.js:12-13,406-412`); otherwise per-cycle lists are built from the `bundleIdTable` and the BundleId is the configured one, or "Default" = the **largest** selected BundleId (min 1000) (`:383,414-453`). README: relation of BundleId to the parameter list "not quite clear"; 1000 "will likely exclude some Expert parameters" (`README.md:65-69`).

Changed-since mechanism (`LastAccess`/`GuiIdChanged`, `lib/wss.js:61-62,746-747,896-914,937-943`):
- First request per cycle: `LastAccess: null`, `GuiIdChanged: true` ⇒ server returns the full value list (logged at info, `:928-931`).
- The response's `LastAccess` string is stored per cycle and echoed in the next request (`GuiIdChanged: false`) ⇒ only changed values come back.
- Per-cycle `LastAccessShort`/`LastAccessLong`; **a request in one cycle resets the other cycle's `LastAccess` to null** (`:912-914`), so after each long poll the next short poll is a full fetch and vice versa. Both reset on every `init()` (re-login) (`:746-747`).
- README (`:73`): in user mode the periodic polls only return updates for user-level parameters; expert-level values need the expert login.

Rate limiting / backoff: **none**. No HTTP 429 handling at all (the only 429 check is in the unrelated Google-translate helper, `lib/tools.js:91`). No exponential backoff.
Error handling: `GetParameterValues` HTTP 400/401 ⇒ `_refreshAuthToken()` (`lib/wss.js:971-976`); other errors logged, timer continues at the normal interval. 10 consecutive responses with empty `Values` ⇒ `_mainloop(null)` full restart (`main.js:588-600`). Any `_mainloop` failure ⇒ retry after fixed 60 s (`main.js:678-685`). Tokens refreshed at `expires_in` (§1).

API profiling states (optional): `info_api.poll_req_bundle_id`, `poll_req_num_params`, `poll_resp_num_params`, `poll_resp_num_values` (= count of `State == 1`), warn listing ValueIds with `State != 1` (`lib/wss.js:916-919,944-969`; `README.md:113-121`).

## 7. Expert / Fachmann login

- Request: `GET /portal/api/portal/ExpertLogin?Password=<expertPassword>` – password in the **query string, not URL-encoded**, headers = API header with bearer token and empty `Content-Type` (`lib/wss.js:17,30,699-709`). Success = any 2xx (status logged, body ignored, `:713-714`); any error ⇒ `false` (`:715-718`).
- When: inside `init()` after `CreateSession2` + `CurrentUserLoadDataSlim`, only if `config.doExpertLogin` (`lib/wss.js:749-757`); sets `isExpertSession = true` (informational only).
- Re-login: "Expert Mode needs periodic re-initialization" – `ExpertTimeout` re-runs the whole `init()` every **2 h** (`_API_INTERVAL_EXPERT_LOGIN = 7200000`, `lib/wss.js:34,71,758-764`). `init()` keeps the existing OIDC token if present (`:729-731`) and does a fresh `CreateSession2` + `CurrentUserLoadDataSlim` + `ExpertLogin` (`:733-757`), resetting both `LastAccess` values (`:746-747`).
- Config: `doExpertLogin` (default false), `expertPassword` (encrypted/protected, default "") (`io-package.json:170-177,185-186`; `admin/jsonConfig.json:332-353`).
- Documented behaviour (`README.md:71-111`): expert level is server-side sticky ("Pandora's box"): disabling it, logging out and deleting tokens/session is not enough; "only a change of the adapter's public IP address in combination with an adapter instance reload" returns to user level (`:83-87`). Side effect: some pre-period statistics (ParameterIds `27017500001`, `27017600001`, `27017700001`) are not updated reliably in expert mode (`:89-100`). Expert parameters live under the "Fachmann" subtree and are only refreshed by polling after expert login (`:73-79`).

## 8. Multiple sessions, gateway/system IDs, IP awareness, error codes

- IDs: the admin UI stores the selected system object from `GetSystemList` as JSON in `config.device`; at start `device.SystemId = device.Id` (`main.js:766-797,809-813`). `GatewayId` + `SystemId` go into `GetGuiDescriptionForGateway`, `GetParameterValues`, `parameters/write`; `systemstate` takes `parseInt(SystemId)` in the path (`main.js:548`). One adapter instance per device (`README.md:35`).
- Client-IP awareness (`README.md:106-108`, `main.js:629-648,722-734`): the server "associates some application state information with the public IP address of the client"; on IP change the adapter discards the `WolfSmartSet` object and does a full login + session (optional check via ipify every 5th short cycle; otherwise only on the hourly re-auth).
- Parallel sessions: the admin "getDeviceList" message may create a second client (second OIDC login + `CreateSession2`) if credentials/IP differ from the running one; it is adopted as the instance client if none exists (`main.js:710-763`). Each `init()` creates a fresh portal session without ending the previous one; `stop()` ends only the OIDC session (`lib/wss.js:782-788,482-535`). README states the Wolf app/portal can be used in parallel (`README.md:16`).
- HTTP codes handled: login POST must answer **302** (`lib/wss.js:283-286`); `UpdateSession` **400/401** ⇒ new session, then full init (`:605-610`); `GetParameterValues` **400/401** ⇒ silent token refresh (`:973-975`); OIDC `prompt=none` error `login_required` ⇒ full re-login (`:471-475`); `endsession` expects 200 (`:522`). Nothing for 403/429/5xx. API response-level codes: `Values[].State == 1` = value present (`:950,965`); `systemstate.AccessLevel` (sample value 4) returned but unused (`:855`).
- Misc headers/quirks: `Host` set manually (`:114`), `Connection: keep-alive` without a keep-alive agent, `Cache-control: no-cache`, `Timestamp` in CreateSession2 is local time without zone (`:124-133`), `GetSystemList` gets a cache-buster `?_=<ms>` (`:645`).
