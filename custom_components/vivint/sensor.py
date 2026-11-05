"""Support for Vivint sensors."""

from vivintpy.devices import VivintDevice

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import VivintConfigEntry
from .const import DOMAIN
from .hub import VivintEntity, VivintHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Vivint sensors using config entry."""
    entities = []
    hub: VivintHub = entry.runtime_data

    for system in hub.account.systems:
        for alarm_panel in system.alarm_panels:
            for device in alarm_panel.devices:
                if (
                    not device.is_subdevice
                    and getattr(device, "battery_level", None) is not None
                ):
                    entities.append(VivintBatterySensorEntity(device=device, hub=hub))

    if not entities:
        return

    async_add_entities(entities)

    @callback
    def async_add_sensor(device: VivintDevice) -> None:
        """Add Vivint sensor."""
        entities: list[VivintBatterySensorEntity] = []
        if (
            not device.is_subdevice
            and getattr(device, "battery_level", None) is not None
        ):
            entities.append(VivintBatterySensorEntity(device=device, hub=hub))

        async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{entry.entry_id}_add_{SENSOR_DOMAIN}",
            async_add_sensor,
        )
    )


class VivintBatterySensorEntity(VivintEntity, SensorEntity):
    """Vivint Battery Sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self) -> str:
        """Return the name of this entity."""
        return f"{self.device.name} Battery Level"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self.device.alarm_panel.id}-{self.device.id}"

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        return self.device.battery_level
