"""Tests for Vivint translations."""

from __future__ import annotations

from collections.abc import Iterator
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.vivint.device_trigger import TRIGGER_TYPES
from homeassistant.helpers.entity import EntityDescription

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / "vivint"
PLATFORMS = ("binary_sensor", "button", "event", "switch", "update")


def _load(name: str) -> dict[str, Any]:
    """Load a JSON file from the integration directory."""
    return json.loads((INTEGRATION_DIR / name).read_text())


def _descriptions(value: Any) -> Iterator[EntityDescription]:
    """Yield entity descriptions nested in module-level containers."""
    # Match by class name, as Home Assistant's test plugin may recreate the
    # description classes, which breaks isinstance checks
    if any(cls.__name__ == "EntityDescription" for cls in type(value).__mro__):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _descriptions(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _descriptions(item)


def _translation_keys(platform: str) -> set[str]:
    """Return the translation keys used by a platform's entity descriptions."""
    module = importlib.import_module(f"custom_components.vivint.{platform}")
    return {
        description.translation_key
        for value in vars(module).values()
        for description in _descriptions(value)
        if description.translation_key
    }


def _keys(data: Any) -> Any:
    """Return the nested key structure of a translation file."""
    if isinstance(data, dict):
        return {key: _keys(value) for key, value in data.items()}
    return None


def test_en_matches_strings() -> None:
    """Test translations/en.json has the same keys as strings.json."""
    assert _keys(_load("translations/en.json")) == _keys(_load("strings.json"))


@pytest.mark.parametrize("platform", PLATFORMS)
def test_translation_keys_exist(platform: str) -> None:
    """Test every translation key used in code has a translation."""
    entities = _load("translations/en.json")["entity"].get(platform, {})
    assert _translation_keys(platform) <= set(entities)


def test_device_triggers_have_translations() -> None:
    """Test every device trigger type has a translation."""
    translations = _load("translations/en.json")["device_automation"]["trigger_type"]
    assert set(TRIGGER_TYPES) <= set(translations)
