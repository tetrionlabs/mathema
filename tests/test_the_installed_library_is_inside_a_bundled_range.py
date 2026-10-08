# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The bundled compendium files for an installed library admit the
version installed: at least one file's `versions:` range contains it.
When a library's new major release lands outside every bundled range,
every row-level test for that library skips, and a run that checked
nothing would pass; this test fails instead, naming the version and
the ranges, so the rows are checked against the new release and the
ranges widened (or the changed rows stated per version)."""
import os

import pytest
import yaml


def _bundled_files(library: str) -> list:
    from mathema.compendium import _bundled_dir
    from mathema.spec import claims_file_paths
    out = []
    for path in claims_file_paths(_bundled_dir()):
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if data.get("compendium") == library:
            out.append((os.path.relpath(path, _bundled_dir()),
                        str(data.get("versions", "*")),
                        tuple(data.get("aliases") or ())))
    return out


@pytest.mark.third_party_compendiums
@pytest.mark.parametrize("library", ["numpy", "pandas", "polars"])
def test_some_bundled_file_admits_the_installed_version(library):
    pytest.importorskip(library)
    from mathema.compendium import _installed_version, applicable_tag
    files = _bundled_files(library)
    assert files, f"no bundled compendium file is about {library}"
    installed = _installed_version(library)
    in_range = [name for name, versions, aliases in files
                if applicable_tag(library, versions, aliases) is not None]
    ranges = "; ".join(f"{name} ({versions})" for name, versions, _a in files)
    assert in_range, (
        f"{library} {installed} is outside every bundled compendium file's "
        f"range: {ranges}. Every row test for {library} would skip and the "
        f"run would pass without checking it. Check the rows against "
        f"{library} {installed}, then widen the ranges, or state the rows "
        f"whose behaviour changed per version.")
