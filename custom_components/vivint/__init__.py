"""The Vivint integration."""

import logging
import os

from aiohttp import ClientResponseError
from aiohttp.client_exceptions import ClientConnectorError
from vivintpy.devices import VivintDevice
from vivintpy.devices.alarm_panel import DEVICE_DELETED, DEVICE_DISCOVERED
from vivintpy.devices.camera import DOORBELL_DING, MOTION_DETECTED, Camera
from vivintpy.devices.wireless_sensor import WirelessSensor
from vivintpy.enums import CapabilityCategoryType
from vivintpy.exceptions import (
    VivintSkyApiAuthenticationError,
    VivintSkyApiError,
    VivintSkyApiMfaRequiredError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    ATTR_DOMAIN,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_REFRESH_TOKEN, DOMAIN, EVENT_TYPE
from .hub import VivintHub, get_device_id

type VivintConfigEntry = ConfigEntry[VivintHub]


_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

ATTR_TYPE = "type"


async def async_setup_entry(hass: HomeAssistant, entry: VivintConfigEntry) -> bool:
    """Set up Vivint from a config entry."""
    undo_listener = entry.add_update_listener(update_listener)

    hub = VivintHub(hass, entry.data, undo_listener)
    entry.runtime_data = hub

    try:
        await hub.login(load_devices=True, subscribe_for_realtime_updates=True)
    except (VivintSkyApiMfaRequiredError, VivintSkyApiAuthenticationError) as ex:
        raise ConfigEntryAuthFailed(ex) from ex
    except (VivintSkyApiError, ClientResponseError, ClientConnectorError) as ex:
        raise ConfigEntryNotReady(ex) from ex

    dev_reg = device_registry.async_get(hass)

    @callback
    def async_on_device_discovered(device: VivintDevice) -> None:
        if getattr(device, "battery_level", None) is not None:
            async_dispatcher_send(hass, f"{DOMAIN}_{entry.entry_id}_add_sensor", device)
        if isinstance(device, WirelessSensor):
            async_dispatcher_send(
                hass, f"{DOMAIN}_{entry.entry_id}_add_binary_sensor", device
            )

    @callback
    def async_on_device_deleted(device: VivintDevice) -> None:
        _LOGGER.debug("Device deleted: %s", device)
        device = dev_reg.async_get_device({get_device_id(device)})
        if device:
            dev_reg.async_remove_device(device.id)

    @callback
    def async_on_device_event(event_type: str, viv_device: VivintDevice) -> None:
        """Relay Vivint device event to hass."""
        device = dev_reg.async_get_device({get_device_id(viv_device)})
        hass.bus.async_fire(
            EVENT_TYPE,
            {
                ATTR_TYPE: event_type,
                ATTR_DOMAIN: DOMAIN,
                ATTR_DEVICE_ID: device.id,
            },
        )

    for system in hub.account.systems:
        for alarm_panel in system.alarm_panels:
            entry.async_on_unload(
                alarm_panel.on(
                    DEVICE_DISCOVERED,
                    lambda event: async_on_device_discovered(event["device"]),
                )
            )
            entry.async_on_unload(
                alarm_panel.on(
                    DEVICE_DELETED,
                    lambda event: async_on_device_deleted(event["device"]),
                )
            )
            for device in alarm_panel.get_devices([Camera]):
                entry.async_on_unload(
                    device.on(
                        MOTION_DETECTED,
                        lambda event: async_on_device_event(
                            MOTION_DETECTED, event["device"]
                        ),
                    )
                )
                if CapabilityCategoryType.DOORBELL in device.capabilities:
                    entry.async_on_unload(
                        device.on(
                            DOORBELL_DING,
                            lambda event: async_on_device_event(
                                DOORBELL_DING, event["device"]
                            ),
                        )
                    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Check for devices that no longer exist and remove them
    stored_devices = device_registry.async_entries_for_config_entry(
        dev_reg, entry.entry_id
    )
    alarm_panels = [
        alarm_panel
        for system in hub.account.systems
        for alarm_panel in system.alarm_panels
    ]
    all_devices = alarm_panels + [
        device for alarm_panel in alarm_panels for device in alarm_panel.devices
    ]
    known_devices = [
        dev_reg.async_get_device({get_device_id(device)}) for device in all_devices
    ]

    # Devices that are in the device registry that are not known by the hub can be removed
    for device in stored_devices:
        if device not in known_devices:
            dev_reg.async_remove_device(device.id)

    @callback
    async def _async_save_tokens(ev: Event) -> None:
        """Save tokens to the config entry data."""
        await entry.runtime_data.disconnect()
        hass.config_entries.async_update_entry(
            entry, data=entry.data | {CONF_REFRESH_TOKEN: hub.account.refresh_token}
        )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_save_tokens)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: VivintConfigEntry) -> bool:
    """Unload config entry."""
    await entry.runtime_data.disconnect()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: VivintConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s", entry.version, entry.minor_version
    )

    if entry.version > 1:
        # This means the user has downgraded from a future version
        return False

    if entry.version == 1:
        if entry.minor_version < 2:
            for filename in (".vivintpy_cache.pickle", ".vivintpy_cache_1.pickle"):
                try:
                    os.remove(hass.config.path(filename))
                except Exception:  # noqa: BLE001,S110
                    pass

            hass.config_entries.async_update_entry(entry, minor_version=2)

    _LOGGER.debug(
        "Migration to version %s.%s successful",
        entry.version,
        entry.minor_version,
    )

    return True


async def update_listener(hass: HomeAssistant, entry: VivintConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
