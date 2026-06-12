"""A wrapper 'hub' for the Vivint API and base entity for common attributes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging

from aiohttp import ClientResponseError
from aiohttp.client import ClientSession
from aiohttp.client_exceptions import ClientConnectorError
from vivintpy.account import Account
from vivintpy.devices import VivintDevice
from vivintpy.devices.alarm_panel import AlarmPanel
from vivintpy.entity import UPDATE
from vivintpy.enums import (
    CapabilityCategoryType as Category,
    CapabilityType as Capability,
    FeatureType as Feature,
)
from vivintpy.exceptions import (
    VivintSkyApiAuthenticationError,
    VivintSkyApiError,
    VivintSkyApiMfaRequiredError,
)

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = 300


@callback
def get_device_id(device: VivintDevice) -> tuple[str, str]:
    """Get device registry identifier for device."""
    return (
        DOMAIN,
        f"{device.panel_id}-{device.parent.id if device.is_subdevice else device.id}",
    )


def has_capability(device: VivintDevice, category: Category, capability: Capability):
    """Check if a device has a capability."""
    if capability in (device.capabilities or {}).get(category, []):
        return True
    return False


def has_feature(device: VivintDevice, feature: Feature):
    """Check if a device has a feature."""
    return feature in (device.features or [])


class VivintHub:
    """A Vivint hub wrapper class."""

    def __init__(
        self, hass: HomeAssistant, data: dict, undo_listener: Callable | None = None
    ) -> None:
        """Initialize the Vivint hub."""
        self._data = data
        self.__undo_listener = undo_listener
        self.account: Account = None
        self.logged_in = False
        self.session = ClientSession()
        self._lock = asyncio.Lock()

        async def _async_update_data() -> None:
            """Update all device states from the Vivint API."""
            return await self.account.refresh()

        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_method=_async_update_data,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def login(
        self, load_devices: bool = False, subscribe_for_realtime_updates: bool = False
    ) -> bool:
        """Login to Vivint."""
        self.logged_in = False

        self.account = Account(
            username=self._data[CONF_USERNAME],
            password=self._data[CONF_PASSWORD],
            refresh_token=self._data.get(CONF_REFRESH_TOKEN),
            client_session=self.session,
        )
        try:
            await self.account.connect(
                load_devices=load_devices,
                subscribe_for_realtime_updates=subscribe_for_realtime_updates,
            )
            return self.save_session()
        except VivintSkyApiMfaRequiredError as ex:
            raise ex
        except VivintSkyApiAuthenticationError as ex:
            _LOGGER.error("Invalid credentials")
            raise ex
        except (VivintSkyApiError, ClientResponseError, ClientConnectorError) as ex:
            _LOGGER.error("Unable to connect to the Vivint API")
            raise ex

    async def disconnect(self) -> None:
        """Disconnect from Vivint, close the session and stop listener."""
        async with self._lock:
            if self.account.connected:
                await self.account.disconnect()
            if not self.session.closed:
                await self.session.close()
            if self.__undo_listener:
                self.__undo_listener()
                self.__undo_listener = None

    async def verify_mfa(self, code: str) -> bool:
        """Verify MFA."""
        try:
            await self.account.verify_mfa(code)
            return self.save_session()
        except Exception as ex:
            raise ex

    def save_session(self) -> bool:
        """Save session for reuse."""
        self.logged_in = True
        return self.logged_in


class VivintBaseEntity(CoordinatorEntity):
    """Generic Vivint entity representing common data and methods."""

    device: VivintDevice

    _attr_has_entity_name = True

    def __init__(
        self,
        device: VivintDevice,
        hub: VivintHub,
        entity_description: EntityDescription,
    ) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(hub.coordinator)
        self.device = device
        self.hub = hub
        self.entity_description = entity_description

        prefix = f"{device.alarm_panel.id}-" if device.alarm_panel else ""
        self._attr_unique_id = f"{prefix}{device.id}-{entity_description.key}"
        device = self.device.parent if self.device.is_subdevice else self.device
        self._attr_device_info = DeviceInfo(
            identifiers={get_device_id(device)},
            name=device.name if device.name else type(device).__name__,
            manufacturer=device.manufacturer,
            model=device.model,
            serial_number=device.serial_number,
            sw_version=device.software_version,
            via_device=(
                None
                if isinstance(device, AlarmPanel)
                else get_device_id(device.alarm_panel)
            ),
        )

    async def async_added_to_hass(self) -> None:
        """Set up a listener for the entity."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.device.on(UPDATE, lambda _: self.async_write_ha_state())
        )


class VivintEntity(CoordinatorEntity):
    """Generic Vivint entity representing common data and methods."""

    device: VivintDevice

    def __init__(self, device: VivintDevice, hub: VivintHub) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(hub.coordinator)
        self.device = device
        self.hub = hub

        device = self.device.parent if self.device.is_subdevice else self.device
        self._attr_device_info = DeviceInfo(
            identifiers={get_device_id(device)},
            name=device.name if device.name else type(device).__name__,
            manufacturer=device.manufacturer,
            model=device.model,
            serial_number=device.serial_number,
            sw_version=device.software_version,
            via_device=(
                None
                if isinstance(device, AlarmPanel)
                else get_device_id(device.alarm_panel)
            ),
        )

    async def async_added_to_hass(self) -> None:
        """Set up a listener for the entity."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.device.on(UPDATE, lambda _: self.async_write_ha_state())
        )

    @property
    def name(self) -> str:
        """Return the name of this entity."""
        return self.device.name
