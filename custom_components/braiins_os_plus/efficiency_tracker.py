# custom_components/braiins_os_plus/efficiency_tracker.py

from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# Wait this many consecutive readings at the same power target before recording.
# At 5s polling this is ~1 minute, allowing the miner to stabilise after a target change.
MIN_STABLE_READINGS = 12

# A power level needs at least this many recorded samples before it's trusted
# for "best target" selection (~2 minutes of stable data).
MIN_VALID_SAMPLES = 24

# Exponential moving average weight applied to each new sample.
# Lower values smooth more aggressively; 0.1 gives ~18 samples to reach 95% convergence.
EMA_ALPHA = 0.1

# Persist to storage at most once per minute to avoid excessive I/O.
SAVE_EVERY_N_UPDATES = 12


class PowerEfficiencyTracker:
    """Accumulates efficiency data at each power target to find the optimal setting.

    Data is keyed by power target (watts) and stored as an exponential moving average
    of efficiency (J/TH) and hashrate (TH/s).  Readings are only recorded once the
    miner has held a stable power target for MIN_STABLE_READINGS polls.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, f"braiins_os_plus_{entry_id}_efficiency")
        self._readings: dict[str, dict] = {}
        self._stable_count = 0
        self._last_power_target: int | None = None
        self._updates_since_save = 0

    async def async_load(self) -> None:
        """Load persisted readings from storage."""
        data = await self._store.async_load()
        if data:
            self._readings = data.get("readings", {})
            _LOGGER.debug(
                "Loaded efficiency profile: %d power levels on record", len(self._readings)
            )

    async def async_save(self) -> None:
        """Persist current readings to storage."""
        await self._store.async_save({"readings": self._readings})

    def update(
        self,
        power_target_watt: int | None,
        actual_consumption_watt: int | None,
        efficiency_jth: float | None,
        hashrate_ths: float | None,
    ) -> None:
        """Record a new data point.

        Call this on every coordinator update.  The tracker silently ignores
        readings during the stabilisation period after a power target change,
        and any reading where actual consumption is more than 10% away from
        the target (i.e. the hardware is still adjusting).
        """
        if power_target_watt is None or actual_consumption_watt is None or efficiency_jth is None or hashrate_ths is None:
            return
        if efficiency_jth <= 0 or hashrate_ths <= 0 or power_target_watt <= 0:
            return

        if power_target_watt != self._last_power_target:
            self._stable_count = 0
            self._last_power_target = power_target_watt
        else:
            self._stable_count += 1

        if self._stable_count < MIN_STABLE_READINGS:
            return

        if abs(actual_consumption_watt - power_target_watt) / power_target_watt > 0.10:
            return

        key = str(power_target_watt)
        if key not in self._readings:
            self._readings[key] = {"samples": 0, "avg_efficiency": 0.0, "avg_hashrate": 0.0}

        entry = self._readings[key]
        if entry["samples"] == 0:
            entry["avg_efficiency"] = efficiency_jth
            entry["avg_hashrate"] = hashrate_ths
        else:
            entry["avg_efficiency"] = (1 - EMA_ALPHA) * entry["avg_efficiency"] + EMA_ALPHA * efficiency_jth
            entry["avg_hashrate"] = (1 - EMA_ALPHA) * entry["avg_hashrate"] + EMA_ALPHA * hashrate_ths
        entry["samples"] += 1

        self._updates_since_save += 1
        if self._updates_since_save >= SAVE_EVERY_N_UPDATES:
            self._updates_since_save = 0
            self._hass.async_create_task(self.async_save())

    def get_best_power_target(self) -> int | None:
        """Return the power target (W) with the lowest average efficiency, or None if not enough data."""
        valid = {k: v for k, v in self._readings.items() if v["samples"] >= MIN_VALID_SAMPLES}
        if not valid:
            return None
        return int(min(valid, key=lambda k: valid[k]["avg_efficiency"]))

    def get_best_efficiency(self) -> float | None:
        """Return the best (lowest) average efficiency in J/TH, or None if not enough data."""
        best = self.get_best_power_target()
        if best is None:
            return None
        return round(self._readings[str(best)]["avg_efficiency"], 2)

    def get_sampled_level_count(self) -> int:
        """Return the number of power levels with enough data to be trusted."""
        return sum(1 for v in self._readings.values() if v["samples"] >= MIN_VALID_SAMPLES)

    def get_all_readings(self) -> dict:
        """Return all recorded readings sorted by power target, for use as sensor attributes."""
        return {
            int(k): {
                "avg_efficiency_jth": round(v["avg_efficiency"], 2),
                "avg_hashrate_ths": round(v["avg_hashrate"], 4),
                "samples": v["samples"],
                "trusted": v["samples"] >= MIN_VALID_SAMPLES,
            }
            for k, v in sorted(self._readings.items(), key=lambda x: int(x[0]))
        }
