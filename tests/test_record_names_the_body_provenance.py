# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record proved from a body that arrived as KOINE names where the
body came from (`meta["mathema.provenance"]`: the frontend that wrote
it and its `koine_hash`), a record of a Python function read from its
source carries no such key, and verify re-adjudicates a record whose
body or frontend moved under an unchanged form."""
import sys
import textwrap
from dataclasses import replace

import pytest

import mathema
from mathema.koine import Document, facts_from_koine, koine_hash
from mathema.spec import to_spec
from tests._koine_docs import golden, golden_text, koine_fixture

GROWTH = "for r in [-1, 5], for x in [-10, 10], f(x, r) == x * (1 + r)"


def _carrying(d: Document, provenance=None):
    """A callable computing `growth` whose injected facts carry `d`."""
    def growth(x, r):
        if r < -1:
            raise ValueError("rate below -1")
        return x * (1 + r)
    growth.__mathema_facts__ = replace(facts_from_koine(d), provenance=provenance)
    return growth


def test_the_record_names_the_frontend_and_the_koine_hash():
    d = golden("growth_py")
    spec = to_spec(mathema.check(_carrying(d), claims=[GROWTH]))
    assert spec["meta"]["mathema.provenance"] == {
        "frontend": {"language": "py", "name": "mathema", "version": "0"},
        "koine_hash": koine_hash(d)}


def test_supplied_provenance_is_kept_beside_the_hash_core_computes():
    d = golden("growth_py")
    supplied = {"frontend": {"language": "py", "name": "writer", "version": "2.1"},
                "koine_hash": "not the hash", "agreement": {"sampled": 200}}
    spec = to_spec(mathema.check(_carrying(d, supplied), claims=[GROWTH]))
    assert spec["meta"]["mathema.provenance"] == {
        "frontend": {"language": "py", "name": "writer", "version": "2.1"},
        "koine_hash": koine_hash(d), "agreement": {"sampled": 200}}


def test_a_python_function_read_from_its_source_has_no_provenance_key():
    spec = to_spec(mathema.check(koine_fixture().growth, claims=[GROWTH]))
    assert "mathema.provenance" not in (spec.get("meta") or {})


# --- freshness ---------------------------------------------------------------

MODULE = '''
import pathlib
from dataclasses import replace

from mathema.koine import facts_from_koine

_TEXT = (pathlib.Path(__file__).parent / "growth.koi").read_text()


def growth(x, r):
    if r < -1:
        raise ValueError("rate below -1")
    return x * (1 + r)


growth.__mathema_facts__ = replace(facts_from_koine(_TEXT), form="label:growth")
'''

CLAIMS = f"""
bodymod.growth:
  claims:
    - name: growth
      statement: '{GROWTH}'
