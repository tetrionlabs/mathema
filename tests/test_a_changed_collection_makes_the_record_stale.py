# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A verified record of a claim over a named collection is stale once
the collection changes: each row carries the collection's members by
position, name and hash, and verify lists the collection again and
names what moved, a member added, removed or changed, or the members
reordered. The claim's own text names only the path, so the claim is
the same claim throughout."""
import shutil
import sys
import textwrap

from mathema import _collection

_MODULE = '''
from __future__ import annotations


def percent_to_fraction(percent: float) -> float:
    """A percent as a fraction."""
    return percent / 100


def fraction_to_growth_factor(fraction: float) -> float:
    """A fraction as the factor it grows a value by."""
    return 1 + fraction


def halve(value: float) -> float:
    """Half a value."""
    return value / 2


def describe(fn) -> str:
    """One line for a function's annotations."""
    notes = dict(fn.__annotations__)
    result = notes.pop("return", "?")
    return f"({', '.join(str(note) for note in notes.values())}) -> {result}"


STAGES = (percent_to_fraction, fraction_to_growth_factor)
'''

_STAGES = "STAGES = (percent_to_fraction, fraction_to_growth_factor)"


def _project(root, module=_MODULE):
    # a rewrite of the same size within a second would otherwise be read
    # from the bytecode cached for the text before it
    shutil.rmtree(root / "__pycache__", ignore_errors=True)
    (root / "cstale.py").write_text(module)
    (root / "claims").mkdir(exist_ok=True)
    (root / "claims" / "cstale.claims.yaml").write_text(textwrap.dedent("""
        cstale.describe:
          claims:
            - name: each_stage_maps_a_float
              statement: 'for fn in cstale.STAGES, describe(fn) == "(float) -> float"'
    """))


def _why(root) -> str:
    from mathema.verify import verify_project
    sys.modules.pop("cstale", None)
    result = verify_project(str(root))
    return {entry["key"]: entry for entry in result.keys}["cstale.describe"]["why"]


def test_a_record_over_an_unchanged_collection_is_fresh(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _project(tmp_path)
    assert _why(tmp_path) == "no baseline record"
    assert _why(tmp_path) == "fresh"


def test_a_member_whose_code_changes_makes_the_record_stale(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _project(tmp_path)
    _why(tmp_path)
    _project(tmp_path, _MODULE.replace("return 1 + fraction", "return 1.0 + fraction"))
    assert _why(tmp_path) == ("the collection cstale.STAGES moved: "
                              "cstale.fraction_to_growth_factor changed")
    assert _why(tmp_path) == "fresh"


def test_a_member_added_removed_or_reordered_makes_the_record_stale(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _project(tmp_path)
    _why(tmp_path)
    _project(tmp_path, _MODULE.replace(
        _STAGES, "STAGES = (percent_to_fraction, fraction_to_growth_factor, halve)"))
    assert _why(tmp_path) == "the collection cstale.STAGES moved: cstale.halve added"
    _project(tmp_path, _MODULE.replace(_STAGES, "STAGES = (percent_to_fraction,)"))
    assert _why(tmp_path) == ("the collection cstale.STAGES moved: "
                              "cstale.fraction_to_growth_factor, cstale.halve removed")
    _project(tmp_path)
    _why(tmp_path)
    _project(tmp_path, _MODULE.replace(
        _STAGES, "STAGES = (fraction_to_growth_factor, percent_to_fraction)"))
    assert _why(tmp_path) == "the collection cstale.STAGES moved: its members reordered"


def test_a_name_that_stops_being_a_collection_makes_the_record_stale(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _project(tmp_path)
    _why(tmp_path)
    _project(tmp_path, _MODULE.replace(_STAGES, "STAGES = 2"))
    assert _why(tmp_path) == "the collection cstale.STAGES no longer resolves"


def test_a_changed_collection_is_one_of_the_triggers_that_invalidate_a_record():
    from mathema.transitions import OWN_TRIGGERS
    from mathema.verify import _fired_triggers
    quiet = dict(form=False, claims=False, defaults=False, pseudo_infinity=False,
                 definitions=False, provenance=None, library_version=None, premises=False,
                 dependency=False)
    assert _fired_triggers(**quiet) == []
    assert _fired_triggers(**quiet, collection="the collection p.C moved") == ["collection"]
    assert "collection" in OWN_TRIGGERS


def test_what_moved_is_read_from_the_two_member_lists():
    def record(*members, kind="tuple"):
        listed = [_collection.Member(i, name, digest) for i, (name, digest) in enumerate(members)]
        return _collection.collection_record("p.C", kind, listed)

    same = record(("a", "1"), ("b", "2"))
    assert _collection.collection_moved(same, record(("a", "1"), ("b", "2"))) is None
    assert _collection.collection_moved(same, record(("b", "2"), ("a", "1"))) == (
        "the collection p.C moved: its members reordered")
    assert _collection.collection_moved(same, record(("a", "1"), ("b", "3"), ("c", "4"))) == (
        "the collection p.C moved: c added, b changed")
    assert _collection.collection_moved(same, record(("a", "1"), ("b", "2"), kind="list")) == (
        "the collection p.C moved: it is now a list")
    assert _collection.collection_moved(same, None) == "the collection p.C no longer resolves"
