"""Test browsing and playing recordings from the Vivint DVR."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from vivintpy.exceptions import SpaceMonkeyError
from vivintpy.spacemonkey import DvrRecording

from custom_components.vivint import media_source
from custom_components.vivint.const import DOMAIN
from homeassistant.components.media_player import BrowseError
from homeassistant.components.media_source import MediaSourceItem, Unresolvable
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

RECORDING_ID = "2026-10-24-17:30:00"
RECORDING_START = datetime(2026, 10, 24, 17, 30, tzinfo=UTC)
SEGMENT_SECONDS = 12
SEGMENT_COUNT = 3600
CAMERA_ID = 27
PANEL_ID = 4000000000000001
SEGMENT_BYTES = b"\x47" + b"\x00" * 1000


class FakeDvr:
    """A DVR holding one twelve-hour recording of 12-second segments."""

    def __init__(self) -> None:
        """Initialize the fake DVR."""
        self.fail = False

    async def get_status(self) -> dict:
        """Return a status with two cameras, one of them disabled."""
        return {
            "cameras": [
                {"id": 48, "name": "Backyard", "disabled": True},
                {"id": CAMERA_ID, "name": "Doorbell", "disabled": False},
            ]
        }

    async def get_recordings(self, camera_id: int) -> list[DvrRecording]:
        """Return the recordings of a camera."""
        if self.fail:
            raise SpaceMonkeyError("DVR unreachable")
        if camera_id != CAMERA_ID:
            return []
        end = RECORDING_START + timedelta(seconds=SEGMENT_SECONDS * SEGMENT_COUNT)
        return [DvrRecording(RECORDING_ID, camera_id, RECORDING_START, end)]

    async def get_playlist(self, camera_id: int, recording_id: str) -> str:
        """Return the playlist of a recording."""
        lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:14"]
        for number in range(1, SEGMENT_COUNT + 1):
            lines += [f"#EXTINF:{SEGMENT_SECONDS}.000000,", f"stream{number}.ts"]
        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines)

    async def stream_segment(
        self, camera_id: int, recording_id: str, number: int
    ) -> AsyncIterator[bytes]:
        """Stream a segment."""
        yield SEGMENT_BYTES[:500]
        yield SEGMENT_BYTES[500:]


@pytest.fixture(name="dvr")
def dvr_fixture() -> FakeDvr:
    """Return the fake DVR."""
    return FakeDvr()


@pytest.fixture(name="entry")
async def entry_fixture(hass: HomeAssistant, dvr: FakeDvr) -> MockConfigEntry:
    """Return a loaded config entry whose system has a DVR."""
    await hass.config.async_set_time_zone("America/Chicago")
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    system = SimpleNamespace(id=PANEL_ID, dvr=dvr)
    entry.runtime_data = SimpleNamespace(
        account=SimpleNamespace(systems=[system]), disconnect=AsyncMock()
    )
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return entry


def _item(hass: HomeAssistant, identifier: str | None) -> MediaSourceItem:
    return MediaSourceItem(hass, DOMAIN, identifier, None)


def _ident(entry: MockConfigEntry, kind: str, *rest: object) -> str:
    return "|".join([kind, entry.entry_id, str(PANEL_ID), *map(str, rest)])


async def test_browse_cameras(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Test the root lists the DVR's enabled cameras."""
    source = await media_source.async_get_media_source(hass)

    root = await source.async_browse_media(_item(hass, None))

    assert [c.title for c in root.children] == ["Doorbell"]
    assert root.children[0].media_content_id == (
        f"media-source://{DOMAIN}/{_ident(entry, 'CAM', CAMERA_ID)}"
    )
    assert root.children[0].can_expand


