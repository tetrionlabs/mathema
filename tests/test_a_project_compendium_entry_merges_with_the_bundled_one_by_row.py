# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A project compendium entry for a function the bundled files state
merges with the bundled entry by row name: a project row replaces only
its bundled namesake, so the bundled guards (`is_defined`, `raises`,
policy rows) keep applying. Two project files on one key merge the same
way, the deeper file winning per row, and the declared layer reads the
same rows the library loader does. Each row names the file it comes
from, and a project row replacing a bundled definition row is the
project's testimony: evidence until it is accepted as trusted."""
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _names(info):
    return [r["name"] for r in info["entry"]["claims"]]


def test_the_bundled_guard_survives_a_project_row(tmp_path):
    from mathema.compendium import load_library_claims
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=2.0"
        numpy.sqrt:
          claims:
            - name: my_bound
              statement: "for x in [1, 4], f(x) <= x"
    """)
    info = load_library_claims(str(tmp_path))["numpy.sqrt"]
    names = _names(info)
    assert "is_defined" in names and "my_bound" in names, names
    rows = {r["name"]: r for r in info["entry"]["claims"]}
    assert rows["my_bound"]["meta"]["mathema.compendium_source"] == \
        "claims/numpy.claims.yaml"
    assert rows["is_defined"]["meta"]["mathema.compendium_source"] == \
        "mathema/compendium/numpy/scalars.claims.yaml"


def test_a_proof_still_meets_the_bundled_guard(tmp_path, monkeypatch):
    import mathema
    from mathema import compendium
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=2.0"
        numpy.sqrt:
          claims:
            - name: my_bound
              statement: "for x in [1, 4], f(x) <= x"
    """)
    _write(tmp_path / "rpkg" / "__init__.py", "")
    _write(tmp_path / "rpkg" / "mod.py", '''
        import numpy as np


        def root2(x: float) -> float:
            """The square root of x."""
            return float(np.sqrt(x))
    ''')
    monkeypatch.syspath_prepend(str(tmp_path))
    from rpkg.mod import root2
    compendium.uninstall()
    compendium.install(str(tmp_path))
    try:
        rec = mathema.check(root2, claims=[{
            "name": "squares_back",
            "statement": "for x in [-4, 4], f(x) * f(x) == x",
            "route": "derive"}])
    finally:
        compendium.uninstall()
    (row,) = [p for p in rec.probes if p.name == "squares_back"]
    assert row.verdict != "proven", (row.verdict, row.sketch)


def test_a_project_row_replaces_only_its_namesake(tmp_path):
    from mathema.compendium import load_library_claims
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=2.0"
        numpy.sqrt:
          claims:
            - name: is_defined
              statement: "x >= 0"
              note: "the project's own reading"
    """)
    info = load_library_claims(str(tmp_path))["numpy.sqrt"]
    names = _names(info)
    assert names.count("is_defined") == 1
    assert "is_defined_over_complex" in names
    (row,) = [r for r in info["entry"]["claims"] if r["name"] == "is_defined"]
    assert row["note"] == "the project's own reading"


def test_two_project_files_merge_by_row_and_both_loaders_agree(tmp_path):
    from mathema.compendium import load_library_claims
    from mathema.spec import load_declared
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=2.0"
        numpy.sqrt:
          claims:
            - name: shallow_only
              statement: "for x in [0, 1], f(x) >= x"
            - name: both
              statement: "for x in [0, 1], f(x) >= 0"
    """)
    _write(tmp_path / "claims" / "deeper" / "np.claims.yaml", """
        compendium: numpy
        versions: ">=2.0"
        numpy.sqrt:
          claims:
            - name: both
              statement: "for x in [0, 1], f(x) <= 1"
    """)
    info = load_library_claims(str(tmp_path))["numpy.sqrt"]
    rows = {r["name"]: r for r in info["entry"]["claims"]}
    assert rows["both"]["statement"] == "for x in [0, 1], f(x) <= 1"
    assert "shallow_only" in rows and "is_defined" in rows
    declared = load_declared(str(tmp_path))["numpy.sqrt"]["entry"]
    assert sorted(r["name"] for r in declared["claims"]) == sorted(rows)


def test_a_replaced_definition_row_is_evidence(tmp_path):
    from mathema import compendium
    from mathema.definitions import RowBook
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=2.0"
        numpy.std:
          claims:
            - name: definition
              statement: "for a in R^n, f(a) ~= std(a, ddof=0)"
    """)
    compendium.uninstall()
    compendium.install(str(tmp_path))
    try:
        book = RowBook(str(tmp_path))
        rows = book.rows("numpy.std")
    finally:
        compendium.uninstall()
    # the project's definition row replaces the bundled one, and until
    # verify records it holding (or it is accepted) it feeds no proof;
    # it is never an axiom, and the bundled definition is not used
    defs = [r for r in rows if r.name == "definition"]
    assert all(r.standing == "evidence"
               and r.source == "claims/numpy.claims.yaml" for r in defs), defs
    (pinned,) = [r for r in rows if r.name == "definition@ddof=1"]
    assert pinned.standing == "axiom", pinned
    assert pinned.source == "mathema/compendium/numpy/reductions.claims.yaml"


def test_a_replaced_definition_row_verified_here_caps_as_evidence(tmp_path):
    from mathema import compendium
    from mathema.definitions import RowBook
    from mathema.spec import verified_dir, write_yaml
    statement = "for a in R^n, f(a) ~= std(a, ddof=0)"
    _write(tmp_path / "claims" / "numpy.claims.yaml", f"""
        compendium: numpy
        versions: ">=2.0"
        numpy.std:
          claims:
            - name: definition
              statement: "{statement}"
    """)
    import os
    import numpy
    minor = ".".join(numpy.__version__.split(".")[:2])
    os.makedirs(verified_dir(str(tmp_path)), exist_ok=True)
    write_yaml(os.path.join(verified_dir(str(tmp_path)), "numpy.std.yaml"),
               {"numpy.std": {"claims": [{
                   "name": "definition", "statement": statement,
                   "verdict": "holds",
                   "meta": {"mathema.surface": "compendium",
                            "mathema.compendium": f"compendium:numpy-{minor}"}}]}})
    compendium.uninstall()
    compendium.install(str(tmp_path))
    try:
        (row,) = [r for r in RowBook(str(tmp_path)).rows("numpy.std")
                  if r.name == "definition"]
    finally:
        compendium.uninstall()
    assert row.standing == "evidence", row
    assert row.source == "claims/numpy.claims.yaml"
