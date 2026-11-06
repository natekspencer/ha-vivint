"""Tests for the Vivint integration setup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from aiohttp import ClientResponseError
from aiohttp.client_exceptions import ClientConnectorError
import pytest
from vivintpy.account import Account
from vivintpy.devices.camera import MOTION_DETECTED, Camera
from vivintpy.exceptions import (
    VivintSkyApiAuthenticationError,
    VivintSkyApiError,
    VivintSkyApiMfaRequiredError,
)

from custom_components.vivint.const import (
    CONF_HD_STREAM,
    CONF_REFRESH_TOKEN,
    CONF_RTSP_STREAM,
    DOMAIN,
    EVENT_TYPE,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from . import (
    PASSWORD,
    REFRESH_TOKEN,
    USERNAME,
    MockConfigEntry,
    create_entry,
    setup_integration,
)


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_api: MagicMock,
    mock_pubnub: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test setting up and unloading closes every connection."""
    hub = init_integration.runtime_data
    assert init_integration.state is ConfigEntryState.LOADED
    mock_pubnub.subscribe.assert_called_once_with()

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    mock_pubnub.stop.assert_awaited_once_with()
    mock_api.disconnect.assert_awaited_once_with()
    assert hub.session.closed


async def test_unload_removes_stop_listener(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """Test each unload removes the listener added by its setup."""
    entry = await setup_integration(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    listeners = hass.bus.async_listeners()[EVENT_HOMEASSISTANT_STOP]

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.bus.async_listeners()[EVENT_HOMEASSISTANT_STOP] == listeners


@pytest.mark.parametrize(
    "error",
    [
        VivintSkyApiAuthenticationError("Rejected"),
        VivintSkyApiMfaRequiredError("MFA required"),
    ],
)
async def test_setup_starts_reauth(
    hass: HomeAssistant, mock_api: MagicMock, error: Exception
) -> None:
    """Test authentication failures ask the user to reauthenticate."""
    mock_api.connect.side_effect = error
    entry = create_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH


@pytest.mark.parametrize(
    "error",
    [
        VivintSkyApiError("Unavailable"),
        ClientResponseError(MagicMock(), (), status=500),
        ClientConnectorError(MagicMock(), OSError("Connection failed")),
    ],
)
async def test_setup_retries_on_connection_error(
    hass: HomeAssistant, mock_api: MagicMock, error: Exception
) -> None:
    """Test connection failures retry the setup later."""
    mock_api.connect.side_effect = error
    entry = create_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_removes_stale_devices(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test devices no longer on the account are removed on setup."""
    entry = create_entry(hass)
    device_registry = dr.async_get(hass)
    stale = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "1-999")}
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert device_registry.async_get(stale.id) is None
    assert dr.async_entries_for_config_entry(device_registry, entry.entry_id)


async def test_camera_motion_fires_event(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test camera motion is relayed to the event bus for device triggers."""
    events: list[Event] = []

    @callback
    def capture(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_TYPE, capture)
    (system,) = init_integration.runtime_data.account.systems
    (camera,) = system.alarm_panels[0].get_devices([Camera])

    camera.emit(MOTION_DETECTED, {})
    await hass.async_block_till_done()

    (event,) = events
    device = dr.async_get(hass).async_get(event.data[ATTR_DEVICE_ID])
    assert device is not None
    assert device.name == camera.name


async def test_migrates_rtsp_stream_option(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """Test old entries move to the current version and stream option values."""
    entry = create_entry(hass, minor_version=1, options={CONF_RTSP_STREAM: "1"})

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 4
    assert entry.options[CONF_RTSP_STREAM] == "internal"


async def test_future_version_fails_migration(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """Test entries from a newer version of the integration aren't set up."""
    entry = create_entry(hass, version=2)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_migration_removes_the_password(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """Test a saved password is removed and the refresh token is used to log in."""
    entry = create_entry(
        hass,
        minor_version=3,
        data={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_REFRESH_TOKEN: REFRESH_TOKEN,
        },
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 4
    assert entry.data == {CONF_USERNAME: USERNAME, CONF_REFRESH_TOKEN: REFRESH_TOKEN}
    mock_api.connect.assert_awaited_once_with(None)


async def test_new_refresh_token_is_saved_without_reloading(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """Test a rotated token is saved right away and doesn't cause a reload."""
    with patch("custom_components.vivint.hub.Account", wraps=Account) as account_cls:
        entry = await setup_integration(hass)
    save_token = account_cls.call_args.kwargs["on_refresh_token_changed"]

    save_token("new-token")
    await hass.async_block_till_done()

    assert entry.data[CONF_REFRESH_TOKEN] == "new-token"
    assert entry.state is ConfigEntryState.LOADED
    mock_api.connect.assert_awaited_once()


async def test_new_options_reload(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test changing the options reloads the integration."""
    entry = await setup_integration(hass)

    hass.config_entries.async_update_entry(entry, options={CONF_HD_STREAM: False})
    await hass.async_block_till_done()

    assert mock_api.connect.await_count == 2
    assert entry.state is ConfigEntryState.LOADED


async def test_rejected_token_during_an_update_starts_reauth(
    hass: HomeAssistant, mock_api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the user is asked to log in when a running session can't be renewed."""
    mock_api.get_authuser_data.side_effect = VivintSkyApiAuthenticationError("Rejected")

    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == "reauth"
    assert flow["step_id"] == "reauth_confirm"
