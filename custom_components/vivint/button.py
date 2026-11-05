"""Support for Vivint buttons."""

from __future__ import annotations

from vivintpy.devices.alarm_panel import AlarmPanel
from vivintpy.devices.camera import Camera as VivintCamera
from vivintpy.entity import UPDATE
from vivintpy.enums import (
    CapabilityCategoryType as Category,
    CapabilityType as Capability,
)

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VivintConfigEntry
from .hub import VivintBaseEntity, VivintHub, has_capability

REBOOT_ENTITY = ButtonEntityDescription(
    key="reboot", device_class=ButtonDeviceClass.RESTART
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vivint button platform."""
    hub: VivintHub = entry.runtime_data
    entities = [
        VivintButtonEntity(
            device=alarm_panel, hub=hub, entity_description=REBOOT_ENTITY
        )
        for system in hub.account.systems
        if system.is_admin
        for alarm_panel in system.alarm_panels
    ]
    entities.extend(
        VivintButtonEntity(device=device, hub=hub, entity_description=REBOOT_ENTITY)
        for system in hub.account.systems
        for alarm_panel in system.alarm_panels
        for device in alarm_panel.devices
        if isinstance(device, VivintCamera)
        and has_capability(device, Category.CAMERA, Capability.REBOOT_CAMERA)
    )
    async_add_entities(entities)


class VivintButtonEntity(VivintBaseEntity, ButtonEntity):
    """A class that describes device button entities."""

    device: AlarmPanel | VivintCamera

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if isinstance(self.device, AlarmPanel):
            return (
                super().available and self.device._AlarmPanel__panel.data["can_reboot"]
            )
        return super().available

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.device.reboot()

    async def async_added_to_hass(self) -> None:
        """Set up a listener for the entity."""
        await super().async_added_to_hass()
        if isinstance(self.device, AlarmPanel):
            self.async_on_remove(
                self.device._AlarmPanel__panel.on(
                    UPDATE, lambda _: self.async_write_ha_state()
                )
            )
