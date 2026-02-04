"""Support for Vivint cameras."""

from __future__ import annotations

import logging

from vivintpy.devices.camera import Camera as VivintCamera

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VivintConfigEntry
from .const import (
    CONF_HD_STREAM,
    CONF_RTSP_STREAM,
    CONF_RTSP_URL_LOGGING,
    DEFAULT_HD_STREAM,
    DEFAULT_RTSP_STREAM,
    DEFAULT_RTSP_URL_LOGGING,
    RTSP_STREAM_DIRECT,
    RTSP_STREAM_INTERNAL,
)
from .hub import VivintEntity, VivintHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VivintConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vivint cameras using config entry."""
    entities = []
    hub: VivintHub = entry.runtime_data

    hd_stream = entry.options.get(CONF_HD_STREAM, DEFAULT_HD_STREAM)
    rtsp_stream = entry.options.get(CONF_RTSP_STREAM, DEFAULT_RTSP_STREAM)
    rtsp_url_logging = entry.options.get(
        CONF_RTSP_URL_LOGGING, DEFAULT_RTSP_URL_LOGGING
    )

    for system in hub.account.systems:
        for alarm_panel in system.alarm_panels:
            for device in alarm_panel.devices:
                if isinstance(device, VivintCamera):
                    if rtsp_url_logging:
                        await log_rtsp_urls(device)

                    entities.append(
                        VivintCameraEntity(
                            device=device,
                            hub=hub,
                            hd_stream=hd_stream,
                            rtsp_stream=rtsp_stream,
                        )
                    )

    if not entities:
        return

    async_add_entities(entities)


async def log_rtsp_urls(device: VivintCamera) -> None:
    """Logs the rtsp urls of a Vivint camera."""
    _LOGGER.info(
        "%s rtsp urls:\n  direct hd: %s\n  direct sd: %s\n  internal hd: %s\n  internal sd: %s\n  external hd: %s\n  external sd: %s",
        device.name,
        await device.get_direct_rtsp_url(hd=True),
        await device.get_direct_rtsp_url(hd=False),
        await device.get_rtsp_url(internal=True, hd=True),
        await device.get_rtsp_url(internal=True, hd=False),
        await device.get_rtsp_url(internal=False, hd=True),
        await device.get_rtsp_url(internal=False, hd=False),
    )


class VivintCameraEntity(VivintEntity, Camera):
    """Vivint camera entity."""

    device: VivintCamera

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        device: VivintCamera,
        hub: VivintHub,
        hd_stream: bool = DEFAULT_HD_STREAM,
        rtsp_stream: int = DEFAULT_RTSP_STREAM,
    ) -> None:
        """Initialize a Vivint camera."""
        super().__init__(device=device, hub=hub)
        Camera.__init__(self)

        self._attr_device_info.setdefault("connections", set()).add(
            (CONNECTION_NETWORK_MAC, format_mac(device.mac_address))
        )

        self.__hd_stream = hd_stream
        self.__rtsp_stream = rtsp_stream
        self.__last_image = None

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self.device.alarm_panel.id}-{self.device.id}"

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        await self.device.alarm_panel.get_panel_credentials()
        url = self.device.get_rtsp_access_url(self.__rtsp_stream, self.__hd_stream)
        if not url and self.__rtsp_stream == RTSP_STREAM_DIRECT:
            url = self.device.get_rtsp_access_url(
                RTSP_STREAM_INTERNAL, self.__hd_stream
            )
        return url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a frame from the camera stream."""
        try:
            self.__last_image = await async_get_image(
                hass=self.hass,
                input_source=await self.stream_source(),
                width=width,
                height=height,
            )
        except:  # pylint:disable=bare-except  # noqa: E722
            _LOGGER.debug("Could not retrieve latest image for %s", self.name)

        return self.__last_image
