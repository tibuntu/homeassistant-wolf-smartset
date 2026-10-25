# Phase 0 – Discovery: Wolf-SmartSet-Cloud-API, bestehende Implementierungen, Gap-Analyse

Stand: 2026-10-14. Alle Aussagen sind mit Quelle markiert. Kennzeichnung der Belastbarkeit:

- **[Code]** direkt aus Quellcode abgeleitet (wolf-comm, HA-Core, heatwrite, wolflink-write, ioBroker, offizielles Portal-JavaScript)
- **[Doku]** README/Kommentar eines Maintainers
- **[Bericht]** Nutzerbeobachtung ohne Verifikation
- **[Offen]** nicht belegt, muss am echten System geprüft werden (nur lesend, bis Freigabe)

Es wurde **nichts** gegen die Wolf-Cloud mit Zugangsdaten ausgeführt. Einzige Netzwerkzugriffe: öffentliche, unauthentifizierte GETs auf die Portal-Startseite und deren JavaScript-Bundles (statische Assets), GitHub-API, PyPI.

## 0. Kurzfassung

1. **Auth** ist OpenID Connect Authorization-Code + PKCE gegen den IdentityServer `/idsrv` mit dem öffentlichen Client `smartset.web`; das Login-Formular wird gescrapt (`__RequestVerificationToken`). Kein Refresh-Token; Token-Laufzeit laut ioBroker 1 h; wolf-comm loggt sich bei Ablauf komplett neu ein. [Code]
2. Auf dem Token sitzt eine **Portal-Session** (`CreateSession2` → `BrowserSessionId`), die per `UpdateSession` am Leben gehalten wird (wolf-comm/ioBroker: alle 60 s). Jede Session aktiviert beim Lesen „Push-Bundles“ am Gateway; `CloseSystem`/`DeactivatePushBundle` geben sie frei. [Code]
3. **Parallele Sessions** sind das Normalmodell des Portals (App, Web-Portal, mehrere Browser). ioBroker läuft dokumentiert parallel zur App; der HA-Codeowner nutzt Integration und App gleichzeitig. Es gibt keinen Beleg, dass eine zweite Session eine andere „entwertet“. [Doku/Code] Was es gibt, sind **IP-basierte, temporäre Sperren** (Minuten bis ~1 h, in einem Fall Tage) nach zu vielen **Logins** oder fehlerhaftem Polling; sie treffen Portal und App auf derselben IP mit, das Gateway bleibt online. Wolf hat 2024 den Passwort-Login „wegen extrem vieler Login-Requests“ abgeschaltet und verlangt Token-Wiederverwendung. Die Cloud kennt den Fehlercode `ToManyRequests` (10); die einzige Zahl ist `MaxSystemBusSamplingRateSec = 60`. [Code/Wolf offiziell/Bericht, Abschnitt 11]
4. **Fachmann-Login** (`ExpertLogin?Password=…`) ist serverseitig „klebrig“ und an die öffentliche IP gebunden; ioBroker dokumentiert, dass man nur per IP-Wechsel plus Neustart zurück auf Benutzer-Level kommt und einzelne Statistiken dann nicht mehr aktualisieren. Die Fachmann-Parameter**beschreibung** kommt ohne ExpertLogin; viele Fachmann-**Werte** ebenfalls, einige nur, solange eine Fachmann-Session desselben Kontos aktiv ist (ioBroker #242). Ob ExpertLogin fürs **Schreiben** von Fachmann-Parametern (Sparfaktor, Heizkurve) nötig ist, ist unbelegt. [Doku/Offen]
5. Die **Parameterbeschreibung** (`GetGuiDescriptionForGateway`) ist ein GUI-Baum (`MenuItems` → `TabViews`/`SubMenuEntries` → `ParameterDescriptors`). Pro Descriptor: `ValueId`, `ParameterId`, `Name`, `NamePrefix`, `Group`, `IsReadOnly`, `ControlType`, `Unit`, `MinValue`/`MaxValue`/`StepWidth`/`Decimals`, `ListItems`, aktueller `Value`. Die `ControlType`-Enum ist im Portal-JS vollständig benannt (36 Werte). [Code]
6. `IsReadOnly == false` allein reicht **nicht** als Schreibkriterium: Übersichts-Werte (ControlType 0) tragen `IsReadOnly: false`, obwohl sie Messwerte sind; außerdem fehlt das Feld in Schema-Konfigurationen ganz, und dieselbe `ValueId` steht in bis zu drei Tabs mit widersprüchlichem `IsReadOnly`. Schreibbarkeit muss aus `IsReadOnly` **und** `ControlType` **und** dem `AccessLevel` des Systems abgeleitet werden. [Code]
7. **Schreiben**: Das Web-Portal selbst nutzt `WriteParameterValues` mit genau dem Payload von wolf-comm (`{WriteParameterValues:[{ValueId, Value:"<string>", ParameterName}], SystemId, GatewayId, BundleId, SessionId}`) und bestätigt den Schreibvorgang durch Nachlesen (Poll alle 3 s, max. 60 s, Zustandsmaschine `EnParamState`: WritePending → WriteAcknowledge/OK). ioBroker nutzt den neueren Endpoint `parameters/write` und bekommt die neuen Werte direkt in der Antwort. [Code]
8. **wolf-comm 0.0.52** liefert Auth, Session, Systemliste, Werte lesen und einen Write-Aufruf. Es verliert aber Name (übersetzt), Gruppe, Min/Max/Step/Decimals, ControlType, NamePrefix und dedupliziert per `value_id` „wer zuerst kommt“, wirft unbekannte Einheiten weg, hat keine öffentliche Roh-Abfrage und wiederholt Writes nach HTTP 401/500 blind. [Code]
9. **heatwrite** hat die richtigen Schutzmechanismen (No-Op, Rate-Limit, Lock, Historie in `.storage`, Undo, Snapshots, dry_run, nur aktivierte Entitäten pollen), hängt aber per Design an `wolflink`-Interna (`entry.runtime_data`, `coordinator._wolf_client`, `_WolfClient__request`, Umschalten von `client.expert_mode` auf dem fremden Client). Das verletzt Regel 3 und ist nicht Core-fähig. [Code]
10. **Empfehlung**: eigenständige Integration mit eigener, HA-freier, dünner API-Schicht im Repo (Auth-Flow aus wolf-comm portiert, Rohbeschreibung, Write mit Bestätigung, Fehlercodes), kein Huckepack, kein wolf-comm-Fork. Begründung in Abschnitt 8. Entscheidung formal in Phase 1 (ADR).

## 1. Quellen und Versionsstand

| Quelle | Stand | Verwendet für |
|---|---|---|
| `janrothkegel/wolf-comm` | Commit `b5cea37` (2026-06-15), Version 0.0.52 = PyPI 0.0.52 (identisch, per `diff` geprüft) | Auth, Session, Mapping, Tests, `parameters-examples/` (vier echte `GetGuiDescriptionForGateway`-Antworten: Gas, Gas-Hybrid, Wärmepumpe, Lüftung) |
| `home-assistant/core` `homeassistant/components/wolflink` | Tag `2026.10.1` (2026-10-10) und `dev` `e456864` (2026-10-14) | aktueller Read-Pfad, Entity-/Device-Modell, Quality Scale |
| PR home-assistant/core#128988 | geschlossen 2024-12-30 (stale), Autor baststar | Review-Diskussion zu Services vs. Entitäten |
| `mike-139/heatwrite` | `a271b8c` (2026-10-01), Version 0.1.0 | Feature- und Fallstrick-Referenz |
| `11790415/wolflink-write` | `8820e0b` (2026-09-14), Version 0.7.6 | minimaler Service-Port, Beobachtungen zu Fachmann-Werten |
| `iobroker-community-adapters/ioBroker.wolf-smartset` | `24790aa` (2026-10-13), Version 2.1.2 | funktionierende JS-Implementierung inkl. Schreiben, ExpertLogin, Polling-Strategie |
| `zivillian/ism7mqtt` | `6a0aeca` (2026-09-27) | Abgrenzung (lokal, ISM7-Einzelverbindung) |
| Portal-JavaScript `https://www.wolf-smartset.com/js/app-all-20261008.min.js` | Build vom 2026-10-08, öffentlich abrufbar | offizielle Enums (`EnControlType`, `EnParamState`, `BusinessServiceErrorCodeEnum`, `AccessLevel`), Write-/Poll-Logik des Web-Clients |
| `probatio` 0.13.0 (PyPI), HA `pyproject.toml` 2026.4–2026.10 | | HA-Plattformfakten (Abschnitt 7) |

Detailauswertungen (ioBroker-Bericht, jq-Statistiken über die Beispiel-Beschreibungen) liegen im Session-Scratchpad; die relevanten Zahlen sind hier übernommen.

## 2. Auth-Flow (wolf-comm 0.0.52)

### 2.1 Ablauf [Code: `wolf_comm/token_auth.py`, `constants.py`]

| Schritt | Request | Details |
|---|---|---|
| 0 | lokal | `pkce.generate_pkce_pair()` → `code_verifier`/`code_challenge`; `state = shortuuid.uuid()` |
| 1 | `GET https://www.wolf-smartset.com/idsrv/Account/Login?ReturnUrl=/idsrv/connect/authorize/callback&client_id=smartset.web&redirect_uri=https://www.wolf-smartset.com/signin-callback.html&response_type=code&scope=openid profile api role&state=…&code_challenge=…&code_challenge_method=S256&response_mode=query&lang=en-GB` | HTML-Login-Seite; daraus per lxml `//input[@name="__RequestVerificationToken"]/@value` |
| 2 | `POST …/idsrv/Account/Login?ReturnUrl=<wie oben>` Form: `Input.Username`, `Input.Password`, `__RequestVerificationToken`; Cookies aus Schritt 1; `follow_redirects=True` | Endet auf `signin-callback.html?code=…&state=…`; `code` aus `r.url.params` |
| 3 | `POST …/idsrv/connect/token` Form: `client_id=smartset.web`, `code`, `redirect_uri`, `code_verifier`, `grant_type=authorization_code` | JSON mit `access_token`, `expires_in`; bei Key `error` → `InvalidAuth` |

- Client ist ein **öffentlicher** OIDC-Client ohne Secret (ioBroker: `token_endpoint_auth_method: none`, Discovery unter `/idsrv/.well-known/openid-configuration`). [Code ioBroker `lib/wss.js:185-196`]
- Passwörter > 30 Zeichen werden clientseitig abgelehnt (`PasswordToLong`), weil der Server sie stillschweigend ablehnt. [Code/Doku wolf-comm]
- wolf-comm sendet feste Browser-Header (Firefox-UA, `Sec-Fetch-*`); ioBroker ebenfalls. Ob der Server darauf prüft, ist unbekannt. [Offen]

### 2.2 Token-Lebensdauer und Erneuerung

- `Tokens.expire_date = now + expires_in`; bei Ablauf wird der **komplette Login** (Schritte 1–3) wiederholt. Kein Refresh-Token, kein `id_token` genutzt. [Code wolf-comm]
- Die Laufzeit (`expires_in`) ist in keiner Quelle protokolliert; ein ioBroker-Maintainer nennt „meistens 1h“ (2023), ioBroker-Logs zeigen alle ~10 h ein `login_required` (Ende der IdentityServer-Session, danach voller Login). ioBroker erneuert per **silent re-authorize** (`prompt=none&id_token_hint=<id_token>` mit den `idsrv.session`-Cookies); bei `login_required` voller Login. [Code ioBroker `lib/wss.js:368-477`, Doku README]
- Konsequenz: wolf-comm wiederholt bei Token-Ablauf den vollen Login (bei 1 h Laufzeit 24 Logins/Tag); genau diese **Login-Häufigkeit** ist laut Wolf und allen Sperr-Berichten der kritische Faktor (Abschnitt 11). Silent-Renew mit den IdentityServer-Cookies reduziert das auf wenige Logins pro Tag, ist aber nur in JS belegt. [Offen: in Python nachbauen und testen]

### 2.3 Fehlerbilder im Login [Code wolf-comm]

| Exception | Bedeutung | Reaktion sinnvoll |
|---|---|---|
| `InvalidAuth` | Token-Endpoint liefert `error` (falsche Credentials) oder beliebige andere Ausnahme im Flow (breit gefangen, `raise … from e`) | Reauth-Flow nur bei echtem Credential-Fehler |
| `PortalUnavailable` (Subklasse von `InvalidAuth`) | Login-Seite ohne `__RequestVerificationToken` → laut Docstring „portal is rate-limiting, in maintenance, or serving an error page“; Credentials wurden nie gesendet | zurückhalten und später erneut versuchen, **nicht** reauth |
| `PasswordToLong` | > 30 Zeichen | Config-Flow-Validierung |

Wichtig für uns: wolf-comm unterscheidet nicht zwischen „Credentials falsch“ und „Flow kaputt“ (z. B. HTML geändert). Ein eigener Client sollte das Token-Endpoint-`error` (z. B. `invalid_grant`) explizit auswerten.

### 2.4 Portal-Session [Code wolf-comm `create_session.py`, `wolf_client.py`; Portal-JS; ioBroker]

| Aufruf | Payload | Antwort / Verhalten |
|---|---|---|
| `POST /portal/api/portal/CreateSession2` | `{"Timestamp": "YYYY-MM-DD HH:MM:SS"}` (lokale Zeit) | `{"BrowserSessionId": <int>, "IsProfessional": bool, "IsProfessionalPasswordReset": bool, "CultureInfoCode": …, "CommittedUserInfoMessageIds": […]}` (Felder laut Portal-JS) |
| `POST /portal/api/portal/UpdateSession` | `{"SessionId": <id>}` | Antwort enthält `Maintenance`; bei `Maintenance == 1` meldet das Portal den Nutzer nach 60 s ab. wolf-comm ruft es lazy vor einem Request auf, wenn der letzte Refresh > 60 s her ist; ioBroker per Timer alle 60 s; bei HTTP 400/401 legt ioBroker eine neue Session an |
| `POST /portal/api/portal/CloseSystem` | `{"SessionId": <id>}` | Portal ruft es beim Schließen eines Systems; wolf-comm hat `close_system()`, core `wolflink` ruft es **nie** |
| `POST /portal/api/portal/DeactivatePushBundle` | `{"SessionId", "GatewayId", "BundleId", "IsSubBundle": true}` | Portal ruft es beim Schließen von Unterdialogen (Zeitprogramme, Party-Modus); gibt das am Gateway aktivierte Bundle frei |

wolf-comm injiziert `SessionId` automatisch in jeden JSON-Body (dict) und setzt den Bearer-Header; bei HTTP **401 oder 500** wird einmal komplett neu eingeloggt und der Request wiederholt (`RETRY_STATUS_CODES = {401, 500}`). Das gilt auch für `WriteParameterValues` → ein Write, der serverseitig durchging und mit 500 beantwortet wurde, würde ein zweites Mal gesendet. [Code `wolf_client.py:102-129`]

### 2.5 Weitere Endpunkte, die das Portal kennt [Code Portal-JS `FuncType`]

`GetSystemList`, `GetSystemStateList` (POST, wolf-comm) bzw. `systemstate/{systemId}` (GET, ioBroker; liefert `AccessLevel`, `IsOnline`, `IsLocked`, `MaintenanceState`, `LastDisconnect`), `CurrentUserLoadDataSlim` (u. a. `MaxSystemBusSamplingRateSec`), `GetGuiDescriptionForGateway`, `GetGuiDescriptionForAppGateway2` (App-Variante), `GetParameterValues`, `WriteParameterValues`, `parameters/write` (ioBroker), `ExpertLogin`, `UnlockSystem` (Passwort-Freischaltung eines gesperrten Systems), Snapshots (`StartCreateSystemSnapshot`, `WriteSystemSnapshotValues`, …), Datalog, Störmeldungen, EEBus. Für uns relevant sind nur die ersten acht.

## 3. Parallele Sessions, Rate-Limits, Sperren

### 3.1 Was der Server kennt [Code Portal-JS `Declarations`]

- `BusinessServiceErrorCodeEnum`: `Unknown:0, InvalidSession:1, TimeoutException:2, InvalidCredentials:3, SystemOffline:4, Unspecified:5, Maintenance:6, IncompatibleWebApiVersion:7, BusScanPending:8, DatalogStartedByForeignUser:9, ToManyRequests:10`. Fehler kommen als JSON `{ErrorCode, ErrorType, Message, MessageParams}` (ErrorType 0 = Feldfehlerliste `Errors[].Messages`). Das Portal meldet bei `InvalidSession` und `ToManyRequests` den Nutzer ab.
- `AccessLevel` pro System: `0 Keine Berechtigung, 1 Benutzer lesen, 2 Benutzer schreiben, 3 Fachmann lesen, 4 Fachmann schreiben`; `isExpertMenuVisible = AccessLevel >= 3`; `hasWriteAccess` prüft gegen eine `WriteAccessLevel`-Liste. ioBroker sieht in `systemstate` den Wert 4 bei einem eigenen System. Geteilte Systeme („SystemShareId“, core `wolflink` seit 2026.7) können weniger haben.
- `GatewayOfflineCause`: `None, NormalDisconnect, SystemconfigChanged, KeepAliveTimeout, ForceDisconnectBundle, MissingResponse, SocketServerShutdown, AlreadyConnected` – zeigt, dass das Gateway Bundle-/Keepalive-Zustände hat, die durch Clients beeinflusst werden.
- `EnParamState`: `ReadPending:0, OK:1, WritePending:2, WriteAcknowledge:3, Timeout:4, Error:5` (siehe 5.1/5.2).
- Der Server ist **client-IP-bewusst**: ioBroker dokumentiert, dass Anwendungszustand (insbesondere der Fachmann-Level) an die öffentliche IP des Clients gebunden ist, und erzwingt bei IP-Wechsel einen Neu-Login. [Doku ioBroker README, Code `main.js:629-648`]

### 3.2 Evidenz zu parallelen Sessions

| Beleg | Art | Aussage |
|---|---|---|
| Portal-Architektur (`BrowserSessionId` pro Client, `CreateSession2` bei jedem Seitenaufruf) | [Code] | Mehrere gleichzeitige Sessions pro Konto sind das Normalmodell (Web + App + mehrere Browser) |
| ioBroker README Zeile 16 | [Doku] | Adapter kann parallel zur Wolf-App/zum Portal genutzt werden |
| ioBroker `init()` | [Code] | legt bei jedem Init (Start, alle 2 h im Expertenmodus, nach Token-Verlust, nach IP-Wechsel) eine **neue** Session an und schließt die alte nicht; der Admin-Gerätepicker öffnet eine zweite Login-Session. Keine dokumentierten Probleme dadurch |
| heatwrite README | [Doku] | „Keine zweite Anmeldung, keine zweite Cloud-Session“ ist eine **Designentscheidung** des Autors, kein Beleg für ein Problem |
| wolflink-write `sensor.py` Docstring | [Bericht] | Hypothese des Autors, ein zweiter `WolfClient` mit `expert_p=True` „würde eine zweite Sitzung auf demselben Konto öffnen und die Sitzung der offiziellen Integration entwerten können“ – nicht belegt |
| Core `wolflink` + `heatwrite` + App | [Bericht] | heatwrite-Nutzer betreiben Portal/App parallel zur HA-Session (impliziert durch den Workflow „ValueIds im Portal nachsehen“) |
| HA-Codeowner EnjoyingM, HA #116780 (2024-05) | [Doku] | „I'm able to use this integration and at the same time the smart apps.“ |
| HA #155531 (2025-10 bis 2026-01) | [Bericht/Doku] | Sechs Config-Entries = sechs gleichzeitige Logins beim HA-Start → `KeyError: 'code'`, IP gesperrt; Codeowner: Wolf erlaubt nur „a very [small] number of api calls for getting the token“. Behoben durch das Hub-Modell (ein Login pro Konto, HA 2026.7) |
| HA #173609 (2026-06) | [Doku] | Geteilte Systeme (Zweitnutzer mit „Fachmann schreiben“- bzw. „Contractor“-Rechten) funktionieren seit wolf-comm 0.0.52 über `SystemShareId`; ein dedizierter Smartset-Nutzer pro Client ist möglich |

Fazit: Es gibt **keinen Beleg**, dass die Cloud eine zweite Session ablehnt oder eine bestehende beendet. Belegt ist: der Fachmann-Level klebt serverseitig und IP-gebunden (3.3), jede Session aktiviert eigene Push-Bundles am Gateway (3.4), und **gleichzeitige Logins** mehrerer Clients von derselben IP (z. B. beim HA-Start) lösen Sperren aus. Core `wolflink` parallel bedeutet zwei Logins beim Start und zwei pro Token-Ablauf. Ob es weiterlaufen soll, ist damit eine Last-/Risikofrage, keine Funktionsfrage. [Offen: im Read-only-MVP parallel zu core `wolflink` beobachten: Werteaktualität, Fehler im Log beider Integrationen]

### 3.3 Evidenz zu Rate-Limits und Sperren

| Beleg | Art | Aussage |
|---|---|---|
| `BusinessServiceErrorCodeEnum.ToManyRequests = 10` | [Code Portal-JS] | Die API hat ein explizites Rate-Limit-Fehlerbild; das Portal loggt den Nutzer dann aus. Schwellen unbekannt |
| wolf-comm `PortalUnavailable` | [Code/Doku] | Maintainer hat Login-Seiten ohne Token gesehen und deutet sie als Rate-Limiting/Wartung; betrifft den **Login**, nicht die API |
| wolflink-write README | [Bericht] | „Wolf sperrt IPs zeitweise bei zu vielen Auth-Vorgängen – daher Schaltvorgänge nicht im Sekundentakt auslösen“ |
| `CurrentUserLoadDataSlim.MaxSystemBusSamplingRateSec = 60` | [Code ioBroker] | ioBroker interpretiert es als serverseitiges Minimum fürs Polling und warnt darunter (README: darunter „may even disconnect your session“). Im Portal-JS ist derselbe Wert das **Maximum** des Abtastintervalls im Datalog-Dialog. Lesart „nicht schneller als 60 s“ ist für beide Interpretationen sicher |
| `LuConViewModel.Communication.MaxErrorDurationSec = 120`, Timeout `WriteParameterValues`/`GetParameterValues` 60 s | [Code Portal-JS] | Das Portal toleriert bis 120 s Kommunikationsfehler bei `UpdateSession`, bevor es Fehler anzeigt |
| Core `wolflink` pollt alle 60 s (seit Jahren, bronze) | [Code] | 60 s pro System ist offensichtlich verträglich |
| ioBroker Defaults: kurz 120 s (UI-Minimum 60 s), lang 60 min | [Code] | konservativer als core |
| Wolf-Dev-Team auf GitHub (2024-03-14) | [Wolf offiziell] | „Due to extreme high amounts of login requests we had to take action and disable today your currently used method. If you try again please use the OAuth flow and reuse your tokens like the official products.“ |
| HA #113492, #104595, ioBroker #249/#516, openHAB #17541 (2023–2026) | [Bericht] | IP-Sperren nach häufigen Logins/Polls: Portal und App auf derselben IP blockiert, Gateway bleibt online; Dauer „einige Minuten“ bis „~1 h“, nach Router-Neustart (neue IP) sofort frei; openHAB-Maintainer: Sperre über Tage (429, dann 400) |
| ioBroker #242 (2025-01) | [Doku] | Nach ~20 h Fachmann-Polling mit vielen Werten HTTP 400 auf `GetGuiDescriptionForGateway`, danach auch im Portal keine Fachmann-Werte; 75 % leere `GetParameterValues`-Antworten bei 15 s Intervall = Drosselung; Maintainer-Regel „je mehr Werte, desto länger das Intervall“ (60 → 120 s) |
| ioBroker #459 (2025-05) | [Bericht/Doku] | Polling mit einer für die Anlage **ungültigen BundleId** ließ das Portal „Zugang gesperrt – Ungültige Konfiguration“ anzeigen und die App „offline“; nur ein IP-Wechsel half |
| ioBroker #427 (2025-02) | [Bericht] | Ein Skript, das denselben Wert bei jedem Trigger schrieb, erzeugte regelmäßige Verbindungssperren; nach Umstellung auf „nur bei Änderung“ keine mehr |
| HA PR #111483 / #116758 (2024) | [Doku] | 60 → 90 → 60 s; Codeowner: „The vendor is not restricting polling on the API only on the authentication“; Web und App pollen alle 10 s |
| HA #157250 / PR #158912 (2025-12) | [Doku] | Langsame Wolf-Server, HTTP-Timeout 5 → 20 s; Contributor: „The Wolf backend is not build to handle so many requests“ |
| Community-Berichte im Detail | Abschnitt 11 und Anhang | |

Fazit: Ein Poll-Intervall ≥ 60 s pro System, **so wenige Logins wie möglich**, eine Session, nur gültige BundleIds und Backoff bei `ToManyRequests`/`PortalUnavailable`/leeren Antworten sind die belegbaren Regeln. Konkrete Sperrschwellen kennt niemand; alle Sperren sind IP-bezogen und temporär.

### 3.4 Gateway-Last durch Bundles [Code Portal-JS, ioBroker, wolflink-write]

- `GetParameterValues` nimmt `BundleId` + `IsSubBundle` + `ValueIdList` + `LastAccess` + `GuiIdChanged`. Das Portal fragt nur das Bundle des sichtbaren Tabs ab (alle 10 s, nach Writes 3 s) und deaktiviert Sub-Bundles beim Schließen eines Dialogs. Das Gateway „pusht“ offenbar nur Werte aktiver Bundles aus dem eBus in die Cloud.
- wolflink-write beobachtet: Fachmann-Werte frieren ein, wenn keine GUI-Session sie angefordert hat; Abhilfe war ein erneuter `GetGuiDescriptionForGateway`-Aufruf bzw. `IsSubBundle: true` (im Code dort fälschlich als `Bundle` bezeichnet). [Bericht]
- ioBroker README: Werte der Fachmann-Ebene werden nur nach ExpertLogin per Polling aktualisiert; im Expertenmodus aktualisieren bestimmte Statistiken (ParameterIds 27017500001–27017700001) nicht zuverlässig. [Doku]
- ioBroker #242 (Maintainer-Befund 2025-01): einzelne Fachmann-Werte kommen nur, solange eine Fachmann-Session desselben Kontos aktiv ist (Portal mit PIN geöffnet oder `ExpertLogin` in der eigenen Session), danach noch ~10 min. Zusätzlich muss der erste `GetParameterValues`-Aufruf mit `LastAccess: null, GuiIdChanged: true` erfolgen. „Viele Fachmann-Werte kommen auch ohne Fachmann-Login, einige halt nicht.“ [Doku]
- wolf-comm im Expertenmodus sendet pro Poll **eine Anfrage pro BundleId** (Wärmepumpen-Beispiel: 10 Tabs mit 7 verschiedenen Bundles); heatwrite pollt nur Bundles aktivierter Entitäten.

Konsequenz: Nur Bundles abfragen, deren Parameter aktiv sind; Intervall ≥ 60 s; Verhalten eingefrorener Fachmann-Werte im Read-only-MVP messen. [Offen]

### 3.5 Community-Berichte (Web-Recherche)

Ergebnis des separaten Recherche-Agenten (GitHub-Issues, HA-Community, ioBroker-Forum, deutsche Heizungsforen) – siehe Nachtrag am Ende dieses Dokuments, Abschnitt 11.

### 3.6 Empfehlungen für unseren Client

1. Genau **eine** Session pro Konto und HA-Instanz; `CloseSystem` beim Entladen; `UpdateSession` nur, solange gepollt wird.
2. Login nur bei Token-Ablauf oder `InvalidSession`; nach `InvalidCredentials` sofort Reauth-Flow, nach `PortalUnavailable`/`ToManyRequests`/HTTP 429 exponentielles Backoff (Minuten), **kein** Retry-Sturm.
3. Keine automatische Wiederholung von `WriteParameterValues` nach 5xx; stattdessen Nachlesen und dem Nutzer den Zustand melden.
4. Poll-Intervall ≥ 60 s, Default eher 120 s wie ioBroker, konfigurierbar; nur aktive Bundles.
5. `AccessLevel` aus `systemstate` auswerten: unter 2 bzw. 4 keine Schreib-Entitäten anbieten.
6. ExpertLogin **nicht** automatisch; erst wenn der Read-only-Test zeigt, dass Fachmann-Werte sonst einfrieren oder Writes abgelehnt werden. Wenn, dann als Opt-in mit klarer Warnung (IP-klebrig, Statistik-Nebenwirkung).
7. **Logins minimieren**: Token über die volle Laufzeit nutzen, Session per `UpdateSession` halten, Silent-Renew prüfen; Login-Zähler und Zeitpunkt des letzten Logins in die Diagnostics. Beim HA-Start nicht gleichzeitig mit core `wolflink` einloggen (Startverzögerung oder `wolflink` deaktivieren).
8. **Nie** mit erfundenen oder veralteten BundleIds pollen; BundleIds ausschließlich aus der aktuellen Beschreibung; nach Beschreibungsänderung neu laden.
9. Leere `Values`-Antworten als Drossel-Signal werten (Intervall automatisch verlängern), nicht als Fehler-Retry.
10. Backoff nach Sperren wie im ioBroker-Fork: 1 → 4 → 16 min, Obergrenze Stunden; Repair-Issue „IP vermutlich temporär gesperrt“.

## 4. Struktur der Parameterbeschreibung (`GetGuiDescriptionForGateway`)

Grundlage: die vier echten Antworten in `wolf-comm/parameters-examples/` (Gas 442 Descriptoren, Gas-Hybrid 520, Wärmepumpe 529, Lüftung 139) und das Portal-JS. Zahlen unten beziehen sich, wenn nicht anders gesagt, auf die Wärmepumpe (BM-2, CHA, MM1, ISM) als nächstliegendem Fall.

### 4.1 Baum

```
{ "MenuItems": [ Benutzer, Fachmann ], "DynFaultMessageDevices": [], "SystemHasWRSClassicDevices": true }

MenuItem:      { Name, ImageName, ParameterNode: bool, TabViews: [...], SubMenuEntries: [MenuItem...] }
  Benutzer:    TabViews direkt (z. B. Übersicht, Heizung, Warmwasser[, Solar]); SubMenuEntries leer
  Fachmann:    TabViews leer; SubMenuEntries = Geräte (Heizgerät, Bedienmodul BM-2 0, Mischermodul MM1, ISM, Solarmodul SM1 …), jedes mit eigenen TabViews

TabView:       { TabName, IsExpertView, GuiId, BundleId, ViewType, SvgSchemaDeviceId, GetValueLastAccess,
                 TabViewGroups, ParameterDescriptors: [...],
                 optional: SVGHeatingSchemaConfigDevices (nur Übersicht), SchemaTabViewConfigDTO (Geräte-Konfigurationsschema),
                 TileMainParameterTagType, TileVisualizationType }
```

Wärmepumpen-Beispiel, alle TabViews:

| TabName | IsExpertView | BundleId | GuiId | Descriptoren | davon schreibbar (IsReadOnly false, ControlType ≠ 0/19) |
|---|---|---|---|---|---|
| Übersicht | false | 1000 | 13500 | 14 | 0 (alles ControlType 0, Messwerte) |
| Heizung | false | 1000 | 2000 | 56 | 10 (inkl. versteckter ControlType-31-Duplikate) |
| Warmwasser | false | 1000 | 3000 | 9 | 6 |
| Heizgerät | true | 3100 | 3100 | 74 | 2 |
| Parameter HG | true | 3500 | 3500 | 69 | 61 |
| Einstellungen und Anzeigen (BM-2) | true | 6300 | 6300 | 31 | 17 (Sparfaktor, Heizkurve, Winter/Sommer, …) |
| Parameter (BM-2) | true | 7100 | 7100 | 16 | 13 |
| Mischermodul MM1 | true | 10000 | 10000 | 26 | 0 |
| Parameter MM1 | true | 10700 | 10700 | 8 | 6 |
| NULL (ISM) | true | 11500 | 11500 | 14 | 0 |

Alle Benutzer-Tabs teilen sich `BundleId 1000`; jeder Fachmann-Tab hat ein eigenes Bundle (= `GuiId`). `BundleId` steht **nur am TabView**, nicht am Descriptor; wolf-comm stempelt es im Expertenmodus auf jeden Descriptor (`_extract_parameter_descriptors`).

### 4.2 Felder eines `ParameterDescriptor`

Häufigkeit im Wärmepumpen-Beispiel (529 Descriptoren):

| Feld | n | Bedeutung / Beobachtung |
|---|---|---|
| `ValueId` | 529 | Handle für Lesen/Schreiben. In allen vier Beispielen gilt `ValueId == ParameterId` für jeden echten Datenpunkt; `ValueId 0` markiert Platzhalter (65×). Core `wolflink` geht davon aus, dass ValueIds sich ändern können („Refreshing value IDs“ nach `ParameterReadError`) und schlüsselt deshalb intern nach `ParameterId` |
| `ParameterId` | 529 | stabile Identität; `-1` bei Containern (Zeitprogramm-Gruppen) |
| `ControlType` | 529 | GUI-Steuerelement, Enum siehe 4.3 |
| `ValueState` | 529 | `EnParamState` (0 ReadPending, 1 OK, …) für den eingebetteten `Value` |
| `Name` | 474 | deutscher Anzeigename (Kultur der Session); mehrdeutig („Programmwahl“ 4×, „Tagtemperatur“ 3×) |
| `Value` | 449 | **aktueller Wert ist in der Beschreibung enthalten** (String) – nutzbar für Initialzustand und Diagnose |
| `IsReadOnly` | 379 | fehlt bei 150 Descriptoren – alle in `SchemaTabViewConfigDTO.Configs[].Parameters` (Geräte-Konfigurationsschemata), nicht in regulären `ParameterDescriptors` |
| `NoDataPoint` | 379 | `true` (10×) = kein Datenpunkt (Container) |
| `IsExpertProtectable` | 379 | in allen Beispielen `false`; Semantik vermutlich „Schreiben nur mit Fachmann-Login“ [Offen] |
| `HasDependentParameter`, `DependsOnMeVIDs` | 379 / 9 | Abhängigkeiten zwischen Parametern (GUI-Sichtbarkeit/Neuladen) |
| `SortId`, `SubBundleId` | 379 | Sortierung; Sub-Bundle für Dialoge (Party-Modus 4100, Zeitprogramm 400) |
| `Group` | 357 | `"NNN_Name"` (NNN = Sortierpräfix), z. B. `030_Gemeinsame Einstellungen`, `073_Mischerkreis 1`, `250_Warmwasser`, `431_Einstellungen`; Sondergruppen `Mo…So`, `StartDate/StopTime/BM2Date`, `invisible` |
| `Decimals` | 314 | Nachkommastellen (0–2) |
| `Unit` | 255 | siehe 4.7 |
| `MinValue`/`MaxValue` | 199 | numerische Grenzen; bei Listen = kleinster/größter Listenwert; bei Strings = Längen |
| `MinValueCondition`/`MaxValueCondition` | 199 | String-Ausdrücke, die das Portal clientseitig auswertet (`Utilities.evalCondition`, können `V[<valueId>]` referenzieren). ioBroker nimmt `parseFloat(…Condition)` und bevorzugt es, weil `MinValue/MaxValue` „bei Floats falsch sein können“ |
| `ProtGrp`, `PortName`, `PortDesc` | 161 / 150 | Protokollgruppe (Gerät, z. B. `HG <1>`), Klemmenbezeichnung aus dem Schema |
| `ListItems` | 128 | `[{Value: "0", DisplayText: "Aus", IsSelectable, HighlightIfSelected, optional ImageName, Description}]` |
| `StepWidth` | 99 | Schrittweite (0.1, 0.5, 1, 10) |
| `NamePrefix` | 93 | **Wolf-Parameternummer** (`A12`, `WP025`, `HG03`, `MI03`), ideal für eindeutige, dokumentationskonforme Entity-Namen |
| `EnergyCockpitParameterType` | 28 | Energie-Cockpit-Klassifizierung |
| `ClientChooseCondition` | 25 | Sichtbarkeitsbedingung (Ausdruck über andere Werte) |
| `ChildParameterDescriptors` | 10 | verschachtelte Descriptoren (Zeitprogramme: 13 → 19 → 14; Party-/Urlaubsmodus: 24 → 9/10) |
| `HintDescription`, `FunctionOn/OffMessage`, `ImageName`, `PreloadChilds`, `TileParameterTagType` | wenige | GUI-Texte/Icons |

### 4.3 `ControlType` – offizielle Enum und Vorkommen

Enum aus dem Portal-JS (`EnControlType`) [Code]:

```
0 ComboBoxImageText   1 ComboBoxText       2 StateField          3 StateFieldImages   4 StateFieldSymbol
5 CheckBox            6 NumericInput       7 CheckBoxText        8 CheckBoxNumber     9 DateInput
10 TimeInput          11 TimeLabel         12 DateLabel          13 TimeProgram       14 DaySwitchTimes
15 SolarStatistics    16 SolarStatisticsBlock 17 NO_DISPLAY      18 UNKNOWN           19 TimeSubProgram
20 TextInput          21 IPInput           22 URLInput           23 PasswordInput     24 TimedFunction
25 MessageBoxButton   26 TextLabel         27 OrderNumber        28 ClimateSubProgram 29 CircularSlider
30 ProgramSelection   31 Client_NO_DISPLAY 32 CircularSliderVentilation 33 StateButtonSubDialogTimespan
34 TimeProgramDayOrWeek 35 ProgramSelectionListView
```

Vorkommen über alle vier Beispiele (1 630 Descriptoren) und Vorschlag für das HA-Mapping:

| CT | Name | n | `IsReadOnly=false` | ListItems | Unit | Min/Max | Beispiele | Vorschlag |
|---|---|---|---|---|---|---|---|---|
| 0 | ComboBoxImageText | 182 | 37 (!) | 2 | – | – | `KF Kesseltemperatur`, `3WUV …`, `AU Außenlufttemperatur` (Übersicht/Schema) | **sensor**, nie schreibbar (trotz `IsReadOnly: false`; es sind Messwerte im Anlagenschema). Einheit nur via `SVGHeatingSchemaConfigDevices` |
| 1 | ComboBoxText | 337 | 80 | 337 | – | 207 | `1x Warmwasser`, `Raumeinfluss`, `SG/PV`, `Betriebsart …` | **select** wenn schreibbar, sonst sensor mit Enum-Übersetzung; Zwei-Wert-Listen (Aus/Ein, Deaktiviert/Aktiviert) optional als **switch** |
| 5 | CheckBox | 12 | 0 | – | – | 12 | `DHCP Aktiv`, `WLAN Aktiv` | binary_sensor (schreibbar nie gesehen → später switch) |
| 6 | NumericInput | 695 | 224 | – | 623 | 259 | `Tagtemperatur`, `Sparfaktor`, `Heizkurve …`, Temperaturen | **number** wenn schreibbar (Min/Max/Step/Decimals vorhanden), sonst sensor mit device_class aus Unit |
| 9 / 10 | DateInput / TimeInput | 28 / 34 | 24 / 26 | – | – | – | `Datum Ende`, `Uhrzeit Start` (Party/Urlaub), `Uhrzeit BM2` | später (date/time-Entität); nicht MVP |
| 13 / 19 / 14 | TimeProgram / TimeSubProgram / DaySwitchTimes | 8 / 28 / 168 | alle | 8 / – / – | – / – / `Uhr` | | Zeitprogramme (`"00:00-23:59;00:00-00:00;…"` pro Wochentag) – nicht MVP, später eigener Dialog/Service |
| 15 / 16 | SolarStatistics(Block) | 2 / 34 | alle | – | `Wh;kWh;MWh` | | Solarertrag-Statistik | sensor (energy) |
| 20 / 21 | TextInput / IPInput | 24 / 16 | 0 | – | – | Längen | `Anlagenname`, `ISM Seriennummer`, `IP Adresse` | sensor diagnostic, deaktiviert |
| 24 | TimedFunction | 8 | alle | 8 | – | 0/1 | `Partymodus`, `Urlaubsmodus` mit Kindern 9/10 | später (Composite-Write) |
| 31 | Client_NO_DISPLAY | 47 | 18 | – | 13 | 39 | `Programmwahl`, `Tagtemperatur`, `Reglertyp`, `Seriennummer` | **ausblenden**: versteckte Duplikate der sichtbaren Parameter mit eigener ValueId; genau das ist der „Reglertyp“, den core `wolflink` per Name entfernt, weil die API keinen Wert liefert |
| 35 | ProgramSelectionListView | 7 | alle | 7 | – | | `Programmwahl` (Standby/Auto/Permanent mit Icons/Beschreibung) | **select** |
| 17 / 18 / 2–4 / 11 / 12 / 25–30 / 32–34 | übrige | 0 in Beispielen | | | | | | ausblenden bzw. sensor, sobald beobachtet |

### 4.4 `IsReadOnly` – Semantik und Konflikte [Code]

- Wert `false` bei ControlType 0 ist kein Schreibrecht (Übersicht zeigt nur Messwerte). ioBroker nimmt trotzdem `!IsReadOnly` als einziges Kriterium und markiert damit Messwerte als beschreibbar.
- Fehlt das Feld (150× in Schema-Konfigurationen, bei wolf-comm-Mapping Default `True`), handelt es sich um Konfigurationsparameter des Anlagenschemas, nicht um Entitäten.
- **Dieselbe `ValueId` kommt mehrfach vor**: Wärmepumpe 63 Gruppen (ohne ValueId 0), davon 11 mit unterschiedlichem ControlType (Übersicht CT 0 vs. Tab CT 6) und 16 mit gleichem ControlType, aber **widersprüchlichem `IsReadOnly`** – z. B. `Sparfaktor`, `Winter/Sommer Umschaltung`, `Sockeltemperatur Heizkurve`: in „Einstellungen und Anzeigen“ (Bundle 6300) schreibbar, in „Mischermodul MM1“ (Bundle 10000) nur lesbar. Gas: 40 Gruppen, 20 mit Konflikt. Dreifach-Vorkommen existieren (Übersicht + Solar + Parameter SM1).
- wolf-comm behält beim Dedup die **erste** Variante (Reihenfolge: Standardmodus Tabs reversed, Expertenmodus nach ValueId sortiert → effektiv zufällig). heatwrite liest die Rohbeschreibung erneut und lässt die schreibbare Variante samt ihrer BundleId gewinnen.
- Zusätzlich gilt der `AccessLevel` des Systems (3.1): ohne Schreibrecht ist nichts schreibbar.

Vorschlag für das Parametermodell: pro `ParameterId` alle Vorkommen sammeln; Schreibbarkeit = `AccessLevel` erlaubt **und** mindestens ein Vorkommen mit `IsReadOnly == false` **und** ControlType in der Schreib-Menge {1, 5, 6, 9, 10, 20–24, 29, 30, 32, 35}; für Lesen/Schreiben die BundleId des schreibbaren Vorkommens nutzen; Expertenstatus = alle Vorkommen liegen in `IsExpertView: true`-Tabs. [Offen: ob Writes über das Benutzer-Bundle 1000 auch für Fachmann-Parameter funktionieren – ioBroker schreibt alles mit `BundleId: 1000`]

### 4.5 Grenzen, Schrittweite, Dezimalstellen

- Schreibbare NumericInputs haben fast immer `MinValue`, `MaxValue`, `StepWidth`, `Decimals` (Wärmepumpe: 66 von 73). Beispiele: `Tagtemperatur` 5–30 °C Schritt 0.5; `Sparfaktor` 0–10 Schritt 0.5; `Sollwertkorrektur` −4…4 Schritt 0.5; `Warmwassersolltemperatur eingestellt` 25–65 Schritt 1; `Winter/Sommer Umschaltung` 0–40 Schritt 0.5; `Normaußentemperatur Heizkurve` −25…0 Schritt 1.
- Fehlen sie (7 schreibbare CT 6 ohne Unit, z. B. `Priorität ZWE` 1–3 oder `Sparfaktor` ohne Unit), muss ein Fallback greifen (heatwrite: großzügige Bereiche je Einheit). Besser: `MinValueCondition`/`MaxValueCondition` auswerten, wenn sie reine Zahlen sind.
- Werte kommen als Strings; Dezimaltrenner ist `.` in den Beispielen; heatwrite/wolflink-write ersetzen vorsichtshalber `,` → `.` [Bericht]. Platzhalter wie `--`/`----` kommen vor (wolf-comm `convert_raw_value`, Portal `EMPTY_VALUE = " ---- "`).

### 4.6 `ListItems`

`[{Value: "0", DisplayText: "Aus", IsSelectable: true, HighlightIfSelected: false}, …]`; `Value` ist die zu schreibende Zahl (als String), `DisplayText` deutsch (bei `lang=en-GB`-Login dennoch deutsch; wolf-comm übersetzt über `text.culture.<culture>.js`). `ProgramSelectionListView` (35) hat zusätzlich `ImageName` und `Description`. Nicht alle Listenwerte sind `IsSelectable` (Status-Enums wie `Warmwasser Status` mit 15 Einträgen sind reine Anzeigen mit `IsReadOnly: true`).

### 4.7 Einheiten

Alle Einheiten in den Beispielen: `°C, bar, %, Std, kW, kWh, Wh;kWh, Wh;kWh;MWh, U/min, l/min, Hz, K, K/K, K/(K*h), min, s, sec, m³/h, ppm, Pa, V, Cent/kWh, pls/kWh, Uhr` (Uhr = Zeitstrings). Das Portal zerlegt `Wh;kWh;MWh` in Skalierungsfaktoren 1/1000/10⁶ – Rohwert in Wh. wolf-comm kennt nur `°C, bar, %, Std, kW, kWh, Wh;kWh(;MWh), U/min, l/min, Hz` und **verwirft** Descriptoren mit anderen Einheiten komplett (`_map_parameter` → `None`, bewusst so getestet). Betroffen sind u. a. `K` (Heizkurvenabstand, Hysteresen), `min` (`Max. Zeit Warmwasserbetrieb`), `m³/h`, `Pa`, `V`.

### 4.8 Sonderfälle

- `ValueId == 0`: 65 Descriptoren (Container `Zeitprogramm 1–3` mit `ParameterId -1`, `Gerätetyp` mit `NoDataPoint: true`, Schema-Ports). wolf-comm dedupliziert nach `value_id` → **alle** kollabieren auf einen Pseudo-Parameter mit ValueId 0; dessen Abfrage ist der wahrscheinlichste Auslöser von `ParameterReadError` („ein nicht lesbarer Parameter reißt das ganze Bündel mit“, heatwrite README). Filterregel: `ValueId > 0`, `ParameterId > 0`, `NoDataPoint != true`.
- `ChildParameterDescriptors`: Zeitprogramm- und Party-/Urlaubs-Kinder tragen eigene ValueIds (z. B. Wochentage `32006300001…`), werden von wolf-comm (`_extract_parameter_descriptors` besucht nur Arrays mit Key `ParameterDescriptors`) **nicht** erfasst, von ioBroker bis Tiefe 3.
- `SchemaTabViewConfigDTO.Configs[].Parameters`: Konfigurationsschema des Geräts (Klemmenbelegung), ohne `IsReadOnly`; dort liegen z. B. die `Hz`-Parameter der Wärmepumpe, die wolf-comm nie erreicht.
- `SVGHeatingSchemaConfigDevices[].parameters[]`: liefert `valueId → unit` für die Übersicht (CT 0); wolf-comm injiziert diese Units nur im **Standardmodus** (`_map_view`), im Expertenmodus gehen sie verloren.
- `Name` mit `---`: wolf-comm splittet „`<prefix>---<name>`“ und übersetzt beide Hälften; in den vier Beispielen kommt das Muster nicht vor (Hinweis auf andere Gerätegenerationen).
- Geteilte Systeme liefern `SystemShareId` in `GetSystemList` und brauchen es in `GetSystemStateList` (core seit 2026.7).

### 4.9 Expertenansicht

- Strukturell: `IsExpertView: true` am TabView; alle Fachmann-Tabs hängen unter `MenuItems[1].SubMenuEntries[*]`. Die Beschreibung inklusive Fachmann-Teil kommt **ohne** ExpertLogin (so entstanden die wolf-comm-Beispiele, so arbeiten heatwrite und wolflink-write).
- ExpertLogin (`GET /portal/api/portal/ExpertLogin?Password=<pw>`, Antwort enthält `IsProfessional`) hebt serverseitig den Level an; Portal-Session liefert `IsProfessional` schon in `CreateSession2`. Sticky/IP-gebunden, siehe 3.3. Fachmann-**Werte**: wolf-comm-PR #15 (2024-10) stellt fest, dass ExpertLogin zum Lesen nicht nötig ist; ioBroker #242 (2025-01) zeigt, dass einzelne Werte nur mit aktiver Fachmann-Session kommen (plus erster Aufruf mit `LastAccess: null, GuiIdChanged: true`); wolflink-write beobachtet einfrierende Werte. Ob **Writes** auf Fachmann-Parameter ohne ExpertLogin akzeptiert werden, ist nirgends belegt (heatwrite behauptet Erfolg, es gibt keine unabhängigen Berichte). [Offen – erster Punkt für den Read-only-Test]

### 4.10 Use-Case-Parameter im Wärmepumpen-Beispiel

| Use Case | Parameter (Name, NamePrefix) | ValueId | CT | Tab / Bundle | Grenzen |
|---|---|---|---|---|---|
| 1x Warmwasser bei PV-Überschuss | `1x Warmwasser` | 22004200000 | 1 (Aus/Ein) | Benutzer › Warmwasser / 1000 | 0–1; `HintDescription`: „Der Warmwasserspeicher wird für eine Stunde auf die eingestellte Warmwassertemperatur aufgeheizt.“ → Einmal-Aktion, fällt selbst zurück |
| Warmwasser-Soll | `Warmwassersolltemperatur eingestellt` | 35000900000 | 6 | Benutzer › Warmwasser / 1000 | 25–65 °C, Schritt 1 |
| Sparfaktor | `Sparfaktor` | 36000600001 | 6 | Fachmann › BM-2 › Einstellungen und Anzeigen / 6300 (schreibbar); Duplikat in MM1/10000 read-only | 0–10, Schritt 0.5 |
| Heizkurve | `Sockeltemperatur`, `Startpunkt`, `Normaußentemperatur`, `Vorlauftemperatur Heizkurve`, `Raumeinfluss`, `Winter/Sommer Umschaltung` | 36001200001, 36001300001, 36001400001, 36001500001, 36001000001, 36000700001 | 6/6/6/6/1/6 | Fachmann › BM-2 › Einstellungen und Anzeigen / 6300 | 10–60, 0–40, −25–0, 25–90 °C; 0/1; 0–40 °C |
| Betriebsart Heizkreis | `Programmwahl` (Standby/Auto/Permanent) | 36005100001 | 35 | Benutzer › Heizung / 1000 | ListItems 0/1/2 (+ Duplikat CT 31 mit ValueId 36005800001, verstecken) |
| Betriebsart Warmwasser | `Programmwahl` | 35001200000 | 35 | Benutzer › Warmwasser / 1000 | 0–2 |
| PV/SG-Ready (Fachmann) | `SG/PV` WP025, `Auswirkung SG/PV auf Heizbetrieb` WP032, `Bivalenzpunkt … SG/PV` WP034–036 | 27008900001, 27009400001, 27009600001… | 1/1/6 | Fachmann › Heizgerät › Parameter HG / 3500 | |

Im Gas-Beispiel heißen die Pendants gleich (`1x Warmwasser` 22004200000, `Sparfaktor` 34000600000 im Direkten Heizkreis), haben aber teils andere ValueIds und Schreibrechte → keine festen IDs im Code, immer aus der Beschreibung ableiten.

## 5. Werte lesen und schreiben

### 5.1 Lesen: `POST /portal/api/portal/GetParameterValues` [Code wolf-comm, Portal-JS, ioBroker]

Request:

```json
{ "BundleId": 1000, "IsSubBundle": false, "ValueIdList": [22004200000, …],
  "GatewayId": <gw>, "SystemId": <sys>, "LastAccess": null | "<string aus letzter Antwort>",
  "GuiIdChanged": true | false, "SessionId": <BrowserSessionId> }
```

Antwort: `{ "LastAccess": "<cursor>", "Values": [ { "ValueId": …, "Value": "21.5", "State": 1 }, … ] }` – `State` ist `EnParamState` (1 = OK, 0 = ReadPending → kein `Value`, 4 Timeout, 5 Error). Fehler: `{ErrorCode, ErrorType, Message}`; wolf-comm wirft bei `Message == "internal msg: ReadParameterValues error"` `ParameterReadError`, sonst `FetchFailed`.

- Portal: erster Aufruf `LastAccess: null, GuiIdChanged: true` → komplette Liste; danach Cursor → nur Änderungen. wolf-comm sendet pro `fetch_value`-Aufruf immer `LastAccess: null` (frische Map), `GuiIdChanged: false` → immer Vollabfrage; eine Anfrage pro BundleId.
- ioBroker füllt `ValueIdList` mit ParameterIds (Quirk, funktioniert, weil ValueId == ParameterId).
- wolflink-write berichtet, `IsSubBundle: true` zwinge das Gateway zum Neu-Einlesen des Bundles [Bericht]; im Portal ist `IsSubBundle: true` für Dialog-Sub-Bundles reserviert.

### 5.2 Schreiben

Web-Portal (offizieller Client) [Code Portal-JS]:

```json
POST /portal/api/portal/WriteParameterValues
{ "WriteParameterValues": [ { "ValueId": 22004200000, "Value": "1", "ParameterName": "1x Warmwasser" } ],
  "SystemId": <sys>, "GatewayId": <gw>, "BundleId": <BundleId des Tabs>, "SessionId": <BrowserSessionId> }
```

- `Value` ist **immer ein String** (`WriteValue.toString()`); Listen schreiben die Zahl des `ListItems.Value`; Zeitprogramme den `Uhr`-String; Checkboxen vermutlich `"True"/"False"` (ioBroker sendet `"true"/"false"`, liest `"True"` – ungeprüft).
- Bestätigung: Der Descriptor geht auf `ValueState = WritePending (2)`, das Portal pollt `GetParameterValues` alle 3 s (`refreshPeriod` 3000 ms, sonst 10 s) bis maximal 60 s (`maxReadWritePendingTryMSec`), bis der Wert mit `State` OK/WriteAcknowledge zurückkommt. Timeout für den Write-Request selbst: 60 s.
- wolf-comm `write_value(gateway_id, system_id, bundle_id, {"ValueId": …, "State": …})` baut exakt diesen Payload (ohne `ParameterName`), gibt die rohe Antwort zurück und wirft `ParameterWriteError`/`WriteFailed` bei `ErrorCode`/`ErrorType`. Signatur hat sich zwischen 0.0.16 (3 Argumente) und heute (4 Argumente) geändert – wolflink-write prüft die Signatur zur Laufzeit.
- ioBroker: `POST /portal/api/portal/parameters/write` mit `{SessionId, BundleId: 1000, GatewayId, SystemId, WriteParameterValues: [{ValueId, ParameterId, Value: "<string>", ParameterName}], WaitForResponseTimeout: null, GuiId: null}`; Antwort `{Values: […]}` wie beim Lesen → direkte Bestätigung ohne Nachlesen. Keine Wiederholung, kein Debounce, keine Min/Max-Prüfung. [Code ioBroker `lib/wss.js:986-1014`]
- Welcher Write-Endpoint für uns: `WriteParameterValues` ist der vom Web-Portal (Build 2026-10-08) aktiv genutzte und durch wolf-comm/heatwrite-Nutzer bestätigte Weg; `parameters/write` liefert die bessere Antwort. Beide im ersten Live-Test gegen denselben harmlosen Parameter prüfen. [Offen]

### 5.3 Fehler und Zustände, die der Client behandeln muss

| Signal | Quelle | Bedeutung |
|---|---|---|
| HTTP 401 | API | Token ungültig → einmal neu anmelden (nicht bei Writes blind wiederholen) |
| HTTP 400/401 bei `UpdateSession` | ioBroker | Session weg → `CreateSession2` |
| `ErrorCode 1 InvalidSession` | Portal-JS | Session serverseitig beendet (z. B. Wartung, anderer Client?) → neue Session |
| `ErrorCode 3 InvalidCredentials` | Portal-JS | Reauth-Flow |
| `ErrorCode 4 SystemOffline` / `GatewayState.IsOnline == false` | Portal-JS / wolf-comm | Entitäten `unavailable`, keine Writes |
| `ErrorCode 6 Maintenance`, `UpdateSession.Maintenance == 1` | Portal-JS | Wartung, Backoff |
| `ErrorCode 8 BusScanPending` | Portal-JS | Gateway scannt den Bus, später erneut |
| `ErrorCode 10 ToManyRequests` | Portal-JS | Rate-Limit → langes Backoff, Repair-Issue |
| `Values[].State` 0/4/5 | API | Wert nicht verfügbar / Timeout / Fehler → Entität `unknown`, Write als nicht bestätigt melden |
| `Message "internal msg: ReadParameterValues error"` | wolf-comm | einzelner ValueId nicht lesbar → isolieren und merken (heatwrite-Strategie) |

## 6. Gap-Analyse

### 6.1 wolf-comm 0.0.52

Kann: Login (2.1), Session (2.4), `fetch_system_list`, `fetch_system_state_list` (IsOnline), `fetch_parameters` (typisierte Objekte, Standard- oder Expertenmodus), `fetch_value` (pro Bundle gebündelt, Wh→kWh), `write_value`, `close_system`, Übersetzung der Namen per Portal-Sprachdatei. Tests gegen die vier echten Beschreibungen. Apache-2.0.

Lücken (alle [Code]):

1. **Verlustbehaftetes Mapping**: nur `value_id, name (übersetzt), parameter_id, bundle_id, read_only, parent (TabName), unit/items`; `Group`, `NamePrefix`, `ControlType`, `MinValue/MaxValue/StepWidth/Decimals`, `ListItems.IsSelectable`, `Value`, `ValueState`, `IsExpertView`, `HintDescription` gehen verloren.
2. **Dedup nach `value_id`, erster gewinnt** (zweimal: inline und `fix_duplicated_parameters`); die schreibbare Variante und ihre BundleId gehen verloren; alle `ValueId 0` kollabieren.
3. **Unbekannte Einheiten werden verworfen** (`K`, `min`, `m³/h`, `Pa`, `V`, `ppm`, `Uhr`, …), auch mit `ListItems`.
4. Expertenmodus: SVG-Units gehen verloren, `parent` ist `None`, `ChildParameterDescriptors` und `SchemaTabViewConfigDTO` werden nicht besucht.
5. **Keine öffentliche Roh-Abfrage** (`__request` ist name-mangled privat) → heatwrite/wolflink-write greifen auf `_WolfClient__request` zu.
6. `write_value` ohne Validierung, ohne Bestätigung, Rückgabe untypisiert; Signaturänderung ohne Versionierung; **Retry nach 401/500 auch für Writes**.
7. Kein Umgang mit `ErrorCode`-Enum (`ToManyRequests`, `InvalidSession`, `SystemOffline`), kein Backoff, kein Silent-Renew; `PortalUnavailable` ist Subklasse von `InvalidAuth`.
8. `fetch_value` immer Vollabfrage (kein `LastAccess`), `expert_mode` ist mutierbarer Instanzzustand (heatwrite schaltet ihn auf dem fremden Client um → Race mit dem `wolflink`-Coordinator, der bei `ParameterReadError` neu lädt).
9. `python_requires >= 3.14`, Abhängigkeiten `httpx`, `lxml`, `pkce`, `shortuuid`; HA `dev` migriert gerade zu `httpx2` (Commit 2026-10-06), wolf-comm bleibt bei `httpx`.
10. Das Repo hat **keinen Issue-Tracker** (Issues deaktiviert); Zusammenarbeit nur per PR, Maintainer-Aktivität sporadisch (letzter Fremd-PR März 2026).
11. Versionspin: core `wolflink` pinnt `wolf-comm==0.0.52`. Eine Custom Integration mit anderem Pin erzeugt in derselben HA-Umgebung einen Requirements-Konflikt (HA installiert pro Integration; zwei Pins auf dasselbe Paket schlagen sich gegenseitig bei jedem Start um). Upstream-Erweiterungen von wolf-comm sind für uns also erst nutzbar, wenn core den Pin hebt.

### 6.2 Core `wolflink` (2026.10.1)

- Hub-Config-Entry v2.2 (`unique_id = username.lower()`), ein `WolfLinkCoordinator` pro System (60 s), Device pro System mit `identifiers={(wolflink, str(system_id))}`, Sensoren mit `unique_id = f"{system_id}:{parameter_id}"`, `has_entity_name`, Zustands-Übersetzungen für ~80 deutsche Enum-Texte (`STATES`/`strings.json`). Entfernt `Reglertyp` per Name.
- Pro Poll: `GetSystemStateList` (Online-Check) + `GetParameterValues` (Bundle 1000) + ggf. `UpdateSession`; bei Offline oder `ParameterReadError` werden die Parameter neu geladen.
- httpx-Client mit **`verify_ssl=False`** (Grund nicht dokumentiert; für uns erst mit Verifikation versuchen).
- Quality Scale `bronze`; `reauthentication-flow`, `parallel-updates`, `diagnostics`, `entity-category`, `entity-disabled-by-default` sind `todo`. `action-setup` exempt („no custom actions“).
- Config-Flow nutzt `probatio` (seit 2026.9), `probatio.Secret(CONF_PASSWORD)`.
- Wiederverwendbar für uns: Entity-/Device-Schnitt, STATES-Übersetzungstabelle (Lizenz Apache-2.0), Test-Fixture-Stil (`conftest.py` mit `MockConfigEntry`, Snapshot-Tests).

### 6.3 heatwrite 0.1.0 (mike-139)

Kann [Code]:

- Expertenliste über den `wolflink`-Client (schaltet `expert_mode` temporär um), liest zusätzlich die Rohbeschreibung und holt `Name`, `NamePrefix`, `Group`, `IsReadOnly`, `BundleId`, `MinValue`, `MaxValue`, `StepWidth` zurück; schreibbare Variante gewinnt bei Duplikaten; Anzeigename `"<NamePrefix> <Name> (<Group>) (<value_id>)"` zur Eindeutigkeit.
- Entitäten: `number` (NumberMode.BOX, Grenzen aus Rohdaten, sonst Bereich je Einheit), `select` (Optionen = `DisplayText`), `sensor` für nicht schreibbare Expertenparameter; alle `entity_registry_enabled_default = False`, `EntityCategory.CONFIG`; Werteabruf nur für aktivierte Entitäten über eigenen Coordinator (Default 5 min), Fallback auf `wolflink`-Daten.
- Schutz: `IsReadOnly` respektiert (`force` übersteuert), No-Op-Erkennung (Vergleich normalisierter Strings, Listen-Namen ↔ Zahl), Rate-Limit 20 Writes/h (Option), ein `asyncio.Lock` für Lesen und Schreiben, Historie (200 Einträge, `.storage/heatwrite.data`), Undo (mit `bypass_noop`), Snapshots aller schreibbaren Werte inkl. automatischem Vorher-Snapshot beim Restore, `dry_run` bei allen schreibenden Services, Isolierung nicht lesbarer ValueIds.
- Services: `set_value`, `set_by_name`, `undo`, `snapshot_create/restore/delete`, `reload_parameters`, `describe_parameter` (Rohdaten als Response); Buttons Undo/Snapshot, Diagnose-Sensoren Historie/Snapshots.
- Optimistischer Zustand nach Write, Korrektur beim nächsten Poll; Writes mit `BundleId` des schreibbaren Vorkommens.
- Lokale Brand-Assets unter `custom_components/heatwrite/brand/` (laut README seit HA 2026.3 möglich – in Phase 4 verifizieren). Smoke-Test ohne HA (`tests/smoke_test.py`).

Grenzen [Code/Doku]:

1. Hängt vollständig an `wolflink`-Interna (`entry.runtime_data`, `coordinator._wolf_client`, `_gateway_id`, `device_id`, `_WolfClient__request`) und **mutiert** den fremden Client (`expert_mode`). Verstößt gegen Regel 3; Core-untauglich; bricht bei jeder `wolflink`-Umstrukturierung (zuletzt 2026.6 Hub-Umbau).
2. Nutzt wolf-comm-Objekte als Basis, d. h. erbt dessen Einheiten-Verluste (Parameter mit `K`, `min`, … fehlen) und das Typmodell; `ControlType` wird nicht ausgewertet (CT-0-Messwerte mit `IsReadOnly: false` würden als `number` erscheinen, sofern wolf-comm sie typisiert).
3. Ein einziger Config-Entry (`unique_id = DOMAIN`), kein Reauth (kein eigener Login), keine Diagnostics, keine Übersetzungen der Entity-Namen (Namen deutsch aus der API), Historien-Keys deutsch (`alt`, `neu`, `ergebnis`), `voluptuous` statt `probatio` (funktioniert nur über HAs Kompatibilitäts-Alias).
4. Keine Write-Bestätigung (nur optimistisch), kein Umgang mit `ErrorCode`-Enum, kein `AccessLevel`, kein Backoff.
5. Keine pytest-Tests mit `pytest-homeassistant-custom-component`, keine CI, kein hassfest/HACS-Validation.
6. Lock umfasst auch das Lesen → Polls und Writes serialisieren sich global.

Bewertung: Die Schutzmechanismen und die Rohdaten-Strategie sind das Vorbild; Fundament und Entity-Erzeugung müssen neu.

### 6.4 wolflink-write 0.7.6

Minimaler Service `wolflink_write.set_value(value_id, state, gateway_id?, system_id?, bundle_id?)`, holt Client/IDs per Attribut-Raten aus `wolflink`-Coordinatoren (oder eigener `WolfClient` aus den Credentials des `wolflink`-Entries), globaler Lock, BundleId aus `coordinator.parameters` sonst 1000, loggt bei Fehlern den Quelltext von `write_value`. Zusätzlich fest verdrahtete Fachmann-Temperatursensoren über `_WolfClient__request` mit `IsSubBundle: true` und periodischem `GetGuiDescriptionForGateway`-Refresh gegen eingefrorene Werte. Wert für uns: die Beobachtungen zu Push-Bundles (3.4) und der Hinweis auf IP-Sperren nach vielen Logins (3.3), sonst genau der Service-Ansatz, den PR #128988 abgelehnt hat.

### 6.5 PR home-assistant/core#128988 – Review-Kernaussagen [Code/Doku]

- Inhalt: Service `wolflink.set_value(value_id, state, gateway_id?, system_id?)`, registriert in `async_setup_entry`, Bump auf wolf-comm 0.0.16.
- joostlek (Core): Services in `async_setup` registrieren, nicht pro Entry; „Can you elaborate more on what kind of values you write and for what purpose?“; „ideally we don't add uncontextualized services. They require quite a lot of knowledge of the user … I want to push back a bit to see if this can be figured out“ → Ziel: Kontext aus der JSON-Beschreibung parsen und als Entitäten abbilden.
- EnjoyingM (Codeowner): „Technically part of the integration will need to be re-written to get the full support working“; Wolf-Mapping ist pro Gerät unterschiedlich.
- Ergebnis: stale, geschlossen 2024-12-30. Für uns: Entitäten mit Kontext (Name, Gerät, Grenzen, Optionen) sind Pflicht; rohe `value_id`-Services allenfalls als Experten-Werkzeug mit `dry_run`.

### 6.6 ioBroker.wolf-smartset 2.1.2 (Referenz, JS)

Siehe Abschnitte 2–5; zusätzlich: Dedup nach ParameterId (Benutzer-Vorkommen gewinnt), Objekt-Pfad `<Menü>.<Gerät>.<Tab>[.<Gruppe>].<ParameterId>`, ControlType-Mapping (5 → bool, 9/10/14/20/21 → string, Rest → number mit states), zwei Poll-Zyklen (kurz/lang) mit `LastAccess`-Cursor, Public-IP-Check alle 5 Zyklen, ExpertLogin optional mit Re-Init alle 2 h, Logout der OIDC-Session beim Stop, keine 429-Behandlung, Token-Set wird im Info-Log ausgegeben (nicht nachmachen).

### 6.7 ism7mqtt (Abgrenzung)

Lokaler Zugriff auf das ISM7 (TLS, eigenes XML-Protokoll), kein Cloud-Zugriff, MQTT inkl. HA-Discovery, Schreiben möglich. Das ISM7 akzeptiert **nur eine Verbindung**: ism7mqtt schließt SmartSet-App und -Portal aus (README „Cons“). Damit keine Option für ein Setup, das die Wolf-App behalten will; umgekehrt ist unser Ansatz für ism7mqtt-Nutzer irrelevant. Keine Mischform sinnvoll.

## 7. Rahmenbedingungen HA 2026.10.1 / HACS [Code]

- Python `>= 3.14.2`; `httpx==0.28.1`; `probatio==0.13.0`. **voluptuous ist seit 2026.9 keine Core-Abhängigkeit mehr**; `homeassistant/__init__.py` installiert `probatio.compat.install_as_voluptuous`, damit alte Custom Integrations weiterlaufen. Neue Code sollte direkt `probatio` nutzen (Drop-in-API: `Schema, Required, Optional, All, Any, Coerce, Invalid`, plus `Secret`, `EnsureList`, `Port`). Ruff in Core verbietet `voluptuous`-Importe.
- `dev` (2026.11) migriert Integrationen von `httpx` auf `httpx2` (Commit 2026-10-06, betrifft auch `wolflink`). Unser Client sollte den HTTP-Client injiziert bekommen und möglichst wenig httpx-spezifische API nutzen, um den Wechsel abzufedern. [Offen: `create_async_httpx_client` in 2026.11 prüfen]
- Lokale Brand-Assets in `custom_components/<domain>/brand/` laut heatwrite-README seit 2026.3 möglich und bevorzugt gegenüber `home-assistant/brands`. [Offen: Dev-Docs prüfen, Phase 4]
- Quality-Scale-Regeln für Bronze (aus `wolflink/quality_scale.yaml`): `action-setup`, `appropriate-polling`, `brands`, `common-modules`, `config-flow`, `config-flow-test-coverage`, `dependency-transparency`, `docs-*`, `entity-event-setup`, `entity-unique-id`, `has-entity-name`, `runtime-data`, `test-before-configure`, `test-before-setup`, `unique-config-entry`. `dependency-transparency` verlangt für einen späteren Core-PR eine **veröffentlichte Bibliothek** (PyPI, offene Quelle, CI-Build) – ein im Repo eingebetteter Client ist für HACS in Ordnung, für Core nicht.
- Test-Fixtures: Die vier wolf-comm-Beispiele enthalten keine Gateway-/System-IDs, keine Tokens, keine IP/MAC-Werte (Werte `null`), nur eine Geräteseriennummer; sie sind öffentlich und als Basis-Fixtures nutzbar. Eigene Aufzeichnungen müssen `GatewayId`, `SystemId`, `SystemShareId`, `BrowserSessionId`, Anlagenname, Seriennummern, IP/MAC, Nutzerdaten (`CurrentUserLoadDataSlim`) redigieren.

## 8. Empfehlung

| Option | Bewertung |
|---|---|
| **A. heatwrite forken / beitragen** | Features top, Fundament (Huckepack auf `wolflink`-Interna, mutierter Fremd-Client, wolf-comm-Typmodell) widerspricht Regel 3 und dem Core-Ziel. Ein Beitrag müsste das Fundament ersetzen = Neubau unter fremdem Namen. **Nein**, aber Mechanismen (No-Op, Rate-Limit, Historie, Undo, Snapshots, dry_run, Isolierung nicht lesbarer IDs, Rohdaten-Vorrang) übernehmen; MIT erlaubt das mit Hinweis. |
| **B. wolf-comm as-is nutzen** | Öffentliche API reicht für Auth/Session/Systemliste/Werte, aber nicht für Rohbeschreibung (nur über `_WolfClient__request`) und nicht für kontrollierte Writes (blinder Retry, keine Fehlercodes). Pin `==0.0.52` fix, solange core `wolflink` parallel läuft. **Nur als Übergangsmöglichkeit**, nicht als Fundament. |
| **C. wolf-comm per Upstream-PR erweitern** | Sinnvolle PRs: öffentliche `fetch_gui_description()`, Fehlercode-Enum, kein Write-Retry, `LastAccess`. Aber: Releases erst nach Merge, core hebt den Pin erst Wochen später, bis dahin Requirements-Konflikt in jeder HA-Instanz mit `wolflink`. Maintainer-Aktivität sporadisch (letzter PR März 2026). **Parallel anstoßen, nicht darauf bauen.** |
| **D. wolf-comm forken** | Erbt Modellprobleme (Klassen pro Einheit, Dedup), Python-3.14-Pin, httpx-Bindung; Paketname-Kollision (`wolf_comm`) mit core. **Nein.** |
| **E. Eigene dünne API-Schicht** | ~400–600 Zeilen: OIDC/PKCE-Login (aus wolf-comm portiert, Apache-2.0-Hinweis), Session, `GetSystemList`, `systemstate` (AccessLevel/IsOnline), Rohbeschreibung → eigenes Parametermodell (ParameterId-zentriert, alle Vorkommen, ControlType, Grenzen, Listen, Bundle, Expertenflag), `GetParameterValues` mit `LastAccess`, `WriteParameterValues` + Bestätigung per Nachlesen, Fehlercode-Enum, Backoff, keine HA-Importe. Testbar gegen die vier Beispiele plus eigene redigierte Fixtures. Keine Requirements-Konflikte mit core. Später als eigenes PyPI-Paket extrahierbar (Core-Pfad). **Empfehlung.** |

Begründung in einem Satz: Das Kernproblem (verlustbehaftetes Mapping, fehlende Rohdaten, unkontrollierte Writes) liegt in der Bibliothek, die wir wegen des Core-Pins nicht verändern können, und das Huckepack-Modell ist ausgeschlossen – also eigener Client, so klein wie möglich, HA-frei, mit der Option, ihn später zu veröffentlichen.

Koexistenz mit core `wolflink`: funktional möglich (zweite Session), aber doppelte Polling-Last und – kritischer – **doppelte Logins** (beim HA-Start gleichzeitig, danach bei jedem Token-Ablauf). Gleichzeitige Logins von einer IP haben in HA #155531 Sperren ausgelöst. Empfehlung für den Betrieb: unsere Integration übernimmt die Sensoren der Benutzerebene mit (ohnehin dieselben Daten), sodass `wolflink` deaktiviert werden kann; während der Entwicklung `wolflink` nur zum Vergleich. Alternativ bekommt HA einen dedizierten Smartset-Zweitnutzer („Fachmann schreiben“), was Konto-Kopplungen (Expert-Session) vermeidet; IP-Sperren träfen ihn trotzdem. Entity-IDs bleiben über eigene `unique_id`s getrennt (keine Migration der Historie – bewusst, siehe Phase-1-ADR Device-/Entity-Modell).

## 9. Offene Fragen an dich (vor Phase 1)

1. ~~Welche Anlage?~~ **Beantwortet (Typenschild-Fotos, 2026-10-25):**
   - Wärmepumpe Wolf **CHA-07/400V oder CHA-10/400V** (das Inspektionsschild nennt beide Typen), Innenteil-Steuerung „Gesamtmontage Steuerung CHA IDU“.
   - Gateway **WOLF Link home**, Firmware 4.40.
   - Warmwasser-Wärmepumpenspeicher **SEW-2-200** (190 l), Pufferspeicher **SPU-2-500** (490 l).
   - Zirkulationspumpe Grundfos Comfort PM mit eigener Zeitsteuerung, nicht über die Wolf-Regelung angebunden. Sie taucht daher voraussichtlich nicht in der API auf.
   - Offen bleibt, ob ein Bedienmodul BM-2 und ein Mischermodul MM1 verbaut sind. Das zeigt die Parameterbeschreibung beim ersten lesenden Abruf.

   Folgen: Das wolf-comm-Beispiel `heatpumpparameter.json` (Gerätevorlage `CHA`, BM-2, MM1) ist die nächstliegende Fixture-Basis. heatwrite wurde an genau dieser Gerätefamilie entwickelt (CHA-10 mit BM-2, 241 Parameter, 117 beschreibbar). Die Use-Case-Tabelle in 4.10 gilt damit sehr wahrscheinlich unverändert, die konkreten ValueIds werden trotzdem aus der echten Beschreibung gelesen.
2. **Konto**: Ist das System in deinem eigenen Konto (AccessLevel vermutlich 4) oder geteilt? Hast du das Fachmann-Passwort und willst du ExpertLogin überhaupt erlauben (IP-klebrig, Statistik-Nebenwirkung)?
3. **Core `wolflink`** soll während der Entwicklung parallel laufen (Vergleichswerte, zweite Session) oder deaktiviert werden?
4. Die **Use Cases** im Auftrag standen noch als Platzhalter („z. B. …“): 1x Warmwasser, Sparfaktor/Heizkurve, Betriebsart – bestätigen oder ergänzen (z. B. Warmwasser-Soll, SG/PV-Parameter, Zeitprogramme später)?
5. **Sprache** der Doku: Discovery und ADRs auf Deutsch (wie hier) oder Englisch mit Blick auf Core/HACS-Leser? README wird ohnehin zweisprachig.
6. Darf der Read-only-MVP (Phase 2) gegen die echte Cloud **lesen** (Login, Beschreibung, Werte), um redigierte Fixtures aufzuzeichnen? Schreiben bleibt bis zur expliziten Freigabe in Phase 3 gesperrt.
7. Soll HA einen **eigenen Smartset-Nutzer** bekommen (Systemfreigabe an einen Zweitaccount mit Schreibrecht) oder dein Hauptkonto nutzen?

## 10. Risiken

| Risiko | Einschätzung | Gegenmaßnahme |
|---|---|---|
| Wolf ändert Login-HTML/OIDC-Flow | mittel; passiert laut PR-Historie von wolf-comm alle paar Monate (Session-Fixes 2024, Password-Fix 2026) | Login-Flow isoliert, mit Fixture-Tests; `PortalUnavailable`-Unterscheidung; Repair-Issue statt Reauth-Schleife |
| Rate-Limit/Sperre durch zu viele Logins oder Polls | unbekannte Schwellen; `ToManyRequests` existiert | eine Session, ≥ 60 s, Backoff, Login-Zähler im Diagnostics |
| Fachmann-Werte frieren ein / Writes auf Fachmann-Parameter abgelehnt | widersprüchlich belegt | Read-only-Messung in Phase 2; ExpertLogin nur Opt-in |
| Falscher Parameter geschrieben (Duplikate, ValueId-Wechsel) | real, s. 4.4 | ParameterId-zentriertes Modell, BundleId aus schreibbarem Vorkommen, Bestätigung per Nachlesen, dry_run default im Dev |
| EEPROM-Verschleiß durch Automationsschleifen | real (heatwrite-Motivation) | No-Op-Erkennung, Rate-Limit, Lock, Historie |
| HA-Plattformwechsel (httpx → httpx2, probatio) | sicher kommend | injizierter HTTP-Client, probatio von Anfang an, CI gegen HA `dev` |
| Zweite Session beeinflusst core `wolflink` | nicht belegt | Beobachtung im MVP, Option zum Deaktivieren dokumentieren |
| Core-Pfad scheitert an „library on PyPI“ | bekannt | Client HA-frei halten, Extraktion als separates Paket vorsehen |
| Wolf unterbindet Drittzugriff | real: Dev-Team 2024 „not working for unofficial products“, Support 2026 „nicht unterstützt“; Nutzungsbedingungen des Portals nicht auffindbar | README mit Risikohinweis; Verhalten wie die offiziellen Clients (OAuth, Token-Reuse, ≥ 60 s); keine aggressiven Retries |
| Auth-Ausfälle und Strukturänderungen bei Wolf (2023-01, 2024-02/03, 2025-04/07, 2026-03, 2026-06) | mehrmals pro Jahr | Fixtures je Variante, schnelle Patch-Releases, `PortalUnavailable` als „warten“ statt Reauth |

## 11. Community-Berichte (Web-Recherche)

Vollständige, zitierte Fassung: [`discovery-appendix-community.md`](discovery-appendix-community.md) (GitHub-Issues/PRs von HA-Core, wolf-comm, ioBroker, openHAB; HA-/ioBroker-/openHAB-/simon42-Foren; wolf.eu). Die ioBroker-Code-Analyse mit Zeilenreferenzen liegt in [`discovery-appendix-iobroker.md`](discovery-appendix-iobroker.md). Kernaussagen beider Anhänge wurden gegen den gelesenen Quellcode geprüft.

Die wichtigsten Befunde:

1. **Keine Session-Kicks.** Nirgends ein Bericht, dass App oder Portal durch HA/ioBroker ausgeloggt werden; HA-Codeowner und ioBroker-Maintainer nutzen beides parallel. [Doku]
2. **IP-Sperren sind der reale Mechanismus.** Zu viele Logins (defekte wolf-comm 0.0.4–0.0.6 im März 2024; sechs gleichzeitige Config-Entries 2025/26; „zu oft an der OpenID-Seite gespielt“) oder fehlerhaftes Polling (15 s; ungültige BundleId) sperren die öffentliche IP für Minuten bis ~1 h (openHAB: Tage); Portal und App sind mitbetroffen, das Gateway bleibt online; neue IP hebt die Sperre sofort auf. Es gibt keine Berichte über **Konto**-Sperren. [Bericht/Doku]
3. **Offizielle Haltung.** Wolf-Dev-Team (GitHub `WOLF-Smartset`, 2024-03-14): keine Unterstützung inoffizieller Produkte, OAuth verpflichtend, „reuse your tokens like the official products“. Wolf-Support per Mail (2026-01): HA-Anbindung „nicht geplant, vorerst nicht unterstützt“. Dasselbe Dev-Team half 2026-02 dem lokalen Projekt ism7mqtt. Keine Nutzungsbedingungen des Smartset-Portals auffindbar, kein Entwicklerprogramm. [Wolf offiziell / von Nutzern wiedergegeben]
4. **Polling.** Einzige Zahl: `MaxSystemBusSamplingRateSec = 60`. Core-Codeowner: Wolf limitiert die API nicht, nur die Authentifizierung; Web/App pollen alle 10 s. ioBroker-Maintainer: unter 60 s kommen bis zu 75 % leere Antworten; viele Werte → 120 s; 20 h Fachmann-Polling mit vielen Werten endete in HTTP 400 und fehlenden Fachmann-Werten auch im Portal. Wolf-Server sind zeitweise langsam (HA-Timeout 2026.1 auf 20 s erhöht). [Doku/Bericht]
5. **Fachmann-Werte** kommen teilweise nur mit aktiver Fachmann-Session desselben Kontos (ioBroker #242); ExpertLogin ist zum Lesen der meisten Werte nicht nötig (wolf-comm PR #15). Fachmann-PIN ist typischerweise die Werkseinstellung; Schreibrecht hängt am Portal-Recht „Fachmann schreiben“. [Doku]
6. **Schreiben.** ioBroker schreibt seit 2021 (inkl. Zeitprogramme). Zu wolf-comm `write_value`, heatwrite und wolflink-write gibt es **keinen einzigen unabhängigen Nutzerbericht** (0 Issues in beiden Repos), nur Autorenangaben. ioBroker-Erfahrungen: API-Grenzen (`Min/MaxValueCondition`) deckeln Werte, teils inkonsistent (`MinValue 5, MaxValue 3`); zu häufiges Schreiben desselben Werts erzeugte Sperren. Der EEPROM-Hinweis stammt allein aus dem heatwrite-README. [Doku/Bericht]
7. **Auth-Historie** (jeweils Ausfall der Integrationen): 2023-01 erster OpenID-Umstieg (zurückgerollt), 2024-02 endgültig OpenID → wolf-comm, 2024-03 Passwort-Flow abgeschaltet + IP-Sperren → Token-Reuse/UpdateSession (wolf-comm 0.0.7, HA 2024.5), 2025-04/07 Login-Seiten ohne Formular (Wolf-Ausfälle), 2025-10 `KeyError: 'code'` bei Mehrfach-Login, 2026-03 GUI-Strukturänderung (Solar-Sensoren weg), 2026-06 `SystemShareId` für geteilte Systeme. `id.wolf.eu` taucht nirgends auf; es bleibt `www.wolf-smartset.com/idsrv` (IdentityServer, JWT verweist auf „lucon IoT Hub“). [Doku]
8. **Lokal vs. Cloud.** ISM7 erlaubt nur eine lokale Verbindung (Wolf bestätigt, ism7mqtt-README); ISM8 parallel zum Link Pro möglich; CHA/FHA-Wärmepumpen laut Wolf „EEBus-ready“ (seit 2025-11) – ein möglicher späterer lokaler Pfad, hier nicht weiterverfolgt. [Doku/Bericht]
9. **ValueIds können sich ändern** (HA #44453, 2021: nach IP-Wechsel/Reconnect `ReadParameterValues error`, neue ValueIds) – stützt das ParameterId-zentrierte Modell. [Bericht]

## 12. Nachtrag 2026-10-25: Gerät der Warmwasser-Parameter

**Frage:** Lassen sich die Warmwasser-Parameter (ValueId-Präfix 35 sowie `22004200000` „1x Warmwasser“) über das Anlagenschema einem Gerät zuordnen? Ein Abgleich über den Vorlagennamen `WWSystem_BM_2` reicht als Beleg nicht. Geprüft wird, ob die `parameters`-Liste des Schema-Eintrags diese ValueIds enthält.

**Rohdaten** (aufgezeichnete Beschreibung der Anlage, `SVGHeatingSchemaConfigDevices` im Tab „Übersicht“; ValueIds unverändert, keine System- oder Gateway-IDs enthalten):

```json
[
  {"dt": "HG", "di": 1, "deviceTemplateName": "CHA", "configIndex": 4, "hdt": null, "hdi": null,
   "parameters": [27000600001, 27000900001, 27002900001, 27000700001, 27002800001, 27003000001,
                  27001200001, 27001300001, 27001400001, 27004800001, 27001600001]},
  {"dt": "BM", "di": 0, "deviceTemplateName": "BM_2", "configIndex": 0},
  {"dt": "MM", "di": 1, "deviceTemplateName": "MM", "configIndex": 8, "hdt": "MM", "hdi": 1,
   "parameters": [4000100001, 4000200001, 4002700001]},
  {"dt": "MK", "di": 1, "deviceTemplateName": "MK_BM_2", "configIndex": 0, "hdt": "MM", "hdi": 1},
  {"dt": "WWSystem", "di": 0, "deviceTemplateName": "WWSystem_BM_2", "configIndex": 0, "hdt": "CHA", "hdi": 1}
]
```

(`parameters` gekürzt auf die `valueId`s; jedes Element hat zusätzlich `parameterName`, `parameterId` und optional `unit`.)

**Ergebnis: nein.**

- Der Eintrag `WWSystem_BM_2` hat keine `parameters`-Liste. `35000900000`, `35001200000`, `35000100000` und `22004200000` kommen in keinem Schema-Eintrag als `valueId` vor.
- Nur die Einträge `CHA` (11 ValueIds, alle Präfix 27) und `MM` (3 ValueIds, alle Präfix 4) haben Parameter. Diese Parameter sind über die Fachmann-Untermenüs bzw. die Präfix-Regel (ADR-Model-009) bereits demselben Gerät zugeordnet. Eine Zuordnung über die Schema-Listen bringt also keine neue Information.
- Die Felder `hdt`/`hdi` (vermutlich „host device type/index“) nennen für `WWSystem` den Wärmeerzeuger `CHA 1` als Host, nicht das BM-2. Der Vorlagenname hätte damit auf das falsche Gerät gezeigt. Für eine Zuordnung taugen auch `hdt`/`hdi` nicht, weil die Verbindung zwischen Präfix 35 und dem Schema-Gerät `WWSystem` in den Daten fehlt.

**Entscheidung** (nach der vorgegebenen Regel): Die Warmwasser-Parameter bleiben am System-Gerät. Es gibt kein logisches Gerät „Warmwasser“ und keine Zuordnung über Schema-Listen, weil die Prüfung negativ ist. Der Code bleibt unverändert. `test_device_by_value_id_prefix` sichert ab, dass Präfix 35 am System-Gerät bleibt.

## 13. Nachtrag 2026-10-25: Beleg für das Gerät von „1x Warmwasser“ und die Schema-Konfiguration

**Frage:** Die Präfix-Regel (ADR-Model-009) hatte `22004200000` („1x Warmwasser“), `36005100001` („Programmwahl (Heizung)“), `36002900001` („Sollwertkorrektur“) und `4007000001` („Mischerkreispumpe“) einem Modul-Gerät zugeordnet. Gibt es dafür einen Beleg in den Daten?

**Geprüfte Quellen** für alle vier ValueIds in der aufgezeichneten Beschreibung:

| Quelle | Ergebnis |
|---|---|
| Fachmann-Untermenüs (`MenuItems[1].SubMenuEntries[*].TabViews[*].ParameterDescriptors`) | kein Vorkommen |
| `ProtGrp` an einem ihrer Deskriptoren | nicht gesetzt |
| `SVGHeatingSchemaConfigDevices[*].parameters` | kein Vorkommen (siehe Abschnitt 12) |
| `SchemaTabViewConfigDTO.Configs[*].Parameters` (Geräte-Schemakonfiguration) | kein Vorkommen |

**Ergebnis: kein Beleg.** Die vier Parameter gehören ans System-Gerät. Die Präfix-Regel entfällt (ADR-Model-010).

**Neu gefunden: die Geräte-Schemakonfiguration.** Expert-Tabs mit Anlagenschema enthalten `SchemaTabViewConfigDTO.Configs[]`: je Hydraulik-Konfiguration eine Liste der Klemmen mit `PortName`, `PortDesc`, `ProtGrp`, `Unit` und `ListItems`, ohne `IsReadOnly`. Ausschnitt der aufgezeichneten Anlage (ein Eintrag je Port, gekürzt; jede Konfiguration wiederholt die Ports):

```json
// Untermenü "Heizgerät", Tab "Heizgerät"
{"ValueId": 27004800001, "Name": "Verdichterfrequenz", "PortName": "----", "PortDesc": "Verdichterfrequenz",
 "ControlType": 6, "Unit": "Hz", "ProtGrp": "HG <1>"}
// Untermenü "Mischermodul MM1", Tab "Mischermodul MM1"
{"ValueId": 4000100001, "Name": "Ausgang MKP", "PortName": "MKP", "PortDesc": "MKP Mischerkreispumpe",
 "ControlType": 1, "ProtGrp": "MM <1>", "ListItems": [{"Value": "0", "DisplayText": "Aus"}, {"Value": "1", "DisplayText": "Ein"}]}
{"ValueId": 4000200001, "Name": "Mischermotor", "PortName": "MM", "PortDesc": "Mischermotor MM",
 "ControlType": 1, "ProtGrp": "MM <1>", "ListItems": [{"Value": "0", "DisplayText": "Aus"}, {"Value": "1", "DisplayText": "Zu"}, {"Value": "2", "DisplayText": "Auf"}]}
```

Abgedeckt sind auf dieser Anlage elf ValueIds unter „Heizgerät“ und drei unter „Mischermodul MM1“, genau die Ports der Übersicht. Damit erhalten die Übersichts-Ports Gerät, Einheit und Klartext-Werte aus den Daten (ADR-Model-010, ADR-Model-011). `PortDesc` minus `PortName` ergibt die Funktion: „Mischerkreispumpe“ ist zugleich der Name des Tab-Parameters `4007000001`, „Ausgang MKP“ ist also ein Duplikat und startet deaktiviert.

## 14. Nachtrag 2026-10-25: Verhalten von „1x Warmwasser“ (22004200000)

Quelle: erster echter Write-Test am 25.10.2026 (Freigabe des Eigentümers), Write-Historie der Integration und HA-Recorder. Uhrzeiten MEZ, Poll-Intervall 120 s.

| Zeit | Ereignis |
|---|---|
| 17:56:20 | 3-Wege-Umschaltventil HZ/WW auf „Warmwasser“, „Warmwasser Status“ = „Ein“ (5). Die Ladung läuft bereits über das normale Programm (Speicher 26 °C, Soll 48 °C). |
| 18:04:50 | Write 22004200000 = 1. Antwort des Portals ohne Fehler. |
| 18:06:27 | Poll: 22004200000 = 1, „Warmwasser Status“ = „1x Warmwasser“ (4). Bestätigt. |
| 18:12:13 | Write 22004200000 = 0 gestartet; die Antwort kam erst nach rund 17 s (Schalter-Zustand ab 18:12:30). |
| 18:12:29 | Poll, der **während** des Writes lief: noch 1 und „1x Warmwasser“. |
| 18:14:29 | Erster Poll nach dem Write: 22004200000 = 0, „Warmwasser Status“ = „Ein“ (5). Bestätigt. |
| bis 18:18 | Speichertemperatur steigt weiter (31,5 → 32,6 °C), Ventil weiter auf „Warmwasser“. |

**Ergebnis:**

1. Der Parameter ist lesbar und beschreibbar. Das Portal bietet ihn als Liste „Aus“/„Ein“ an (`ControlType 1`) und beschreibt ihn so: „Der Warmwasserspeicher wird für eine Stunde auf die eingestellte Warmwassertemperatur aufgeheizt.“
2. Schreiben von 0 beendet die 1x-Funktion: Der Status wechselt von „1x Warmwasser“ zurück auf „Ein“. Dass die Ladung danach weiterlief, liegt an der normalen Warmwasser-Anforderung. Sie lief schon vor dem Test, also gibt der Test keinen Beleg, dass 1x überhaupt eine Ladung ausgelöst hat.
3. Die Meldung „weiterhin 1x Warmwasser“ nach dem Ausschalten stammt vom Poll, der während des 17 s langen Writes lief. Seit 0.2.0 behält die Integration den geschriebenen Wert bei Polls in den ersten 30 s (ADR-Writes-013).
4. Ob und wann sich 22004200000 selbst zurücksetzt, klärt der zweite Test (Abschnitt 15).

## 15. Nachtrag 2026-10-25: Zweiter Test „1x Warmwasser“ ohne laufende Ladung

Freigabe des Eigentümers; ein einziger Write, danach nur Polls. Ausgangslage 18:48: Warmwasser-Programm außerhalb des Zeitfensters („Warmwasser Status“ = „Aus“), Ventil auf „Heizen“, Speicher 44,6 °C bei 48 °C Soll. Ab etwa 18:53 wurde gebadet (große Warmwasser-Entnahme), daher der Temperaturabfall.

| Zeit | Ereignis |
|---|---|
| 18:50:12 | Write 22004200000 = 1; Antwort nach etwa 18 s. Historie `confirmed: null`. |
| 18:52:29 | Poll: Ventil „Warmwasser“, Verdichter „Betrieb“, Status „1x Warmwasser“, 22004200000 = 1 (`confirmed: true`, `read_back: "1"`). |
| 18:56 | Speicher 30,0 °C (Entnahme beim Baden). |
| 19:04:44 | Speicher 35,0 °C, Verdichter 36 Hz, Status weiter „1x Warmwasser“. |
| 19:06:48 | **22004200000 = 0** ohne Write (weder Integration noch, nach Kenntnis des Eigentümers, Bedienmodul, App oder Portal). Status „Aus“, Ventil „Heizen“, Verdichter „Sperrzeit“, 0 Hz. Speicher 37,2 °C. |
| 19:08:48 | Verdichter „Standby“. |

**Ergebnis:**

1. „1x Warmwasser“ startet eine Ladung selbst: Ventil und Verdichter schalten innerhalb eines Poll-Intervalls auf Warmwasser.
2. Die Regelung setzt den Parameter selbst auf 0 zurück. Hier nach etwa 16 Minuten, bei 37 °C, also weder nach der im Portal genannten Stunde noch bei Solltemperatur. Was das Ende ausgelöst hat, zeigen die gepollten Werte nicht.
3. Zusammen mit Abschnitt 14: Der Parameter hat einen lesbaren Zustand, die Regelung beendet ihn selbst, und Schreiben von 0 beendet ihn vorzeitig.
4. **Entscheidung (Eigentümer, 2026-10-25):** Der Parameter bleibt ein `switch`. Er zeigt, ob 1x läuft, folgt dem Rücksetzen der Regelung über den Poll und kann die Ladung abbrechen. Ein `button` hätte das Abbrechen und den sichtbaren Zustand verloren.
