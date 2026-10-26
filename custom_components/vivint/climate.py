"""Support for Vivint thermostats."""

from __future__ import annotations

from typing import Any

from vivintpy.const import ThermostatAttribute
from vivintpy.devices.thermostat import Thermostat
from vivintpy.enums import (
    CapabilityCategoryType,
    CapabilityType,
    FanMode,
    OperatingMode,
    OperatingState,
)
from vivintpy.exceptions import VivintSkyApiRateLimitError

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    FAN_AUTO,
    FAN_ON,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VivintConfigEntry
from .const import DOMAIN
from .hub import VivintEntity, VivintHub

RATE_LIMIT_MESSAGE = (
    "Vivint limits how often a thermostat can be changed. Try again in a minute."
)

# Map Vivint HVAC Mode to Home Assistant value
VIVINT_HVAC_MODE_MAP = {
    OperatingMode.OFF: HVACMode.OFF,
    OperatingMode.HEAT: HVACMode.HEAT,
    OperatingMode.COOL: HVACMode.COOL,
    OperatingMode.AUTO: HVACMode.HEAT_COOL,
    OperatingMode.EMERGENCY_HEAT: HVACMode.HEAT,
    OperatingMode.RESUME: HVACMode.AUTO,  # maybe?
    OperatingMode.FAN_ONLY: HVACMode.FAN_ONLY,
    OperatingMode.FURNACE: HVACMode.HEAT,
    OperatingMode.DRY_AIR: HVACMode.DRY,
    OperatingMode.MOIST_AIR: HVACMode.DRY,  # maybe?
    OperatingMode.AUTO_CHANGEOVER: HVACMode.HEAT_COOL,
    OperatingMode.ENERGY_SAVE_HEAT: HVACMode.HEAT,
    OperatingMode.ENERGY_SAVE_COOL: HVACMode.COOL,
    OperatingMode.AWAY: HVACMode.HEAT_COOL,
    OperatingMode.ECO: HVACMode.HEAT_COOL,
}

# Map Home Assistant HVAC Mode to Vivint value
VIVINT_HVAC_INV_MODE_MAP = {
    HVACMode.OFF: OperatingMode.OFF,
    HVACMode.HEAT: OperatingMode.HEAT,
    HVACMode.COOL: OperatingMode.COOL,
    HVACMode.HEAT_COOL: OperatingMode.AUTO,
}

VIVINT_CAPABILITY_FAN_MODE_MAP = {
    CapabilityType.FAN15_MINUTE: FanMode.TIMER_15,
    CapabilityType.FAN30_MINUTE: FanMode.TIMER_30,
    CapabilityType.FAN45_MINUTE: FanMode.TIMER_45,
    CapabilityType.FAN60_MINUTE: FanMode.TIMER_60,
    CapabilityType.FAN120_MINUTE: FanMode.TIMER_120,
    CapabilityType.FAN240_MINUTE: FanMode.TIMER_240,
    CapabilityType.FAN480_MINUTE: FanMode.TIMER_480,
    CapabilityType.FAN960_MINUTE: FanMode.TIMER_960,
}

VIVINT_FAN_MODE_MAP = {
    FanMode.AUTO_LOW: FAN_AUTO,
    FanMode.ON_LOW: FAN_ON,
    FanMode.TIMER_15: "15 minutes",
    FanMode.TIMER_30: "30 minutes",
    FanMode.TIMER_45: "45 minutes",
    FanMode.TIMER_60: "1 hour",
    FanMode.TIMER_120: "2 hours",
    FanMode.TIMER_240: "4 hours",
    FanMode.TIMER_480: "8 hours",
    FanMode.TIMER_720: "12 hours",
    FanMode.TIMER_960: "16 hours",
}

VIVINT_FAN_INV_MODE_MAP = {v: k for k, v in VIVINT_FAN_MODE_MAP.items()}

