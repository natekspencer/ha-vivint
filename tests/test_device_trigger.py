"""Tests for the Vivint device triggers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from vivintpy.devices.camera import DOORBELL_DING, MOTION_DETECTED

from custom_components.vivint.const import DOMAIN
from custom_components.vivint.device_trigger import async_get_triggers
from homeassistant.const import CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import PANEL_ID, MockConfigEntry
from .conftest import CAMERA_ID, LOCK_ID


def get_device_id(hass: HomeAssistant, entry: MockConfigEntry, vivint_id: int) -> str:
    """Return the device registry id of a Vivint device."""
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, f"{PANEL_ID}-{vivint_id}"), entry.entry_id
    )
    assert device is not None
    return device.id


async def test_doorbell_camera_triggers(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a doorbell camera offers the motion and ding triggers."""
    device_id = get_device_id(hass, init_integration, CAMERA_ID)

    triggers = await async_get_triggers(hass, device_id)

    assert [trigger[CONF_TYPE] for trigger in triggers] == [
        MOTION_DETECTED,
        DOORBELL_DING,
    ]


async def test_other_device_has_no_triggers(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a device that isn't a camera offers no triggers."""
    device_id = get_device_id(hass, init_integration, LOCK_ID)

    assert await async_get_triggers(hass, device_id) == []


async def test_unknown_device_raises(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test an unknown device registry id is rejected."""
    with pytest.raises(ValueError):
        await async_get_triggers(hass, "unknown")


async def test_device_shared_with_another_integration(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a device reporting another integration's entry still gets its triggers.

    A device id from before devices were split per config entry resolves to a
    composite device, whose config entry may belong to the other integration.
    """
    composite = MagicMock(
        identifiers={(DOMAIN, f"{PANEL_ID}-{CAMERA_ID}")},
        config_entry_id="other-integration",
    )

    with patch.object(dr.DeviceRegistry, "async_get", return_value=composite):
        triggers = await async_get_triggers(hass, "composite-device-id")

    assert len(triggers) == 2


async def test_unloaded_entry_has_no_triggers(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a device of an unloaded entry offers no triggers."""
    device_id = get_device_id(hass, init_integration, CAMERA_ID)

    await hass.config_entries.async_unload(init_integration.entry_id)

    assert await async_get_triggers(hass, device_id) == []
