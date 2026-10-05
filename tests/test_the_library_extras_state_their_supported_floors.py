# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `numpy`, `pandas` and `polars` extras state the oldest release
each supports (numpy 2.0, pandas 2.2, polars 1.0), and the bundled
pandas and polars compendium files start at the same release, so a file
never claims to apply to a version the extra does not support."""
import pathlib

try:
    import tomllib
except ModuleNotFoundError:      # Python 3.10 predates tomllib
    import tomli as tomllib

import yaml

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_FLOORS = {"numpy": "2.0", "pandas": "2.2", "polars": "1.0"}


def _extras() -> dict:
    with open(_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)["project"]["optional-dependencies"]


def _lower(spec: str) -> tuple:
    for part in spec.split(","):
        part = part.strip()
        if part.startswith(">="):
            nums = [int(p) for p in part[2:].split(".")]
            return tuple((nums + [0, 0])[:2])
    return ()


def test_each_library_extra_states_its_floor():
    extras = _extras()
    for library, floor in _FLOORS.items():
        assert extras[library] == [f"{library}>={floor}"], extras[library]


def test_the_bundled_pandas_and_polars_files_start_at_the_floor():
    for library in ("pandas", "polars"):
        floor = tuple(int(p) for p in _FLOORS[library].split("."))
        for path in sorted((_ROOT / "mathema" / "compendium" / library)
                           .glob("*.claims.yaml")):
            versions = str(yaml.safe_load(path.read_text())["versions"])
            assert _lower(versions) == floor, (path.name, versions)

