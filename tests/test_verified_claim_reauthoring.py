# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A verified claim changes only by a deliberate act. Re-authoring how
it is checked (its tolerance or its route) is a supersession, the same
as re-authoring its statement: the verified version keeps adjudicating
and the sweep names `mathema accept --as superseded`. The route a claim
was authored with is kept on its verified row, so a claim restored from
that row adjudicates the way it was written and the store settles."""
import textwrap

import pytest
import yaml


@pytest.fixture(autouse=True)
def user_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


_SOURCE = '''\
def offset(x: float) -> float:
    return x + 0.001
'''


def _project(tmp_path, monkeypatch, module, claims_yaml):
    (tmp_path / f"{module}.py").write_text(_SOURCE)
    (tmp_path / f"{module}.claims.yaml").write_text(
        textwrap.dedent(claims_yaml))
    monkeypatch.syspath_prepend(str(tmp_path))


def _claims(tmp_path, module, body):
    (tmp_path / f"{module}.claims.yaml").write_text(textwrap.dedent(body))


def _row(tmp_path, key, name):
    path = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    entry = yaml.safe_load(path.read_text())[key]
    return next(c for c in entry["claims"] if c.get("name") == name)


def _key_report(out, key):
    return next(k for k in out.keys if k["key"] == key)


def test_loosening_a_tolerance_is_a_supersession(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    key = "reauth_tol.offset"
    _project(tmp_path, monkeypatch, "reauth_tol", f"""
        {key}:
          claims:
            - name: exact
              statement: 'for x in [0, 1], f(x) == x'
        """)
    verify_project(root=str(tmp_path))
    assert _row(tmp_path, key, "exact")["verdict"].startswith("falsified")
    _claims(tmp_path, "reauth_tol", f"""
        {key}:
          claims:
            - name: exact
              statement: 'for x in [0, 1], f(x) == x'
              tolerance: 0.01
        """)
    out = verify_project(root=str(tmp_path))
    assert any("exact" in p and "--as superseded" in p for p in out.problems)
    assert _key_report(out, key)["passed"] is False
    # the verified version keeps adjudicating until the change is accepted
    row = _row(tmp_path, key, "exact")
    assert row["verdict"].startswith("falsified")
    assert row.get("tolerance") is None


def test_changing_the_route_is_a_supersession(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    key = "reauth_route.offset"
    _project(tmp_path, monkeypatch, "reauth_route", f"""
        {key}:
          claims:
            - name: shifted
              statement: 'for x in [0, 1], f(x) == x + 0.001'
              route: derive
        """)
    verify_project(root=str(tmp_path))
    assert _row(tmp_path, key, "shifted")["verdict"] == "proven"
    _claims(tmp_path, "reauth_route", f"""
        {key}:
          claims:
            - name: shifted
              statement: 'for x in [0, 1], f(x) == x + 0.001'
              route: probe
        """)
    out = verify_project(root=str(tmp_path))
    assert any("shifted" in p and "--as superseded" in p
               for p in out.problems)
    assert _row(tmp_path, key, "shifted")["verdict"] == "proven"


def test_a_row_keeps_the_route_it_was_authored_with(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    key = "reauth_keep.offset"
    _project(tmp_path, monkeypatch, "reauth_keep", f"""
        {key}:
          claims:
            - name: best_route
              statement: 'for x in [0, 1], f(x) == x + 0.001'
            - name: probe_route
              statement: 'for x in [0, 1], f(x) >= 0'
              route: probe
        """)
    verify_project(root=str(tmp_path))
    assert _row(tmp_path, key, "best_route")["authored"]["route"] == "best"
    assert _row(tmp_path, key, "probe_route")["authored"]["route"] == "probe"


def test_an_unchanged_best_route_claim_is_no_supersession(tmp_path,
                                                         monkeypatch):
    from mathema.verify import verify_project
    key = "reauth_same.offset"
    _project(tmp_path, monkeypatch, "reauth_same", f"""
        {key}:
          claims:
            - name: shifted
              statement: 'for x in [0, 1], f(x) == x + 0.001'
        """)
    verify_project(root=str(tmp_path))
    out = verify_project(root=str(tmp_path), all=True)
    assert not out.problems, out.problems


def test_a_restored_claim_settles_on_the_next_sweep(tmp_path, monkeypatch):
    # authored with the default route, proven by derivation: removed from
    # the claims file, it is restored from its verified row with the
    # route it was written with, so the claim set is unchanged and the
    # very next sweep is fresh
    from mathema.verify import verify_project
    key = "reauth_restore.offset"
    _project(tmp_path, monkeypatch, "reauth_restore", f"""
        {key}:
          claims:
            - name: shifted
              statement: 'for x in [0, 1], f(x) == x + 0.001'
        """)
    verify_project(root=str(tmp_path))
    assert _row(tmp_path, key, "shifted")["route"].startswith("derive")
    _claims(tmp_path, "reauth_restore", f"{key}:\n  claims: []\n")
    out = verify_project(root=str(tmp_path))
    assert out.fresh == 1 and out.adjudicated == 0, out.lines
    assert _row(tmp_path, key, "shifted")["verdict"] == "proven"


def test_a_legacy_row_without_an_authored_route_still_reads(tmp_path,
                                                          monkeypatch):
    # a row written before the authored route was kept: an authored
    # default route is no change, an explicit different one is
    from mathema.spec import write_yaml
    from mathema.verify import verify_project
    key = "reauth_legacy.offset"
    _project(tmp_path, monkeypatch, "reauth_legacy", f"""
        {key}:
          claims:
            - name: shifted
              statement: 'for x in [0, 1], f(x) == x + 0.001'
        """)
    verify_project(root=str(tmp_path))
    path = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    doc = yaml.safe_load(path.read_text())
    for c in doc[key]["claims"]:
        (c.get("authored") or {}).pop("route", None)
    write_yaml(str(path), doc)
    out = verify_project(root=str(tmp_path), all=True)
    assert not out.problems, out.problems
    _claims(tmp_path, "reauth_legacy", f"""
        {key}:
          claims:
            - name: shifted
              statement: 'for x in [0, 1], f(x) == x + 0.001'
              route: probe
        """)
    doc = yaml.safe_load(path.read_text())
    for c in doc[key]["claims"]:
        (c.get("authored") or {}).pop("route", None)
    write_yaml(str(path), doc)
    out = verify_project(root=str(tmp_path))
    assert any("shifted" in p and "--as superseded" in p
               for p in out.problems)


def test_a_tolerance_spelled_differently_is_the_same_tolerance(tmp_path,
                                                              monkeypatch):
    from mathema.verify import verify_project
    key = "reauth_spell.offset"
    _project(tmp_path, monkeypatch, "reauth_spell", f"""
        {key}:
          claims:
            - name: close
              statement: 'for x in [0, 1], f(x) == x'
              tolerance: 1e-2
        """)
    verify_project(root=str(tmp_path))
    out = verify_project(root=str(tmp_path), all=True)
    assert not any("superseded" in p for p in out.problems), out.problems


def _accept(root, key, name, as_):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    apply_acceptance(plan_acceptance(str(root), key, name, as_, by="tester"))


def test_a_superseding_version_survives_its_own_removal(tmp_path,
                                                        monkeypatch):
    # membership is append-only for the new version too: once the
    # superseding claim is verified, deleting it from the claims file
    # repopulates it from its row like any other verified claim
    from mathema.verify import verify_project
    key = "reauth_sup.offset"
    _project(tmp_path, monkeypatch, "reauth_sup", f"""
        {key}:
          claims:
            - name: bound
              statement: 'for x in [0, 1], f(x) >= 0'
        """)
    verify_project(root=str(tmp_path))
    _claims(tmp_path, "reauth_sup", f"""
        {key}:
          claims:
            - name: bound
              statement: 'for x in [0, 1], f(x) >= -1'
        """)
    verify_project(root=str(tmp_path))
    _accept(tmp_path, key, "bound", "superseded")
    verify_project(root=str(tmp_path))
    assert "-1" in _row(tmp_path, key, "bound")["statement"]
    _claims(tmp_path, "reauth_sup", f"{key}:\n  claims: []\n")
    out = verify_project(root=str(tmp_path))
    assert not out.problems, out.problems
    assert "-1" in _row(tmp_path, key, "bound")["statement"]
    out = verify_project(root=str(tmp_path), all=True)
    assert "-1" in _row(tmp_path, key, "bound")["statement"]


def test_a_new_law_under_a_discovered_name_survives_its_removal(
        tmp_path, monkeypatch):
    from mathema.verify import verify_project
    key = "reauth_disc.offset"
    _project(tmp_path, monkeypatch, "reauth_disc", f"""
        {key}:
          claims:
            - name: bound
              statement: 'for x in [0, 1], f(x) >= 1'
        """)
    verify_project(root=str(tmp_path))
    _accept(tmp_path, key, "bound", "discovery")
    _claims(tmp_path, "reauth_disc", f"""
        {key}:
          claims:
            - name: bound
              statement: 'for x in [0, 1], f(x) >= 0'
        """)
    verify_project(root=str(tmp_path))
    assert _row(tmp_path, key, "bound")["verdict"] == "proven"
    _claims(tmp_path, "reauth_disc", f"{key}:\n  claims: []\n")
    verify_project(root=str(tmp_path))
    verify_project(root=str(tmp_path), all=True)
    assert _row(tmp_path, key, "bound")["statement"].endswith(">= 0")


_DOC_SOURCE = '''\
def sq(x):
    """Square.

    Claims:
        nonneg: for x in [-10, 10], sq(x) >= 0
    """
    return x * x
'''


def test_a_claim_stated_two_ways_is_not_recorded_until_they_agree(
        tmp_path, monkeypatch):
    import warnings

    from mathema.verify import verify_project
    key = "reauth_twoway.sq"
    (tmp_path / "reauth_twoway.py").write_text(_DOC_SOURCE)
    _claims(tmp_path, "reauth_twoway", f"""
        {key}:
          claims:
            - name: nonneg
              statement: 'for x in [-10, 10], sq(x) >= -1'
        """)
    monkeypatch.syspath_prepend(str(tmp_path))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for _ in range(2):
            out = verify_project(root=str(tmp_path))
            assert any("nonneg" in p and "docstring" in p
                       for p in out.problems), out.problems
            with pytest.raises(StopIteration):
                _row(tmp_path, key, "nonneg")
    # the author makes the two surfaces agree: the claim adjudicates and
    # the sweep passes without any acceptance
    _claims(tmp_path, "reauth_twoway", f"""
        {key}:
          claims:
            - name: nonneg
              statement: 'for x in [-10, 10], sq(x) >= 0'
        """)
    out = verify_project(root=str(tmp_path))
    assert not out.problems, out.problems
    assert _row(tmp_path, key, "nonneg")["statement"].endswith(">= 0")


def test_docsync_settles_a_claim_stated_two_ways(tmp_path, monkeypatch):
    # the remedy the sweep names works: docsync resolves toward the
    # docstring, and the next sweep records that version and passes
    import warnings

    from mathema.cli import main
    from mathema.verify import verify_project
    key = "reauth_settle.sq"
    (tmp_path / "reauth_settle.py").write_text(_DOC_SOURCE)
    _claims(tmp_path, "reauth_settle", f"""
        {key}:
          claims:
            - name: nonneg
              statement: 'for x in [-10, 10], sq(x) >= -1'
        """)
    monkeypatch.syspath_prepend(str(tmp_path))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        verify_project(root=str(tmp_path))
        assert main(["docsync", "reauth_settle", "--root", str(tmp_path),
                     "--yes"]) == 0
    out = verify_project(root=str(tmp_path))
    assert not out.problems, out.problems
    assert _row(tmp_path, key, "nonneg")["statement"].endswith(">= 0")
