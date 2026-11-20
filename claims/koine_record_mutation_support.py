# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about the mutation sites of a membership
document are stated over.

The module under claim is `mathema.koine.record_mutation_sites`: the
places of a membership document at which one change can be made, each
with a stable address, and the document with one such change.

Each function takes indices into `VECTORS`, the valid conformance
vectors of the record-language term (a vector that holds a list node,
or is no definition of this kind and version, has no membership
document and every statement is true of it), a site number within the
vector's at_most document (a number past the last site makes the
statement true), and into `VALUES`. `mathema.record_language.member` on
the vector is the truth of the unchanged document."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _question_support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_question_support", _HERE / "koine_record_question_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Q = _question_support()
REF = Q.REF
VECTORS = Q.VECTORS
VALUES = Q.VALUES
#: no document of a vector has more sites than this
MOST_SITES = 120
#: the operators that have an inverse, and the operator that undoes each
INVERSE = {"swap_required_and_optional": "swap_required_and_optional",
           "negate_has_key": "negate_has_key",
           "remove_name_from_no_other_key": "add_name_to_no_other_key",
           "add_name_to_no_other_key": "remove_name_from_no_other_key"}
OPERATORS = ("drop_conjunct", "swap_required_and_optional", "negate_has_key",
             "read_null_as_unset", "remove_name_from_no_other_key",
             "add_name_to_no_other_key", "remove_choice_constant")


def _ms():
    from mathema.koine import record_mutation_sites
    return record_mutation_sites


def _rt():
    from mathema.koine import record_terms
    return record_terms


def _rl():
    from mathema import record_language
    return record_language


def _document(i: int):
    """The at_most membership document of vector `i`, or None."""
    documents = Q._vector_documents(i)
    return None if documents is None else documents[0]


def _site(i: int, s: int):
    """`(document, site)` for site `s` of vector `i`, or None when the
    vector has no document or fewer sites."""
    document = _document(i)
    if document is None:
        return None
    sites = _ms().sites(document)
    return (document, sites[int(s)]) if int(s) < len(sites) else None


def _truth(document, value):
    """The truth the interpreter gives `document` at `value`, or None
    where it gives none or does not run."""
    from mathema.koine.interpret import InterpretError, Value
    try:
        outcome = _rt().interpret(document, [value])
    except InterpretError:
        return None
    return outcome.value if isinstance(outcome, Value) else None


def the_sites_of_a_document_are_stable(i: int) -> bool:
    """Whether the sites of vector `i`'s document are the same listed
    twice, no two have one operator, address and detail, there are at
    most `MOST_SITES`, each names a known operator and one of the three
    directions, and each address is that of a term of the document."""
    ms, document = _ms(), _document(i)
    if document is None:
        return True
    sites = ms.sites(document)
    if sites != ms.sites(document) or len(sites) > MOST_SITES:
        return False
    if len({(s.operator, s.address, s.detail) for s in sites}) != len(sites):
        return False
    for site in sites:
        if site.operator not in OPERATORS or site.operator not in ms.OPERATORS:
            return False
        if site.direction not in ("never_shrinks", "never_grows", "either"):
            return False
        if site.polarity not in (1, -1):
            return False
        try:
            ms.term_at(document, site.address)
        except LookupError:
            return False
    return True


def a_changed_document_is_valid_and_another_document(i: int, s: int) -> bool:
    """Whether the document of vector `i` with site `s` changed is
    valid KOINE and is not the document it was made from, by its
    hash."""
    from mathema.koine import koine_hash
    found = _site(i, s)
    if found is None:
        return True
    document, site = found
    changed = _ms().change(document, site)
    return _rt().validate(changed) == [] and koine_hash(changed) != koine_hash(document)


def a_change_with_an_inverse_is_undone(i: int, s: int) -> bool:
    """Whether site `s` has an inverse exactly when its operator is one
    of those with one, the inverse is of the operator that undoes it,
    and the changed document changed at the inverse is the document it
    was made from, term for term."""
    ms = _ms()
    found = _site(i, s)
    if found is None:
        return True
    document, site = found
    inverse = ms.inverse(site)
    if site.operator not in INVERSE:
        return inverse is None
    if inverse is None or inverse.operator != INVERSE[site.operator]:
        return False
    changed = ms.change(document, site)
    return inverse in ms.sites(changed, more_names=(site.name,) if site.name else ()) \
        and ms.change(changed, inverse) == document


def a_change_moves_the_language_the_way_its_site_says(i: int, s: int, v: int) -> bool:
    """Whether, at value `v`, the document with site `s` changed keeps
    to the direction the site states against the vector's own
    membership: for `never_shrinks`, a member stays one wherever the
    changed document has a value; for `never_grows`, a value the
    changed document holds was a member."""
    found = _site(i, s)
    if found is None:
        return True
    document, site = found
    value = VALUES[int(v)]
    was = _rl().member(VECTORS[int(i)]["document"], value, bound="at_most")
    now = _truth(_ms().change(document, site), value)
    if site.direction == "never_shrinks":
        return not was or now in (True, None)
    if site.direction == "never_grows":
        return now is not True or was
    return True


def a_changed_document_has_a_solver_reading(i: int, s: int) -> bool:
    """Whether the question "inside the changed document, outside the
    one it was made from", and the reverse, is read by the solver
    route: each gives a member, none, or no answer for a reason other
    than having no reading; and a member found one way or the other
    when the site's direction forbids that way is never returned."""
    from mathema.koine import solver_question as sq
    found = _site(i, s)
    if found is None:
        return True
    document, site = found
    changed = _ms().change(document, site)
    grew = sq.find_member([changed], [document])
    shrank = sq.find_member([document], [changed])
    for answer in (grew, shrank):
        if answer.status == "unknown" and "no solver reading" in answer.reason:
            return False
    if site.direction == "never_grows" and grew.status == "member":
        return False
    if site.direction == "never_shrinks" and shrank.status == "member":
        return False
    return True


def a_record_has_a_site_of_each_operator() -> bool:
    """Whether the membership document of the nested configuration
    record has at least one site of every operator, and its sites are
    in the order of their addresses."""
    ms = _ms()
    from mathema.koine import record_membership
    sites = ms.sites(record_membership.membership_document(REF.CHILD))
    return ({s.operator for s in sites} == set(OPERATORS)
            and [s.address for s in sites] == sorted(s.address for s in sites))


def a_site_names_what_it_changes(i: int, s: int) -> bool:
    """Whether the text of site `s` is its operator, its address
    written with dots after `return`, and its detail, and reads back to
    the site by `site_at`."""
    ms = _ms()
    found = _site(i, s)
    if found is None:
        return True
    document, site = found
    text = ms.site_text(site)
    address = ".".join(["return", *[str(n) for n in site.address]])
    return text.startswith(f"{site.operator} at {address}") \
        and ms.site_at(document, text) == site
