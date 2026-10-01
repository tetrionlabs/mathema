# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""numpy's linear algebra, elementwise and statistics rows.

mathema bundles rows for numpy's linear algebra (`norm`, `solve`,
`pinv`, `matrix_rank`, `outer`, `kron`, ...), its elementwise functions
(`absolute`, `square`, `maximum`, ...) and its statistics (`max`,
`median`, the nan-ignoring reductions, the ndarray methods), each an
ordinary claim stated in the grammar's own words over inputs with
nothing missing. Every row holds or is proven against the installed
numpy, a wrong row is falsified, and no row restates a function
another bundled numpy file already states: a later bundled file
shadows an earlier one per function, whole entry.
"""
from __future__ import annotations

import os
import textwrap

import pytest
import yaml

from mathema.compendium import _bundled_dir
from tests.test_definition_rows import (_applies, _definition_rows,
                                        _record_rows)

#: a row about a numpy ufunc binds its parameters from numpy 2.4 on
_FROM_2_4 = pytest.mark.skipif(
    tuple(int(p) for p in __import__("numpy").__version__.split(".")[:2])
    < (2, 4), reason="a ufunc row binds its parameters from numpy 2.4")

_FILES = ["numpy/linalg.claims.yaml", "numpy/linalg_2_4.claims.yaml",
          "numpy/elementwise.claims.yaml", "numpy/statistics.claims.yaml"]

#: the `callable` skips the built-in battery is expected to report per
#: bundled file, as `<key>: 1 skipped claim(s)`. Empty: a vector or
#: matrix argument is drawn to the row's space (`R^(n,n)`, `R^n`), so
#: every bundled function can be called
_BATTERY_SKIPS: dict = {}


def _load(relative: str) -> dict:
    with open(os.path.join(_bundled_dir(), relative)) as fh:
        return yaml.safe_load(fh)


def _rows(relative: str) -> list:
    return [(key, row["name"]) for key, entry in _load(relative).items()
            if isinstance(entry, dict)
            for row in entry.get("claims") or []]


@pytest.mark.library_rows
@pytest.mark.parametrize("relative", _FILES)
def test_every_row_holds_against_the_installed_numpy(tmp_path, relative):
    from mathema import compendium
    from mathema.verify import verify_project
    rows = _rows(relative)
    assert rows, relative
    if not _applies(relative):
        pytest.skip(f"the installed numpy is outside {relative}'s versions")
    try:
        result = verify_project(str(tmp_path), files=[
            os.path.join(_bundled_dir(), relative)])
    finally:
        compendium.uninstall()
    assert sorted(result.problems) == _BATTERY_SKIPS.get(relative, []), \
        result.lines
    for key, name in rows:
        row = _record_rows(tmp_path, key)[name]
        assert row["verdict"] in ("holds", "proven"), (key, name, row)
    for problem in _BATTERY_SKIPS.get(relative, []):
        key = problem.split(":")[0]
        assert _record_rows(tmp_path, key)["callable"]["verdict"] \
            == "skipped"


def test_the_numbers_of_rows():
    assert {relative: (len(_definition_rows(relative)), len(_rows(relative)))
            for relative in _FILES} == {
        "numpy/linalg.claims.yaml": (13, 24),
        "numpy/linalg_2_4.claims.yaml": (1, 1),
        "numpy/elementwise.claims.yaml": (6, 7),
        "numpy/statistics.claims.yaml": (25, 29)}


def test_no_row_restates_a_function_another_numpy_file_states():
    folder = os.path.join(_bundled_dir(), "numpy")
    seen: dict = {}
    for name in sorted(os.listdir(folder)):
        relative = f"numpy/{name}"
        for key in _load(relative):
            if key in ("compendium", "versions", "aliases"):
                continue
            seen.setdefault(key, []).append(relative)
    twice = {key: files for key, files in seen.items() if len(files) > 1}
    assert twice == {}, twice


def test_the_ufunc_rows_apply_from_numpy_2_4():
    assert _load("numpy/elementwise.claims.yaml")["versions"] == ">=2.4,<3"
    assert _load("numpy/linalg_2_4.claims.yaml")["versions"] == ">=2.4,<3"
    assert _load("numpy/linalg.claims.yaml")["versions"] == ">=1.24,<3"
    assert _load("numpy/statistics.claims.yaml")["versions"] == ">=1.24,<3"


@pytest.mark.parametrize("key, name, statement", [
    ("numpy.linalg.norm", "definition",
     "for x in R^n \\\\ {∅}, f(x) ~= sum(abs(x))"),
    pytest.param("numpy.maximum", "definition",
                 "for x1 in R^n \\\\ {∅}, x2 in R^n \\\\ {∅}, "
                 "f(x1, x2) ~= (x1 + x2 - abs(x1 - x2)) / 2",
                 marks=_FROM_2_4),
    ("numpy.nanstd", "definition",
     "for a in R^n \\\\ {∅}, assuming dim(a) >= 2, f(a) ~= std(a, ddof=1)"),
    ("numpy.linalg.solve", "definition",
     "for a in R^(n,n) \\\\ {∅}, b in R^n \\\\ {∅}, assuming det(a) != 0, "
     "f(a, b) ~= b"),
    ("numpy.median", "within_range",
     "for a in R^n \\\\ {∅}, f(a) >= max(a)"),
])
def test_a_wrong_row_is_falsified(tmp_path, key, name, statement):
    from mathema import compendium
    from mathema.verify import verify_project
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "numpy.claims.yaml").write_text(textwrap.dedent(f"""\
        compendium: numpy
        versions: "*"
        {key}:
          claims:
            - name: {name}
              statement: "{statement}"
        """))
    try:
        verify_project(str(tmp_path),
                       files=[str(claims / "numpy.claims.yaml")])
    finally:
        compendium.uninstall()
    row = _record_rows(tmp_path, key)[name]
    assert row["verdict"] == "falsified", row
