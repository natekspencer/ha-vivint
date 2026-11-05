#!/usr/bin/env python3
"""Print the GitHub Actions matrix of Home Assistant versions to test against.

Channels:
  minimum  the version declared in hacs.json
  stable   the latest Home Assistant release
  beta     the latest pre-release, while it is newer than stable
  manual   the version passed as an argument, if any

Each entry names the newest test package that is not newer than its Home
Assistant version. The test package may lag behind, so CI installs it with an
override that forces the exact Home Assistant version.
"""

from __future__ import annotations

from functools import cache
from http.client import HTTPException
import json
from pathlib import Path
import sys
from time import sleep
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen

from packaging.version import Version

ROOT = Path(__file__).parent.parent

# Home Assistant publishes this package itself, starting with 2026.11.0b4.
TEST_PACKAGE = "pytest-homeassistant"
# Covers older versions. Remove once the minimum in hacs.json reaches 2026.11.
LEGACY_TEST_PACKAGE = "pytest-homeassistant-custom-component"
# Seconds to wait before each retry of a failed PyPI request.
RETRY_DELAYS = (2, 5, 15)


def fetch_json(url: str) -> dict[str, Any]:
    """Return the JSON at a URL."""
    with urlopen(url, timeout=30) as response:
        return json.load(response)


@cache
def pypi(path: str) -> dict[str, Any]:
    """Return the PyPI JSON for a package or a package release.

    Retries network errors and server errors, but not a missing package.
    """
    url = f"https://pypi.org/pypi/{path}/json"
    for delay in RETRY_DELAYS:
        try:
            return fetch_json(url)
        except (OSError, HTTPException) as err:
            if isinstance(err, HTTPError) and err.code < 500 and err.code != 429:
                raise
            print(f"Retrying {url} in {delay}s: {err}", file=sys.stderr)
            sleep(delay)
    return fetch_json(url)


def releases(package: str) -> list[Version]:
    """Return the non-yanked releases of a package, newest first."""
    return sorted(
        (
            Version(version)
            for version, files in pypi(package)["releases"].items()
            if files and not all(file["yanked"] for file in files)
        ),
        reverse=True,
    )


def declared_minimum() -> Version:
    """Return the minimum Home Assistant version declared in hacs.json."""
    return Version(json.loads((ROOT / "hacs.json").read_text())["homeassistant"])


def legacy_test_package(target: Version) -> str:
    """Return the newest legacy test package not newer than the target version."""
    for release in releases(LEGACY_TEST_PACKAGE):
        requires = pypi(f"{LEGACY_TEST_PACKAGE}/{release}")["info"]["requires_dist"]
        pin = next(req for req in requires if req.startswith("homeassistant=="))
        if Version(pin.removeprefix("homeassistant==")) <= target:
            return f"{LEGACY_TEST_PACKAGE}=={release}"
    raise SystemExit(f"No test package found for Home Assistant {target}")


def test_package(target: Version, available: list[Version]) -> str:
    """Return the requirement of the test package to use for the target version."""
    for release in available:
        # Releases below 2026 are an unrelated earlier use of the package name.
        if release.major >= 2026 and release <= target:
            return f"{TEST_PACKAGE}=={release}"
    return legacy_test_package(target)


def main() -> None:
    """Print the matrix as JSON."""
    homeassistant = releases("homeassistant")
    stable = next(version for version in homeassistant if not version.is_prerelease)
    channels = {
        "minimum": declared_minimum(),
        "stable": stable,
    }
    if homeassistant[0] > stable:
        channels["beta"] = homeassistant[0]
    if len(sys.argv) > 1 and sys.argv[1]:
        channels["manual"] = Version(sys.argv[1])

    available = releases(TEST_PACKAGE)
    include = [
        {
            "channel": channel,
            "homeassistant": str(version),
            "test_package": test_package(version, available),
        }
        for channel, version in channels.items()
    ]
    print(json.dumps({"include": include}))


if __name__ == "__main__":
    main()
