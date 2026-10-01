# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every bundled numpy, pandas and polars compendium file loads, every
row in it parses, and every row holds against the installed library.

The bundled files state what numpy, pandas and polars compute for the
calls numerical and data code makes most: the median and the
quantiles, a weighted average, a clipped vector, the second
differences, a QR or singular value factorisation, a DataFrame's
columns, and polars' extrema, shifts and rolling windows.
Loading and parsing are checked in every run; adjudicating the rows
against the installed libraries checks the libraries (or mathema's
reading of them), so it runs with `--library-rows`.
"""
from __future__ import annotations

import glob
import os

import pytest
import yaml

from mathema.compendium import _bundled_dir
from tests.test_definition_rows import _applies, _record_rows

_FIELDS = ("compendium", "versions", "aliases")
_LIBRARIES = ("numpy", "pandas", "polars")


def _relative_files() -> list:
    """The bundled numpy, pandas and polars files, as paths relative to
    the bundled directory."""
    root = _bundled_dir()
    return sorted(os.path.relpath(p, root).replace(os.sep, "/")
                  for library in _LIBRARIES
                  for p in glob.glob(os.path.join(root, library,
                                                  "*.claims.yaml")))


def _load(relative: str) -> dict:
    with open(os.path.join(_bundled_dir(), relative)) as fh:
        return yaml.safe_load(fh)


def _rows(relative: str) -> list:
    return [(key, row) for key, entry in _load(relative).items()
            if key not in _FIELDS and isinstance(entry, dict)
            for row in entry.get("claims") or []]


#: rows that state what a commonly called function computes, by the
#: function and the row's name
_COMMON_CALLS = {
    "numpy.average": ["definition", "weighted"],
    "numpy.clip": ["definition"],
    "numpy.mean": ["definition@axis=0", "definition@axis=1"],
    "numpy.sum": ["definition@axis=0", "definition@axis=1"],
    "numpy.cumsum": ["definition@axis=0"],
    "numpy.median": ["definition", "definition@axis=0"],
    "numpy.quantile": ["definition"],
    "numpy.percentile": ["definition"],
    "numpy.diff": ["definition@n=2"],
    "numpy.ptp": ["definition"],
    "numpy.cov": ["of_a_vector"],
    "pandas.Series.sem": ["definition"],
    "numpy.linalg.norm": ["definition@ord=inf"],
    "numpy.linalg.qr": ["factors"],
    "numpy.linalg.svd": ["factors"],
    "numpy.dot": ["of_matrices"],
    "numpy.inner": ["definition"],
    "pandas.Series.shift": ["shifted@periods=-1"],
    "pandas.Series.diff": ["differences@periods=2"],
    "pandas.DataFrame.abs": ["columns"],
    "pandas.DataFrame.cumsum": ["columns"],
    "pandas.Series.clip": ["definition"],
    "polars.Series.clip": ["definition"],
    "polars.Series.min": ["definition"],
    "polars.Series.max": ["definition"],
    "polars.Series.abs": ["definition"],
    "polars.Series.sqrt": ["definition"],
    "polars.Series.dot": ["definition"],
    "polars.Series.cum_max": ["definition"],
    "polars.Series.cum_min": ["definition"],
    "polars.Series.shift": ["shifted", "shifted@n=-1"],
    "polars.Series.diff": ["differences"],
    "polars.Series.pct_change": ["changes"],
    "polars.Series.rolling_mean": ["windows@window_size=2",
                                   "windows@window_size=3"],
    "polars.Series.rolling_sum": ["windows@window_size=2"],
    "polars.Series.ewm_mean": ["recursion@adjust=False,alpha=0.5"],
    "polars.Series.median": ["definition"],
    "polars.Series.quantile": ["within_range"],
}


@pytest.mark.parametrize("relative", _relative_files())
def test_every_bundled_file_is_a_valid_claims_file(relative):
    from mathema.spec import validate_claims_file
    validate_claims_file(_load(relative), relative)


@pytest.mark.parametrize("relative", _relative_files())
def test_every_bundled_row_parses(relative):
    from mathema.conjecture import claim
    for key, row in _rows(relative):
        claim(str(row["statement"]), name=row["name"])


@pytest.mark.parametrize("relative", _relative_files())
def test_every_bundled_definition_row_reads_as_a_rewrite(relative):
    from mathema.definitions import _parse_row, is_definition_name
    for key, row in _rows(relative):
        if is_definition_name(row["name"]):
            assert _parse_row(key, row) is not None, (key, row["name"])


def test_the_commonly_called_functions_state_what_they_compute():
    stated: dict = {}
    for relative in _relative_files():
        for key, row in _rows(relative):
            stated.setdefault(key, set()).add(row["name"])
    missing = {key: sorted(set(names) - stated.get(key, set()))
               for key, names in _COMMON_CALLS.items()
               if set(names) - stated.get(key, set())}
    assert missing == {}, missing


@pytest.mark.library_rows
@pytest.mark.parametrize("relative", _relative_files())
def test_every_bundled_row_holds_against_the_installed_library(tmp_path,
                                                               relative):
    from mathema import compendium
    from mathema.compendium import (_installed_version, _version_in_range)
    from mathema.verify import verify_project
    if not _applies(relative):
        pytest.skip(f"the installed library is outside {relative}'s "
                    f"versions")
    library = _load(relative)["compendium"]
    installed = _installed_version(library)
    try:
        verify_project(str(tmp_path), files=[
            os.path.join(_bundled_dir(), relative)])
    finally:
        compendium.uninstall()
    for key, row in _rows(relative):
        spec = row.get("versions")
        if spec is not None and not _version_in_range(installed, str(spec)):
            continue
        recorded = _record_rows(tmp_path, key)[row["name"]]
        assert recorded["verdict"] in ("holds", "proven"), \
            (key, row["name"], recorded.get("note"),
             recorded.get("counterexample"))
