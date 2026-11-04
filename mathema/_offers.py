# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What the note of a falsified claim offers in its place.

A claim falsified by a shape it did not mean has a spelling that says what
it meant: a vector of one element against a number is compared by its
element or as a whole, and an ordering that fails where the result is empty
holds once the domain leaves that point out. An offer is the whole claim, as
the user wrote it, with its domain. Each is adjudicated on that domain before
it is offered, so an offered claim holds when written. That costs one more
check of the claim per spelling tried (`_MOST_NARROWINGS` at most for a
narrowed domain), only on a claim falsified at one of these two shapes, and
stops at `_OFFER_SECONDS`.
"""
from __future__ import annotations

import ast
import contextvars
import time
from typing import Callable

from ._missing_words import options
from ._timeout import EXTENSIVE_TIMEOUT_SECONDS

#: the most narrowed domains tried, each past the last one's empty point
_MOST_NARROWINGS = 8
_OFFER_SECONDS = EXTENSIVE_TIMEOUT_SECONDS

_ORDERINGS = ("<", "<=", ">", ">=")
_EQUALITIES = ("==", "~=", "!=")

#: the sides and the point a claim being adjudicated last failed at
_LAST_MISS: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_last_miss", default=None)
#: set while an offer is adjudicated, which offers nothing of its own
_ADJUDICATING: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_adjudicating_an_offer", default=False)


def record_miss(*seen) -> None:
    """Remember the two sides a claim just failed with, and where."""
    from .probing import plain_value
    if len(seen) == 3:
        lv, rv, point = seen
    else:
        (lv, rv), point = seen
    _LAST_MISS.set((plain_value(lv), plain_value(rv), dict(point)))


def forget_miss() -> None:
    """Start a claim with no miss remembered."""
    _LAST_MISS.set(None)


def last_miss():
    """The `(left, right, point)` last recorded, or None."""
    return _LAST_MISS.get()


def adjudicating() -> bool:
    """Whether the claim in hand is itself an offer being adjudicated."""
    return _ADJUDICATING.get()


def split_claim(raw: str) -> "tuple[str, str, str, str] | None":
    """Intent:
        A claim's text as `(prefix, left, relation, right)`: `prefix` its
        domain and premises with their closing `, ` ("" for a ground
        claim), and the relation at the top level of what follows. None
        when no relation stands at the top level there.
    """
    depth, quote, cut = 0, None, 0
    spots: list = []
    for i, ch in enumerate(raw):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and ch == ",":
            cut, spots = i + 1, []
        elif depth == 0 and raw[i:i + 2] in ("==", "~=", "!=", "<=", ">="):
            spots.append((i, raw[i:i + 2]))
        elif depth == 0 and ch in "<>" and raw[i:i + 2] not in ("<=", ">="):
            spots.append((i, ch))
    if len(spots) != 1:
        return None
    at, relation = spots[0]
    return (raw[:cut] + (" " if cut else ""), raw[cut:at].strip(), relation,
            raw[at + len(relation):].strip())


def _indexed(side: str) -> str:
    """The claim side `side` read at its first element: a call, a name or
    an index takes `[0]` as it stands, any other expression in
    parentheses, so the index reads the whole side."""
    try:
        node = ast.parse(side, mode="eval").body
    except SyntaxError:
        return f"({side})[0]"
    if isinstance(node, (ast.Name, ast.Call, ast.Subscript, ast.Attribute)):
        return f"{side}[0]"
    return f"({side})[0]"


def _one_element(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 1


def _an_element(value) -> bool:
    return isinstance(value, (int, float, complex, str))


def element_spellings(raw: str, lv, rv) -> list:
    """Intent:
        The claims that say what a claim comparing a vector of one
        element with a number, a bool or a string may have meant, as
        `[(words, claim)]`: the element, then the whole. Empty when the
        sides are no such pair.
    """
    parts = split_claim(raw)
    if parts is None or parts[2] not in _EQUALITIES:
        return []
    prefix, left, relation, right = parts
    if _one_element(lv) and _an_element(rv):
        element, whole = (f"{_indexed(left)} {relation} {right}",
                          f"{left} {relation} [{right}]")
    elif _one_element(rv) and _an_element(lv):
        element, whole = (f"{left} {relation} {_indexed(right)}",
                          f"[{left}] {relation} {right}")
    else:
        return []
    return [("to compare the element, write", prefix + element),
            ("to compare the whole, write", prefix + whole)]


def _past(point: dict) -> "str | None":
    """The premise that leaves a one-parameter point out from below:
    `n >= 1` past the whole number 0, `x > 0.5` past a float."""
    if len(point) != 1:
        return None
    (name, value), = point.items()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int):
        return f"{name} >= {value + 1}"
    return f"{name} > {value}"


def _orders_nothing(relation: str, lv, rv) -> bool:
    from .probing import has_no_elements
    return relation in _ORDERINGS and (has_no_elements(lv)
                                       or has_no_elements(rv))


def _held(verdict) -> bool:
    return str(verdict).split(":", 1)[0] in ("holds", "proven")


def offers_for(raw: str, relation: str, miss,
               adjudicate: Callable[[str], tuple]) -> str:
    """Intent:
        The words a falsified claim's note gains from the miss it failed
        with, `(left, right, point)`: the mismatch or the empty ordering
        stated, and the spellings that hold. "" when the miss is neither.

        `adjudicate(claim_text)` gives `(verdict, miss)` for a claim.
    """
    lv, rv, point = miss
    deadline = time.monotonic() + _OFFER_SECONDS
    spellings = element_spellings(raw, lv, rv)
    if spellings:
        held = [f"{words}: {text}" for words, text in spellings
                if time.monotonic() < deadline and _held(adjudicate(text)[0])]
        words = "a vector of one element is not its element"
        return f"{words}\n{options(held)}" if held else words
    if not _orders_nothing(relation, lv, rv):
        return ""
    words = "an ordering over an empty value does not hold"
    for _ in range(_MOST_NARROWINGS):
        premise = _past(point)
        if premise is None or time.monotonic() >= deadline:
            break
        text = f"assuming {premise}, {raw}"
        verdict, inner = adjudicate(text)
        if _held(verdict):
            return (f"{words}\nif the empty result is outside what you "
                    f"claim, state: {text}")
        if inner is None or not _orders_nothing(relation, inner[0], inner[1]):
            break
        point = inner[2]
    return words


def with_offers(probe, cj, adjudicate_claim: Callable) -> object:
    """Intent:
        `probe` with what its claim's last miss offers added to its
        note, as the last lines, where `remedy_statements` reads them.
        Unchanged unless the row is the claim's own and falsified.
    """
    miss = last_miss()
    if miss is None or adjudicating() or probe.name != cj.name \
            or str(probe.verdict).split(":", 1)[0] != "falsified" \
            or not getattr(cj, "raw", ""):
        return probe

    def adjudicate(text: str) -> tuple:
        token = _ADJUDICATING.set(True)
        forget_miss()
        try:
            return adjudicate_claim(text), last_miss()
        except Exception:
            return None, None
        finally:
            _ADJUDICATING.reset(token)

    added = offers_for(cj.raw, cj.relation, miss, adjudicate)
    forget_miss()
    if added:
        probe.note = f"{probe.note}\n{added}" if probe.note else added
        probe.meta = {**(probe.meta or {}), "mathema.offer": added}
    return probe
