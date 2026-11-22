# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about `mathema.record_term`, the record-term
document format, are stated over.

Each takes an index into the conformance vectors
(`tests/data/record_language_vectors.json`), into the record-language
oracle's catalogues of terms and values, or into its definitions, and
returns the truth of one statement, so a claim reads `f(i) == True`.
The vectors state each valid document's canonical text and hash; the
oracle's `member` (`tests/_record_language_oracle.py`) is the written
meaning a canonical form and a built definition must keep."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_VECTORS = json.loads((_HERE.parent / "tests" / "data" / "record_language_vectors.json")
                      .read_text(encoding="utf-8"))["vectors"]
VALID = [v for v in _VECTORS if not v.get("invalid")]
INVALID = [v for v in _VECTORS if v.get("invalid")]


def _oracle_support():
    spec = importlib.util.spec_from_file_location(
        "record_language_oracle_support",
        _HERE.parent / "tests" / "claims" / "record_language_oracle_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REF = _oracle_support()
TERMS = REF.TERMS
VALUES = REF.VALUES
DEFINITIONS = REF.DOCUMENTS


def _rt():
    from mathema import record_term
    return record_term


def _member(document, value, bound=None) -> bool:
    return REF._load().member(document, value, bound=bound)


def a_valid_vector_has_its_canonical_text_and_hash(i: int) -> bool:
    """Whether valid vector `i` is accepted by `validate` and has the
    canonical text and hash the vector states."""
    rt, vector = _rt(), VALID[int(i)]
    document = copy.deepcopy(vector["document"])
    rt.validate(document)
    return (rt.canonical_text(document) == vector["canonical"]
            and rt.term_hash(document) == vector["hash"])


def an_invalid_vector_is_refused(i: int) -> bool:
    """Whether `validate`, `canonical_text` and `term_hash` each refuse
    invalid vector `i` with `InvalidTerm`, and `is_definition` is false
    of it."""
    rt, document = _rt(), INVALID[int(i)]["document"]
    for read in (rt.validate, rt.canonical_text, rt.term_hash):
        try:
            read(copy.deepcopy(document))
        except rt.InvalidTerm:
            continue
        return False
    return rt.is_definition(copy.deepcopy(document)) is False


def canonical_is_idempotent(t: int) -> bool:
    """Whether the canonical form of catalogue term `t` is its own
    canonical form."""
    rt = _rt()
    once = rt.canonical(copy.deepcopy(TERMS[int(t)]))
    return rt.canonical(copy.deepcopy(once)) == once


def canonical_keeps_the_written_meaning(t: int, v: int) -> bool:
    """Whether catalogue term `t` and its canonical form hold value `v`
    alike, by the oracle's written meaning."""
    term = TERMS[int(t)]
    return _member(_rt().canonical(copy.deepcopy(term)), VALUES[int(v)]) == _member(
        term, VALUES[int(v)])


def built_definitions_keep_the_written_meaning(d: int, e: int, v: int) -> bool:
    """Whether, for definitions `d` and `e` and value `v`, under each
    bound: the complement of `d` holds `v` exactly when `d`'s other
    bound does not; their union and intersection hold it as `or` and
    `and`; the record of the two as fields `a` (required) and `b`
    (optional) holds a map exactly as its fields do; and a list of `d`
    of one or two items holds a list exactly when each item is in
    `d`."""
    rt = _rt()
    a, b, value = DEFINITIONS[int(d)], DEFINITIONS[int(e)], VALUES[int(v)]
    other = {"at_most": "at_least", "at_least": "at_most"}
    record = rt.record_of([("a", a, True), ("b", b, False)])
    listed = rt.list_of(a, 1, 2)
    for bound in ("at_most", "at_least"):
        in_a, in_b = _member(a, value, bound), _member(b, value, bound)
        if _member(rt.complement_of(a), value, bound) != (not _member(a, value, other[bound])):
            return False
        if _member(rt.union_of(a, b), value, bound) != (in_a or in_b):
            return False
        if _member(rt.inter_of(a, b), value, bound) != (in_a and in_b):
            return False
        as_record = {"a": value, "b": value}
        if _member(record, as_record, bound) != (in_a and in_b):
            return False
        if _member(listed, [value], bound) != in_a:
            return False
    return True
