# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The mutation sites of a membership document: the places at which
one change can be made to the KOINE statement of membership, each with
a stable address, and the document with one such change.

Draft, not part of the public interface. A document is one built by
`record_membership` (or any function of one value whose body returns
one expression). The address of a site is the path from the returned
expression to a term, as argument positions: `()` is the expression
itself, `(2, 1)` the second argument of its third. The same document
always lists the same sites, in the order of their addresses.

The operators, and the direction each moves the language when its site
stands under an even number of negations (`polarity` 1; under an odd
number, `polarity` -1, the direction is the other one):

    drop_conjunct
        one part of an `operator::logic::and` is left out. Never
        shrinks.
    swap_required_and_optional
        a required field's part, `and(has_key, inside)`, becomes the
        optional one, `or(not(has_key), inside)`: never shrinks; an
        optional field's part becomes the required one: never grows.
        Its own inverse.
    negate_has_key
        a `value::map::has_key` is negated, or the negation standing
        directly on one is removed. Either way. Its own inverse.
    read_null_as_unset
        a `value::map::has_key(m, k)` becomes "the value at k is not
        absent", so a key holding null counts as unset. The test
        becomes harder to pass: never grows where the test itself
        stands under an even number of negations, never shrinks under
        an odd number.
    remove_name_from_no_other_key
        one name is taken out of a
        `value::map::has_no_key_other_than` list. Never grows. Undone
        by `add_name_to_no_other_key` of that name at that position.
    add_name_to_no_other_key
        one name is put into the list. Never shrinks. Undone by
        removing it.
    remove_choice_constant
        the test of one constant of a choice (`value::is_absent`, or a
        test of kind and an equality) is left out of the disjunction
        it is a part of, or becomes `false` where it is no part of one.
        Never grows.

A direction is a statement about the points where the changed document
has a value. A change can leave a document with no value at some
points: with the test of `kind::dict` dropped, a `value::map::` term is
evaluated on a value that is no map.

`change(document, site)` keeps the document's envelope and replaces the
returned expression, so a change undone gives back the same document,
term for term.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import record_terms as T
from .document import Document
from .syntax import Bool, Int, List, Real, Str, Term, inline

NOT, AND, OR = "operator::logic::not", "operator::logic::and", "operator::logic::or"
EQUAL = "operator::comparison::equal"

DROP_CONJUNCT = "drop_conjunct"
SWAP = "swap_required_and_optional"
NEGATE_HAS_KEY = "negate_has_key"
NULL_AS_UNSET = "read_null_as_unset"
REMOVE_NAME = "remove_name_from_no_other_key"
ADD_NAME = "add_name_to_no_other_key"
REMOVE_CONSTANT = "remove_choice_constant"
OPERATORS = (DROP_CONJUNCT, SWAP, NEGATE_HAS_KEY, NULL_AS_UNSET, REMOVE_NAME, ADD_NAME,
             REMOVE_CONSTANT)
#: the name `add_name_to_no_other_key` puts in when no other is asked for
OTHER_NAME = "other"

_GROWS, _SHRINKS, _EITHER = "never_shrinks", "never_grows", "either"


@dataclass(frozen=True)
class Site:
    """One place a document can be changed at: the `operator`; the
    `address` of the term it changes; the `polarity` of that term (1
    under an even number of negations, -1 under an odd number); the
    `direction` the change moves the language (`never_shrinks`,
    `never_grows` or `either`); a `detail` saying what is changed, in
    words; and, for the two operators on a list of names, the `name`
    and its `index` in the list."""
    operator: str
    address: tuple
    polarity: int
    direction: str
    detail: str
    name: "str | None" = None
    index: "int | None" = None


def returned_expression(document: Document):
    """Intent:
        The one expression the body of `document` returns.

    Raises:
        ValueError: the body is not one `statement::return`.
    """
    body = document.body if isinstance(document, Document) else ()
    if not (len(body) == 1 and isinstance(body[0], Term)
            and body[0].head == "statement::return" and len(body[0].args) == 1):
        raise ValueError("a document whose body returns one expression is read")
    return body[0].args[0]


def term_at(document: Document, address) -> object:
    """Intent:
        The term of `document` at `address`.

    Raises:
        LookupError: the document has no term there.
    """
    node = returned_expression(document)
    for position in address:
        if not isinstance(node, Term) or not 0 <= position < len(node.args):
            raise LookupError(f"no term at {tuple(address)!r}")
        node = node.args[position]
    return node


def _directed(polarity: int, grows: bool) -> str:
    return _GROWS if grows == (polarity == 1) else _SHRINKS


def _is_has_key(node) -> bool:
    return isinstance(node, Term) and node.head == T.HAS_KEY and len(node.args) == 2


def _is_negated_has_key(node) -> bool:
    return isinstance(node, Term) and node.head == NOT and len(node.args) == 1 \
        and _is_has_key(node.args[0])


