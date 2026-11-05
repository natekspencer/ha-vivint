"""Support for Vivint door locks."""

from typing import Any

from vivintpy.devices.door_lock import DoorLock

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VivintConfigEntry
from .hub import VivintEntity, VivintHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vivint door locks using config entry."""
    entities = []
    hub: VivintHub = entry.runtime_data

    for system in hub.account.systems:
        for alarm_panel in system.alarm_panels:
            for device in alarm_panel.devices:
                if isinstance(device, DoorLock):
                    entities.append(VivintLockEntity(device=device, hub=hub))

    if not entities:
        return

    async_add_entities(entities)


class VivintLockEntity(VivintEntity, LockEntity):
    """Vivint Lock."""

    device: DoorLock

    @property
    def is_locked(self) -> bool:
        """Return true if the lock is locked."""
        return self.device.is_locked

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self.device.alarm_panel.id}-{self.device.id}"

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        await self.device.lock()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        await self.device.unlock()
