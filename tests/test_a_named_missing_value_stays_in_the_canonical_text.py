# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The canonical text of a claim keeps a missing value its author named.
A union beside an interval stays a union (`[0.0, 1.0] | {absent}`,
`[0.0, 1.0] | {nan}`), a named type keeps only what was written beside
it (`R|absent`), a set keeps its members and a type clause that differs
from the default stays as written. Read back, from the text or from a
record, the claim has the domain it was written with, so it is judged
at the same named values on the derive and probe routes, and its
canonical text is a fixed point. A claim that names a value, and the
same claim naming none, are different claims with different
fingerprints. A domain that names nothing keeps the text and
fingerprint it had. A type clause that spells out exactly the default
(`: float|absent|missing`) names nothing, and has the text of the plain
interval."""
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.spec import (canonical_claim_text, claims_fingerprint, entry_claims,
                          render_claim_text)
from mathema.sync import _completed


def unannotated(x):
    return x


def floats(x: float) -> float:
    return x


def optional(x: Optional[float]) -> float:
    return x  # type: ignore[return-value]


def whole(x: int) -> int:
    return x


def negative_only_at_none(x):
    if x is None:
        return -1.0
    return 1.0 if x != x else x


def negative_only_at_nan(x):
    if x is None:
        return 1.0
    return -1.0 if x != x else x


def negative_only_at_none_float(x: float) -> float:
    if x is None:
        return -1.0
    return 1.0 if x != x else x


def negative_only_at_nan_float(x: float) -> float:
    if x is None:
        return 1.0
    return -1.0 if x != x else x


def _law(domain: str) -> str:
    return f"for x in {domain}, f(x) >= 0"


def _domain_text(text: str) -> str:
    assert text.startswith("for x in ") and text.endswith(", f(x) >= 0"), text
    return text[len("for x in "):-len(", f(x) >= 0")]


def _canonical(domain: str, fn=None) -> str:
    return _domain_text(canonical_claim_text(_completed(claim(_law(domain)), fn)))


def _fingerprint(domain: str, fn=None) -> str:
    return claims_fingerprint([{"name": "c", "statement": _law(domain)}], fn=fn)


# what the author wrote, and its canonical text read without a function
NAMED = [
    ("[0, 1] | {None}", "[0.0, 1.0] | {absent}"),
    ("[0, 1] | {absent}", "[0.0, 1.0] | {absent}"),
    ("[0,1]|None", "[0.0, 1.0] | {absent}"),
    ("[0, 1] | {nan}", "[0.0, 1.0] | {nan}"),
    ("[0,1]|nan", "[0.0, 1.0] | {nan}"),
    ("[0, 1] | {missing}", "[0.0, 1.0] | {missing}"),
    ("[0, 1] | {None, nan}", "[0.0, 1.0] | {absent, nan}"),
    ("[0, 1] | {None, missing}", "[0.0, 1.0] | {absent, missing}"),
    ("(0, 1] | {None}", "(0.0, 1.0] | {absent}"),
    ("[0, inf) | {None}", "[0.0, inf) | {absent}"),
    ("[0, 1] | [2, 3] | {nan}", "[0.0, 1.0] | [2.0, 3.0] | {nan}"),
    ("[0, 1] \\ {0.5} | {None}", "[0.0, 1.0] \\ {0.5} | {absent}"),
    ("[0, 1] | {0.5, None}", "[0.0, 1.0] | {0.5} | {absent}"),
    ("[0, 1] : float|absent", "[0.0, 1.0] : float|absent"),
    ("[0, 1] : float|nan", "[0.0, 1.0] : float|nan"),
    ("[0, 1] : float|absent|nan", "[0.0, 1.0] : float|absent|nan"),
    ("{1, None}", "{1, absent}"),
    ("{1, nan}", "{1, nan}"),
    ("R | {None}", "R|absent"),
    ("R|absent", "R|absent"),
    ("R | {nan}", "R|nan"),
    ("Z | {None}", "Z|absent"),
]
NAMED_IDS = [written for written, _canonical_text in NAMED]
FUNCTIONS = [None, unannotated, floats, optional]
FUNCTION_IDS = ["no function", "unannotated", "float", "Optional[float]"]


@pytest.mark.parametrize("written, canonical", NAMED, ids=NAMED_IDS)
def test_the_canonical_text_keeps_the_named_value(written, canonical):
    assert _canonical(written) == canonical


@pytest.mark.parametrize("fn", FUNCTIONS, ids=FUNCTION_IDS)
@pytest.mark.parametrize("written, _canonical_text", NAMED, ids=NAMED_IDS)
def test_the_canonical_text_reads_back_as_the_domain_that_was_written(
        written, _canonical_text, fn):
    cj = claim(_law(written))
    text = canonical_claim_text(_completed(cj, fn))
    again = claim(text)
    assert again.domain == cj.domain, (text, again.domain, cj.domain)
    assert canonical_claim_text(_completed(again, fn)) == text


@pytest.mark.parametrize("unicode", [False, True], ids=["ascii", "unicode"])
@pytest.mark.parametrize("written, _canonical_text", NAMED, ids=NAMED_IDS)
def test_a_displayed_claim_reads_back_as_the_domain_that_was_written(
        written, _canonical_text, unicode):
    cj = claim(_law(written))
    shown = render_claim_text(cj, unicode=unicode)
    assert claim(shown).domain == cj.domain, shown
    assert canonical_claim_text(claim(shown)) == canonical_claim_text(cj)


@pytest.mark.parametrize("written, text, digest", [
    ("[0, 1] | {None}", "[0.0, 1.0] | {absent}", "a87ea5985529"),
    ("[0, 1] | {nan}", "[0.0, 1.0] | {nan}", "c3d97f2d0b76"),
    ("[0, 1] | {missing}", "[0.0, 1.0] | {missing}", "e251b751d124"),
    ("[0, 1]", "[0.0, 1.0] : float|absent|missing", "bc746253295f"),
])
def test_a_named_value_has_the_text_and_fingerprint_pinned_here(written, text, digest):
    assert (_canonical(written), _fingerprint(written)) == (text, digest)


@pytest.mark.parametrize("fn", FUNCTIONS, ids=FUNCTION_IDS)
def test_naming_none_naming_nan_and_naming_nothing_are_three_claims(fn):
    domains = ("[0, 1] | {None}", "[0, 1] | {nan}", "[0, 1]")
    assert len({_canonical(d, fn) for d in domains}) == 3
    assert len({_fingerprint(d, fn) for d in domains}) == 3


@pytest.mark.parametrize("fn", FUNCTIONS, ids=FUNCTION_IDS)
@pytest.mark.parametrize("named, plain", [
    ("R | {None}", "R"), ("R | {nan}", "R"), ("Z | {None}", "Z"),
    ("[0, 1] | {None, nan}", "[0, 1] | {None}"),
    ("[0, 1] | {None, nan}", "[0, 1] | {nan}"),
    ("[0, 1] | {missing}", "[0, 1]"),
])
def test_a_claim_that_names_a_value_is_not_the_claim_without_it(named, plain, fn):
    assert _canonical(named, fn) != _canonical(plain, fn)
    assert _fingerprint(named, fn) != _fingerprint(plain, fn)


# a domain that names nothing: its canonical text and fingerprint read
# without a function, beside a `float` parameter and beside an `int` one
NOTHING_NAMED = [
    ("[0, 1]",
     "[0.0, 1.0] : float|absent|missing", "bc746253295f",
     "[0.0, 1.0] : float|missing", "5666b6b87f4b",
     "[0, 1] : int", "c16c6f0759cf"),
    ("[1, 5]",
     "[1.0, 5.0] : float|absent|missing", "d3f0e26904f0",
     "[1.0, 5.0] : float|missing", "be5802a4be24",
     "[1, 5] : int", "cc0b03c175e8"),
    ("R",
     "R|absent|missing", "3070dc29c995",
     "R|missing", "8a8f8db0d4b5",
     "R", "f54059adadb9"),
    ("Z",
     "Z|absent|missing", "0cbf931aa645",
     "Z|missing", "c9317bd2dcc8",
     "Z", "03cb304fb161"),
    ("(0, inf)",
     "(0.0, inf) : float|absent|missing", "0d569f458c84",
     "(0.0, inf) : float|missing", "05b2657489d9",
     "(0, inf) : int", "1a1ffd570cb6"),
    ("[0, 1] | [2, 3]",
     "[0.0, 1.0] | [2.0, 3.0] : float|absent|missing", "b61fa54cffbc",
     "[0.0, 1.0] | [2.0, 3.0] : float|missing", "f7b45dc49d2f",
     "[0, 1] | [2, 3] : int", "73abcd0cf68a"),
    ("[0, 1] \\ {0.5}",
     "[0.0, 1.0] \\ {0.5} : float|absent|missing", "2c613cb78154",
     "[0.0, 1.0] \\ {0.5} : float|missing", "b68dea6689e3",
     "[0, 1] \\ {0.5} : int", "33cbde3956a0"),
    ("{1, 2, 3}",
     "{1, 2, 3}", "bf3b8f87eea9",
     "{1, 2, 3}", "bf3b8f87eea9",
     "{1, 2, 3}", "bf3b8f87eea9"),
    ("[0, 5] : int",
     "[0, 5] : int", "58e47011b447",
     "[0, 5] : int", "58e47011b447",
     "[0, 5] : int", "58e47011b447"),
    ("[0, 1] : float",
     "[0.0, 1.0] : float", "22691e7b91d5",
     "[0.0, 1.0] : float", "22691e7b91d5",
     "[0.0, 1.0] : float", "22691e7b91d5"),
    ("[0, 1] \\ {None}",
     "[0.0, 1.0] : float|missing", "5666b6b87f4b",
     "[0.0, 1.0] : float|missing", "5666b6b87f4b",
     "[0, 1] : int", "c16c6f0759cf"),
    ("[0, 1] \\ {missing}",
     "[0.0, 1.0] : float|absent", "d5932b0cc3b0",
     "[0.0, 1.0] : float", "22691e7b91d5",
     "[0.0, 1.0] : float|absent", "d5932b0cc3b0"),
]


@pytest.mark.parametrize(
    "written, text, digest, float_text, float_digest, int_text, int_digest",
    NOTHING_NAMED, ids=[row[0] for row in NOTHING_NAMED])
def test_a_domain_that_names_nothing_keeps_its_text_and_fingerprint(
        written, text, digest, float_text, float_digest, int_text, int_digest):
    assert (_canonical(written), _fingerprint(written)) == (text, digest)
    assert (_canonical(written, unannotated),
            _fingerprint(written, unannotated)) == (text, digest)
    assert (_canonical(written, floats),
            _fingerprint(written, floats)) == (float_text, float_digest)
    assert (_canonical(written, whole),
            _fingerprint(written, whole)) == (int_text, int_digest)


@pytest.mark.parametrize("written", [row[0] for row in NOTHING_NAMED])
def test_the_text_of_a_domain_that_names_nothing_is_a_fixed_point(written):
    for fn in (None, floats, whole):
        text = canonical_claim_text(_completed(claim(_law(written)), fn))
        assert canonical_claim_text(_completed(claim(text), fn)) == text


# the default written out by hand names nothing: the stated limit
DEFAULT_BY_HAND = [
    ("[0, 1] : float|absent|missing", "[0, 1]", None),
    ("[0, 1] : float|absent|missing", "[0, 1]", unannotated),
    ("[0, 1] : float|missing", "[0, 1]", floats),
    ("R|absent|missing", "R", None),
    ("R | {None, missing}", "R", None),
    ("R|missing", "R", floats),
]


@pytest.mark.parametrize("by_hand, plain, fn", DEFAULT_BY_HAND)
def test_the_default_written_out_by_hand_is_the_plain_domain(by_hand, plain, fn):
    assert _canonical(by_hand, fn) == _canonical(plain, fn)
    assert _fingerprint(by_hand, fn) == _fingerprint(plain, fn)


def _row(fn, cj):
    (row,) = check_conjectures(fn, [cj])
    return row


def _from_record(row, route):
    (rebuilt,) = entry_claims({"claims": [{
        "name": "c", "statement": row.statement, "domain": row.domain,
        "route": route}]})
    return rebuilt


def _judged(row):
    return (row.verdict, row.counterexample)


# what the author wrote, whether the claim is falsified by a function
# negative only at None, and by one negative only at nan
JUDGED = [
    ("[0, 1] | {None}", True, False),
    ("[0, 1] | {nan}", False, True),
    ("[0, 1] | {None, nan}", True, True),
    ("[0, 1] | {missing}", False, True),
    ("[0, 1] : float|absent", True, False),
    ("[0, 1] : float|nan", False, True),
    ("{0.5, None}", True, False),
    ("{0.5, nan}", False, True),
]
JUDGED_IDS = [written for written, _none, _nan in JUDGED]


@pytest.mark.parametrize("annotated", [False, True], ids=["unannotated", "float"])
@pytest.mark.parametrize("written, at_none, at_nan", JUDGED, ids=JUDGED_IDS)
def test_a_proof_read_back_is_judged_at_the_values_that_were_named(
        written, at_none, at_nan, annotated):
    functions = ((negative_only_at_none_float, negative_only_at_nan_float)
                 if annotated else (negative_only_at_none, negative_only_at_nan))
    for fn, named, witness in zip(functions, (at_none, at_nan),
                                  ("x = None", "x = nan")):
        first = _row(fn, claim(_law(written)))
        assert (first.verdict == "falsified") == named, (first.verdict, first.note)
        if named:
            assert first.counterexample == witness
        from_record = _row(fn, _from_record(first, "best"))
        from_text = _row(fn, claim(canonical_claim_text(claim(_law(written)))))
        assert _judged(from_record) == _judged(first), (first.statement,
                                                        from_record.note)
        assert _judged(from_text) == _judged(first), from_text.note
        assert from_record.statement == first.statement


@pytest.mark.parametrize("annotated", [False, True], ids=["unannotated", "float"])
@pytest.mark.parametrize("written, _at_none, _at_nan", JUDGED, ids=JUDGED_IDS)
def test_a_probe_read_back_is_judged_at_the_values_that_were_named(
        written, _at_none, _at_nan, annotated):
    functions = ((negative_only_at_none_float, negative_only_at_nan_float)
                 if annotated else (negative_only_at_none, negative_only_at_nan))
    for fn in functions:
        first = _row(fn, claim(_law(written), route="probe"))
        from_record = _row(fn, _from_record(first, "probe"))
        from_text = _row(fn, claim(canonical_claim_text(claim(_law(written))),
                                   route="probe"))
        assert _judged(from_record) == _judged(first), (first.statement,
                                                        from_record.note)
        assert _judged(from_text) == _judged(first), from_text.note
        assert from_record.statement == first.statement


def test_the_default_written_out_by_hand_is_not_judged_at_none():
    row = _row(negative_only_at_none,
               claim(_law("[0, 1] : float|absent|missing")))
    assert row.verdict != "falsified", (row.verdict, row.note)
