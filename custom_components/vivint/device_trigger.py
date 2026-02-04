"""Provides device triggers for Vivint."""

from __future__ import annotations

from typing import Any

from vivintpy.devices import VivintDevice
from vivintpy.devices.camera import DOORBELL_DING, MOTION_DETECTED, Camera
from vivintpy.enums import CapabilityCategoryType
import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from . import VivintConfigEntry
from .const import DOMAIN, EVENT_TYPE
from .hub import VivintHub

TRIGGER_TYPES = {MOTION_DETECTED, DOORBELL_DING}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_vivint_device(
    hass: HomeAssistant, device_id: str
) -> VivintDevice | None:
    """Get a Vivint device for the given device registry id."""
    dev_reg = dr.async_get(hass)
    if not (device_entry := dev_reg.async_get(device_id)):
        raise ValueError(f"Device ID {device_id} is not valid")

    identifiers = device_entry.identifiers
    if not (identifier := next((id[1] for id in identifiers if id[0] == DOMAIN), None)):
        return None

    [panel_id, vivint_device_id] = [int(item) for item in identifier.split("-")]
    for config_entry_id in device_entry.config_entries:
        config_entry: VivintConfigEntry | None
        if not (config_entry := hass.config_entries.async_get_entry(config_entry_id)):
            continue

        hub: VivintHub = config_entry.runtime_data
        for system in hub.account.systems:
            if system.id != panel_id:
                continue
            for alarm_panel in system.alarm_panels:
                for device in alarm_panel.devices:
                    if device.id == vivint_device_id:
                        return device
    return None


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device triggers for Vivint devices."""
    device = await async_get_vivint_device(hass, device_id)

    triggers = []

    if device and isinstance(device, Camera):
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: MOTION_DETECTED,
            }
        )
        if CapabilityCategoryType.DOORBELL in device.capabilities:
            triggers.append(
                {
                    CONF_PLATFORM: "device",
                    CONF_DOMAIN: DOMAIN,
                    CONF_DEVICE_ID: device_id,
                    CONF_TYPE: DOORBELL_DING,
                }
            )

    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    automation_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: EVENT_TYPE,
            event_trigger.CONF_EVENT_DATA: {
                CONF_DEVICE_ID: config[CONF_DEVICE_ID],
                CONF_TYPE: config[CONF_TYPE],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, automation_info, platform_type="device"
    )
