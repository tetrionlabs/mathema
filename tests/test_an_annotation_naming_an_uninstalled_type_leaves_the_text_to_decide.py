# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter annotated with a type mathema cannot resolve (a library
that is not installed here, a name the module never binds) carries no
missing-value policy of its own: the claim's text decides, as for a
parameter with no annotation. So the canonical text mathema renders for
such a claim re-parses to the same claim and the same verdict, and is
never refused as misspecified. A slot type mathema does know to hold no
hole (`str`) still refuses a written `{missing}`."""
from typing import Optional

from mathema.conjecture import check_conjectures, claim
from mathema.domain import NO_ANNOTATION
from mathema.spec import canonical_claim_text
from mathema.types import missing_policy_from_signature


def entries(A: "nosuchlib.Matrix") -> float:  # noqa: F821
    """The sum of every entry of a matrix given as rows."""
    return float(sum(sum(r) for r in A))


def maybe_entries(A: Optional["nosuchlib.Matrix"]) -> float:  # noqa: F821
    return 0.0 if A is None else entries(A)


def shout(s: str) -> str:
    return s.upper()


def test_the_defaults_are_those_of_an_unannotated_parameter():
    (policy,) = missing_policy_from_signature(entries).values()
    assert policy.absent == NO_ANNOTATION.absent
    assert policy.members == NO_ANNOTATION.members
    assert not policy.annotated
    (optional,) = missing_policy_from_signature(maybe_entries).values()
    assert optional.absent is True


def test_the_canonical_text_reparses_to_the_same_claim_and_verdict():
    original = claim("for A in R^(m,n), f(A) == f(A)", route="probe")
    restored = claim(canonical_claim_text(original), route="probe")
    assert restored.domain["A"].absent
    (before,) = check_conjectures(entries, [original], extensive=False)
    (after,) = check_conjectures(entries, [restored], extensive=False)
    assert not after.verdict.startswith("skipped"), (after.verdict, after.note)
    assert before.verdict == after.verdict, (before.verdict, before.note,
                                             after.verdict, after.note)
    assert canonical_claim_text(restored) == canonical_claim_text(original)


def test_a_known_slot_type_without_a_hole_still_refuses_a_written_hole():
    (p,) = check_conjectures(shout, [claim("for s in {missing}, f(s) == s",
                                          route="probe")])
    assert p.verdict == "skipped:misspecified", (p.verdict, p.note)
    assert "has no hole" in (p.note or ""), p.note
