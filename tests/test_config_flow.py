"""Tests for the Vivint config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientResponseError
from aiohttp.client_exceptions import ClientConnectorError
import pytest
from vivintpy.exceptions import (
    VivintSkyApiAuthenticationError,
    VivintSkyApiError,
    VivintSkyApiMfaRequiredError,
)

from custom_components.vivint.const import (
    CONF_DISARM_CODE,
    CONF_HD_STREAM,
    CONF_MFA,
    CONF_REFRESH_TOKEN,
    CONF_RTSP_STREAM,
    CONF_RTSP_URL_LOGGING,
    DOMAIN,
    RTSP_STREAM_EXTERNAL,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType

from . import PASSWORD, REFRESH_TOKEN, USERNAME, MockConfigEntry, create_entry

USER_INPUT = {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD}
ENTRY_DATA = {CONF_USERNAME: USERNAME, CONF_REFRESH_TOKEN: REFRESH_TOKEN}

LOGIN_ERRORS = [
    (VivintSkyApiAuthenticationError("Rejected"), "invalid_auth"),
    (VivintSkyApiError("Unavailable"), "cannot_connect"),
    (ClientResponseError(MagicMock(), (), status=500), "cannot_connect"),
    (ClientConnectorError(MagicMock(), OSError("Failed")), "cannot_connect"),
    (ValueError("Unexpected"), "unknown"),
]


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Stop a completed flow from setting up the integration."""
    with patch(
        "custom_components.vivint.async_setup_entry", return_value=True
    ) as setup_entry:
        yield setup_entry


async def start_user_flow(hass: HomeAssistant) -> FlowResult:
    """Start a config flow from the user step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_user_flow(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Test a successful login creates an entry and closes the connection."""
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == USERNAME
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == DOMAIN
    mock_api.disconnect.assert_awaited_once_with()


@pytest.mark.parametrize(("error", "expected"), LOGIN_ERRORS)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_api: MagicMock,
    mock_setup_entry: AsyncMock,
    error: Exception,
    expected: str,
) -> None:
    """Test a failed login shows its error, and the form can be submitted again."""
    result = await start_user_flow(hass)
    connect = mock_api.connect.side_effect

    mock_api.connect.side_effect = error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": expected}

    mock_api.connect.side_effect = connect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """Test the same account can't be added twice."""
    create_entry(hass)
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_api.connect.assert_not_awaited()


@pytest.mark.xfail(
    strict=True, reason="A new account replaces the existing entry's credentials"
)
async def test_user_flow_different_account(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Test adding a different account leaves the existing entry unchanged."""
    entry = create_entry(hass)
    result = await start_user_flow(hass)

    await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT | {CONF_USERNAME: "other@example.com"}
    )

    assert entry.data[CONF_USERNAME] == USERNAME


async def start_mfa_flow(hass: HomeAssistant, mock_api: MagicMock) -> FlowResult:
    """Start a config flow and reach the MFA step."""
    result = await start_user_flow(hass)
    mock_api.connect.side_effect = VivintSkyApiMfaRequiredError("MFA required")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mfa"
    return result


async def test_mfa_flow(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Test a login that requires MFA creates an entry once the code is verified."""
    result = await start_mfa_flow(hass, mock_api)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MFA: "123456"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    mock_api.verify_mfa.assert_awaited_once_with("123456")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (VivintSkyApiAuthenticationError("Incorrect code"), "Incorrect code"),
        (ValueError("Unexpected"), "unknown"),
    ],
)
async def test_mfa_flow_errors(
    hass: HomeAssistant,
    mock_api: MagicMock,
    mock_setup_entry: AsyncMock,
    error: Exception,
    expected: str,
) -> None:
    """Test a rejected MFA code shows its error, and can be entered again."""
    result = await start_mfa_flow(hass, mock_api)

    mock_api.verify_mfa.side_effect = error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MFA: "000000"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mfa"
    assert result["errors"] == {"base": expected}

    mock_api.verify_mfa.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MFA: "123456"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def start_reauth_flow(hass: HomeAssistant, entry: MockConfigEntry) -> FlowResult:
    """Start reauthentication, which always asks for the password."""
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] is None
    return result


async def test_reauth_flow(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test the password entered for reauthentication is used, and not saved."""
    entry = create_entry(hass, data=ENTRY_DATA)
    result = await start_reauth_flow(hass, entry)
    mock_api.connect.assert_not_awaited()

    schema = result["data_schema"].schema
    username = next(key for key in schema if key == CONF_USERNAME)
    assert username.description == {"suggested_value": USERNAME}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_api.connect.await_args_list[0].args == (PASSWORD,)
    assert entry.data == ENTRY_DATA
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(("error", "expected"), LOGIN_ERRORS)
async def test_reauth_flow_errors(
    hass: HomeAssistant, mock_api: MagicMock, error: Exception, expected: str
) -> None:
    """Test a failed login can be tried again."""
    entry = create_entry(hass)
    connect = mock_api.connect.side_effect
    result = await start_reauth_flow(hass, entry)

    mock_api.connect.side_effect = error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": expected}

    mock_api.connect.side_effect = connect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert CONF_PASSWORD not in entry.data
    assert entry.state is ConfigEntryState.LOADED


async def test_reauth_flow_with_mfa(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test reauthenticating an account that requires MFA."""
    entry = create_entry(hass)
    connect = mock_api.connect.side_effect
    result = await start_reauth_flow(hass, entry)

    mock_api.connect.side_effect = VivintSkyApiMfaRequiredError("MFA required")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mfa"

    mock_api.connect.side_effect = connect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MFA: "123456"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    mock_api.verify_mfa.assert_awaited_once_with("123456")
    assert entry.state is ConfigEntryState.LOADED


async def test_options_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test options are validated, saved and reload the entry."""
    hub = init_integration.runtime_data
    options = {
        CONF_DISARM_CODE: "1234",
        CONF_HD_STREAM: False,
        CONF_RTSP_STREAM: RTSP_STREAM_EXTERNAL,
        CONF_RTSP_URL_LOGGING: False,
    }

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options | {CONF_DISARM_CODE: "abcd"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "disarm_code_invalid"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == options
    assert init_integration.state is ConfigEntryState.LOADED
    assert init_integration.runtime_data is not hub