VIVINT_HVAC_STATUS_MAP = {
    OperatingState.IDLE: HVACAction.IDLE,
    OperatingState.HEATING: HVACAction.HEATING,
    OperatingState.COOLING: HVACAction.COOLING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vivint climate using config entry."""
    entities = []
    hub: VivintHub = entry.runtime_data

    for system in hub.account.systems:
        for alarm_panel in system.alarm_panels:
            for device in alarm_panel.devices:
                if isinstance(device, Thermostat):
                    entities.append(VivintClimate(device=device, hub=hub))

    if entities:
        async_add_entities(entities)

    @callback
    def async_add_climate(device: Thermostat) -> None:
        """Add a thermostat that was discovered after setup."""
        async_add_entities([VivintClimate(device=device, hub=hub)])

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{entry.entry_id}_add_{CLIMATE_DOMAIN}",
            async_add_climate,
        )
    )


class VivintClimate(VivintEntity, ClimateEntity):
    """Vivint Climate."""

    device: Thermostat

    _attr_hvac_modes = [HVACMode.COOL, HVACMode.HEAT, HVACMode.HEAT_COOL, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, device: Thermostat, hub: VivintHub) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(device=device, hub=hub)
        self._attr_fan_modes = [FAN_AUTO, FAN_ON] + [
            VIVINT_FAN_MODE_MAP[VIVINT_CAPABILITY_FAN_MODE_MAP[x]]
            for k, v in device.capabilities.items()
            if k == CapabilityCategoryType.THERMOSTAT
            for x in v
            if x in VIVINT_CAPABILITY_FAN_MODE_MAP
        ]

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self.device.alarm_panel.id}-{self.device.id}"

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.device.temperature

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity level."""
        return self.device.humidity

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        if self.hvac_mode == HVACMode.HEAT:
            return self.device.heat_set_point
        if self.hvac_mode == HVACMode.COOL:
            return self.device.cool_set_point
        return None

    @property
    def target_temperature_high(self) -> float | None:
        """Return the highbound target temperature we try to reach."""
        return (
            None if self.hvac_mode != HVACMode.HEAT_COOL else self.device.cool_set_point
        )

    @property
    def target_temperature_low(self) -> float | None:
        """Return the lowbound target temperature we try to reach."""
        return (
            None if self.hvac_mode != HVACMode.HEAT_COOL else self.device.heat_set_point
        )

    @property
    def max_temp(self) -> float | None:
        """Return the maximum temperature."""
        return self.device.maximum_temperature

    @property
    def min_temp(self) -> float | None:
        """Return the minimum temperature."""
        return self.device.minimum_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation ie. heat, cool mode."""
        return VIVINT_HVAC_MODE_MAP.get(self.device.operating_mode, HVACMode.HEAT_COOL)

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running hvac operation if supported."""
        return VIVINT_HVAC_STATUS_MAP.get(self.device.operating_state, HVACAction.IDLE)

    @property
    def fan_mode(self) -> str:
        """Return the fan mode."""
        return VIVINT_FAN_MODE_MAP.get(self.device.fan_mode, FAN_ON)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        await self._async_set_state(
            **{
                ThermostatAttribute.FAN_MODE: VIVINT_FAN_INV_MODE_MAP.get(
                    fan_mode, VIVINT_FAN_INV_MODE_MAP.get(self.fan_modes[-1])
                )
            }
        )

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        await self._async_set_state(
            **{ThermostatAttribute.OPERATING_MODE: VIVINT_HVAC_INV_MODE_MAP[hvac_mode]}
        )

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT_COOL)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        low_temp = kwargs.get(ATTR_TARGET_TEMP_LOW)
        high_temp = kwargs.get(ATTR_TARGET_TEMP_HIGH)

        cool = self._changed_target(
            temp if self.hvac_mode == HVACMode.COOL else high_temp,
            self.device.cool_set_point,
        )
        heat = self._changed_target(
            temp if self.hvac_mode == HVACMode.HEAT else low_temp,
            self.device.heat_set_point,
        )
        if heat is not None or cool is not None:
            try:
                await self.device.set_set_points(heat=heat, cool=cool)
            except VivintSkyApiRateLimitError as err:
                raise HomeAssistantError(RATE_LIMIT_MESSAGE) from err

    async def _async_set_state(self, **kwargs: Any) -> None:
        """Change the thermostat, explaining when Vivint is limiting changes."""
        try:
            await self.device.set_state(**kwargs)
        except VivintSkyApiRateLimitError as err:
            raise HomeAssistantError(RATE_LIMIT_MESSAGE) from err

    @staticmethod
    def _changed_target(target: float | None, current: float | None) -> float | None:
        """Return the target if it differs enough from the current set point."""
        if target is None or (current is not None and abs(target - current) < 0.5):
            return None
        return target
