"""SolArk switches (inverter settings that are safe to control from HA)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import SolArkCloudAPI, SolArkCloudAPIError
from .const import COMMAND_SETTLE_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolArk switches from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SolArkGridChargeSwitch(
                data["settings_coordinator"], data["api"], entry
            )
        ]
    )


class SolArkGridChargeSwitch(CoordinatorEntity, SwitchEntity):
    """Whether the inverter may charge the battery from the grid.

    Mirrors the Grid Charge toggle on the portal's Battery Setting page.
    """

    _attr_has_entity_name = True
    _attr_name = "Grid Charge"
    _attr_icon = "mdi:transmission-tower-import"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: SolArkCloudAPI,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"{entry.entry_id}_grid_charge"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "SolArk",
            "manufacturer": "SolArk",
        }
        # State we have commanded but the inverter has not yet echoed back.
        self._pending: Optional[bool] = None
        self._pending_until: Optional[datetime] = None

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    @property
    def _reported(self) -> Optional[bool]:
        """Grid Charge as last reported by the inverter, if at all."""
        settings = self.coordinator.data
        if not isinstance(settings, dict):
            return None
        return SolArkCloudAPI.parse_grid_charge(settings)

    def _clear_settled_pending(self) -> None:
        """Drop the optimistic value once confirmed or once it has timed out."""
        if self._pending is None:
            return
        if self._reported == self._pending or (
            self._pending_until is not None
            and datetime.utcnow() >= self._pending_until
        ):
            if self._reported != self._pending:
                _LOGGER.warning(
                    "SolArk Grid Charge command was accepted but the inverter "
                    "still reports %s after %ss; showing the reported value",
                    self._reported,
                    COMMAND_SETTLE_SECONDS,
                )
            self._pending = None
            self._pending_until = None

    @property
    def is_on(self) -> Optional[bool]:
        self._clear_settled_pending()
        if self._pending is not None:
            return self._pending
        return self._reported

    @property
    def available(self) -> bool:
        # A command in flight keeps the switch usable even if a poll is late.
        if self._pending is not None:
            return True
        return bool(self.coordinator.last_update_success) and (
            self._reported is not None
        )

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, enabled: bool) -> None:
        try:
            await self._api.async_set_grid_charge(enabled)
        except SolArkCloudAPIError as err:
            raise HomeAssistantError(
                f"Failed to set SolArk Grid Charge to {enabled}: {err}"
            ) from err

        # The API only confirms the command was queued; the inverter applies it
        # a few seconds later. Show the requested state until it echoes back,
        # so the switch does not visibly snap back on the next poll.
        self._pending = enabled
        self._pending_until = datetime.utcnow() + timedelta(
            seconds=COMMAND_SETTLE_SECONDS
        )
        self.async_write_ha_state()

        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------
    # attributes
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Surface the related Grid Start thresholds for context."""
        settings = self.coordinator.data
        if not isinstance(settings, dict):
            return {}
        attrs = {
            "grid_start_soc": settings.get("sdStartCap"),
            "grid_start_voltage": settings.get("sdStartVolt"),
            "grid_charge_current": settings.get("sdBatteryCurrent"),
        }
        return {k: v for k, v in attrs.items() if v is not None}
