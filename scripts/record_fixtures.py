"""Record redacted read-only API responses as test fixtures.

Reads only: login, system list, system state, parameter description, one
GetParameterValues call for the user-level bundle. Nothing is written to the
heating system.

Usage (in your own terminal, so the password never lands in a log):

    read -r WOLF_USERNAME && read -rs WOLF_PASSWORD && export WOLF_USERNAME WOLF_PASSWORD
    .venv/bin/python scripts/record_fixtures.py tests/fixtures/real

Without the environment variables the script prompts for both values.
Check the output with `git diff` before committing it.

Fault messages (owner's go 2026-11-21, backlog brief 08): login, system list,
then exactly one ReadFaultMessages call for the first system, sent without
SessionId like the portal. Writes only fault_messages.json; the other fixtures
stay untouched.

    .venv/bin/python scripts/record_fixtures.py --faults tests/fixtures/real
"""

import asyncio
import getpass
import json
import os
from pathlib import Path
import sys
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.wolf_smartset.api import WolfClient
from custom_components.wolf_smartset.model import parse_description
from custom_components.wolf_smartset.redact import (
    redact_description,
    redact_faults,
    redact_ids,
    redact_values,
    secret_value_ids,
)


def credentials() -> tuple[str, str]:
    """Username and password from the environment, else prompted."""
    username = os.environ.get("WOLF_USERNAME") or input("Wolf SmartSet username: ")
    password = os.environ.get("WOLF_PASSWORD") or getpass.getpass("Password: ")
    return username, password


async def record_faults(target: Path) -> None:
    """One ReadFaultMessages call for the first system, without SessionId."""
    username, password = credentials()
    target.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=30) as http:
        client = WolfClient(http, username, password)
        try:
            systems = await client.get_systems()
            print(f"{len(systems)} system(s); reading fault messages of the first only")
            # _call, not _request: _request adds SessionId and retries; the owner
            # approved exactly one call with the portal's payload.
            raw = await client._call(
                "POST",
                "ReadFaultMessages",
                json={
                    "LastRead": None,
                    "GatewayId": systems[0].gateway_id,
                    "SystemId": systems[0].id,
                },
            )
            write(target / "fault_messages.json", redact_faults(raw))
        finally:
            await client.close()
    print(f"logins: {client.login_count}; wrote {target / 'fault_messages.json'}")


async def record(target: Path) -> None:
    """Fetch, redact and store the responses."""
    username, password = credentials()
    target.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=30) as http:
        client = WolfClient(http, username, password)
        try:
            systems = await client.get_systems()
            print(f"{len(systems)} system(s)")
            raw_systems = await client._request("GET", "GetSystemList")
            write(target / "system_list.json", redact_ids(raw_systems))
            for index, system in enumerate(systems):
                entry: dict[str, Any] = {"SystemId": system.id, "GatewayId": system.gateway_id}
                if system.share_id is not None:
                    entry["SystemShareId"] = system.share_id
                state = await client._request(
                    "POST", "GetSystemStateList", json={"SystemList": [entry]}
                )
                write(target / f"system_state_{index}.json", redact_ids(state))
                description = await client.get_description(system)
                write(target / f"description_{index}.json", redact_description(description))
                model = parse_description(description)
                user_level = [
                    p for p in model.parameters.values() if p.kind and p.bundle_id == 1000
                ]
                raw_values = await client._request(
                    "POST",
                    "GetParameterValues",
                    json={
                        "BundleId": 1000,
                        "IsSubBundle": False,
                        "ValueIdList": [p.value_id for p in user_level],
                        "GatewayId": system.gateway_id,
                        "SystemId": system.id,
                        "LastAccess": None,
                        "GuiIdChanged": True,
                    },
                )
                write(
                    target / f"values_{index}.json",
                    redact_values(raw_values, secret_value_ids(description)),
                )
                print(
                    f"system {index}: {len(model.parameters)} parameters, "
                    f"{len(user_level)} user-level values requested, "
                    f"{len(raw_values.get('Values') or [])} returned"
                )
        finally:
            await client.close()
    print(f"logins: {client.login_count}; files in {target}")


def write(path: Path, data: Any) -> None:
    """Pretty JSON, UTF-8."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[1:]
    faults = "--faults" in args
    paths = [a for a in args if a != "--faults"]
    out = Path(paths[0] if paths else "tests/fixtures/real")
    asyncio.run(record_faults(out) if faults else record(out))
