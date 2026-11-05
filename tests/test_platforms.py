"""Smoke tests for the Vivint platforms."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.vivint import PLATFORMS
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration

EXPECTED_UNIQUE_IDS = {
    Platform.ALARM_CONTROL_PANEL: {"1"},
    Platform.BINARY_SENSOR: {
        "1-20",
        "1-20-bypassed",
        "1-20-tampered",
        "1-30-bypassed",
        "1-30-online",
        "1-30-tampered",
        "1-40-online",
        "1-50-online",
        "1-51-online",
        "1-70",
        "1-70-online",
    },
    Platform.BUTTON: {"1-reboot", "1-70-reboot"},
    Platform.CAMERA: {"1-70"},
    Platform.CLIMATE: {"1-60"},
    Platform.COVER: {"1-40"},
    Platform.EVENT: {"1-70-doorbell", "1-70-motion"},
    Platform.LIGHT: {"1-51"},
    Platform.LOCK: {"1-30"},
    Platform.SENSOR: {"1-20", "1-30"},
    Platform.SWITCH: {
        "1-50-is_on",
        "1-70-chime_extender",
        "1-70-deter_mode",
        "1-70-privacy_mode",
    },
    Platform.UPDATE: {"1-firmware"},
}


def test_all_platforms_covered() -> None:
    """Test a new platform can't be added without a smoke test."""
    assert set(EXPECTED_UNIQUE_IDS) == set(PLATFORMS)


@pytest.mark.parametrize("platform", PLATFORMS)
async def test_entities_created(
    hass: HomeAssistant, mock_api: MagicMock, platform: Platform
) -> None:
    """Test a platform creates its entities and they have a state."""
    entry = await setup_integration(hass, [platform])

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)

    assert {entity.unique_id for entity in entities} == EXPECTED_UNIQUE_IDS[platform]
    for entity in entities:
        assert entity.domain == platform
        assert hass.states.get(entity.entity_id) is not None, entity.entity_id


@pytest.mark.xfail(
    strict=True,
    reason="Platforms fail if they run before the panel device is registered",
)
async def test_entities_created_before_panel_device(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """Test a platform doesn't depend on another having registered the panel.

    Platforms are set up concurrently, so on the first setup the order isn't fixed.
    """
    entry = await setup_integration(hass, [Platform.LIGHT], register_panel=False)

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert {entity.unique_id for entity in entities} == {"1-51"}