def _is_constant_test(node) -> bool:
    """Whether a term tests one constant of a choice: `value::is_absent`,
    or a test of kind and an equality with a literal."""
    if not isinstance(node, Term):
        return False
    if node.head == T.IS_ABSENT:
        return True
    return (node.head == AND and len(node.args) == 2 and isinstance(node.args[1], Term)
            and node.args[1].head == EQUAL and len(node.args[1].args) == 2
            and isinstance(node.args[1].args[1], (Bool, Int, Real, Str)))


def _names(node) -> list:
    return [x.value for x in node.args[1].items]


def _walk(node, address: tuple, polarity: int, more_names: tuple, out: list) -> None:
    if not isinstance(node, Term):
        return
    head = node.head
    if _is_constant_test(node):
        what = "null" if head == T.IS_ABSENT else inline(node.args[1].args[1])
        out.append(Site(REMOVE_CONSTANT, address, polarity, _directed(polarity, False),
                        f"the constant {what}"))
    if head == AND and len(node.args) == 2 and _is_has_key(node.args[0]):
        out.append(Site(SWAP, address, polarity, _directed(polarity, True),
                        f"required {inline(node.args[0].args[1])} becomes optional"))
    if head == OR and len(node.args) == 2 and _is_negated_has_key(node.args[0]):
        out.append(Site(SWAP, address, polarity, _directed(polarity, False),
                        f"optional {inline(node.args[0].args[0].args[1])} becomes required"))
    if _is_has_key(node):
        key = inline(node.args[1])
        out.append(Site(NEGATE_HAS_KEY, address, polarity, _EITHER, f"has_key {key} negated"))
        out.append(Site(NULL_AS_UNSET, address, polarity, _directed(polarity, False),
                        f"has_key {key} reads null as unset"))
        return
    if _is_negated_has_key(node):
        key = inline(node.args[0].args[1])
        out.append(Site(NEGATE_HAS_KEY, address, polarity, _EITHER,
                        f"the negation of has_key {key} removed"))
    if head == T.HAS_NO_KEY_OTHER_THAN and T.shape_problem(node) is None:
        listed = _names(node)
        for i, name in enumerate(listed):
            out.append(Site(REMOVE_NAME, address, polarity, _directed(polarity, False),
                            f"the name {inline(Str(name))} removed", name, i))
        for name in dict.fromkeys((*more_names, _fresh(listed))):
            if name not in listed:
                out.append(Site(ADD_NAME, address, polarity, _directed(polarity, True),
                                f"the name {inline(Str(name))} added", name, len(listed)))
        return
    if head == AND:
        for i in range(len(node.args)):
            out.append(Site(DROP_CONJUNCT, (*address, i), polarity,
                            _directed(polarity, True),
                            f"part {i + 1} of {len(node.args)} dropped"))
    if head in (AND, OR, NOT):
        inner = -polarity if head == NOT else polarity
        for i, arg in enumerate(node.args):
            _walk(arg, (*address, i), inner, more_names, out)


def _fresh(listed: list) -> str:
    name = OTHER_NAME
    while name in listed:
        name += "_"
    return name


def sites(document: Document, *, more_names: tuple = ()) -> tuple:
    """Intent:
        Every site of `document`, in the order of their addresses and,
        at one address, of `OPERATORS`. `add_name_to_no_other_key` has
        one site for each of `more_names` a list does not hold, and one
        for a name no list holds (`OTHER_NAME`, with underscores added
        until it is not listed).

    Raises:
        ValueError: the body is not one `statement::return`.
    """
    out: list = []
    _walk(returned_expression(document), (), 1, tuple(more_names), out)
    return tuple(sorted(out, key=lambda s: (s.address, OPERATORS.index(s.operator),
                                            s.index if s.index is not None else -1,
                                            s.name or "")))


#: what an edit returns for a part left out of the conjunction it
#: stands in, and for a constant test left out of its disjunction
_PART_DROPPED = object()
_CONSTANT_DROPPED = object()


def _edited(node, address: tuple, edit):
    """`node` with the term at `address` replaced by `edit(term)`. A
    part edited to `_PART_DROPPED` is left out of the conjunction it is
    a part of, and a constant test edited to `_CONSTANT_DROPPED` out of
    the disjunction it is a part of; either becomes its one remaining
    part when one remains. A constant test that is no part of a
    disjunction becomes `false`."""
    if not address:
        return edit(node)
    if not isinstance(node, Term) or not 0 <= address[0] < len(node.args):
        raise LookupError(f"no term at {address!r}")
    i = address[0]
    inner = _edited(node.args[i], address[1:], edit)
    spliced = (inner is _PART_DROPPED and node.head == AND) \
        or (inner is _CONSTANT_DROPPED and node.head == OR)
    if spliced:
        left = (*node.args[:i], *node.args[i + 1:])
        return left[0] if len(left) == 1 else Term(node.head, left, node.named)
    if inner is _CONSTANT_DROPPED:
        inner = Bool(False)
    return Term(node.head, (*node.args[:i], inner, *node.args[i + 1:]), node.named)


