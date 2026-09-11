"""SolArk numbers: the retained battery SOC for each Time-of-Use slot."""
from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import SolArkCloudAPI, coerce_bool, coerce_number
from .const import (
    BATT_MODE_FIELD,
    DOMAIN,
    SLOT_GRID_CHARGE_FIELD,
    SLOT_SOC_FIELD,
    SLOT_START_FIELD,
    SOC_MODE_VALUES,
    TIME_SLOT_COUNT,
)
from .entity import SolArkSettingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one retained-SOC number per Time-of-Use slot."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SolArkSlotSocNumber(
            data["settings_coordinator"], data["api"], entry, slot
        )
        for slot in range(1, TIME_SLOT_COUNT + 1)
    )


class SolArkSlotSocNumber(SolArkSettingEntity, NumberEntity):
    """Battery SOC the inverter retains during one Time-of-Use slot.

    Mirrors the "Battery SOC N" field on the portal's Work Mode page
    (settings field `capN`). The inverter will not discharge the battery
    below this level during the slot, so raising it reserves more capacity
    and lowering it allows deeper discharge.
    """

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = NumberDeviceClass.BATTERY
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: SolArkCloudAPI,
        entry: ConfigEntry,
        slot: int,
    ) -> None:
        self._slot = slot
        super().__init__(
            coordinator,
            api,
            entry,
            SLOT_SOC_FIELD.format(n=slot),
            f"slot_{slot}_soc",
        )
        self._attr_name = f"Time Slot {slot} Battery SOC"

    def _parse(self, raw: Any) -> Optional[float]:
        return coerce_number(raw)

    def _serialize(self, value: Any) -> str:
        # The portal posts these as whole-number strings.
        return str(int(round(float(value))))

    @property
    def native_value(self) -> Optional[float]:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        await self._async_command(float(value))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Identify which slot this is, and whether the SOC value applies."""
        settings = self.settings
        batt_mode = settings.get(BATT_MODE_FIELD)
        attrs: dict[str, Any] = {
            "slot": self._slot,
            "slot_start": settings.get(SLOT_START_FIELD.format(n=self._slot)),
            "grid_charge_enabled": coerce_bool(
                settings.get(SLOT_GRID_CHARGE_FIELD.format(n=self._slot))
            ),
        }
        if batt_mode is not None:
            # In voltage mode the inverter uses sellTimeNVolt instead, and
            # writes to capN have no effect.
            attrs["battery_mode"] = batt_mode
            attrs["applies_in_current_mode"] = batt_mode in SOC_MODE_VALUES
        return {k: v for k, v in attrs.items() if v is not None}
