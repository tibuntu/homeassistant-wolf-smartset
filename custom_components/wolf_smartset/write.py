"""Write pipeline: every write from entities and undo goes through here (ADR-Writes-012).

Order: writable check, validation, then under one lock: no-op check, dry run,
rate limit, API call, optimistic state, history. The next poll confirms or
corrects the value.
"""

import asyncio
from collections.abc import Callable
import math
import time
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import WolfError
from .const import (
    CONF_DRY_RUN,
    CONF_MAX_WRITES_PER_HOUR,
    DEFAULT_DRY_RUN,
    DEFAULT_MAX_WRITES_PER_HOUR,
    DOMAIN,
    LOGGER,
)
from .model import Kind, Parameter

if TYPE_CHECKING:
    from .coordinator import WolfSystemCoordinator

STORAGE_VERSION = 1
HISTORY_LIMIT = 200
# A value read earlier than this after the write may predate the controller's update.
CONFIRM_AFTER_SECONDS = 30
# AccessLevel values of the portal: 2 user write, 4 expert write.
ACCESS_USER_WRITE = 2
ACCESS_EXPERT_WRITE = 4

RESULT_OK = "ok"
RESULT_UNCHANGED = "unchanged"
RESULT_DRY_RUN = "dry_run"
RESULT_RATE_LIMITED = "rate_limited"
RESULT_ERROR = "error"
RESULT_NOT_APPLIED = "not_applied"