def _changed_term(site: Site):
    """The edit a site makes to the term at its address."""
    def edit(node):
        op = site.operator
        if op == DROP_CONJUNCT:
            return _PART_DROPPED
        if op == REMOVE_CONSTANT:
            return _CONSTANT_DROPPED
        if op == SWAP:
            if node.head == AND:
                return Term(OR, (Term(NOT, (node.args[0],)), node.args[1]))
            return Term(AND, (node.args[0].args[0], node.args[1]))
        if op == NEGATE_HAS_KEY:
            return node.args[0] if node.head == NOT else Term(NOT, (node,))
        if op == NULL_AS_UNSET:
            return Term(NOT, (Term(T.IS_ABSENT, (Term(T.VALUE_AT_KEY, node.args),)),))
        listed = list(node.args[1].items)
        if op == REMOVE_NAME:
            if not (site.index is not None and site.index < len(listed)
                    and listed[site.index] == Str(site.name)):
                raise LookupError(f"the list does not hold {site.name!r} at {site.index}")
            del listed[site.index]
        else:
            if Str(site.name) in listed or site.index is None \
                    or not 0 <= site.index <= len(listed):
                raise LookupError(f"{site.name!r} cannot be added at {site.index}")
            listed.insert(site.index, Str(site.name))
        return Term(node.head, (node.args[0], List(tuple(listed))), node.named)
    return edit


def _fits(node, site: Site) -> bool:
    """Whether the term at a site's address is one its operator
    changes."""
    op = site.operator
    if op == DROP_CONJUNCT:
        return True
    if op == REMOVE_CONSTANT:
        return _is_constant_test(node)
    if op == SWAP:
        return isinstance(node, Term) and len(node.args) == 2 and (
            (node.head == AND and _is_has_key(node.args[0]))
            or (node.head == OR and _is_negated_has_key(node.args[0])))
    if op == NEGATE_HAS_KEY:
        return _is_has_key(node) or _is_negated_has_key(node)
    if op == NULL_AS_UNSET:
        return _is_has_key(node)
    return (op in (REMOVE_NAME, ADD_NAME) and isinstance(node, Term)
            and node.head == T.HAS_NO_KEY_OTHER_THAN and T.shape_problem(node) is None)


def change(document: Document, site: Site) -> Document:
    """Intent:
        `document` with the one change `site` names made, its envelope
        kept.

    Raises:
        LookupError: the document has no term at the site's address
            that the site's operator changes.
        ValueError: the body is not one `statement::return`, or the
            operator is not one of `OPERATORS`.
    """
    if site.operator not in OPERATORS:
        raise ValueError(f"an operator is one of {', '.join(OPERATORS)}, not "
                         f"{site.operator!r}")
    expression = returned_expression(document)
    if site.operator == DROP_CONJUNCT:
        parent = term_at(document, site.address[:-1]) if site.address else None
        if not (isinstance(parent, Term) and parent.head == AND):
            raise LookupError(f"no part of a conjunction at {site.address!r}")
    if not _fits(term_at(document, site.address), site):
        raise LookupError(f"{site.operator} does not change the term at {site.address!r}")
    changed = _edited(expression, tuple(site.address), _changed_term(site))
    if changed is _CONSTANT_DROPPED:
        changed = Bool(False)
    returned = document.body[0]
    return document.with_body([Term(returned.head, (changed,), returned.named)])


def inverse(site: Site) -> "Site | None":
    """The site that undoes `site` in the changed document, for the
    operators that have one: a swap and a negation undo themselves, and
    a name removed is added back at its position; None for the rest."""
    op = site.operator
    if op == NEGATE_HAS_KEY:
        return site
    if op == SWAP:
        return Site(SWAP, site.address, site.polarity, _other(site.direction), site.detail)
    if op in (REMOVE_NAME, ADD_NAME):
        return Site(ADD_NAME if op == REMOVE_NAME else REMOVE_NAME, site.address,
                    site.polarity, _other(site.direction), site.detail, site.name, site.index)
    return None


def _other(direction: str) -> str:
    return {_GROWS: _SHRINKS, _SHRINKS: _GROWS}.get(direction, direction)


def site_text(site: Site) -> str:
    """A site in one line: `<operator> at return.<i>.<j>: <detail>`."""
    address = ".".join(["return", *[str(n) for n in site.address]])
    return f"{site.operator} at {address}: {site.detail}"


def site_at(document: Document, text: str) -> Site:
    """Intent:
        The site of `document` whose `site_text` is `text`.

    Raises:
        LookupError: the document has no such site.
    """
    for site in sites(document):
        if site_text(site) == text:
            return site
    raise LookupError(f"no site {text!r}")


__all__ = ["ADD_NAME", "DROP_CONJUNCT", "NEGATE_HAS_KEY", "NULL_AS_UNSET", "OPERATORS",
           "OTHER_NAME", "REMOVE_CONSTANT", "REMOVE_NAME", "SWAP", "Site", "change",
           "inverse", "returned_expression", "site_at", "site_text", "sites", "term_at"]
