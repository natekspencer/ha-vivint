"""Fixtures for Vivint tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
import copy
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from vivintpy.enums import (
    CapabilityCategoryType as Category,
    CapabilityType as Capability,
    DeviceType,
    EquipmentCode,
    EquipmentType,
    FeatureType,
    SensorType,
)

from homeassistant.core import EventBus, HomeAssistant

from . import PANEL_ID, REFRESH_TOKEN, MockConfigEntry, setup_integration

PANEL_DEVICE_ID = 10
SENSOR_ID = 20
LOCK_ID = 30
GARAGE_DOOR_ID = 40
SWITCH_ID = 50
DIMMER_ID = 51
THERMOSTAT_ID = 60
CAMERA_ID = 70

AUTH_USER: dict[str, Any] = {
    "u": {
        "_id": "user-id",
        "mbc": "broadcast-channel",
        "system": [{"panid": PANEL_ID, "sn": "Home", "ad": True}],
    }
}

SYSTEM: dict[str, Any] = {
    "system": {
        "panid": PANEL_ID,
        "u": [],
        "par": [
            {
                "panid": PANEL_ID,
                "parid": 1,
                "pmac": "00:11:22:33:44:55",
                "s": 0,
                "d": [
                    {
                        "_id": PANEL_DEVICE_ID,
                        "panid": PANEL_ID,
                        "t": DeviceType.PANEL.value,
                        "n": "Panel",
                        "pant": 1,
                        "csv": "1.0.0",
                        "sus": "Idle",
                        "can_reboot": True,
                    },
                    {
                        "_id": SENSOR_ID,
                        "panid": PANEL_ID,
                        "t": DeviceType.WIRELESS_SENSOR.value,
                        "n": "Front Door",
                        "ser": 1001,
                        "ec": EquipmentCode.DW11_THIN_DOOR_WINDOW.value,
                        "eqt": EquipmentType.CONTACT.value,
                        "set": SensorType.EXIT_ENTRY_1.value,
                        "s": False,
                        "b": 0,
                        "ta": False,
                        "bl": 90,
                    },
                    {
                        "_id": LOCK_ID,
                        "panid": PANEL_ID,
                        "t": DeviceType.DOOR_LOCK.value,
                        "n": "Front Lock",
                        "s": True,
                        "ol": True,
                        "b": 0,
                        "ta": False,
                        "bl": 80,
                    },
                    {
                        "_id": GARAGE_DOOR_ID,
                        "panid": PANEL_ID,
                        "t": DeviceType.GARAGE_DOOR.value,
                        "n": "Garage",
                        "s": 1,
                        "ol": True,
                    },
                    {
                        "_id": SWITCH_ID,
                        "panid": PANEL_ID,
                        "t": DeviceType.BINARY_SWITCH.value,
                        "n": "Outlet",
                        "s": False,
                        "val": 0,
                        "ol": True,
                    },
                    {
                        "_id": DIMMER_ID,
                        "panid": PANEL_ID,
                        "t": DeviceType.MULTI_LEVEL_SWITCH.value,
                        "n": "Dimmer",
                        "s": True,
                        "val": 50,
                        "ol": True,
                    },
                    {
                        "_id": THERMOSTAT_ID,
                        "panid": PANEL_ID,
                        "t": DeviceType.THERMOSTAT.value,
                        "n": "Hallway",
                        "val": 21.0,
                        "hmdt": 40,
                        "csp": 24.0,
                        "hsp": 19.0,
                        "maxt": 30.0,
                        "mint": 10.0,
                        "fm": 0,
                        "om": 3,
                        "os": 0,
                        "caca": [
                            {
                                "t": Category.THERMOSTAT.value,
                                "ca": [Capability.FAN15_MINUTE.value],
                            }
                        ],
                    },
                    {
                        "_id": CAMERA_ID,
                        "panid": PANEL_ID,
                        "t": DeviceType.CAMERA.value,
                        "act": "vivint_dbc350_camera_device",
                        "n": "Doorbell",
                        "cmac": "aa:bb:cc:dd:ee:ff",
                        "sv": "2.0.0",
                        "ol": True,
                        "cex": False,
                        "cpri": False,
                        "deter_on_duty": False,
                        "fea": {FeatureType.DETER.value: True},
                        "caca": [
                            {
                                "t": Category.CAMERA.value,
                                "ca": [
                                    Capability.CHIME_EXTENDER.value,
                                    Capability.PRIVACY_MODE.value,
                                    Capability.REBOOT_CAMERA.value,
                                ],
                            },
                            {"t": Category.DOORBELL.value, "ca": []},
                        ],
                    },
                ],
            }
        ],
    }
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


@pytest.fixture(autouse=True)
async def remove_stop_listener(hass: HomeAssistant) -> AsyncGenerator[None]:
    """Remove the stop listeners that async_setup_entry leaves behind.

    The hass fixture unloads entries before stopping, and the listeners then fail
    because the entry has no runtime data. Delete this once they are removed on
    unload, see test_unload_removes_stop_listener.
    """
    listen_once = EventBus.async_listen_once
    removers = []

    def tracking_listen_once(bus: EventBus, event_type: Any, listener: Any) -> Any:
        remove = listen_once(bus, event_type, listener)
        if listener.__name__ == "_async_save_tokens":
            removers.append(remove)
        return remove

    with patch.object(EventBus, "async_listen_once", tracking_listen_once):
        yield

    for remove in removers:
        remove()


@pytest.fixture
def mock_pubnub() -> Generator[MagicMock]:
    """Mock the PubNub client used for realtime updates."""
    with patch("vivintpy.account.PubNubAsyncio", autospec=True) as pubnub_cls:
        yield pubnub_cls.return_value


@pytest.fixture
def mock_api(mock_pubnub: MagicMock) -> Generator[MagicMock]:
    """Mock the Vivint API client, keeping the real account and device classes."""
    with patch("vivintpy.account.VivintSkyApi", autospec=True) as api_cls:
        api = api_cls.return_value
        api.tokens = {"refresh_token": REFRESH_TOKEN}
        api.connect.side_effect = lambda: copy.deepcopy(AUTH_USER)
        api.get_authuser_data.side_effect = lambda: copy.deepcopy(AUTH_USER)
        api.get_system_data.side_effect = lambda _: copy.deepcopy(SYSTEM)
        api.get_system_update.return_value = {}
        yield api


@pytest.fixture
async def init_integration(hass: HomeAssistant, mock_api: MagicMock) -> MockConfigEntry:
    """Set up the Vivint integration with all platforms."""
    return await setup_integration(hass)
