# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema verify` checks a function after the functions its claims'
premises name, so a premise on another function's claim resolves on
the first run of a fresh project, and a cycle of such premises across
functions is reported as one.
"""
import sys
import textwrap

import pytest
import yaml


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _fresh_modules(package):
    for name in [m for m in sys.modules
                 if m == package or m.startswith(package + ".")]:
        sys.modules.pop(name, None)


def _rows(tmp_path, key):
    record = yaml.safe_load((tmp_path / ".mathema" / "verified"
                             / f"{key}.yaml").read_text())
    return {c["name"]: c for c in record[key]["claims"]}


def _order(result):
    return [row["key"] for row in result.keys]


@pytest.fixture
def helper_project(tmp_path, monkeypatch):
    """A project whose `main.f` rests on a claim of `helpers.g`."""
    _write(tmp_path / "sweepapp" / "__init__.py", "")
    _write(tmp_path / "sweepapp" / "helpers.py", """
        def g(x):
            return x * x
    """)
    _write(tmp_path / "sweepapp" / "main.py", """
        from sweepapp import helpers


        def f(x):
            return helpers.g(x) + 1
    """)
    _write(tmp_path / "claims" / "sweepapp.claims.yaml", """
        sweepapp.helpers.g:
          claims:
            - name: nonneg
              statement: "for x in [-10, 10], f(x) >= 0"
        sweepapp.main.f:
          claims:
            - name: above_one
              statement: "assuming sweepapp.helpers.g.nonneg is proven, for x in [-10, 10], f(x) >= 1"
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    _fresh_modules("sweepapp")
    yield tmp_path
    _fresh_modules("sweepapp")


def test_a_premise_on_another_functions_claim_resolves_on_the_first_run(
        helper_project):
    from mathema.verify import verify_project
    result = verify_project(str(helper_project))
    order = _order(result)
    assert order.index("sweepapp.helpers.g") < order.index("sweepapp.main.f")
    row = _rows(helper_project, "sweepapp.main.f")["above_one"]
    assert row["verdict"] in ("proven", "holds"), row
    assert (row.get("meta") or {}).get("mathema.premise") is None, row
    assert not result.problems, result.lines


def test_a_second_run_finds_the_dependent_fresh(helper_project):
    from mathema.verify import verify_project
    verify_project(str(helper_project))
    again = verify_project(str(helper_project))
    whys = {row["key"]: row["why"] for row in again.keys}
    assert whys == {"sweepapp.helpers.g": "fresh",
                    "sweepapp.main.f": "fresh"}, again.lines


@pytest.fixture
def forward_project(tmp_path, monkeypatch):
    """`a_main.f` sorts before the `z_helpers.g` its premise names, and
    `m_other.h` rests on nothing."""
    _write(tmp_path / "sweepapp" / "__init__.py", "")
    _write(tmp_path / "sweepapp" / "z_helpers.py", """
        def g(x):
            return x * x
    """)
    _write(tmp_path / "sweepapp" / "m_other.py", """
        def h(x):
            return x + 1
    """)
    _write(tmp_path / "sweepapp" / "a_main.py", """
        from sweepapp import z_helpers


        def f(x):
            return z_helpers.g(x) + 1
    """)
    _write(tmp_path / "claims" / "sweepapp.claims.yaml", """
        sweepapp.a_main.f:
          claims:
            - name: above_one
              statement: "assuming sweepapp.z_helpers.g.nonneg holds, for x in [-10, 10], f(x) >= 1"
        sweepapp.m_other.h:
          claims:
            - name: grows
              statement: "for x in [-10, 10], f(x) > x"
        sweepapp.z_helpers.g:
          claims:
            - name: nonneg
              statement: "for x in [-10, 10], f(x) >= 0"
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    _fresh_modules("sweepapp")
    yield tmp_path
    _fresh_modules("sweepapp")


def test_a_prerequisite_named_later_in_the_sweep_is_checked_first(
        forward_project):
    from mathema.verify import verify_project
    result = verify_project(str(forward_project))
    assert _order(result) == ["sweepapp.z_helpers.g", "sweepapp.a_main.f",
                              "sweepapp.m_other.h"], result.lines
    row = _rows(forward_project, "sweepapp.a_main.f")["above_one"]
    assert row["verdict"] in ("proven", "holds"), row
    assert not result.problems, result.lines


def test_a_prerequisite_outside_the_swept_targets_keeps_its_old_reading(
        forward_project):
    from mathema.verify import verify_project
    result = verify_project(str(forward_project), only=["sweepapp.a_main.f"])
    assert _order(result) == ["sweepapp.a_main.f"]
    row = _rows(forward_project, "sweepapp.a_main.f")["above_one"]
    assert row["verdict"] == "unknown", row
    assert row["meta"]["mathema.premise"] == "missing-prerequisite", row


def test_a_premise_cycle_across_functions_is_reported_as_one(
        tmp_path, monkeypatch):
    from mathema.verify import verify_project
    _write(tmp_path / "sweepapp" / "__init__.py", "")
    _write(tmp_path / "sweepapp" / "a.py", """
        def f(x):
            return 2 * x
    """)
    _write(tmp_path / "sweepapp" / "b.py", """
        def g(x):
            return x + 1
    """)
    _write(tmp_path / "claims" / "sweepapp.claims.yaml", """
        sweepapp.a.f:
          claims:
            - name: doubles
              statement: "assuming sweepapp.b.g.grows holds, for x in [0, 10], f(x) == 2*x"
        sweepapp.b.g:
          claims:
            - name: grows
              statement: "assuming sweepapp.a.f.doubles holds, for x in [0, 10], f(x) > x"
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    _fresh_modules("sweepapp")
    try:
        verify_project(str(tmp_path))
        for key, name, other in (
                ("sweepapp.a.f", "doubles", "sweepapp.b.g.grows"),
                ("sweepapp.b.g", "grows", "sweepapp.a.f.doubles")):
            row = _rows(tmp_path, key)[name]
            assert row["verdict"] == "skipped", row
            assert row["meta"]["mathema.premise"] == "dependency-cycle", row
            assert (f"premise cycle: {name} and {other} rest on each "
                    f"other") in row["note"], row
    finally:
        _fresh_modules("sweepapp")


def test_the_sweep_order_moves_only_what_a_premise_demands():
    from mathema.verify import _premise_order
    keys = ["p.a", "p.b", "p.c", "p.d"]
    rows = {"p.a": [("x", ["p.c.y"])],
            "p.c": [("y", ["outside.k.z"])],
            "p.d": [("w", ["p.b.v"])]}
    order, cycles = _premise_order(keys, rows)
    assert order == ["p.c", "p.a", "p.b", "p.d"]
    assert cycles == {}


def test_a_claim_resting_on_a_cross_function_cycle_is_caught_by_it():
    from mathema.verify import _premise_order
    keys = ["p.a", "p.b"]
    rows = {"p.a": [("x", ["p.b.y"]), ("s", ["x"]), ("free", ["p.b.t"])],
            "p.b": [("y", ["p.a.x"])]}
    _order, cycles = _premise_order(keys, rows)
    assert cycles == {"p.a": {"p.b.y", "x"}, "p.b": {"p.a.x"}}