async def test_browse_days_in_local_time(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Test days are local calendar days."""
    source = await media_source.async_get_media_source(hass)

    camera = await source.async_browse_media(
        _item(hass, _ident(entry, "CAM", CAMERA_ID))
    )

    # 17:30Z to 05:30Z the next day is 12:30 to 00:30 local, so two local days.
    assert [c.title for c in camera.children] == [
        "2026-10-25 (Sunday)",
        "2026-10-24 (Saturday)",
    ]


async def test_browse_hours(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Test only hours that overlap a recording are offered."""
    source = await media_source.async_get_media_source(hass)

    day = await source.async_browse_media(
        _item(hass, _ident(entry, "DAY", CAMERA_ID, "2026-10-24"))
    )

    assert day.children[0].title == "12:00 - 13:00"
    assert day.children[-1].title == "23:00 - 00:00"
    assert len(day.children) == 12
    assert all(c.can_play for c in day.children)

    # The recording ends at 00:30 local on the 25th, so that day starts with one hour.
    next_day = await source.async_browse_media(
        _item(hass, _ident(entry, "DAY", CAMERA_ID, "2026-10-25"))
    )
    assert [c.title for c in next_day.children] == ["00:00 - 01:00"]


async def test_browse_errors(
    hass: HomeAssistant, entry: MockConfigEntry, dvr: FakeDvr
) -> None:
    """Test browsing failures are reported as browse errors."""
    source = await media_source.async_get_media_source(hass)

    with pytest.raises(BrowseError):
        await source.async_browse_media(_item(hass, "NOPE|x"))
    with pytest.raises(BrowseError):
        await source.async_browse_media(
            _item(hass, f"CAM|missing|{PANEL_ID}|{CAMERA_ID}")
        )
    dvr.fail = True
    with pytest.raises(BrowseError):
        await source.async_browse_media(_item(hass, _ident(entry, "CAM", CAMERA_ID)))


def test_build_playlist_marks_discontinuities() -> None:
    """Test a playlist spanning two recordings flags the gap."""
    first = DvrRecording("a", 1, RECORDING_START, RECORDING_START)
    second = DvrRecording("b", 1, RECORDING_START, RECORDING_START)
    segment = media_source.DvrSegment

    playlist = media_source.build_playlist(
        [
            (first, [segment("a", 4, RECORDING_START, 12.0)]),
            (second, [segment("b", 1, RECORDING_START, 13.5)]),
        ]
    )

    assert playlist.splitlines() == [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-TARGETDURATION:14",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXTINF:12.000000,",
        "a/stream4.ts",
        "#EXT-X-DISCONTINUITY",
        "#EXTINF:13.500000,",
        "b/stream1.ts",
        "#EXT-X-ENDLIST",
    ]


async def test_resolve_and_play(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test resolving an hour gives a playlist and segments a player can fetch."""
    # The test client freezes the router, so the view has to be registered first.
    source = await media_source.async_get_media_source(hass)
    client = await hass_client_no_auth()

    # 18:00Z to 19:00Z, which is the hour 13:00 local.
    play = await source.async_resolve_media(
        _item(hass, _ident(entry, "HOUR", CAMERA_ID, "20261024T1800Z"))
    )
    assert play.mime_type == "application/x-mpegURL"
    assert play.url.startswith("/api/vivint/dvr/")

    resp = await client.get(play.url)
    assert resp.status == 200
    lines = (await resp.text()).splitlines()
    segments = [line for line in lines if line.endswith(".ts")]
    # Segments 151 to 450 cover the hour exactly, at 12 seconds each.
    assert segments[0] == f"{RECORDING_ID}/stream151.ts"
    assert segments[-1] == f"{RECORDING_ID}/stream450.ts"
    assert len(segments) == 300
    assert lines[-1] == "#EXT-X-ENDLIST"

    base = play.url.rsplit("/", 1)[0]
    resp = await client.get(f"{base}/{segments[0]}")
    assert resp.status == 200
    assert resp.headers["Content-Type"] == "video/mp2t"
    assert await resp.read() == SEGMENT_BYTES

    # Segments outside the resolved hour are not served.
    assert (await client.get(f"{base}/{RECORDING_ID}/stream150.ts")).status == 404
    assert (await client.get(f"{base}/{RECORDING_ID}/stream451.ts")).status == 404
    assert (await client.get(f"{base}/other/stream151.ts")).status == 404
    assert (await client.get(f"{base}/stream151.ts")).status == 404


async def test_unknown_or_expired_token(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test playback URLs only work with a valid, current token."""
    # The test client freezes the router, so the view has to be registered first.
    source = await media_source.async_get_media_source(hass)
    client = await hass_client_no_auth()

    assert (await client.get("/api/vivint/dvr/guess/stream.m3u8")).status == 404

    play = await source.async_resolve_media(
        _item(hass, _ident(entry, "HOUR", CAMERA_ID, "20261024T1800Z"))
    )
    for playback in hass.data[media_source.DATA_PLAYBACKS].values():
        playback.expires = datetime.now(UTC) - timedelta(seconds=1)
    assert (await client.get(play.url)).status == 404


async def test_resolve_errors(
    hass: HomeAssistant, entry: MockConfigEntry, dvr: FakeDvr
) -> None:
    """Test media that cannot be resolved raises Unresolvable."""
    source = await media_source.async_get_media_source(hass)

    with pytest.raises(Unresolvable):
        await source.async_resolve_media(_item(hass, _ident(entry, "CAM", CAMERA_ID)))
    with pytest.raises(Unresolvable):
        await source.async_resolve_media(
            _item(hass, _ident(entry, "HOUR", CAMERA_ID, "bad"))
        )
    # An hour with no footage.
    with pytest.raises(Unresolvable):
        await source.async_resolve_media(
            _item(hass, _ident(entry, "HOUR", CAMERA_ID, "20261020T0000Z"))
        )
    dvr.fail = True
    with pytest.raises(Unresolvable):
        await source.async_resolve_media(
            _item(hass, _ident(entry, "HOUR", CAMERA_ID, "20261024T1800Z"))
        )
