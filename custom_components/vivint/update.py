"""Support for Vivint updates."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from vivintpy.devices.alarm_panel import AlarmPanel
from vivintpy.entity import UPDATE

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature as Feature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VivintConfigEntry
from .hub import VivintBaseEntity, VivintHub

SCAN_INTERVAL = timedelta(days=1)

FIRMWARE_UPDATE_ENTITY = UpdateEntityDescription(
    key="firmware", name="Firmware", device_class=UpdateDeviceClass.FIRMWARE
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vivint update platform."""
    hub: VivintHub = entry.runtime_data
    entities = [
        VivintUpdateEntity(
            device=alarm_panel, hub=hub, entity_description=FIRMWARE_UPDATE_ENTITY
        )
        for system in hub.account.systems
        if system.is_admin
        for alarm_panel in system.alarm_panels
    ]
    async_add_entities(entities, True)


class VivintUpdateEntity(VivintBaseEntity, UpdateEntity):
    """A class that describes device update entities."""

    device: AlarmPanel

    _attr_supported_features = Feature.INSTALL | Feature.PROGRESS

    @property
    def in_progress(self) -> bool:
        """Update installation progress."""
        return self.device._AlarmPanel__panel.data["sus"] not in (
            "Idle",
            "Reboot Pending",
        )

    @property
    def installed_version(self) -> str:
        """Version installed and in use."""
        return self.device.software_version

    @property
    def should_poll(self) -> bool:
        """Set polling to True."""
        return True

    async def async_update(self) -> None:
        """Update the entity."""
        software_update = await self.device.get_software_update_details()
        if software_update.get("available"):
            latest_version = software_update["available_version"]
        else:
            latest_version = self.device.software_version
        self._attr_latest_version = latest_version

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install an update."""
        if (await self.device.get_software_update_details()).get("available"):
            if not await self.device.update_software():
                message = f"Unable to start firmware update on {self.device.name}"
                raise HomeAssistantError(message)

    async def async_added_to_hass(self) -> None:
        """Set up a listener for the entity."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.device._AlarmPanel__panel.on(
                UPDATE, lambda _: self.async_write_ha_state()
            )
        )
