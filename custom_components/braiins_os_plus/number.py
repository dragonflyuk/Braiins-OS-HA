# custom_components/braiins_os_plus/number.py

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .api import BraiinsAPI

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Braiins OS+ number entities from a config entry."""
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([PowerTargetNumber(coordinator, api, config_entry)])


class PowerTargetNumber(CoordinatorEntity, NumberEntity):
    """Number entity to read and set the miner's power target."""

    _attr_name = "Power Target"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 0
    _attr_native_max_value = 10000
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:lightning-bolt"
    _attr_has_entity_name = True

    def __init__(self, coordinator, api: BraiinsAPI, config_entry: ConfigEntry):
        super().__init__(coordinator)
        self._api = api
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_power_target"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            name=f"Braiins OS+ Miner ({self._config_entry.data['miner_ip']})",
            manufacturer="Braiins",
            model="Miner with Braiins OS+",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def native_value(self) -> float | None:
        """Return the current power target in watts."""
        if self.coordinator.data and (power_target := self.coordinator.data.get("power_target")):
            return power_target.get("watt")
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the power target to a specific wattage."""
        if await self._api.set_power_target(int(value)):
            await self.coordinator.async_request_refresh()
