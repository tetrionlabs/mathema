# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Relations between two record languages, each decided from the one
question `solver_question.find_member` over the membership functions
of the two definitions (`record_membership`).

Draft, not part of the public interface. The words are those of
`mathema.domain_relations`: `subset`, `not subset`, `disjoint`, `=` and
`!=`. A definition that is not exact states two bounds, `at_least`
holding every member and `at_most` only members. "No value breaks the
relation" is asked of the bounds that make the set of breaking values
widest, and is then a proof for the languages between the bounds; a
breaking value is asked of the bounds that make it narrowest, and is
then a value that breaks the relation for every language between them.
For exact definitions the two questions are one.

    A subset B     breaking value: in A, outside B
    A disjoint B   breaking value: in A and in B
    A = B          breaking value: in one and outside the other

`not subset` and `!=` are proven by a breaking value of `subset` and
`=`, and falsified when none exists.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..regular import InvalidTerm
from . import record_membership, solver_question

WORDS = ("subset", "not subset", "disjoint", "=", "!=")
_UNIVERSAL = {"subset": "subset", "not subset": "subset", "disjoint": "disjoint",
              "=": "=", "!=": "="}


@dataclass(frozen=True)
class Decision:
    """How a relation was decided: `verdict` is `proven`, `falsified`
    or `unknown`; `reason` says why in a sentence; `witness` is
    `{"value": the JSON value}` when the verdict rests on a value, null
    being a value, and None when it rests on none."""
    verdict: str
    reason: str
    witness: "dict | None" = None


def _questions(word: str, left: tuple, right: tuple) -> list:
    """The questions whose members break the universal relation `word`,
    each as `(widest, narrowest)`, a question being `(inside,
    outside)`. `left` and `right` are `(at_most, at_least)` documents."""
    (a_most, a_least), (b_most, b_least) = left, right
    if word == "disjoint":
        return [(([a_least, b_least], []), ([a_most, b_most], []))]
    forward = (([a_least], [b_most]), ([a_most], [b_least]))
    if word == "subset":
        return [forward]
    return [forward, (([b_least], [a_most]), ([b_most], [a_least]))]


def inconsistency(documents: tuple, *, timeout_ms: int = 5000) -> "str | None":
    """Intent:
        Why the `(at_most, at_least)` membership documents of a
        definition describe no language, or None when they do: a value
        of its at_most outside its at_least (the at_most holds only
        members and the at_least every member, so the one is inside the
        other), named; or no answer to that question, with the reason.
        An exact definition, one document twice, always describes its
        language.
    """
    at_most, at_least = documents
    if at_most is at_least:
        return None
    found = solver_question.find_member([at_most], [at_least], timeout_ms=timeout_ms)
    if found.status == "none":
        return None
    if found.status == "member":
        return (f"the definition's at_most holds {found.member!r}, which its at_least does "
                f"not, so it describes no language")
    return (f"whether the definition's at_most lies inside its at_least has no answer "
            f"({found.reason})")


def decide(word: str, left, right, *, timeout_ms: int = 5000) -> Decision:
    """Intent:
        Decide `left <word> right` for two record-language definitions.
        `proven` or `falsified` as the module states, a breaking value
        carried as the witness; `unknown` with the reason when a
        definition has no membership document, when a definition
        describes no language (`inconsistency`), when the bounds leave
        the relation open, or when the question has no answer.

    Raises:
        ValueError: `word` is not one of `WORDS`.
        InvalidTerm: a definition is not a record-language definition.
    """
    if word not in WORDS:
        raise ValueError(f"a relation word is one of {', '.join(WORDS)}, not {word!r}")
    try:
        documents = (record_membership.membership_documents(left),
                     record_membership.membership_documents(right))
    except record_membership.Declined as e:
        return Decision("unknown", str(e))
    for pair in documents:
        why = inconsistency(pair, timeout_ms=timeout_ms)
        if why is not None:
            return Decision("unknown", why)
    universal = _UNIVERSAL[word]
    holds, breaks = (("proven", "falsified") if word == universal
                     else ("falsified", "proven"))
    why = ""
    none_breaks = True
    for widest, narrowest in _questions(universal, *documents):
        found = solver_question.find_member(*widest, timeout_ms=timeout_ms)
        if found.status == "none":
            continue
        none_breaks = False
        if narrowest != widest:
            found = solver_question.find_member(*narrowest, timeout_ms=timeout_ms)
        if found.status == "member":
            said = f"a value breaks {universal}" + (f"; {found.reason}" if found.reason else "")
            return Decision(breaks, said, {"value": found.member})
        why = why or found.reason or ("the bounds of a definition that is not exact leave "
                                      "the relation open")
    if none_breaks:
        return Decision(holds, f"no value breaks {universal}")
    return Decision("unknown", why)


__all__ = ["Decision", "InvalidTerm", "WORDS", "decide", "inconsistency"]
