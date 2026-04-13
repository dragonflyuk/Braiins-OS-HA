# custom_components/braiins_os_plus/number.py

import logging

from homeassistant.components.number import NumberMode, RestoreNumber
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


class PowerTargetNumber(CoordinatorEntity, RestoreNumber):
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
        self._cached_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known value when HA starts."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_number_data()) is not None:
            self._cached_value = last_data.native_value
            _LOGGER.debug("Restored power target value: %s W", self._cached_value)

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
        """Return the current power target in watts.

        Prefers the live value from the coordinator; falls back to the
        last value set by the user so the entity is never blank.
        """
        if self.coordinator.data and (power_target := self.coordinator.data.get("power_target")):
            if (watt := power_target.get("watt")) is not None:
                return watt
        return self._cached_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the power target to a specific wattage."""
        if await self._api.set_power_target(int(value)):
            self._cached_value = value
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