"""


def _project(tmp_path, monkeypatch, koi: str):
    (tmp_path / "bodymod.py").write_text(MODULE)
    (tmp_path / "growth.koi").write_text(koi)
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "bodymod.claims.yaml").write_text(textwrap.dedent(CLAIMS))
    monkeypatch.syspath_prepend(str(tmp_path))


def _sweep(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    monkeypatch.delitem(sys.modules, "bodymod", raising=False)
    return {row["key"]: row for row in verify_project(str(tmp_path)).keys}


def _stored(tmp_path):
    from mathema.spec import load_verified
    return load_verified(str(tmp_path))["bodymod.growth"]["entry"]


EQUAL_BODY = ("operator::binary::multiplication(x, g)",
              "operator::binary::addition(x, operator::binary::multiplication(x, r))")


@pytest.mark.needs_full_proof_budget
def test_a_changed_koine_hash_makes_the_derive_proved_claims_stale(tmp_path, monkeypatch):
    text = golden_text("growth_py")
    _project(tmp_path, monkeypatch, text)
    first = _sweep(tmp_path, monkeypatch)["bodymod.growth"]
    rows = {c["name"]: c for c in _stored(tmp_path)["claims"]}
    assert (rows["growth"]["verdict"], rows["growth"]["route"]) == ("proven", "derive")
    assert first["why"] == "no baseline record"
    assert _sweep(tmp_path, monkeypatch)["bodymod.growth"]["why"] == "fresh"

    moved = text.replace(*EQUAL_BODY)
    assert koine_hash(Document.parse(moved)) != koine_hash(Document.parse(text))
    (tmp_path / "growth.koi").write_text(moved)
    again = _sweep(tmp_path, monkeypatch)["bodymod.growth"]
    assert again["why"] == "body changed"
    stored = _stored(tmp_path)
    assert stored["identity"]["form"] == "label:growth"
    assert stored["meta"]["mathema.provenance"]["koine_hash"] == \
        koine_hash(Document.parse(moved))
    assert _sweep(tmp_path, monkeypatch)["bodymod.growth"]["why"] == "fresh"


@pytest.mark.needs_full_proof_budget
def test_a_changed_frontend_version_makes_the_record_stale(tmp_path, monkeypatch):
    text = golden_text("growth_py")
    _project(tmp_path, monkeypatch, text)
    _sweep(tmp_path, monkeypatch)
    newer = text.replace('name: "mathema", version: "0"', 'name: "mathema", version: "1"')
    assert koine_hash(Document.parse(newer)) == koine_hash(Document.parse(text))
    (tmp_path / "growth.koi").write_text(newer)
    assert _sweep(tmp_path, monkeypatch)["bodymod.growth"]["why"] == "frontend changed"
    assert _stored(tmp_path)["meta"]["mathema.provenance"]["frontend"]["version"] == "1"


# --- a callee whose body moved under a stable form ---------------------------

def _callee(koine_hash_: str, version: str = "0") -> tuple:
    """A dependency entry and the callee's stored record, both under the
    form label `label:g`, the record proved from body `a`."""
    dep = {"name": "g", "kind": "function", "key": "calleemod.g", "form": "label:g",
           "provenance": {"frontend": {"name": "mathema", "version": version},
                          "koine_hash": koine_hash_}}
    verified = {"calleemod.g": {"entry": {
        "identity": {"form": "label:g"}, "claims": [],
        "meta": {"mathema.provenance": {"frontend": {"name": "mathema", "version": "0"},
                                        "koine_hash": "a"}}}}}
    return dep, verified


def test_a_callee_whose_body_moved_under_the_same_form_is_stale():
    from mathema.spec import _dependency_state
    assert _dependency_state(*_callee("a")) == "current"
    assert _dependency_state(*_callee("b")) == "stale"
    assert _dependency_state(*_callee("a", version="1")) == "stale"


def test_a_python_callee_carries_no_provenance_and_stays_current():
    from mathema.spec import _dependency_state
    dep = {"name": "g", "kind": "function", "key": "calleemod.g", "form": "abc"}
    verified = {"calleemod.g": {"entry": {"identity": {"form": "abc"}, "claims": []}}}
    assert _dependency_state(dep, verified) == "current"


def test_a_dependency_entry_names_the_provenance_of_a_koine_callee(tmp_path, monkeypatch):
    import importlib
    from mathema.inventory import function_dependencies
    _project(tmp_path, monkeypatch, golden_text("growth_py"))
    (tmp_path / "callermod.py").write_text(
        "from bodymod import growth\n\n\n"
        "def caller(x, r):\n    return growth(x, r) + 1\n\n\n"
        "def plain(x):\n    return x\n\n\n"
        "def plain_caller(x):\n    return plain(x) + 1\n")
    monkeypatch.delitem(sys.modules, "bodymod", raising=False)
    monkeypatch.delitem(sys.modules, "callermod", raising=False)
    mod = importlib.import_module("callermod")
    deps = {d["name"]: d for d in function_dependencies(mod.caller)}
    assert deps["growth"]["provenance"]["koine_hash"] == \
        koine_hash(Document.parse(golden_text("growth_py")))
    assert all("provenance" not in d for d in function_dependencies(mod.plain_caller))


@pytest.mark.needs_full_proof_budget
def test_a_caller_of_a_callee_whose_body_moved_is_not_fresh(tmp_path, monkeypatch):
    text = golden_text("growth_py")
    _project(tmp_path, monkeypatch, text)
    (tmp_path / "callermod.py").write_text(
        "from bodymod import growth\n\n\n"
        "def caller(x: float, r: float) -> float:\n    return growth(x, r) + 1\n")
    (tmp_path / "claims" / "callermod.claims.yaml").write_text(textwrap.dedent("""
        callermod.caller:
          claims:
            - name: shifted
              statement: 'for r in [-1, 5], for x in [-10, 10], f(x, r) == x * (1 + r) + 1'
    """))

    def sweep():
        monkeypatch.delitem(sys.modules, "callermod", raising=False)
        return _sweep(tmp_path, monkeypatch)

    sweep()
    assert sweep()["callermod.caller"]["why"] == "fresh"
    (tmp_path / "growth.koi").write_text(text.replace(*EQUAL_BODY))
    assert sweep()["callermod.caller"]["why"] == "dependency changed"
