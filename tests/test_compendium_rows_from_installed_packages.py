# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Compendium files an installed package ships through the
`mathema.compendium` entry-point group.

The bundled files load first, then each package's (sorted by
distribution name), then the project's. A package row adds to its key
by claim name; a package row sharing a name with a bundled row, or
another package's, and stating something different is a conflict: both
rows stay out of the entry (so out of premises, guards and axioms), the
key records the conflict, and `mathema compendium status` lists both
statements and where each comes from. Every package row names its
distribution and file. `mathema verify` adjudicates a package row
against the installed library and gates on it; a package definition row
is evidence until verified or accepted; `export` leaves the rows a
package ships out. With no package installed, the load is the one the
bundled and project files alone give, compared against
`tests/data/compendium_stdlib_load.json` (regenerate it when a bundled
`math` or `statistics` row changes)."""
import json
import os
import sys
import textwrap
import warnings

import pytest

from mathema import compendium
from mathema.compendium import ROW_PACKAGE, ROW_SOURCE, load_library_claims

_GOLDEN = os.path.join(os.path.dirname(__file__), "data",
                       "compendium_stdlib_load.json")

PACKAGE_ROWS = """
    compendium: math
    versions: "*"

    math.fabs:
      claims:
        - name: nonneg
          statement: "for x in [-10, 10], f(x) >= 0"

    math.sqrt:
      claims:
        - name: sqrt_le_x
          statement: "for x in [1, 100], f(x) <= x"
        - name: sqrt_nonneg
          statement: "for x in [0, inf], f(x) > 0"
"""

ENTRY = """
from pathlib import Path


def claims_dirs():
    return [Path(__file__).parent / "claims"]
