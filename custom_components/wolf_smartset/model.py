"""Parameter model built from the raw GetGuiDescriptionForGateway response.

No Home Assistant imports. See docs/adr/ADR-Model-002 and ADR-Model-007.
"""

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any
import unicodedata

# Values of EnControlType in the portal JavaScript.
CT_COMBO_IMAGE = 0
CT_COMBO_TEXT = 1
CT_CHECKBOX = 5
CT_NUMERIC = 6
CT_SOLAR_STATISTICS = 15
CT_SOLAR_STATISTICS_BLOCK = 16
CT_TEXT = 20
CT_IP = 21
CT_HIDDEN = 31
CT_PROGRAM_SELECTION = 35

WRITABLE_CONTROL_TYPES = frozenset({CT_COMBO_TEXT, CT_NUMERIC, CT_PROGRAM_SELECTION})
LIST_CONTROL_TYPES = frozenset({CT_COMBO_TEXT, CT_PROGRAM_SELECTION})

# One-time actions the generic mapping cannot recognise, keyed by ParameterId.
KNOWN_SWITCHES = {22004200000: "dhw_once"}  # "1x Warmwasser"


class Kind(StrEnum):
    """Entity platform a parameter maps to."""

    SENSOR = "sensor"
    ENUM = "enum"
    TEXT = "text"
    BINARY = "binary"
    NUMBER = "number"
    SELECT = "select"
    SWITCH = "switch"


@dataclass(frozen=True)
class Occurrence:
    """Where a parameter appears in the description."""

    tab: str
    bundle_id: int
    expert: bool
    read_only: bool
    control_type: int
    device: str | None


@dataclass
class Parameter:
    """One data point, merged over all its occurrences."""

    parameter_id: int
    value_id: int
    name: str
    prefix: str | None
    group: str | None
    unit: str | None
    minimum: float | None
    maximum: float | None
    step: float | None
    decimals: int | None
    options: dict[str, str]  # ListItems value -> display text
    selectable: list[str]  # values the user may choose
    value: str | None  # current value embedded in the description
    control_type: int
    bundle_id: int
    writable: bool
    expert: bool
    tab: str = ""
    device: str | None = None
    label: str = ""
    occurrences: list[Occurrence] = field(default_factory=list)

    @property
    def kind(self) -> Kind | None:
        """Entity platform, or None when the parameter is not mapped."""
        if self.parameter_id in KNOWN_SWITCHES and set(self.options) == {"0", "1"}:
            return Kind.SWITCH
        ct = self.control_type
        if ct in LIST_CONTROL_TYPES or (ct == CT_COMBO_IMAGE and self.options):
            if not self.options:
                return None
            return Kind.SELECT if self.writable and self.selectable else Kind.ENUM
        if ct == CT_NUMERIC:
            limits_ok = (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum < self.maximum
            )
            return Kind.NUMBER if self.writable and limits_ok else Kind.SENSOR
        if ct in (CT_COMBO_IMAGE, CT_SOLAR_STATISTICS, CT_SOLAR_STATISTICS_BLOCK):
            return Kind.SENSOR
        if ct == CT_CHECKBOX:
            return Kind.BINARY
        if ct in (CT_TEXT, CT_IP):
            return Kind.TEXT
        # ponytail: dates, times, time programs, timed functions are not mapped yet
        return None


@dataclass
class Description:
    """All parameters of one system plus its expert submenus (devices)."""

    parameters: dict[int, Parameter]
    devices: dict[str, str]  # device key -> submenu name


