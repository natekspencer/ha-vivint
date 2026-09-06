"""Support for Vivint alarm control panel."""

from __future__ import annotations

from collections.abc import Iterable

from vivintpy.devices.alarm_panel import AlarmPanel
from vivintpy.enums import ArmedState

from homeassistant.components.alarm_control_panel import (
    DOMAIN as PLATFORM,
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature as Feature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VivintConfigEntry
from .const import CONF_DISARM_CODE, DOMAIN
from .hub import VivintEntity, VivintHub

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
    async_add_entities: AddEntitiesCallback,
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

    # Migrate unique ids
    async_update_unique_id(hass, PLATFORM, entities)

    async_add_entities(entities)


class VivintAlarmControlPanelEntity(VivintEntity, AlarmControlPanelEntity):
    """Vivint Alarm Control Panel."""

    device: AlarmPanel

    _attr_changed_by = None
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


# to be removed 2025-01
def async_update_unique_id(
    hass: HomeAssistant, domain: str, entities: Iterable[VivintAlarmControlPanelEntity]
) -> None:
    """Update unique ID to be based on VIN and entity description key instead of name."""
    ent_reg = er.async_get(hass)
    for entity in entities:
        old_unique_id = int(entity.unique_id)
        if entity_id := ent_reg.async_get_entity_id(domain, DOMAIN, old_unique_id):
            if existing_entity_id := ent_reg.async_get_entity_id(
                domain, DOMAIN, entity.unique_id
            ):
                ent_reg.async_remove(existing_entity_id)
            ent_reg.async_update_entity(entity_id, new_unique_id=entity.unique_id)
