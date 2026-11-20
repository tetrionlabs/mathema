# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A statement about every member of a record language, decided from
the language's membership function and the statement, both in KOINE.

Draft, not part of the public interface. The statement is an expression
of the one parameter `value` (`record_terms.PARAMETER`) that is a truth
value. "For every member r of the language, the statement holds of r"
is broken by a member at which the statement is false, so the question
asked is one document: `and(member(value), not(statement))`, in which
the statement is evaluated only at members.

`every_key_is_one_of(names)` is the statement "every key of the value
is one of `names`", which a claim writes `for k in keys(r), k in
{...}`: `value::map::has_no_key_other_than(value::value_of_present(
value), [names])`. It has no value at a value that is no map.

A definition that is not exact states two bounds. "No member breaks the
statement" is asked of `at_least`, which holds every member, and a
breaking member is asked of `at_most`, which holds only members.
"""
from __future__ import annotations

from . import record_membership, record_terms as T, solver_question
from .record_relations import Decision
from .syntax import List, Name, Str, Term

NOT, AND = "operator::logic::not", "operator::logic::and"


def every_key_is_one_of(names) -> Term:
    """The statement that every key the value holds is one of `names`,
    which are distinct strings."""
    names = list(names)
    if not all(isinstance(n, str) for n in names) or len(set(names)) != len(names):
        raise ValueError(f"the names are distinct strings, not {names!r}")
    of_map = Term(T.VALUE_OF_PRESENT, (Name(T.PARAMETER),))
    return Term(T.HAS_NO_KEY_OTHER_THAN, (of_map, List(tuple(Str(n) for n in names))))


def breaking_document(node, statement):
    """The document true exactly at the members of the record-language
    node `node` at which `statement` is false, the statement evaluated
    only at members."""
    member = record_membership.membership_expression(node, Name(T.PARAMETER))
    return T.function_of_one_value(Term(AND, (member, Term(NOT, (statement,)))),
                                   name="breaks")


def _bounds(definition) -> tuple:
    """`(at_most, at_least)` nodes of a definition, checked as
    `record_membership.membership_documents` checks it."""
    record_membership.membership_documents(definition)
    if definition["exact"]:
        return definition["language"], definition["language"]
    return definition["at_most"], definition["at_least"]


def decide_every_member(definition, statement, *, timeout_ms: int = 5000) -> Decision:
    """Intent:
        Decide "the statement holds of every member" of a
        record-language definition. `falsified` with a member at which
        the statement is false; `proven` when no member breaks it and
        the statement has a value at every member; `unknown` with the
        reason otherwise, as when the statement has no value at some
        member, a definition holds a list node, or the bounds of a
        definition that is not exact leave it open.

    Raises:
        InvalidTerm: the definition is not a record-language definition.
    """
    try:
        at_most, at_least = _bounds(definition)
        narrow = breaking_document(at_most, statement)
        wide = breaking_document(at_least, statement)
    except record_membership.Declined as e:
        return Decision("unknown", str(e))
    problems = T.validate(wide)
    if problems:
        return Decision("unknown", f"the statement is not valid: {'; '.join(problems)}")
    found = solver_question.find_member([narrow], [], valued_only=True,
                                        timeout_ms=timeout_ms)
    if found.status == "member":
        return Decision("falsified", "a member breaks the statement", {"value": found.member})
    none = solver_question.find_member([wide], [], timeout_ms=timeout_ms)
    if none.status == "none":
        return Decision("proven", "no member breaks the statement")
    if none.status == "member":
        return Decision("unknown", "the bounds of a definition that is not exact leave the "
                                   "statement open")
    return Decision("unknown", found.reason or none.reason)


__all__ = ["breaking_document", "decide_every_member", "every_key_is_one_of"]
