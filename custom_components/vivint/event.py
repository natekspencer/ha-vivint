"""Support for Vivint events."""

from __future__ import annotations

import logging

from vivintpy.devices.camera import MOTION_DETECTED, Camera
from vivintpy.enums import CapabilityCategoryType

from homeassistant.components.event import (
    DoorbellEventType,
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VivintConfigEntry
from .hub import VivintBaseEntity, VivintHub

_LOGGER = logging.getLogger(__name__)


DOORBELL_DESCRIPTION = EventEntityDescription(
    key="doorbell",
    translation_key="doorbell",
    device_class=EventDeviceClass.DOORBELL,
    event_types=[DoorbellEventType.RING],
)
MOTION_DESCRIPTION = EventEntityDescription(
    key="motion",
    translation_key="motion",
    device_class=EventDeviceClass.MOTION,
    event_types=[MOTION_DETECTED],
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vivint events using config entry."""
    entities = []
    hub: VivintHub = entry.runtime_data

    for system in hub.account.systems:
        for alarm_panel in system.alarm_panels:
            for device in alarm_panel.get_devices([Camera]):
                entities.append(
                    VivintEventEntity(
                        device=device,
                        hub=hub,
                        entity_description=MOTION_DESCRIPTION,
                    )
                )
                if CapabilityCategoryType.DOORBELL in device.capabilities:
                    entities.append(
                        VivintEventEntity(
                            device=device,
                            hub=hub,
                            entity_description=DOORBELL_DESCRIPTION,
                        )
                    )

    if not entities:
        return

    async_add_entities(entities)


class VivintEventEntity(VivintBaseEntity, EventEntity):
    """Vivint event entity."""

    @callback
    def _async_handle_event(self, *args, **kwargs) -> None:
        """Handle the event."""
        self._trigger_event(self.event_types[0])
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.device.on(self.event_types[0], self._async_handle_event)
        )