"""


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _forget():
    compendium.uninstall()
    compendium._reset_package_discovery()
    compendium._VERSIONS.clear()
    compendium._PROVIDED.clear()
    from mathema import definitions
    definitions._LIBRARY_CACHE.clear()


@pytest.fixture(autouse=True)
def _clean():
    _forget()
    yield
    _forget()
    for name in [m for m in sys.modules
                 if m.split(".")[0] in ("rowpack", "zzpack", "calc")]:
        sys.modules.pop(name, None)


def _package(tmp_path, monkeypatch, name="rowpack", version="1.3",
             rows=PACKAGE_ROWS, file="math.claims.yaml", site=None):
    """A throwaway distribution on the path: its metadata, its
    `mathema.compendium` entry point, and the claims file it ships."""
    site = site or tmp_path / "site"
    _write(site / name / "__init__.py", ENTRY)
    _write(site / name / "claims" / file, rows)
    info = site / f"{name}-{version}.dist-info"
    _write(info / "METADATA",
           f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    _write(info / "entry_points.txt",
           f"[mathema.compendium]\nrows = {name}:claims_dirs\n")
    monkeypatch.syspath_prepend(str(site))
    _forget()
    return site


def _project(tmp_path):
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    return root


def _names(info):
    return [r["name"] for r in info["entry"]["claims"]]


def test_package_rows_load_between_the_bundled_and_the_project_rows(
        tmp_path, monkeypatch):
    _package(tmp_path, monkeypatch)
    root = _project(tmp_path)
    _write(root / "claims" / "math.claims.yaml", """
        compendium: math
        versions: "*"
        math.fabs:
          claims:
            - name: project_row
              statement: "for x in [0, 10], f(x) == x"
    """)
    loaded = load_library_claims(str(root))
    # a new key: the package's row, then the project's
    assert _names(loaded["math.fabs"]) == ["nonneg", "project_row"]
    assert loaded["math.fabs"]["bundled"] is False
    # a bundled key: the bundled rows stay, the package row joins after
    sqrt = loaded["math.sqrt"]
    assert _names(sqrt) == ["nan_propagates", "none_raises", "sqrt_le_x"]
    assert sqrt["bundled"] is False


def test_a_package_installed_in_the_projects_own_environment_loads(
        tmp_path, monkeypatch):
    root = _project(tmp_path)
    _package(tmp_path, monkeypatch,
             site=root / ".venv" / "lib" / "site-packages")
    fabs = load_library_claims(str(root))["math.fabs"]
    (row,) = fabs["entry"]["claims"]
    assert row["meta"][ROW_PACKAGE] == "rowpack 1.3"


def test_a_package_directory_the_project_tree_reads_is_the_projects(
        tmp_path, monkeypatch):
    root = _project(tmp_path)
    _package(tmp_path, monkeypatch, site=root)
    fabs = load_library_claims(str(root))["math.fabs"]
    (row,) = fabs["entry"]["claims"]
    assert ROW_PACKAGE not in row["meta"]
    assert row["meta"][ROW_SOURCE] == "rowpack/claims/math.claims.yaml"


def test_a_project_row_replaces_its_package_namesake(tmp_path, monkeypatch):
    _package(tmp_path, monkeypatch)
    root = _project(tmp_path)
    _write(root / "claims" / "math.claims.yaml", """
        compendium: math
        versions: "*"
        math.sqrt:
          claims:
            - name: sqrt_le_x
              statement: "for x in [1, 50], f(x) <= x"
    """)
    rows = {r["name"]: r for r in
            load_library_claims(str(root))["math.sqrt"]["entry"]["claims"]}
    assert rows["sqrt_le_x"]["statement"] == "for x in [1, 50], f(x) <= x"
    assert rows["sqrt_le_x"]["meta"][ROW_SOURCE] == "claims/math.claims.yaml"
    assert ROW_PACKAGE not in rows["sqrt_le_x"]["meta"]


def test_each_package_row_names_its_distribution_and_file(tmp_path,
                                                          monkeypatch):
    _package(tmp_path, monkeypatch)
    loaded = load_library_claims(str(_project(tmp_path)))
    (row,) = [r for r in loaded["math.fabs"]["entry"]["claims"]]
    meta = row["meta"]
    assert meta[ROW_PACKAGE] == "rowpack 1.3"
    assert meta[ROW_SOURCE] == \
        "rowpack/claims/math.claims.yaml (from rowpack 1.3)"
    assert meta["mathema.compendium"] == "compendium:math (from rowpack 1.3)"
    assert row["source"] == "compendium"
    assert loaded["math.fabs"]["source"] == \
        "rowpack/claims/math.claims.yaml (from rowpack 1.3)"
    assert not compendium.row_is_bundled(row)
    # a bundled row on the same key keeps its own provenance
    bundled = {r["name"]: r for r in
               loaded["math.sqrt"]["entry"]["claims"]}["nan_propagates"]
    assert bundled["meta"][ROW_SOURCE] == "mathema/compendium/math.claims.yaml"
    assert bundled["meta"]["mathema.compendium"] == "compendium:math"
    assert ROW_PACKAGE not in bundled["meta"]


def test_a_package_row_cannot_pass_itself_off_as_bundled(tmp_path,
                                                         monkeypatch):
    _package(tmp_path, monkeypatch, rows="""
        compendium: math
        versions: "*"
        math.fabs:
          claims:
            - name: nonneg
              statement: "for x in [-10, 10], f(x) >= 0"
              meta:
                mathema.compendium_source: mathema/compendium/math.claims.yaml
                mathema.compendium: compendium:math
    """)
    loaded = load_library_claims(str(_project(tmp_path)))
    (row,) = loaded["math.fabs"]["entry"]["claims"]
    assert not compendium.row_is_bundled(row)
    assert row["meta"]["mathema.compendium"] == \
        "compendium:math (from rowpack 1.3)"


def test_a_conflicting_row_is_kept_out_and_recorded_on_the_key(
        tmp_path, monkeypatch):
    _package(tmp_path, monkeypatch)
    root = str(_project(tmp_path))
    loaded = load_library_claims(root)
    sqrt = loaded["math.sqrt"]
    assert "sqrt_nonneg" not in _names(sqrt)
    assert sqrt["conflicts"] == [{
        "name": "sqrt_nonneg",
        "rows": [
            {"statement": "for x in [0, inf], f(x) >= 0",
             "source": "mathema/compendium/math.claims.yaml",
             "package": None},
            {"statement": "for x in [0, inf], f(x) > 0",
             "source": "rowpack/claims/math.claims.yaml (from rowpack 1.3)",
             "package": "rowpack 1.3"},
        ]}]
    assert "sqrt_nonneg" not in {
        r.get("name") for r in compendium.compendium_functions(root)[
            "math.sqrt"]["claims"]}


def test_a_conflicting_row_satisfies_no_premise(tmp_path, monkeypatch):
    _package(tmp_path, monkeypatch)
    root = str(_project(tmp_path))
    premises = compendium.external_premises(root, verified={})
    for name in ("math.sqrt.sqrt_nonneg", "sqrt_nonneg"):
        entry = premises[name]
        assert "verdict" not in entry, entry
        assert "conflict" in entry["hint"], entry
        assert "mathema/compendium/math.claims.yaml" in entry["hint"]
        assert "rowpack 1.3" in entry["hint"]
    # a verdict recorded before the package arrived does not satisfy it
    verified = {"math.sqrt": {"entry": {"claims": [{
        "name": "sqrt_nonneg", "verdict": "proven",
        "statement": "for x in [0, inf], f(x) >= 0",
        "meta": {"mathema.compendium": "compendium:math",
                 "mathema.surface": "compendium"}}]}}}
    premises = compendium.external_premises(root, verified=verified)
    assert "verdict" not in premises["math.sqrt.sqrt_nonneg"]
    assert "verdict" not in premises["sqrt_nonneg"]


def test_two_packages_conflict_with_each_other_in_distribution_order(
        tmp_path, monkeypatch):
    _package(tmp_path, monkeypatch, name="zzpack", version="0.1", rows="""
        compendium: math
        versions: "*"
        math.fabs:
          claims:
            - name: nonneg
              statement: "for x in [-5, 5], f(x) >= 0"
            - name: zz_only
              statement: "for x in [-5, 5], f(x) <= 5"
    """)
    _package(tmp_path, monkeypatch)
    fabs = load_library_claims(str(_project(tmp_path)))["math.fabs"]
    assert _names(fabs) == ["zz_only"]
    (conflict,) = fabs["conflicts"]
    assert [r["package"] for r in conflict["rows"]] == \
        ["rowpack 1.3", "zzpack 0.1"]


def test_the_same_statement_twice_is_no_conflict(tmp_path, monkeypatch):
    _package(tmp_path, monkeypatch, rows="""
        compendium: math
        versions: "*"
        math.sqrt:
          claims:
            - name: sqrt_nonneg
              statement: "for x in [0, inf], f(x) >= 0"
    """)
    sqrt = load_library_claims(str(_project(tmp_path)))["math.sqrt"]
    assert "conflicts" not in sqrt
    (row,) = [r for r in sqrt["entry"]["claims"]
              if r["name"] == "sqrt_nonneg"]
    assert row["meta"][ROW_SOURCE] == "mathema/compendium/math.claims.yaml"


def test_status_lists_a_conflict_with_both_statements_and_sources(
        tmp_path, monkeypatch):
    from mathema.compendium.status import compendium_status, render_status
    _package(tmp_path, monkeypatch)
    data = compendium_status(str(_project(tmp_path)))
    assert data["conflicts"] == [{
        "key": "math.sqrt", "name": "sqrt_nonneg",
        "rows": [
            {"statement": "for x in [0, inf], f(x) >= 0",
             "source": "mathema/compendium/math.claims.yaml",
             "package": None},
            {"statement": "for x in [0, inf], f(x) > 0",
             "source": "rowpack/claims/math.claims.yaml (from rowpack 1.3)",
             "package": "rowpack 1.3"}]}]
    text = render_status(data)
    assert "math.sqrt sqrt_nonneg: conflicting rows" in text, text
    assert "for x in [0, inf], f(x) >= 0 " \
        "(mathema/compendium/math.claims.yaml)" in text, text
    assert "for x in [0, inf], f(x) > 0 " \
        "(rowpack/claims/math.claims.yaml (from rowpack 1.3))" in text, text


def test_status_lists_a_package_file_beside_the_bundled_ones(tmp_path,
                                                            monkeypatch):
    from mathema.compendium.status import _library_files
    _package(tmp_path, monkeypatch)
    files = _library_files(str(_project(tmp_path)))["math"]
    assert [(f["source"], f["origin"]) for f in files] == [
        ("mathema/compendium/math.claims.yaml", "bundled"),
        ("rowpack/claims/math.claims.yaml (from rowpack 1.3)",
         "package rowpack 1.3")]


CALC = '''
import math


def magnitude(x: float) -> float:
    """The distance of x from zero."""
    return math.fabs(x)
'''


def _calc_project(tmp_path, monkeypatch):
    root = _project(tmp_path)
    _write(root / "calc.py", CALC)
    _write(root / "claims" / "calc.claims.yaml", """
        calc.magnitude:
          claims:
            - name: at_least_x
              statement: "for x in [-10, 10], f(x) >= x"
    """)
    monkeypatch.syspath_prepend(str(root))
    return str(root)


def test_verify_adjudicates_a_package_row_and_records_its_provenance(
        tmp_path, monkeypatch):
    from mathema.spec import load_verified
    from mathema.verify import verify_project
    _package(tmp_path, monkeypatch)
    root = _calc_project(tmp_path, monkeypatch)
    result = verify_project(root)
    assert not result.problems, (result.problems, result.lines)
    record = load_verified(root)["math.fabs"]["entry"]
    (row,) = [c for c in record["claims"] if c["name"] == "nonneg"]
    assert row["verdict"] in ("proven", "holds"), row
    assert row["meta"]["mathema.compendium"] == \
        "compendium:math (from rowpack 1.3)"
    assert any("math.fabs" in line and "rowpack" in line
               for line in result.lines), result.lines


def test_verify_gates_on_a_package_row_that_fails(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    _package(tmp_path, monkeypatch, rows="""
        compendium: math
        versions: "*"
        math.fabs:
          claims:
            - name: at_most_five
              statement: "for x in [-10, 10], f(x) <= 5"
    """)
    root = _calc_project(tmp_path, monkeypatch)
    result = verify_project(root)
    assert any("math.fabs" in str(p) for p in result.problems), \
        (result.problems, result.lines)


def test_a_package_definition_row_is_evidence_not_an_axiom(tmp_path,
                                                          monkeypatch):
    from mathema.definitions import RowBook
    _package(tmp_path, monkeypatch, rows="""
        compendium: math
        versions: "*"
        math.fabs:
          claims:
            - name: definition
              statement: "for x in R, f(x) == abs(x)"
    """)
    root = str(_project(tmp_path))
    compendium.install(root)
    book = RowBook(root)
    assert book.states("math.fabs")
    assert book.rows("math.fabs") == []
    (why,) = book.unusable("math.fabs")
    assert "not bundled with mathema" in why, why


def test_export_leaves_out_the_rows_a_package_ships(tmp_path, monkeypatch):
    from mathema.compendium.export import export_compendium
    from mathema.verify import verify_project
    _package(tmp_path, monkeypatch)
    root = _calc_project(tmp_path, monkeypatch)
    verify_project(root)
    notes: list = []
    out = export_compendium("math", root, notes=notes)
    assert "math.fabs" not in out, out
    assert any("rowpack 1.3" in n for n in notes), notes


def test_a_package_that_fails_to_load_is_skipped_with_a_warning(
        tmp_path, monkeypatch):
    site = _package(tmp_path, monkeypatch)
    (site / "rowpack" / "__init__.py").write_text(
        "def claims_dirs():\n    raise RuntimeError('no rows today')\n")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = load_library_claims(str(_project(tmp_path)))
    assert "math.fabs" not in loaded
    assert any("rowpack" in str(w.message) for w in caught), \
        [str(w.message) for w in caught]


def test_with_no_package_the_load_is_the_bundled_and_project_files_alone(
        tmp_path):
    root = _project(tmp_path)
    _write(root / "claims" / "math.claims.yaml", """
        compendium: math
        versions: "*"
        math.sqrt:
          claims:
            - name: sqrt_nonneg
              statement: "for x in [0, 100], f(x) >= 0"
              note: "the project's own reading"
            - name: sqrt_le_square
              statement: "for x in [1, 100], f(x) <= x"
        math.fabs:
          claims:
            - name: nonneg
              statement: "for x in [-10, 10], f(x) >= 0"
    """)

    def stdlib(d):
        return {k: v for k, v in d.items()
                if k.split(".")[0] in ("math", "statistics")}
    got = {"bundled": stdlib(load_library_claims(None)),
           "project": stdlib(load_library_claims(str(root)))}
    with open(_GOLDEN, encoding="utf-8") as fh:
        want = json.load(fh)
    assert json.dumps(got, sort_keys=True, indent=1, default=str) == \
        json.dumps(want, sort_keys=True, indent=1, default=str)
