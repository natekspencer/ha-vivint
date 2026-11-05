"""Test the Vivint climate platform."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vivintpy.devices.climate_thermostat import ClimateThermostat
from vivintpy.exceptions import VivintSkyApiRateLimitError
from vivintpy.proto import climate_pb2
from vivintpy.system import System

from custom_components.vivint import climate
from custom_components.vivint.const import DOMAIN
from custom_components.vivint.hub import get_device_id
from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

PANEL_ID = 4000000000000001
DEVICE_ID = "urn:vivint:google:4000000000000001:device"
Component = climate_pb2.Component


def make_device(
    mode: int = Component.OperatingModeSetting.COOL,
) -> climate_pb2.ClimateDevice:
    """Return a Nest thermostat that is cooling toward 20 °C."""
    return climate_pb2.ClimateDevice(
        id=DEVICE_ID,
        name="Hallway",
        is_online=True,
        nest_thermostat_device=climate_pb2.NestThermostatDevice(),
        components=[
            climate_pb2.Component(
                id="setpoints",
                setpoints=Component.Setpoints(
                    cool_setpoint=20.0,
                    heat_setpoint=15.5,
                    minimum_temperature=10.0,
                    maximum_temperature=32.2,
                ),
            ),
            climate_pb2.Component(
                id="temperature",
                temperature_detection=Component.TemperatureDetection(
                    current_temperature=21.5
                ),
            ),
            climate_pb2.Component(
                id="humidity",
                humidity_detection=Component.HumidityDetection(value=48),
            ),
            climate_pb2.Component(
                id="fan",
                fan_setting=Component.FanSetting(
                    modes_supported=[
                        Component.FanSetting.AUTO_LOW,
                        Component.FanSetting.SIXTY_MINUTE,
                    ],
                    current_mode=Component.FanSetting.AUTO_LOW,
                ),
            ),
            climate_pb2.Component(
                id="mode",
                operating_mode_setting=Component.OperatingModeSetting(
                    current_mode=mode
                ),
            ),
            climate_pb2.Component(
                id="state",
                operating_state=Component.OperatingState(
                    current_state=Component.OperatingState.COOLING
                ),
            ),
        ],
    )


class FakeApi:
    """Records the requests sent to the climate service."""

    def __init__(self) -> None:
        """Initialize the fake API."""
        self.requests: list[tuple[str, Any]] = []
        self.rate_limited = False

    async def climate_request(self, method: str, request: Any) -> None:
        """Record a request."""
        if self.rate_limited:
            raise VivintSkyApiRateLimitError("limit")
        self.requests.append((method, request))

    async def get_climate_devices(self, system_id: int) -> list[Any]:
        """Return no devices."""
        return []


@pytest.fixture
def api() -> FakeApi:
    """Return the fake API."""
    return FakeApi()


@pytest.fixture
def thermostat(api: FakeApi) -> ClimateThermostat:
    """Return a thermostat attached to a panel that uses the fake API."""
    system = System(
        {
            "system": {
                "panid": PANEL_ID,
                "par": [{"panid": PANEL_ID, "parid": 1, "d": []}],
                "u": [],
            }
        },
        api,  # type: ignore[arg-type]
        name="Home",
        is_admin=True,
    )
    return ClimateThermostat(make_device(), system.alarm_panels[0])


@pytest.fixture
def entry(hass: HomeAssistant, thermostat: ClimateThermostat) -> MockConfigEntry:
    """Return a config entry whose hub knows the thermostat's panel."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={get_device_id(thermostat.alarm_panel)},
    )
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(hass=hass, config_entry=entry, data=None),
        account=SimpleNamespace(systems=[]),
    )
    return entry


@pytest.fixture
def entity(
    entry: MockConfigEntry, thermostat: ClimateThermostat
) -> climate.VivintClimate:
    """Return the climate entity of the thermostat."""
    return climate.VivintClimate(thermostat, entry.runtime_data)


def test_state(entity: climate.VivintClimate) -> None:
    """Test the entity reports the thermostat's state."""
    assert entity.unique_id == f"{PANEL_ID}-{DEVICE_ID}"
    assert entity.current_temperature == 21.5
    assert entity.current_humidity == 48
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.hvac_action == HVACAction.COOLING
    assert entity.target_temperature == 20.0
    assert entity.min_temp == 10.0
    assert entity.max_temp == pytest.approx(32.2)
    assert entity.fan_mode == "auto"
    assert entity.fan_modes == ["auto", "on", "1 hour"]
    assert entity.device_info["manufacturer"] == "Google"
    assert entity.device_info["model"] == "Nest"


async def test_set_temperature_in_cool_mode(
    entity: climate.VivintClimate, api: FakeApi
) -> None:
    """Test a single target changes the cool set point."""
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.0})

    [(method, request)] = api.requests
    assert method == "SetCoolSetpoint"
    assert request.celsius == 22.0
    assert request.component_id == "setpoints"


async def test_set_temperature_ignores_small_changes(
    entity: climate.VivintClimate, api: FakeApi
) -> None:
    """Test a target within half a degree of the current one is not sent."""
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 20.2})

    assert not api.requests


async def test_set_temperature_range_is_sent_together(
    entity: climate.VivintClimate, thermostat: ClimateThermostat, api: FakeApi
) -> None:
    """Test a range is sent in one request so the service can check the gap."""
    thermostat.update_device(make_device(Component.OperatingModeSetting.AUTO))
    await entity.async_set_temperature(
        **{ATTR_TARGET_TEMP_LOW: 17.0, ATTR_TARGET_TEMP_HIGH: 23.0}
    )

    [(method, request)] = api.requests
    assert method == "SetTemperatureSetpoints"
    assert (request.heat_celsius, request.cool_celsius) == (17.0, 23.0)


async def test_rate_limit_is_explained(
    entity: climate.VivintClimate, api: FakeApi
) -> None:
    """Test a change refused for being too frequent raises a readable error."""
    api.rate_limited = True

    with pytest.raises(HomeAssistantError, match="Try again in a minute"):
        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.0})
    with pytest.raises(HomeAssistantError, match="Try again in a minute"):
        await entity.async_set_hvac_mode(HVACMode.HEAT)
    with pytest.raises(HomeAssistantError, match="Try again in a minute"):
        await entity.async_set_fan_mode("1 hour")


async def test_set_modes(entity: climate.VivintClimate, api: FakeApi) -> None:
    """Test changing the HVAC and fan modes."""
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    await entity.async_set_fan_mode("1 hour")

    assert [method for method, _ in api.requests] == ["SetOperatingMode", "SetFanMode"]
    assert api.requests[0][1].mode == Component.OperatingModeSetting.HEAT
    assert api.requests[1][1].mode == Component.FanSetting.SIXTY_MINUTE


async def test_thermostat_discovered_after_setup(
    hass: HomeAssistant, entry: MockConfigEntry, thermostat: ClimateThermostat
) -> None:
    """Test a thermostat reported after setup gets an entity."""
    add_entities = MagicMock()

    await climate.async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()

    async_dispatcher_send(hass, f"{DOMAIN}_{entry.entry_id}_add_climate", thermostat)

    entities = add_entities.call_args.args[0]
    assert [entity.device for entity in entities] == [thermostat]
