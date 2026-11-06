#!/usr/bin/env python3
"""Print the lowest Home Assistant version newer than hacs.json that tests pass on.

Retests the minimum first, in case its failure was transient. Then tries each
release up to the latest stable one, oldest first. Prints nothing if the tests
pass on the minimum or fail on all of the newer releases.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from ha_test_matrix import ROOT, TEST_PACKAGE, declared_minimum, releases, test_package
from packaging.version import Version


def run(*command: str | Path) -> bool:
    """Run a command in the repository, keeping stdout free for the result."""
    result = subprocess.run(command, check=False, cwd=ROOT, stdout=sys.stderr)
    return result.returncode == 0


def tests_pass(version: Version, available: list[Version]) -> bool:
    """Return whether the tests pass on a Home Assistant version.

    Exits if the version can't be set up: it is untested, so moving on to a newer
    version could choose a minimum that is higher than needed.
    """
    print(f"Testing Home Assistant {version}", file=sys.stderr)
    with TemporaryDirectory() as tmp:
        python = Path(tmp, "venv", "bin", "python")
        overrides = Path(tmp, "overrides.txt")
        overrides.write_text(f"homeassistant=={version}\n")
        if not (
            run("uv", "venv", "--python", sys.executable, python.parent.parent)
            and run(
                *("uv", "pip", "install", "--python", python),
                *("--requirement", "requirements_test.txt"),
                *(test_package(version, available), "--override", overrides),
            )
        ):
            raise SystemExit(f"Could not set up Home Assistant {version}")
        return run(python, "-m", "pytest")


def main() -> None:
    """Print the lowest passing version, if any."""
    minimum = declared_minimum()
    homeassistant = releases("homeassistant")
    stable = next(version for version in homeassistant if not version.is_prerelease)
    candidates = sorted(
        version
        for version in homeassistant
        if minimum < version <= stable and not version.is_prerelease
    )
    available = releases(TEST_PACKAGE)
    if tests_pass(minimum, available):
        return
    for version in candidates:
        if tests_pass(version, available):
            print(version)
            return


if __name__ == "__main__":
    main()
