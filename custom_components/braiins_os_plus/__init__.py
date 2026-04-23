# custom_components/braiins_os_plus/__init__.py

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, PLATFORMS
from .api import BraiinsAPI
from .efficiency_tracker import PowerEfficiencyTracker

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Braiins OS+ from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    api = BraiinsAPI(hass, entry, session)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_data_coordinator",
        update_method=api.async_update_data,
        update_interval=timedelta(seconds=5),
    )

    tracker = PowerEfficiencyTracker(hass, entry.entry_id)
    await tracker.async_load()

    def _update_tracker() -> None:
        """Feed the latest coordinator data into the efficiency tracker."""
        data = coordinator.data
        if not data:
            return
        power_target = (data.get("power_target") or {}).get("watt")
        efficiency = (data.get("power_stats") or {}).get("efficiency", {}).get("joule_per_terahash")
        total_ghs = sum(
            board.get("stats", {}).get("real_hashrate", {}).get("last_5s", {}).get("gigahash_per_second", 0)
            for board in (data.get("hashboards") or [])
        )
        hashrate_ths = total_ghs / 1000 if total_ghs > 0 else None
        tracker.update(power_target, efficiency, hashrate_ths)

    # Register before first refresh so the tracker is fed from the very first poll.
    coordinator.async_add_listener(_update_tracker)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "tracker": tracker,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        tracker = hass.data[DOMAIN][entry.entry_id].get("tracker")
        if tracker:
            await tracker.async_save()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok