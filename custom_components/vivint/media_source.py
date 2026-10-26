"""Expose the recordings stored on the Vivint DVR in the media browser."""

from __future__ import annotations

from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import logging
import math
import re
import secrets

from aiohttp import ClientError, web
from vivintpy.exceptions import SpaceMonkeyError
from vivintpy.spacemonkey import (
    DvrRecording,
    DvrSegment,
    SpaceMonkeyDvr,
    parse_playlist,
)

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.media_player import BrowseError, MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_PLAYBACKS = f"{DOMAIN}_dvr_playbacks"
DATA_VIEW_REGISTERED = f"{DOMAIN}_dvr_view_registered"

PLAYBACK_URL = "/api/vivint/dvr/{token}/stream.m3u8"
PLAYBACK_LIFETIME = timedelta(hours=3)
PLAYLIST_MIME_TYPE = "application/x-mpegURL"
SEGMENT_PATH = re.compile(r"^(?P<recording>[\w:-]+)/stream(?P<number>\d+)\.ts$")
SEGMENT_MIME_TYPE = "video/mp2t"

DAY_FORMAT = "%Y-%m-%d"
# Hour windows are identified by their UTC start so daylight saving cannot make them ambiguous.
HOUR_FORMAT = "%Y%m%dT%H%MZ"


@dataclass
class Playback:
    """A playlist that has been handed to a player, with what it may fetch."""

    dvr: SpaceMonkeyDvr
    camera_id: int
    playlist: str
    segments: dict[str, range]
    expires: datetime


async def async_get_media_source(hass: HomeAssistant) -> VivintMediaSource:
    """Set up the Vivint media source."""
    if not hass.data.get(DATA_VIEW_REGISTERED):
        hass.http.register_view(VivintDvrView())
        hass.data[DATA_VIEW_REGISTERED] = True
    return VivintMediaSource(hass)


def build_playlist(parts: list[tuple[DvrRecording, list[DvrSegment]]]) -> str:
    """Build a playlist covering segments that may come from several recordings."""
    longest = max(
        (segment.duration for _, segments in parts for segment in segments),
        default=0,
    )
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{math.ceil(longest)}",
        "#EXT-X-MEDIA-SEQUENCE:0",
    ]
    for index, (recording, segments) in enumerate(parts):
        if index:
            lines.append("#EXT-X-DISCONTINUITY")
        for segment in segments:
            lines.append(f"#EXTINF:{segment.duration:.6f},")
            # Recording ids look like "2026-10-24-17:30:00", which a client may take for
            # a URI scheme unless the path is explicitly relative.
            lines.append(f"./{recording.id}/stream{segment.number}.ts")
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def _overlaps(
    start: datetime, end: datetime, window_start: datetime, window_end: datetime
) -> bool:
    return start < window_end and end > window_start


def _day_window(day: date) -> tuple[datetime, datetime]:
    """Return the UTC bounds of a local calendar day."""
    start = datetime.combine(day, time.min, tzinfo=dt_util.get_default_time_zone())
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=start.tzinfo)
    return dt_util.as_utc(start), dt_util.as_utc(end)


class VivintMediaSource(MediaSource):
    """Browse and play recordings from the Vivint DVR."""

    name = "Vivint recordings"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the media source."""
        super().__init__(DOMAIN)
        self.hass = hass

    def _dvr(self, entry_id: str, panel_id: str) -> SpaceMonkeyDvr:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or not hasattr(entry, "runtime_data"):
            raise BrowseError("The Vivint integration is not loaded")
        for system in entry.runtime_data.account.systems:
            if str(system.id) == panel_id and system.dvr:
                return system.dvr
        raise BrowseError("No DVR was found for that Vivint system")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Browse the DVR: cameras, then days, then hours."""
        try:
            if not item.identifier:
                return await self._browse_cameras()
            kind, entry_id, panel_id, camera_id, *rest = item.identifier.split("|")
            dvr = self._dvr(entry_id, panel_id)
            if kind == "CAM":
                return await self._browse_days(dvr, entry_id, panel_id, int(camera_id))
            if kind == "DAY":
                return await self._browse_hours(
                    dvr, entry_id, panel_id, int(camera_id), rest[0]
                )
        except SpaceMonkeyError as err:
            raise BrowseError(str(err)) from err
        except (ValueError, IndexError) as err:
            raise BrowseError(f"Unknown media identifier: {item.identifier}") from err
        raise BrowseError(f"Unknown media identifier: {item.identifier}")

    async def _browse_cameras(self) -> BrowseMediaSource:
        children = []
        for entry in self.hass.config_entries.async_loaded_entries(DOMAIN):
            for system in entry.runtime_data.account.systems:
                if not system.dvr:
                    continue
                status = await system.dvr.get_status()
                for camera in sorted(status["cameras"], key=lambda c: c["name"]):
                    if camera.get("disabled"):
                        continue
                    children.append(
                        BrowseMediaSource(
                            domain=DOMAIN,
                            identifier=f"CAM|{entry.entry_id}|{system.id}|{camera['id']}",
                            media_class=MediaClass.DIRECTORY,
                            media_content_type="",
                            title=camera["name"],
                            can_play=False,
                            can_expand=True,
                        )
                    )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.APP,
            media_content_type="",
            title=self.name,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=children,
        )

    async def _browse_days(
        self, dvr: SpaceMonkeyDvr, entry_id: str, panel_id: str, camera_id: int
    ) -> BrowseMediaSource:
        days: set[date] = set()
        for recording in await dvr.get_recordings(camera_id):
            day = dt_util.as_local(recording.start).date()
            last = dt_util.as_local(recording.end).date()
            while day <= last:
                days.add(day)
                day += timedelta(days=1)

        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"DAY|{entry_id}|{panel_id}|{camera_id}|{day:{DAY_FORMAT}}",
                media_class=MediaClass.DIRECTORY,
                media_content_type="",
                title=f"{day:%Y-%m-%d} ({day:%A})",
                can_play=False,
                can_expand=True,
            )
            for day in sorted(days, reverse=True)
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"CAM|{entry_id}|{panel_id}|{camera_id}",
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title="Days with recordings",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=children,
        )

    async def _browse_hours(
        self,
        dvr: SpaceMonkeyDvr,
        entry_id: str,
        panel_id: str,
        camera_id: int,
        day: str,
    ) -> BrowseMediaSource:
        day_start, day_end = _day_window(datetime.strptime(day, DAY_FORMAT).date())
        recordings = await dvr.get_recordings(camera_id)

        children = []
        hour_start = day_start
        while hour_start < day_end:
            hour_end = hour_start + timedelta(hours=1)
            if any(_overlaps(r.start, r.end, hour_start, hour_end) for r in recordings):
                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=(
                            f"HOUR|{entry_id}|{panel_id}|{camera_id}"
                            f"|{hour_start:{HOUR_FORMAT}}"
                        ),
                        media_class=MediaClass.VIDEO,
                        media_content_type=MediaType.VIDEO,
                        title=(
                            f"{dt_util.as_local(hour_start):%H:%M}"
                            f" - {dt_util.as_local(hour_end):%H:%M}"
                        ),
                        can_play=True,
                        can_expand=False,
                    )
                )
            hour_start = hour_end
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"DAY|{entry_id}|{panel_id}|{camera_id}|{day}",
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=day,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.VIDEO,
            children=children,
        )

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Build a playlist for an hour of footage and return its URL."""
        try:
            kind, entry_id, panel_id, camera, hour = item.identifier.split("|")
            if kind != "HOUR":
                raise ValueError
            camera_id = int(camera)
            dvr = self._dvr(entry_id, panel_id)
            start = datetime.strptime(hour, HOUR_FORMAT).replace(tzinfo=UTC)
        except (ValueError, AttributeError, BrowseError) as err:
            raise Unresolvable(f"Unknown media identifier: {item.identifier}") from err

        end = start + timedelta(hours=1)
        try:
            parts = await self._segments_between(dvr, camera_id, start, end)
        except SpaceMonkeyError as err:
            raise Unresolvable(str(err)) from err
        if not parts:
            raise Unresolvable("There is no footage in that hour")

        playbacks: dict[str, Playback] = self.hass.data.setdefault(DATA_PLAYBACKS, {})
        now = dt_util.utcnow()
        for token in [t for t, p in playbacks.items() if p.expires < now]:
            del playbacks[token]

        token = secrets.token_urlsafe(24)
        playbacks[token] = Playback(
            dvr=dvr,
            camera_id=camera_id,
            playlist=build_playlist(parts),
            segments={
                recording.id: range(segments[0].number, segments[-1].number + 1)
                for recording, segments in parts
            },
            expires=now + PLAYBACK_LIFETIME,
        )
        return PlayMedia(PLAYBACK_URL.format(token=token), PLAYLIST_MIME_TYPE)

    @staticmethod
    async def _segments_between(
        dvr: SpaceMonkeyDvr, camera_id: int, start: datetime, end: datetime
    ) -> list[tuple[DvrRecording, list[DvrSegment]]]:
        parts = []
        for recording in await dvr.get_recordings(camera_id):
            if not _overlaps(recording.start, recording.end, start, end):
                continue
            playlist = await dvr.get_playlist(camera_id, recording.id)
            segments = [
                segment
                for segment in parse_playlist(playlist, recording)
                if _overlaps(segment.start, segment.end, start, end)
            ]
            if segments:
                parts.append((recording, segments))
        return parts


class VivintDvrView(HomeAssistantView):
    """Serve playlists and segments from the DVR to players.

    Players cannot attach Home Assistant credentials to HLS segment requests, so access
    is granted by the unguessable, expiring token in the URL that resolving media issues.
    """

    url = "/api/vivint/dvr/{token}/{path:.+}"
    name = "api:vivint:dvr"
    requires_auth = False

    async def get(
        self, request: web.Request, token: str, path: str
    ) -> web.StreamResponse:
        """Serve a playlist or a segment."""
        hass = request.app[KEY_HASS]
        playback: Playback | None = hass.data.get(DATA_PLAYBACKS, {}).get(token)
        if playback is None or playback.expires < dt_util.utcnow():
            return web.Response(status=404)

        if path == "stream.m3u8":
            return web.Response(
                text=playback.playlist,
                content_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "no-store"},
            )

        match = SEGMENT_PATH.match(path)
        if not match:
            return web.Response(status=404)
        recording, number = match["recording"], int(match["number"])
        if number not in playback.segments.get(recording, range(0)):
            return web.Response(status=404)

        response = web.StreamResponse(headers={"Content-Type": SEGMENT_MIME_TYPE})
        try:
            async with aclosing(
                playback.dvr.stream_segment(playback.camera_id, recording, number)
            ) as chunks:
                async for chunk in chunks:
                    if not response.prepared:
                        await response.prepare(request)
                    await response.write(chunk)
        except (SpaceMonkeyError, ClientError) as err:
            _LOGGER.warning("Unable to stream DVR segment: %s", err)
            if not response.prepared:
                return web.Response(status=502)
        return response