def format_number(value: float) -> str:
    """48.0 -> '48', 20.5 -> '20.5' (the portal sends plain decimal strings)."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def same_value(parameter: Parameter, current: str | None, target: str) -> bool:
    """Compare as numbers for numeric parameters, as strings otherwise."""
    if current is None:
        return False
    if parameter.kind is Kind.NUMBER:
        try:
            return math.isclose(float(current.replace(",", ".")), float(target), abs_tol=1e-6)
        except ValueError:
            return False
    return current.strip() == target


def _error(key: str, **placeholders: Any) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders
    )


def validate(parameter: Parameter, target: str, access_level: int | None) -> None:
    """Refuse anything the description does not allow, before any network call."""
    if not parameter.writable or parameter.kind not in (Kind.NUMBER, Kind.SELECT, Kind.SWITCH):
        raise _error("not_writable", name=parameter.label)
    required = ACCESS_EXPERT_WRITE if parameter.expert else ACCESS_USER_WRITE
    if access_level is not None and access_level < required:
        raise _error("access_denied", name=parameter.label)
    if parameter.kind is not Kind.NUMBER:
        if target not in parameter.selectable:
            raise _error("invalid_option", name=parameter.label, value=target)
        return
    minimum, maximum, value = parameter.minimum, parameter.maximum, float(target)
    if minimum is None or maximum is None or not minimum <= value <= maximum:
        raise _error(
            "out_of_range",
            name=parameter.label,
            value=target,
            min=format_number(minimum or 0),
            max=format_number(maximum or 0),
        )
    step = parameter.step or 1.0
    steps = (value - minimum) / step
    if not math.isclose(steps, round(steps), abs_tol=1e-6):
        raise _error("invalid_step", name=parameter.label, value=target, step=format_number(step))


class WriteManager:
    """One per config entry: lock, rate limit, dry run, history, pending confirmations."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """History lives in .storage/wolf_smartset.<entry_id>.history."""
        self._entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.history"
        )
        self._lock = asyncio.Lock()
        self._writes: list[float] = []
        self._pending: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}
        self._listeners: list[Callable[[], None]] = []
        self.history: list[dict[str, Any]] = []

    @property
    def dry_run(self) -> bool:
        """Default on: nothing is written until the user switches it off."""
        return bool(self._entry.options.get(CONF_DRY_RUN, DEFAULT_DRY_RUN))

    @property
    def max_writes_per_hour(self) -> int:
        """Rolling one-hour limit for real writes."""
        return int(self._entry.options.get(CONF_MAX_WRITES_PER_HOUR, DEFAULT_MAX_WRITES_PER_HOUR))

    async def async_load(self) -> None:
        """Restore the history after a restart."""
        data = await self._store.async_load() or {}
        self.history = data.get("history", [])

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Notify entities (undo button) when the history changes."""
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    async def async_write(
        self,
        coordinator: WolfSystemCoordinator,
        parameter: Parameter,
        target: str,
        *,
        source: str,
        entity: Entity | None = None,
    ) -> dict[str, Any]:
        """Run the full pipeline and return the history record."""
        validate(parameter, target, coordinator.access_level)
        async with self._lock:
            current = (coordinator.data or {}).get(parameter.value_id)
            record = {
                "time": dt_util.utcnow().isoformat(),
                "system_id": coordinator.system.id,
                "parameter_id": parameter.parameter_id,
                "value_id": parameter.value_id,
                "label": parameter.label,
                "old": current,
                "new": target,
                "source": source,
                "result": RESULT_OK,
            }
            if same_value(parameter, current, target):
                LOGGER.info("%s is already %s, nothing sent", parameter.label, target)
                return await self._record(record, RESULT_UNCHANGED)
            if self.dry_run:
                LOGGER.info(
                    "Dry run: would write %s (ValueId %s) %s -> %s",
                    parameter.label,
                    parameter.value_id,
                    current,
                    target,
                )
                return await self._record(record, RESULT_DRY_RUN)
            now = time.monotonic()
            self._writes = [t for t in self._writes if now - t < 3600]
            if len(self._writes) >= self.max_writes_per_hour:
                await self._record(record, RESULT_RATE_LIMITED)
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="rate_limited",
                    translation_placeholders={"limit": str(self.max_writes_per_hour)},
                )
            LOGGER.info(
                "Writing %s (ValueId %s) %s -> %s",
                parameter.label,
                parameter.value_id,
                current,
                target,
            )
            try:
                await coordinator.client.write_value(
                    coordinator.system,
                    parameter.bundle_id,
                    parameter.value_id,
                    target,
                    parameter.name,
                )
            except WolfError as err:
                record["error"] = str(err)
                await self._record(record, RESULT_ERROR)
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="write_failed",
                    translation_placeholders={"name": parameter.label, "error": str(err)},
                ) from err
            self._writes.append(now)
            # Optimistic: show the new value now; the next poll confirms or corrects it.
            if coordinator.data is not None:
                coordinator.data[parameter.value_id] = target
            if entity is not None:
                entity.async_write_ha_state()
            self._pending[(coordinator.system.id, parameter.value_id)] = (now, record)
            return await self._record(record, RESULT_OK)

    @callback
    def async_check_pending(self, coordinator: WolfSystemCoordinator) -> None:
        """After a poll: confirm written values or mark them as not applied."""
        changed = False
        now = time.monotonic()
        for key in [k for k in self._pending if k[0] == coordinator.system.id]:
            written_at, record = self._pending[key]
            if now - written_at < CONFIRM_AFTER_SECONDS:
                continue
            del self._pending[key]
            parameter = coordinator.description.parameters.get(record["parameter_id"])
            current = (coordinator.data or {}).get(key[1])
            if parameter is not None and same_value(parameter, current, record["new"]):
                record["confirmed"] = True
            else:
                record["result"] = RESULT_NOT_APPLIED
                record["read_back"] = current
                LOGGER.warning(
                    "%s was written as %s but reads %s: the controller did not apply it",
                    record["label"],
                    record["new"],
                    current,
                )
            changed = True
        if changed:
            self._store.async_delay_save(self._data, 1)
            self._notify()

    def last_undoable(self) -> dict[str, Any] | None:
        """Latest applied change that has not been undone."""
        for record in reversed(self.history):
            if record["result"] == RESULT_OK and not record.get("undone") and record["old"]:
                return record
        return None

    async def async_undo(self, coordinators: dict[int, WolfSystemCoordinator]) -> None:
        """Write the previous value of the latest change back (through the pipeline)."""
        record = self.last_undoable()
        if record is None:
            raise _error("nothing_to_undo")
        coordinator = coordinators.get(record["system_id"])
        if coordinator is None or record["parameter_id"] not in coordinator.description.parameters:
            raise _error("nothing_to_undo")
        parameter = coordinator.description.parameters[record["parameter_id"]]
        result = await self.async_write(coordinator, parameter, record["old"], source="undo")
        if result["result"] in (RESULT_OK, RESULT_UNCHANGED):
            record["undone"] = True
            await self._store.async_save(self._data())
            self._notify()

    async def _record(self, record: dict[str, Any], result: str) -> dict[str, Any]:
        record["result"] = result
        self.history = [*self.history, record][-HISTORY_LIMIT:]
        await self._store.async_save(self._data())
        self._notify()
        return record

    def _data(self) -> dict[str, Any]:
        return {"history": self.history}

    def _notify(self) -> None:
        for update in list(self._listeners):
            update()
