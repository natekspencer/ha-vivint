"""Config flow for Vivint integration."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientResponseError
from aiohttp.client_exceptions import ClientConnectorError
from vivintpy.exceptions import (
    VivintSkyApiAuthenticationError,
    VivintSkyApiError,
    VivintSkyApiMfaRequiredError,
)
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
    SchemaOptionsFlowHandler,
)
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_DISARM_CODE,
    CONF_HD_STREAM,
    CONF_MFA,
    CONF_REFRESH_TOKEN,
    CONF_RTSP_STREAM,
    CONF_RTSP_URL_LOGGING,
    DEFAULT_HD_STREAM,
    DEFAULT_RTSP_STREAM,
    DEFAULT_RTSP_URL_LOGGING,
    DOMAIN,
    RTSP_STREAM_TYPES,
)
from .hub import VivintHub

_LOGGER = logging.getLogger(__name__)


async def _validate_options(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Validate options config."""
    try:
        cv.matches_regex("^[0-9]*$")(user_input[CONF_DISARM_CODE])
    except vol.Invalid as exc:
        raise SchemaFlowError("disarm_code_invalid") from exc

    return user_input


STEP_USER_DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)
STEP_MFA_DATA_SCHEMA = vol.Schema({vol.Required(CONF_MFA): str})
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DISARM_CODE, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_HD_STREAM, default=DEFAULT_HD_STREAM): bool,
        vol.Optional(CONF_RTSP_STREAM, default=DEFAULT_RTSP_STREAM): vol.In(
            RTSP_STREAM_TYPES
        ),
        vol.Optional(CONF_RTSP_URL_LOGGING, default=DEFAULT_RTSP_URL_LOGGING): bool,
    }
)
OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(OPTIONS_SCHEMA, validate_user_input=_validate_options)
}


class VivintConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vivint."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize a config flow."""
        self._hub: VivintHub = None

    async def _async_create_entry(self) -> FlowResult:
        """Create the config entry."""
        existing_entry = await self.async_set_unique_id(DOMAIN)

        # pylint: disable=protected-access
        config_data = {
            CONF_USERNAME: self._hub._data[CONF_USERNAME],
            CONF_PASSWORD: self._hub._data[CONF_PASSWORD],
            CONF_REFRESH_TOKEN: self._hub.account.refresh_token,
        }

        await self._hub.disconnect()
        if existing_entry:
            self.hass.config_entries.async_update_entry(
                existing_entry, data=config_data
            )
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(
            title=config_data[CONF_USERNAME], data=config_data
        )

    async def async_vivint_login(
        self, step_id, user_input: dict[str, Any] | None, schema: vol.Schema
    ) -> FlowResult:
        """Attempt a login with Vivint."""
        errors = {}

        self._hub = VivintHub(self.hass, user_input)
        try:
            await self._hub.login(load_devices=True)
        except VivintSkyApiMfaRequiredError:
            return await self.async_step_mfa()
        except VivintSkyApiAuthenticationError:
            errors["base"] = "invalid_auth"
        except (VivintSkyApiError, ClientResponseError, ClientConnectorError):
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        if not errors:
            return await self._async_create_entry()

        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            for entry in self._async_current_entries():
                if entry.data[CONF_USERNAME] == user_input[CONF_USERNAME]:
                    return self.async_abort(reason="already_configured")

            return await self.async_vivint_login(
                step_id="user", user_input=user_input, schema=STEP_USER_DATA_SCHEMA
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_mfa(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a multi-factor authentication (MFA) flow."""
        await super().async_step_user()
        if user_input is None:
            return self.async_show_form(step_id="mfa", data_schema=STEP_MFA_DATA_SCHEMA)

        try:
            await self._hub.verify_mfa(user_input[CONF_MFA])
        except VivintSkyApiAuthenticationError as err:  # pylint: disable=broad-except
            _LOGGER.error(err)
            return self.async_show_form(
                step_id="mfa",
                data_schema=STEP_MFA_DATA_SCHEMA,
                errors={"base": str(err)},
            )
        except Exception as ex:  # pylint: disable=broad-except # noqa: BLE001
            _LOGGER.error(ex)
            return self.async_show_form(
                step_id="mfa",
                data_schema=STEP_MFA_DATA_SCHEMA,
                errors={"base": "unknown"},
            )

        return await self._async_create_entry()

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm", data_schema=STEP_USER_DATA_SCHEMA
            )

        return await self.async_vivint_login(
            step_id="reauth_confirm",
            user_input=user_input,
            schema=STEP_USER_DATA_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> SchemaOptionsFlowHandler:
        """Get the options flow for this handler."""
        return SchemaOptionsFlowHandler(entry, OPTIONS_FLOW)
