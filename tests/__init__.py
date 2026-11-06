"""Tests for the Vivint integration."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.vivint import PLATFORMS
from custom_components.vivint.const import CONF_REFRESH_TOKEN, DOMAIN
from homeassistant.const import CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

try:
    from pytest_homeassistant.common import MockConfigEntry
except ImportError:  # Home Assistant < 2026.11
    from pytest_homeassistant_custom_component.common import MockConfigEntry

USERNAME = "user@example.com"
PASSWORD = "password"
REFRESH_TOKEN = "refresh-token"
PANEL_ID = 1


def create_entry(
    hass: HomeAssistant, *, register_panel: bool = True, **kwargs
) -> MockConfigEntry:
    """Add a Vivint config entry to Home Assistant.

    The panel device is registered by default, as it is after the first setup.
    Entities need it to exist, see test_entities_created_before_panel_device.
    """
    entry = MockConfigEntry(
        **{
            "domain": DOMAIN,
            "unique_id": DOMAIN,
            "title": USERNAME,
            "version": 1,
            "minor_version": 4,
            "data": {CONF_USERNAME: USERNAME, CONF_REFRESH_TOKEN: REFRESH_TOKEN},
            **kwargs,
        }
    )
    entry.add_to_hass(hass)
    if register_panel:
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{PANEL_ID}-{PANEL_ID}")},
        )
    return entry


async def setup_integration(
    hass: HomeAssistant, platforms: list[Platform] = PLATFORMS, **kwargs
) -> MockConfigEntry:
    """Set up the Vivint integration with only the given platforms."""
    entry = create_entry(hass, **kwargs)

    with patch("custom_components.vivint.PLATFORMS", platforms):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry
