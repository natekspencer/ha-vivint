"""Support for Vivint garage doors."""

from typing import Any

from vivintpy.devices.garage_door import GarageDoor

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VivintConfigEntry
from .hub import VivintEntity, VivintHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vivint garage doors using config entry."""
    entities = []
    hub: VivintHub = entry.runtime_data

    for system in hub.account.systems:
        for alarm_panel in system.alarm_panels:
            for device in alarm_panel.devices:
                if isinstance(device, GarageDoor):
                    entities.append(VivintGarageDoorEntity(device=device, hub=hub))

    if not entities:
        return

    async_add_entities(entities)


class VivintGarageDoorEntity(VivintEntity, CoverEntity):
    """Vivint Garage Door."""

    device: GarageDoor

    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = CoverEntityFeature.CLOSE | CoverEntityFeature.OPEN

    @property
    def is_opening(self) -> bool:
        """Return whether this device is opening."""
        return self.device.is_opening

    @property
    def is_closing(self) -> bool:
        """Return whether this device is closing."""
        return self.device.is_closing

    @property
    def is_closed(self) -> bool:
        """Return whether this device is closed."""
        return self.device.is_closed

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self.device.alarm_panel.id}-{self.device.id}"

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        await self.device.close()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.device.open()
