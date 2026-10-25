"""Record redacted read-only API responses as test fixtures.

Reads only: login, system list, system state, parameter description, one
GetParameterValues call for the user-level bundle. Nothing is written to the
heating system.

Usage (in your own terminal, so the password never lands in a log):

    read -r WOLF_USERNAME && read -rs WOLF_PASSWORD && export WOLF_USERNAME WOLF_PASSWORD
    .venv/bin/python scripts/record_fixtures.py tests/fixtures/real

Without the environment variables the script prompts for both values.
Check the output with `git diff` before committing it.
"""

import asyncio
import getpass
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.wolf_smartset.api import WolfClient
from custom_components.wolf_smartset.model import parse_description

REDACTED = "**REDACTED**"
# IDs are replaced consistently so the fixtures stay usable.
FAKE_IDS = {"Id": 1234, "SystemId": 1234, "GatewayId": 5678, "SystemShareId": 9012}
SECRET_KEYS = {
    "Name", "Description", "Comment", "ContactInformation", "Email", "UserName",
    "Firstname", "Surname", "Street", "City", "ZipCode", "Phone", "SerialNumber",
    "GatewayUsername",
}  # fmt: skip
SECRET_PARAMETER = re.compile(
    r"seriennummer|serial|mac|ip adresse|gateway|dns|subnetz|anlagenname|herstell",
    re.IGNORECASE,
)
# text, IP, URL, password inputs; dates, times and day switch times (presence patterns)
SECRET_CONTROL_TYPES = {9, 10, 14, 20, 21, 22, 23}


def redact_ids(data: Any) -> Any:
    """Replace system/gateway IDs and personal fields of non-descriptor objects."""
    if isinstance(data, list):
        return [redact_ids(item) for item in data]
    if not isinstance(data, dict):
        return data
    return {
        key: FAKE_IDS[key]
        if key in FAKE_IDS and value is not None
        else REDACTED
        if key in SECRET_KEYS and value
        else redact_ids(value)
        for key, value in data.items()
    }


def redact_description(data: Any) -> Any:
    """Blank values of identifying parameters (serials, MAC, IP, system name)."""
    if isinstance(data, list):
        return [redact_description(item) for item in data]
    if not isinstance(data, dict):
        return data
    result = {key: redact_description(value) for key, value in data.items()}
    if "ValueId" in data and (
        data.get("ControlType") in SECRET_CONTROL_TYPES
        or SECRET_PARAMETER.search(str(data.get("Name") or ""))
    ):
        result["Value"] = REDACTED if data.get("Value") is not None else None
    return result


async def record(target: Path) -> None:
    """Fetch, redact and store the responses."""
    username = os.environ.get("WOLF_USERNAME") or input("Wolf SmartSet username: ")
    password = os.environ.get("WOLF_PASSWORD") or getpass.getpass("Password: ")
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
                write(target / f"values_{index}.json", redact_ids(raw_values))
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
    asyncio.run(record(Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/real")))
