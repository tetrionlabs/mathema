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
