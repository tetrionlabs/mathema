# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every form hash is `<frontend>:<sha>`, Python's included: a Python
function's form is written `py:<sha>`. A record written before forms
were namespaced holds a bare `<sha>`, which reads as Python's: the
code it describes is unchanged, so the next verify re-hashes the record
once (its identity, its dependency forms and its body provenance gain
`py:`, and its integrity is re-stamped) without re-adjudicating a claim,
and an acceptance or a lock taken at the bare form still stands."""
import ast
import importlib
import re
import sys

import pytest
import yaml

import mathema
from mathema.identity import form_hash, namespaced_form, same_form
from mathema.koine.facts import provenance_change

_SHA = re.compile(r"[0-9a-f]{12}")

_BODY = '''\
def halve(x: float) -> float:
    return x / 2.0


def settle(x: float) -> float:
    """Settlement amount for a signed exposure."""
    return abs(halve(x))
'''

_CLAIMS = '''\
pyform.halve:
  claims:
    - name: odd
      statement: "for x in [-5, 5], f(-x) == -f(x)"
      route: probe
pyform.settle:
  claims:
    - name: nonneg
      statement: "for x in [-5, 5], f(x) >= 0"
      route: probe
'''

_KEY = "pyform.settle"


def _parse(source: str):
    return ast.parse(source).body[0]


def test_a_python_form_hash_is_namespaced_py():
    def scaled(x: float) -> float:
        return 3.0 * x
    form = form_hash(_parse("def scaled(x):\n    return 3.0 * x\n"))
    assert form.startswith("py:") and _SHA.fullmatch(form[3:])
    live = mathema.analyze(scaled).form
    assert live.startswith("py:") and _SHA.fullmatch(live[3:])


def test_a_rename_still_keeps_the_python_form():
    a = form_hash(_parse("def f(x):\n    y = x + 1\n    return y\n"))
    b = form_hash(_parse("def g(t):\n    u = t + 1\n    return u\n"))
    assert a == b and a.startswith("py:")


def test_a_bare_recorded_form_reads_as_python_s():
    assert namespaced_form("0011aabbccdd") == "py:0011aabbccdd"
    assert namespaced_form("py:0011aabbccdd") == "py:0011aabbccdd"
    assert namespaced_form("koine-0.0.1:0011aabbccdd") == "koine-0.0.1:0011aabbccdd"
    assert namespaced_form("doc:0011aabbccdd") == "doc:0011aabbccdd"
    assert namespaced_form(None) is None and namespaced_form("") == ""
    assert same_form("0011aabbccdd", "py:0011aabbccdd")
    assert same_form("py:0011aabbccdd", "0011aabbccdd")
    assert not same_form("0011aabbccdd", "py:0011aabbccde")
    assert not same_form("0011aabbccdd", "doc:0011aabbccdd")
    assert not same_form("0011aabbccdd", "koine-0.0.1:0011aabbccdd")
    assert not same_form(None, "py:0011aabbccdd")


def test_a_bare_python_body_hash_is_the_same_body():
    now = {"koine_hash": "koine-0.0.1:aa", "frontend": {"name": "ext"},
           "body_hashes": {"ext": "koine-0.0.1:aa", "python": "py:0011aabbccdd"}}
    was = {"koine_hash": "koine-0.0.1:aa", "frontend": {"name": "ext"},
           "body_hashes": {"ext": "koine-0.0.1:aa", "python": "0011aabbccdd"}}
    assert provenance_change(now, was) is None
    moved = {**was, "body_hashes": {"ext": "koine-0.0.1:aa", "python": "0011aabbccdc"}}
    assert provenance_change(now, moved) == "body"


@pytest.fixture
def project(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    sys.modules.pop("pyform", None)
    importlib.invalidate_caches()
    (tmp_path / "pyform.py").write_text(_BODY)
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "demo.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    out = verify_project(root=str(tmp_path))
    assert not out.problems
    return tmp_path


def _record_path(root):
    return root / ".mathema" / "verified" / f"{_KEY}.yaml"


def _entry(root) -> dict:
    return yaml.safe_load(_record_path(root).read_text())[_KEY]


def _strip_namespace(root, entry: dict) -> None:
    """Rewrite the store as a release before namespaced forms wrote it:
    every `py:` form in the record and the lock file bare, the record's
    integrity stamped over that content."""
    from mathema.spec import integrity_checksum

    def bare(form):
        return form[3:] if isinstance(form, str) and form.startswith("py:") else form

    entry["identity"]["form"] = bare(entry["identity"]["form"])
    for dep in entry.get("dependencies") or []:
        if "form" in dep:
            dep["form"] = bare(dep["form"])
    for claim in entry.get("claims") or []:
        if isinstance(claim.get("accepted"), dict):
            claim["accepted"]["form"] = bare(claim["accepted"].get("form"))
    if isinstance(entry.get("locked"), dict):
        entry["locked"]["form"] = bare(entry["locked"]["form"])
    entry["identity"]["integrity"] = integrity_checksum(entry)
    _record_path(root).write_text(yaml.safe_dump({_KEY: entry}, sort_keys=False))
    locks = root / ".mathema" / "meta" / "locks.yaml"
    if locks.exists():
        data = yaml.safe_load(locks.read_text())
        for value in data.values():
            value["form"] = bare(value["form"])
        locks.write_text(yaml.safe_dump(data))


def test_an_old_store_re_hashes_once_without_re_adjudicating(project):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.locks import load_locks, lock
    from mathema.spec import integrity_matches
    from mathema.verify import verify_project

    live = mathema.analyze(sys.modules["pyform"].settle).form
    assert _entry(project)["identity"]["form"] == live
    apply_acceptance(plan_acceptance(str(project), _KEY, "nonneg", "evidence",
                                     by="lovelace"))
    lock(str(project), _KEY, live, by="lovelace")
    assert not verify_project(root=str(project)).problems
    entry = _entry(project)
    assert entry["locked"]["form"] == live
    deps = [d for d in entry.get("dependencies") or [] if d.get("form")]
    assert deps and all(d["form"].startswith("py:") for d in deps)

    _strip_namespace(project, entry)
    old = _entry(project)
    assert not old["identity"]["form"].startswith("py:")
    assert integrity_matches(old) is True

    out = verify_project(root=str(project))
    assert not out.problems
    assert (out.fresh, out.adjudicated) == (2, 0)
    healed = _entry(project)
    assert healed["identity"]["form"] == live
    assert all(d["form"].startswith("py:")
               for d in healed.get("dependencies") or [] if d.get("form"))
    assert integrity_matches(healed) is True
    claim = next(c for c in healed["claims"] if c["name"] == "nonneg")
    assert claim["verdict"] == next(c for c in old["claims"]
                                    if c["name"] == "nonneg")["verdict"]
    assert claim["accepted"]["as"] == "evidence"
    assert not claim["accepted"].get("stale")
    assert load_locks(str(project))[_KEY]["form"] == live[3:]

    once = _record_path(project).read_bytes()
    out = verify_project(root=str(project))
    assert not out.problems and out.adjudicated == 0
    assert _record_path(project).read_bytes() == once


def test_a_bare_recorded_form_that_differs_is_still_a_changed_body(project):
    from mathema.verify import verify_project
    entry = _entry(project)
    entry["identity"]["form"] = "deadbeef0000"
    from mathema.spec import integrity_checksum
    entry["identity"]["integrity"] = integrity_checksum(entry)
    _record_path(project).write_text(yaml.safe_dump({_KEY: entry}, sort_keys=False))
    out = verify_project(root=str(project))
    assert out.adjudicated >= 1
    assert _entry(project)["identity"]["form"].startswith("py:")


def _bare_lock(root, live: str) -> None:
    from mathema.locks import lock
    lock(str(root), _KEY, live[3:], by="lovelace")


def test_a_bare_lock_on_an_unchanged_body_is_no_pending_decision(project):
    from mathema.interfaces.mcp.tools import pending_decisions
    _bare_lock(project, mathema.analyze(sys.modules["pyform"].settle).form)
    rows = pending_decisions(root=str(project))["rows"]
    assert "locked-changed" not in {r[2] for r in rows}


def test_a_tripped_bare_lock_names_both_forms_namespaced(project):
    from mathema.interfaces.mcp.tools import pending_decisions
    from mathema.verify import verify_project
    live = mathema.analyze(sys.modules["pyform"].settle).form
    _bare_lock(project, live)
    src = project / "pyform.py"
    src.write_text(src.read_text().replace("return abs(halve(x))", "return halve(x)"))
    importlib.invalidate_caches()
    importlib.reload(sys.modules["pyform"])
    changed = mathema.analyze(sys.modules["pyform"].settle).form
    assert changed != live
    message = next(p for p in verify_project(root=str(project)).problems
                   if "locked at form" in p)
    assert f"locked at form {live} but the code is now {changed}" in message
    detail = next(r[3] for r in pending_decisions(root=str(project))["rows"]
                  if r[2] == "locked-changed")
    assert f"locked at {live}, code is now {changed}" in detail
