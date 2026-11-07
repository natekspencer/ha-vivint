"""Support for Vivint alarm control panel."""

from __future__ import annotations

from typing import Any

from vivintpy.devices.alarm_panel import AlarmPanel
from vivintpy.enums import ArmedState

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature as Feature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VivintConfigEntry
from .const import CONF_DISARM_CODE
from .hub import VivintEntity, VivintHub

ATTR_CHANGED_BY_MESSAGE = "changed_by_message"

ARMED_STATE_MAP = {
    ArmedState.DISARMED: AlarmControlPanelState.DISARMED,
    ArmedState.ARMING_AWAY_IN_EXIT_DELAY: AlarmControlPanelState.ARMING,
    ArmedState.ARMING_STAY_IN_EXIT_DELAY: AlarmControlPanelState.ARMING,
    ArmedState.ARMED_STAY: AlarmControlPanelState.ARMED_HOME,
    ArmedState.ARMED_AWAY: AlarmControlPanelState.ARMED_AWAY,
    ArmedState.ARMED_STAY_IN_ENTRY_DELAY: AlarmControlPanelState.PENDING,
    ArmedState.ARMED_AWAY_IN_ENTRY_DELAY: AlarmControlPanelState.PENDING,
    ArmedState.ALARM: AlarmControlPanelState.TRIGGERED,
    ArmedState.ALARM_FIRE: AlarmControlPanelState.TRIGGERED,
    ArmedState.DISABLED: AlarmControlPanelState.DISARMED,
    ArmedState.WALK_TEST: AlarmControlPanelState.DISARMED,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vivint alarm control panel using config entry."""
    entities = []
    hub: VivintHub = entry.runtime_data
    disarm_code = entry.options.get(CONF_DISARM_CODE)

    for system in hub.account.systems:
        for device in system.alarm_panels:
            entities.append(
                VivintAlarmControlPanelEntity(
                    device=device, hub=hub, disarm_code=disarm_code
                )
            )

    if not entities:
        return

    async_add_entities(entities)


class VivintAlarmControlPanelEntity(VivintEntity, AlarmControlPanelEntity):
    """Vivint Alarm Control Panel."""

    device: AlarmPanel

    _attr_code_arm_required = False
    _attr_supported_features = Feature.ARM_HOME | Feature.ARM_AWAY | Feature.TRIGGER

    def __init__(
        self, device: AlarmPanel, hub: VivintHub, disarm_code: str | None
    ) -> None:
        """Create the entity."""
        super().__init__(device, hub)
        self._attr_unique_id = str(self.device.id)
        if disarm_code:
            self._attr_code_format = CodeFormat.NUMBER
            self._disarm_code = disarm_code

    @property
    def changed_by(self) -> str | None:
        """Return what last armed or disarmed the panel."""
        return self.device.changed_by

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return Vivint's description of what last armed or disarmed the panel."""
        return {ATTR_CHANGED_BY_MESSAGE: self.device.changed_by_message}

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current alarm control panel entity state."""
        return ARMED_STATE_MAP.get(self.device.state)

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        if not self.code_format or code == self._disarm_code:
            await self.device.disarm()

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        await self.device.arm_stay()

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        await self.device.arm_away()

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Send alarm trigger command."""
        await self.device.trigger_alarm()
