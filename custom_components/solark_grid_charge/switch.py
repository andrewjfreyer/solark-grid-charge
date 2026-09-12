"""SolArk switches (inverter settings that are safe to control from HA)."""
from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import SolArkCloudAPI, coerce_bool
from .const import DOMAIN, GRID_CHARGE_FIELD
from .entity import SolArkSettingEntity


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


class SolArkGridChargeSwitch(SolArkSettingEntity, SwitchEntity):
    """Whether the inverter may charge the battery from the grid.

    Mirrors the Grid Charge toggle on the portal's Battery Setting page.
    """

    _attr_name = "Grid Charge"
    _attr_icon = "mdi:transmission-tower-import"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: SolArkCloudAPI,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator, api, entry, GRID_CHARGE_FIELD, "grid_charge"
        )

    def _parse(self, raw: Any) -> Optional[bool]:
        return coerce_bool(raw)

    def _serialize(self, value: Any) -> str:
        return "1" if value else "0"

    @property
    def is_on(self) -> Optional[bool]:
        return self._value

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_command(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_command(False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Surface the related Grid Start thresholds for context."""
        settings = self.settings
        attrs = {
            "grid_start_soc": settings.get("sdStartCap"),
            "grid_start_voltage": settings.get("sdStartVolt"),
            "grid_charge_current": settings.get("sdBatteryCurrent"),
        }
        return {k: v for k, v in attrs.items() if v is not None}
