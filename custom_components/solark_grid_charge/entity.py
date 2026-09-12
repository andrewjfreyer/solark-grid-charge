"""Shared base for entities backed by a single inverter settings field."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .api import SolArkCloudAPI, SolArkCloudAPIError
from .const import COMMAND_SETTLE_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SolArkSettingEntity(CoordinatorEntity):
    """An entity backed by one field of the inverter's settings payload.

    The cloud API only confirms that a command was *queued*; the inverter
    applies it over the dongle a few seconds later. Every settings-backed
    entity therefore shares the same optimistic handling: show the value that
    was asked for until the inverter echoes it back, so the entity does not
    visibly snap back on the next poll.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: SolArkCloudAPI,
        entry: ConfigEntry,
        field: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._field = field
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "SolArk",
            "manufacturer": "SolArk",
        }
        # Value we have commanded but the inverter has not yet echoed back.
        self._pending: Any = None
        self._pending_until: Optional[datetime] = None

    # ------------------------------------------------------------------
    # subclass hooks
    # ------------------------------------------------------------------

    def _parse(self, raw: Any) -> Any:
        """Coerce the raw settings value into this entity's value type."""
        raise NotImplementedError

    def _serialize(self, value: Any) -> str:
        """Render a value for the API, which expects strings."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    @property
    def settings(self) -> dict[str, Any]:
        """The last settings payload, or an empty dict if none succeeded."""
        data = self.coordinator.data
        return data if isinstance(data, dict) else {}

    @property
    def _reported(self) -> Any:
        """The value last reported by the inverter, or None if unreported."""
        settings = self.settings
        if self._field not in settings:
            return None
        return self._parse(settings.get(self._field))

    def _clear_settled_pending(self) -> None:
        """Drop the optimistic value once confirmed, or once it has timed out."""
        if self._pending is None:
            return
        reported = self._reported
        timed_out = (
            self._pending_until is not None
            and dt_util.utcnow() >= self._pending_until
        )
        if reported == self._pending or timed_out:
            if reported != self._pending:
                _LOGGER.warning(
                    "SolArk %s: command was accepted but the inverter still "
                    "reports %s after %ss; showing the reported value",
                    self._field,
                    reported,
                    COMMAND_SETTLE_SECONDS,
                )
            self._pending = None
            self._pending_until = None

    @property
    def _value(self) -> Any:
        """What to display: the pending value if any, else what was reported."""
        self._clear_settled_pending()
        if self._pending is not None:
            return self._pending
        return self._reported

    @property
    def available(self) -> bool:
        # A command in flight keeps the entity usable even if a poll is late.
        if self._pending is not None:
            return True
        return bool(self.coordinator.last_update_success) and (
            self._reported is not None
        )

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------

    async def _async_command(self, value: Any) -> None:
        """Write this entity's field, then hold the value until confirmed."""
        try:
            await self._api.async_write_settings(
                **{self._field: self._serialize(value)}
            )
        except SolArkCloudAPIError as err:
            raise HomeAssistantError(
                f"Failed to set SolArk {self._field} to {value}: {err}"
            ) from err

        self._pending = value
        self._pending_until = dt_util.utcnow() + timedelta(
            seconds=COMMAND_SETTLE_SECONDS
        )
        self.async_write_ha_state()

        await self.coordinator.async_request_refresh()