def slugify(text: str) -> str:
    """ASCII slug for device keys, e.g. 'Bedienmodul BM-2 0' -> 'bedienmodul_bm_2_0'."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except TypeError, ValueError:
        return None


def _is_data_point(descriptor: dict[str, Any]) -> bool:
    return (
        (descriptor.get("ValueId") or 0) > 0
        and (descriptor.get("ParameterId") or 0) > 0
        and not descriptor.get("NoDataPoint")
    )


def _flatten(descriptors: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for descriptor in descriptors:
        yield descriptor
        yield from _flatten(descriptor.get("ChildParameterDescriptors") or [])


def _clean_group(group: str | None) -> str | None:
    """'073_Mischerkreis 1' -> 'Mischerkreis 1'."""
    if not group:
        return None
    head, sep, tail = group.partition("_")
    return tail if sep and head.isdigit() else group


def parse_description(raw: dict[str, Any]) -> Description:
    """Build the parameter model; see ADR-Model-002 for the rules."""
    found: dict[int, list[tuple[Occurrence, dict[str, Any]]]] = {}
    svg_units: dict[int, str] = {}
    devices: dict[str, str] = {}

    def walk(menu: dict[str, Any], device: str | None) -> None:
        for tab in menu.get("TabViews") or []:
            for schema in tab.get("SVGHeatingSchemaConfigDevices") or []:
                for item in schema.get("parameters") or []:
                    if item.get("unit"):
                        svg_units[item["valueId"]] = item["unit"]
            for descriptor in _flatten(tab.get("ParameterDescriptors") or []):
                if not _is_data_point(descriptor):
                    continue
                occurrence = Occurrence(
                    tab=tab.get("TabName") or "",
                    bundle_id=int(tab.get("BundleId") or 1000),
                    expert=bool(tab.get("IsExpertView")),
                    read_only=descriptor.get("IsReadOnly", True) is not False,
                    control_type=int(descriptor.get("ControlType", -1)),
                    device=device,
                )
                found.setdefault(descriptor["ParameterId"], []).append((occurrence, descriptor))
        for sub in menu.get("SubMenuEntries") or []:
            sub_device = device
            if sub_device is None and sub.get("Name"):
                sub_device = slugify(sub["Name"])
                devices[sub_device] = sub["Name"]
            walk(sub, sub_device)

    for menu in raw.get("MenuItems") or []:
        walk(menu, None)

    # ProtGrp -> device most often seen with it (ADR-Model-007 rule 2).
    prot_devices: dict[str, Counter[str]] = {}
    for entries in found.values():
        for occurrence, descriptor in entries:
            if descriptor.get("ProtGrp") and occurrence.device:
                prot_devices.setdefault(descriptor["ProtGrp"], Counter())[occurrence.device] += 1

    parameters: dict[int, Parameter] = {}
    for parameter_id, entries in found.items():
        writable = next(
            (
                (o, d)
                for o, d in entries
                if not o.read_only and o.control_type in WRITABLE_CONTROL_TYPES
            ),
            None,
        )
        primary = writable or next(
            ((o, d) for o, d in entries if o.control_type not in (CT_COMBO_IMAGE, CT_HIDDEN)),
            entries[0],
        )
        occurrence, descriptor = primary
        if occurrence.control_type == CT_HIDDEN:
            continue
        value_id = descriptor["ValueId"]
        unit = descriptor.get("Unit") or next(
            (d["Unit"] for _, d in entries if d.get("Unit")), svg_units.get(value_id)
        )
        items = descriptor.get("ListItems") or []
        minimum = _number(descriptor.get("MinValueCondition"))
        maximum = _number(descriptor.get("MaxValueCondition"))
        device = next((o.device for o, _ in entries if o.device), None)
        if device is None:
            prot = next((d["ProtGrp"] for _, d in entries if d.get("ProtGrp")), None)
            if prot in prot_devices:
                device = prot_devices[prot].most_common(1)[0][0]
        parameters[parameter_id] = Parameter(
            parameter_id=parameter_id,
            value_id=value_id,
            name=(descriptor.get("Name") or f"Parameter {parameter_id}").strip(),
            prefix=descriptor.get("NamePrefix"),
            group=_clean_group(descriptor.get("Group")),
            unit=unit,
            minimum=minimum if minimum is not None else _number(descriptor.get("MinValue")),
            maximum=maximum if maximum is not None else _number(descriptor.get("MaxValue")),
            step=_number(descriptor.get("StepWidth")),
            decimals=descriptor.get("Decimals"),
            options={str(i["Value"]): i["DisplayText"] for i in items},
            selectable=[str(i["Value"]) for i in items if i.get("IsSelectable", True)],
            value=str(descriptor["Value"])
            if descriptor.get("ValueState") == 1 and descriptor.get("Value") is not None
            else None,
            control_type=occurrence.control_type,
            # Writes need the writable tab's bundle; reads prefer a user-level bundle,
            # so enabled user entities never poll expert bundles (ADR-Polling-003).
            bundle_id=occurrence.bundle_id
            if writable
            else next((o.bundle_id for o, _ in entries if not o.expert), occurrence.bundle_id),
            writable=writable is not None,
            expert=all(o.expert for o, _ in entries),
            tab=occurrence.tab,
            device=device,
            occurrences=[o for o, _ in entries],
        )

    _assign_labels([p for p in parameters.values() if p.kind])
    return Description(parameters, devices)


def _assign_labels(parameters: list[Parameter]) -> None:
    """Prefix + name, made unique per device with the tab, the group, then the ID."""
    for parameter in parameters:
        prefix = f"{parameter.prefix} " if parameter.prefix else ""
        parameter.label = prefix + parameter.name
    for add in ("tab", "group", "id"):
        counts = Counter((p.device, p.label) for p in parameters)
        for parameter in parameters:
            if counts[(parameter.device, parameter.label)] < 2:
                continue
            if add == "tab" and parameter.tab:
                parameter.label = f"{parameter.label} ({parameter.tab})"
            elif add == "group" and parameter.group:
                parameter.label = f"{parameter.label} ({parameter.group})"
            elif add == "id":
                parameter.label = f"{parameter.label} ({parameter.parameter_id})"
