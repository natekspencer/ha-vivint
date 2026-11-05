"""Support for Vivint switches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from vivintpy.devices.camera import Camera
from vivintpy.devices.switch import BinarySwitch
from vivintpy.enums import (
    CapabilityCategoryType as Category,
    CapabilityType as Capability,
    FeatureType as Feature,
)

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VivintConfigEntry
from .hub import VivintBaseEntity, VivintHub, has_capability, has_feature


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vivint switches using config entry."""
    entities = []
    hub: VivintHub = entry.runtime_data

    for system in hub.account.systems:
        for alarm_panel in system.alarm_panels:
            for device in alarm_panel.devices:
                if isinstance(device, BinarySwitch):
                    entities.append(
                        VivintSwitchEntity(
                            device=device, hub=hub, entity_description=IS_ON
                        )
                    )
                if has_capability(device, Category.CAMERA, Capability.CHIME_EXTENDER):
                    entities.append(
                        VivintSwitchEntity(
                            device=device,
                            hub=hub,
                            entity_description=CAMERA_CHIME_EXTENDER,
                        )
                    )
                if has_capability(device, Category.CAMERA, Capability.PRIVACY_MODE):
                    entities.append(
                        VivintSwitchEntity(
                            device=device, hub=hub, entity_description=PRIVACY_MODE
                        )
                    )
                if has_feature(device, Feature.DETER):
                    entities.append(
                        VivintSwitchEntity(
                            device=device, hub=hub, entity_description=DETER_MODE
                        )
                    )

    if not entities:
        return

    async_add_entities(entities)


@dataclass
class VivintSwitchMixin:
    """Vivint switch required keys."""

    is_on: Callable[[BinarySwitch | Camera], bool | None]
    turn_on: Callable[[BinarySwitch | Camera], bool | None]
    turn_off: Callable[[BinarySwitch | Camera], bool | None]


@dataclass
class VivintSwitchEntityDescription(SwitchEntityDescription, VivintSwitchMixin):
    """Vivint binary sensor entity description."""


IS_ON = VivintSwitchEntityDescription(
    key="is_on",
    is_on=lambda device: device.is_on,
    turn_on=lambda device: device.turn_on(),
    turn_off=lambda device: device.turn_off(),
)
CAMERA_CHIME_EXTENDER = VivintSwitchEntityDescription(
    key="chime_extender",
    entity_category=EntityCategory.CONFIG,
    name="Chime extender",
    is_on=lambda device: device.extend_chime_enabled,
    turn_on=lambda device: device.set_as_doorbell_chime_extender(True),
    turn_off=lambda device: device.set_as_doorbell_chime_extender(False),
)
PRIVACY_MODE = VivintSwitchEntityDescription(
    key="privacy_mode",
    entity_category=EntityCategory.CONFIG,
    name="Privacy mode",
    is_on=lambda device: device.is_in_privacy_mode,
    turn_on=lambda device: device.set_privacy_mode(True),
    turn_off=lambda device: device.set_privacy_mode(False),
)
DETER_MODE = VivintSwitchEntityDescription(
    key="deter_mode",
    entity_category=EntityCategory.CONFIG,
    name="Deter Mode",
    is_on=lambda device: device.is_in_deter_mode,
    turn_on=lambda device: device.set_deter_mode(True),
    turn_off=lambda device: device.set_deter_mode(False),
)


class VivintSwitchEntity(VivintBaseEntity, SwitchEntity):
    """Vivint Switch."""

    device: BinarySwitch | Camera
    entity_description: VivintSwitchEntityDescription

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        return self.entity_description.is_on(self.device)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.entity_description.turn_on(self.device)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.entity_description.turn_off(self.device)
