# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Regular-language terms: the solver-neutral definition a text
language states, and the question core decides about such terms.

A definition is a plain JSON document, `{"kind": "regular_language",
"version": 1, "alphabet": [[lo, hi], ...], "exact": bool, ...}`. An
exact definition carries its language under `language`; one that is not
exact carries two bounds in its place, `at_least` (a language holding
every member) and `at_most` (a language holding only members). A
language is a node keyed by `op`: `empty`, `epsilon`, `literal` (one
string, as its code points), `chars` (one character from inclusive code point ranges),
`concat`, `union`, `inter`, `complement` (every string over the
alphabet outside the argument) and `repeat` (`min` to `max` copies,
`max` null for no upper end). Whatever compiled the definition, a
pattern dialect say, records itself under `source`, which is provenance
and no part of the meaning: `term_hash` reads the alphabet, the exact
flag and the nodes, in canonical form, and nothing else.

`find_member` asks whether some string lies inside every one of a list
of nodes and outside every one of another, which is how inclusion,
equality and disjointness of two languages are all decided. The
alphabet is first cut into its atoms, the sets of characters no `chars`
node or literal tells apart, and the question is asked of z3's
sequence theory over one symbol per atom. The answer is the same as
over the whole alphabet, since no node can distinguish two characters
of one atom, and a string found is mapped back to a character of each
atom. The `z3-solver` dependency is the optional `mathema[smt]` extra.

Membership needs no solver: `member` and `matcher` read a definition by
derivatives over its own alphabet, within a budget, and `node_member`
and `node_matcher` read a bare node over all characters. `validate`,
`member` and `matcher` on a definition, `node_member`, `node_matcher`,
`atoms`, `shortest_member` and `MATCH_BUDGET` are draft, not part of the
public interface yet.
"""
from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from dataclasses import dataclass

KIND = "regular_language"
VERSION = 1
MAX_CODE_POINT = 0x10FFFF

_LEAVES = ("empty", "epsilon")
_MANY = ("concat", "union", "inter")
#: the first of the code points standing for atoms in the solver's
#: strings, one per atom, in a run
_SYMBOL_BASE = 0x4E00


class InvalidTerm(ValueError):
    """A document or node outside the regular-language schema."""


@dataclass(frozen=True)
class Found:
    """The answer to `find_member`: `status` is `member` (with the
    string), `none` (no string exists) or `unknown` (with the
    `reason`: the solver gave no answer in time, or is not
    installed)."""
    status: str
    member: "str | None" = None
    reason: str = ""


# ---- the canonical form and the hash ----------------------------------

#: the keys each operation's node holds beside `op`, and no others
_NODE_KEYS = {"empty": (), "epsilon": (), "literal": ("codes",), "chars": ("ranges",),
              "concat": ("args",), "union": ("args",), "inter": ("args",),
              "complement": ("arg",), "repeat": ("arg", "min", "max")}
#: the language of every string, which an intersection drops
_EVERY_STRING = {"op": "repeat", "arg": {"op": "chars", "ranges": [[0, MAX_CODE_POINT]]},
                 "min": 0, "max": None}


def _code_point(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) \
            or not 0 <= value <= MAX_CODE_POINT:
        raise InvalidTerm(f"{where}: {value!r} is not a code point (a whole number "
                          f"from 0 to {MAX_CODE_POINT})")
    return value


def _ranges(raw, where: str) -> list:
    """Inclusive code point ranges, checked, sorted and merged with
    their overlapping and adjacent neighbours."""
    if not isinstance(raw, list):
        raise InvalidTerm(f"{where}: ranges must be a list of [lo, hi] pairs")
    pairs = []
    for pair in raw:
        if not isinstance(pair, list) or len(pair) != 2:
            raise InvalidTerm(f"{where}: {pair!r} is not a code point range [lo, hi] "
                              f"(a list of two code points, as JSON writes it)")
        lo, hi = _code_point(pair[0], where), _code_point(pair[1], where)
        if lo > hi:
            raise InvalidTerm(f"{where}: the range {pair!r} ends before it starts")
        pairs.append((lo, hi))
    merged: list = []
    for lo, hi in sorted(pairs):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged


def _serial(value) -> str:
    """The one serialisation of a canonical value: JSON with sorted
    keys, no white space, ASCII only."""
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _once_sorted(args: list) -> list:
    """Arguments kept once each, in the order of their serialisation."""
    return [json.loads(text) for text in sorted({_serial(a) for a in args})]


def canonical(node) -> dict:
    """Intent:
        The canonical form of a node, its arguments made canonical
        first, by these rules and no others.

        1. `chars`: ranges sorted, overlapping and adjacent ones
           merged; no range is `empty`; one range of one code point is
           the `literal` of that code point.
        2. `literal`: no code point is `epsilon`.
        3. `concat`: nested concatenations flattened; `epsilon`
           arguments dropped; any `empty` argument makes `empty`;
           neighbouring literals joined; none left is `epsilon`; one
           left is that argument.
        4. `union`: nested unions flattened; `empty` arguments dropped;
           equal arguments kept once; sorted by their serialisation;
           none left is `empty`; one left is that argument.
        5. `inter`: nested intersections flattened; any `empty`
           argument makes `empty`; the every-string node dropped; equal
           arguments kept once; sorted as a union's; none left is the
           every-string node; one left is that argument.
        6. `repeat`: `max` 0 is `epsilon`; of `epsilon` is `epsilon`;
           of `empty` is `epsilon` when `min` is 0, else `empty`;
           `min` and `max` both 1 is the argument.
        7. `complement`, `epsilon` and `empty` are unchanged.

    Raises:
        InvalidTerm: the node is not of the schema: an unknown
            operation, a key the operation does not hold, a code point
            that is not a whole number from 0 to 1114111, a range out
            of order, or a count that is not a whole number.
    """
    if not isinstance(node, dict) or not isinstance(node.get("op"), str):
        raise InvalidTerm(f"{node!r} is not a node (an object with an 'op')")
    op = node["op"]
    if op not in _NODE_KEYS:
        raise InvalidTerm(f"{op!r} is not a regular-language operation")
    if set(node) != {"op", *_NODE_KEYS[op]}:
        raise InvalidTerm(f"{op}: a node holds exactly the keys "
                          f"{sorted(('op', *_NODE_KEYS[op]))}, not {sorted(node)}")
    if op in _LEAVES:
        return {"op": op}
    if op == "literal":
        codes = node["codes"]
        if not isinstance(codes, list):
            raise InvalidTerm("literal: 'codes' must be a list of code points")
        codes = [_code_point(c, "literal") for c in codes]
        return {"op": "literal", "codes": codes} if codes else {"op": "epsilon"}
    if op == "chars":
        ranges = _ranges(node["ranges"], "chars")
        if not ranges:
            return {"op": "empty"}
        if len(ranges) == 1 and ranges[0][0] == ranges[0][1]:
            return {"op": "literal", "codes": [ranges[0][0]]}
        return {"op": "chars", "ranges": ranges}
    if op == "complement":
        return {"op": "complement", "arg": canonical(node["arg"])}
    if op == "repeat":
        lo, hi = node["min"], node["max"]
        if not isinstance(lo, int) or isinstance(lo, bool) or lo < 0 or not (
                hi is None or (isinstance(hi, int) and not isinstance(hi, bool) and hi >= lo)):
            raise InvalidTerm(f"repeat: min {lo!r} and max {hi!r} are not a count range")
        arg = canonical(node["arg"])
        if hi == 0 or arg["op"] == "epsilon":
            return {"op": "epsilon"}
        if arg["op"] == "empty":
            return {"op": "epsilon"} if lo == 0 else {"op": "empty"}
        if lo == 1 and hi == 1:
            return arg
        return {"op": "repeat", "arg": arg, "min": lo, "max": hi}
    raw = node["args"]
    if not isinstance(raw, list):
        raise InvalidTerm(f"{op}: 'args' must be a list of nodes")
    args: list = []
    for arg in (canonical(a) for a in raw):
        args.extend(arg["args"] if arg["op"] == op else [arg])
    if op == "concat":
        if any(a["op"] == "empty" for a in args):
            return {"op": "empty"}
        joined: list = []
        for a in args:
            if a["op"] == "epsilon":
                continue
            if a["op"] == "literal" and joined and joined[-1]["op"] == "literal":
                joined[-1] = {"op": "literal", "codes": joined[-1]["codes"] + a["codes"]}
            else:
                joined.append(a)
        args, nothing = joined, {"op": "epsilon"}
    elif op == "union":
        args, nothing = _once_sorted([a for a in args if a["op"] != "empty"]), {"op": "empty"}
    else:
        if any(a["op"] == "empty" for a in args):
            return {"op": "empty"}
        args, nothing = _once_sorted([a for a in args if a != _EVERY_STRING]), _EVERY_STRING
    if not args:
        return json.loads(_serial(nothing))
    return args[0] if len(args) == 1 else {"op": op, "args": args}


def _closed(node: dict, alphabet: list) -> dict:
    """`node` with every complement taken inside `alphabet`, so the
    node means the same when it is read over a wider alphabet."""
    if alphabet == [[0, MAX_CODE_POINT]]:
        return node
    op = node["op"]
    if op == "complement":
        over = {"op": "repeat", "arg": {"op": "chars", "ranges": alphabet}, "min": 0, "max": None}
        return {"op": "inter", "args": [{"op": "complement", "arg": _closed(node["arg"], alphabet)},
                                        over]}
    if op == "repeat":
        return {**node, "arg": _closed(node["arg"], alphabet)}
    if op in _MANY:
        return {**node, "args": [_closed(a, alphabet) for a in node["args"]]}
    return node


def _read(document) -> tuple:
    """`(alphabet, exact, at_most, at_least)` of a definition this
    module decides questions about: of this kind and version, the
    nodes canonical."""
    if not isinstance(document, dict) or document.get("kind") != KIND:
        raise InvalidTerm(f"not a {KIND} definition")
    if document.get("version") != VERSION or isinstance(document.get("version"), bool):
        raise InvalidTerm(f"{KIND} version {document.get('version')!r} is not read; "
                          f"this reads version {VERSION}")
    return _meaning(document)


def _meaning(document) -> tuple:
    """`(alphabet, exact, at_most, at_least)` of a document's meaning,
    whatever kind and version it states, the nodes canonical."""
    if not isinstance(document, dict):
        raise InvalidTerm("a definition is an object")
    alphabet = _ranges(document.get("alphabet"), "alphabet")
    exact = document.get("exact")
    if "language" in document and ("at_least" in document or "at_most" in document):
        raise InvalidTerm("a definition states either 'language' or the bounds 'at_least' "
                          "and 'at_most', not both")
    if exact is True and "language" in document:
        node = canonical(document["language"])
        return alphabet, True, node, node
    if exact is False and "at_least" in document and "at_most" in document:
        return (alphabet, False, canonical(document["at_most"]),
                canonical(document["at_least"]))
    raise InvalidTerm("an exact definition states 'language'; one that is not exact "
                      "states 'at_least' and 'at_most'")


def bounds(document) -> tuple:
    """Intent:
        `(at_most, at_least)` for a definition, as nodes that read the
        same over any alphabet holding the definition's own: a language
        holding only members, and one holding every member. They are
        one node when the definition is exact. A node may name code
        points outside the alphabet; the language is the node met with
        every string over the alphabet.

    Raises:
        InvalidTerm: the document is not of the schema.
    """
    alphabet, _, at_most, at_least = _read(document)
    if alphabet == [[0, MAX_CODE_POINT]]:
        return at_most, at_least
    over = {"op": "repeat", "arg": {"op": "chars", "ranges": alphabet}, "min": 0, "max": None}
    return ({"op": "inter", "args": [_closed(at_most, alphabet), over]},
            {"op": "inter", "args": [_closed(at_least, alphabet), over]})


def alphabet_of(document) -> list:
    """The definition's alphabet as sorted, merged code point ranges."""
    return _read(document)[0]


def is_definition(document) -> bool:
    """Whether `document` is a regular-language definition this module
    reads."""
    try:
        _read(document)
    except InvalidTerm:
        return False
    return True


def canonical_text(document) -> str:
    """Intent:
        The text a definition's hash is taken of: the serialisation
        (JSON, sorted keys, no white space, ASCII only) of its version,
        its alphabet with the ranges sorted and merged, its exact flag
        and its canonical node or two bounds. `kind`, `source` and any
        other key are not in it, so a document of another kind or a
        later version has a text and a hash too; only `bounds` and the
        questions asked of a definition require this kind and version.

    Raises:
        InvalidTerm: the document is not of the schema.
    """
    alphabet, exact, at_most, at_least = _meaning(document)
    version = document.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise InvalidTerm(f"the version {version!r} is not a whole number")
    meaning: dict = {"version": version, "alphabet": alphabet, "exact": exact}
    if exact:
        meaning["language"] = at_most
    else:
        meaning["at_least"], meaning["at_most"] = at_least, at_most
    return _serial(meaning)


def validate(document) -> None:
    """Intent:
        Nothing when `document` is a well-formed definition of any kind
        and version: an object stating a whole-number version, an
        alphabet of code point ranges written as lists, an exact flag
        that is true with `language` and no bound or false with
        `at_least` and `at_most` and no `language`, and nodes of the
        schema. `is_definition` says whether this module answers
        questions about it, which also needs this kind and version.

    Raises:
        InvalidTerm: naming the rule the document breaks.
    """
    canonical_text(document)


def term_hash(document) -> str:
    """Intent:
        The identity of a definition's meaning: the SHA-256, in lower
        case hex, of its `canonical_text`. The same language compiled
        from another spelling or on another runtime hashes the same.

    Raises:
        InvalidTerm: the document is not of the schema.
    """
    return hashlib.sha256(canonical_text(document).encode("ascii")).hexdigest()


# ---- membership of one string, by derivatives --------------------------

_EMPTY_T = ("empty",)
_EPSILON_T = ("epsilon",)
#: how many derivative terms one membership question may build
_MATCH_STEPS = 200_000
#: how deep the derivative may go into a term before the question is
#: given up, well inside Python's own recursion limit
_MATCH_DEPTH = 300


class MatchBudget(Exception):
    """A membership question built more derivative terms than allowed,
    or went deeper into a term than `_MATCH_DEPTH`: `budget` is the most
    it might build and `spent` how many it had built, when known."""

    def __init__(self, budget: "int | None" = None, spent: "int | None" = None) -> None:
        super().__init__("the membership question did not finish within its budget")
        self.budget, self.spent = budget, spent


def _as_term(node: dict) -> tuple:
    """A canonical node as a nested tuple, which can be remembered."""
    op = node["op"]
    if op in _LEAVES:
        return (op,)
    if op == "literal":
        return ("literal", tuple(node["codes"]))
    if op == "chars":
        return ("chars", tuple((lo, hi) for lo, hi in node["ranges"]))
    if op == "complement":
        return ("complement", _as_term(node["arg"]))
    if op == "repeat":
        return ("repeat", _as_term(node["arg"]), node["min"], node["max"])
    return (op, tuple(_as_term(a) for a in node["args"]))


def _nullable(t: tuple) -> bool:
    """Whether the term holds the empty string."""
    op = t[0]
    if op == "empty" or op == "chars":
        return False
    if op == "epsilon":
        return True
    if op == "literal":
        return not t[1]
    if op == "concat" or op == "inter":
        return all(_nullable(a) for a in t[1])
    if op == "union":
        return any(_nullable(a) for a in t[1])
    if op == "complement":
        return not _nullable(t[1])
    return t[2] == 0 or _nullable(t[1])


def _cat(a: tuple, b: tuple) -> tuple:
    if a == _EMPTY_T or b == _EMPTY_T:
        return _EMPTY_T
    if a == _EPSILON_T:
        return b
    if b == _EPSILON_T:
        return a
    return ("concat", (a, b))


def _alt(parts) -> tuple:
    """The union of `parts`, a union among them read as its own parts,
    so a union of unions stays one level deep."""
    flat: list = []
    for p in parts:
        flat.extend(p[1] if p[0] == "union" else (p,))
    kept = tuple(dict.fromkeys(p for p in flat if p != _EMPTY_T))
    if not kept:
        return _EMPTY_T
    return kept[0] if len(kept) == 1 else ("union", kept)


def _derivative(t: tuple, code: int, seen: dict, depth: int = 0) -> tuple:
    """The term holding each string `w` such that the character `code`
    followed by `w` is in `t`. `depth` counts the terms it is inside;
    past `_MATCH_DEPTH` the question is given up with `MatchBudget`."""
    key = (t, code)
    if key in seen:
        return seen[key]
    limit = getattr(seen, "budget", None)
    if len(seen) > (_MATCH_STEPS if limit is None else limit) or depth > _MATCH_DEPTH:
        raise MatchBudget
    depth += 1
    op = t[0]
    if op in ("empty", "epsilon"):
        out = _EMPTY_T
    elif op == "literal":
        codes = t[1]
        out = (_EPSILON_T if len(codes) == 1 else ("literal", codes[1:])) \
            if codes and codes[0] == code else _EMPTY_T
    elif op == "chars":
        out = _EPSILON_T if any(lo <= code <= hi for lo, hi in t[1]) else _EMPTY_T
    elif op == "concat":
        first, rest = t[1][0], t[1][1:]
        tail = _EPSILON_T if not rest else rest[0] if len(rest) == 1 else ("concat", rest)
        parts = [_cat(_derivative(first, code, seen, depth), tail)]
        if _nullable(first):
            parts.append(_derivative(tail, code, seen, depth))
        out = _alt(parts)
    elif op == "union":
        out = _alt(_derivative(a, code, seen, depth) for a in t[1])
    elif op == "inter":
        parts = tuple(dict.fromkeys(_derivative(a, code, seen, depth) for a in t[1]))
        out = _EMPTY_T if _EMPTY_T in parts else parts[0] if len(parts) == 1 \
            else ("inter", parts)
    elif op == "complement":
        out = ("complement", _derivative(t[1], code, seen, depth))
    else:
        arg, lo, hi = t[1], t[2], t[3]
        if hi == 0:
            out = _EMPTY_T
        else:
            # after one copy the rest is fewer copies; a copy that may be
            # empty makes the lower count no constraint
            fewer = 0 if _nullable(arg) else max(lo - 1, 0)
            rest = ("repeat", arg, fewer, None if hi is None else hi - 1)
            if rest[3] == 0:
                rest = _EPSILON_T
            out = _cat(_derivative(arg, code, seen, depth), rest)
    seen[key] = out
    return out


#: the number of derivative terms a matcher may build when no budget is
#: given
MATCH_BUDGET = _MATCH_STEPS


class _Steps(dict):
    """The derivatives one matcher has taken, by `(term, code)`, with
    the most it may take (`budget`, `_MATCH_STEPS` when None)."""

    def __init__(self, budget: "int | None" = None) -> None:
        super().__init__()
        self.budget = budget


class _Prepared:
    """A term prepared for many membership questions: each term reached
    is given a number, and the step from a numbered term by a character
    is remembered, so a string costs one lookup per character once its
    steps have been taken. Calling it on a string says whether the
    term's language holds it; `spent` is the number of derivative terms
    built so far and `budget` the most it may build."""

    def __init__(self, term: tuple, budget: "int | None") -> None:
        self.terms = [term]
        self.number_of = {term: 0}
        self.accepts = [_nullable(term)]
        self.step: dict = {}
        self.seen = _Steps(budget)

    @property
    def budget(self) -> int:
        return _MATCH_STEPS if self.seen.budget is None else self.seen.budget

    @property
    def spent(self) -> int:
        return len(self.seen)

    def __call__(self, text: str) -> bool:
        try:
            return self._stepped(text)
        except MatchBudget as stopped:
            stopped.budget, stopped.spent = self.budget, self.spent
            raise
        except RecursionError:
            raise MatchBudget(self.budget, self.spent) from None

    def _stepped(self, text: str) -> bool:
        state = 0
        for ch in text:
            key = (state, ch)
            following = self.step.get(key)
            if following is None:
                reached = _derivative(self.terms[state], ord(ch), self.seen)
                following = self.number_of.get(reached)
                if following is None:
                    following = len(self.terms)
                    self.number_of[reached] = following
                    self.terms.append(reached)
                    self.accepts.append(_nullable(reached))
                self.step[key] = following
            state = following
        return self.accepts[state]


def _prepared_node(node, budget: "int | None" = None) -> _Prepared:
    try:
        return _Prepared(_as_term(canonical(node)), budget)
    except RecursionError:
        raise MatchBudget(budget, 0) from None


def node_member(node, text: str) -> bool:
    """Intent:
        Whether the string `text` is in the language of a bare `node`,
        decided by taking the derivative of the term by each character
        in turn and asking whether what is left holds the empty string.
        No solver is involved, so the answer does not depend on one and
        cannot time out; a complement is every string outside its
        argument, over all characters.

    Raises:
        InvalidTerm: the node is not of the schema.
        MatchBudget: the question built more derivative terms than
            allowed, or went deeper into the term than `_MATCH_DEPTH`,
            which no term of ordinary size does.
    """
    return _prepared_node(node)(text)


def node_matcher(node) -> _Prepared:
    """Intent:
        `node_member` for one bare node, prepared once: a function from
        a string to whether the node's language holds it, for asking
        about many strings, reporting the work it has `spent`.

    Raises:
        InvalidTerm: the node is not of the schema.
        MatchBudget: as `node_member`, when the node is prepared or
            when the returned function is called.
    """
    return _prepared_node(node)


#: the prepared definitions, by `(term hash, bound, budget)`
_PREPARED: dict = {}
#: how many prepared definitions are kept
_PREPARED_KEPT = 256
_BOUNDS = ("at_least", "at_most")


def _prepared_definition(document, bound: "str | None", budget: "int | None") -> _Prepared:
    _, exact, _, _ = _read(document)
    if bound is not None and bound not in _BOUNDS:
        raise InvalidTerm(f"the bound {bound!r} is not at_least or at_most")
    if not exact and bound is None:
        raise InvalidTerm("the definition is not exact: ask for its at_least or at_most bound")
    key = (term_hash(document), bound if not exact else None, budget)
    kept = _PREPARED.get(key)
    if kept is None:
        at_most, at_least = bounds(document)
        kept = _prepared_node(at_least if bound == "at_least" else at_most, budget)
        if len(_PREPARED) >= _PREPARED_KEPT:
            _PREPARED.clear()
        _PREPARED[key] = kept
    return kept


def member(document, text: str, *, bound: "str | None" = None,
           budget: "int | None" = None) -> bool:
    """Intent:
        Whether the string `text` is in the language a definition
        states, read over the definition's own alphabet (a text with a
        character outside it is no member, and a complement is taken
        inside it), or, with `bound` (`at_least` or `at_most`), in that
        bound of a definition that is not exact. `budget` is the most
        derivative terms the question may build (`MATCH_BUDGET` when
        None). The prepared term is remembered by the definition's hash,
        so asking again costs one step per character; `matcher` gives
        the work spent.

        A bare node (an object with an `op`) is read as `node_member`
        reads it.

    Raises:
        InvalidTerm: the document is not a definition of this kind and
            version, the bound is neither bound, or the definition is
            not exact and no bound is named.
        MatchBudget: the question built more derivative terms than the
            budget, or went deeper into the term than `_MATCH_DEPTH`;
            it carries the `budget` and the work `spent`.
    """
    if isinstance(document, dict) and "op" in document:
        return node_member(document, text)
    return _prepared_definition(document, bound, budget)(text)


def matcher(document, *, bound: "str | None" = None, budget: "int | None" = None):
    """Intent:
        `member` for one definition, prepared once and remembered by the
        definition's hash: a function from a string to whether the
        definition's language (or its `bound`) holds it, with the
        `budget` it works within and the derivative terms it has
        `spent`. A bare node is prepared as `node_matcher` prepares it.

    Raises:
        InvalidTerm: as `member`.
        MatchBudget: as `member`, when the returned function is called.
    """
    if isinstance(document, dict) and "op" in document:
        return node_matcher(document)
    return _prepared_definition(document, bound, budget)


def places(text: str, inside, outside) -> bool:
    """Whether the matcher puts `text` in every node of `inside` and in
    no node of `outside`: a second reading of a string a solver
    returned for that question."""
    try:
        return all(member(n, text) for n in inside) \
            and not any(member(n, text) for n in outside)
    except MatchBudget:
        return False


def representatives(nodes, alphabet=None) -> list:
    """One character for each atom of `alphabet` (all of Unicode when
    None) under the character sets of `nodes`: the characters no node
    tells apart share an atom, and a printable ASCII character stands
    for an atom that has one."""
    sets: list = []
    for node in nodes:
        _char_sets(canonical(node), sets)
    ranges = _ranges(alphabet, "alphabet") if alphabet is not None else [[0, MAX_CODE_POINT]]
    return [chr(code) for code in _atoms(ranges, sets)[2]]


# ---- atoms ------------------------------------------------------------

def atoms(nodes, alphabet=None) -> list:
    """Intent:
        The atoms of `alphabet` (all of Unicode when None) under the
        character sets of `nodes`, as `(ranges, representative)` pairs:
        the code point ranges, written as lists, of the characters no
        node tells apart, and one character of the atom, a printable
        ASCII one where the atom has one (as `representatives` gives).

    Raises:
        InvalidTerm: a node or the alphabet is not of the schema.
    """
    sets: list = []
    for node in nodes:
        _char_sets(canonical(node), sets)
    ranges = _ranges(alphabet, "alphabet") if alphabet is not None else [[0, MAX_CODE_POINT]]
    starts, atom_of, members = _atoms(ranges, sets)
    ends: list = []
    for i, start in enumerate(starts):
        later = starts[i + 1] if i + 1 < len(starts) else MAX_CODE_POINT + 1
        # a stretch ends where the next begins or where the alphabet stops
        j = bisect_right(ranges, [start, MAX_CODE_POINT + 1]) - 1
        ends.append(min(later - 1, ranges[j][1]))
    held: list = [[] for _ in members]
    for start, end, k in zip(starts, ends, atom_of):
        if held[k] and held[k][-1][1] + 1 == start:
            held[k][-1][1] = end
        else:
            held[k].append([start, end])
    return [(held[k], chr(members[k])) for k in range(len(members))]


def shortest_member(document, *, bound: "str | None" = None, limit: int = 12) -> "str | None":
    """Intent:
        A shortest string of at most `limit` characters in the language
        a definition states (or in its `bound`), or None when it holds
        none that short. The search goes breadth first over the
        derivatives of the prepared term, by one character of each atom
        of the definition's alphabet under its character sets; no node
        tells two characters of one atom apart, so a None is a proof
        that no member is that short. No solver is asked.

    Raises:
        InvalidTerm: as `member`.
        MatchBudget: the search built more derivative terms than
            `MATCH_BUDGET`.
    """
    prepared = _prepared_definition(document, bound, None)
    at_most, at_least = bounds(document)
    node = at_least if bound == "at_least" else at_most
    letters = [shown for _, shown in atoms([node], alphabet_of(document))]
    frontier = [("", 0)]
    reached = {0}
    for _ in range(limit + 1):
        following = []
        for text, state in frontier:
            if prepared.accepts[state]:
                return text
            for letter in letters:
                prepared(text + letter)
                after = prepared.step[(state, letter)]
                if after not in reached and prepared.terms[after] != _EMPTY_T:
                    reached.add(after)
                    following.append((text + letter, after))
        frontier = following
        if not frontier:
            return None
    return None

def _char_sets(node: dict, into: list) -> None:
    """Every distinct character set a node tells characters apart by:
    the ranges of each `chars` node and each character of a literal."""
    op = node["op"]
    if op == "chars":
        if node["ranges"] not in into:
            into.append(node["ranges"])
    elif op == "literal":
        for code in node["codes"]:
            one = [[code, code]]
            if one not in into:
                into.append(one)
    elif op in ("complement", "repeat"):
        _char_sets(node["arg"], into)
    elif op in _MANY:
        for arg in node["args"]:
            _char_sets(arg, into)


def _holds(ranges: list, code: int) -> bool:
    i = bisect_right(ranges, [code, MAX_CODE_POINT + 1]) - 1
    return i >= 0 and ranges[i][0] <= code <= ranges[i][1]


def _atoms(alphabet: list, sets: list) -> tuple:
    """Intent:
        The atoms of `alphabet` under `sets`: `(starts, atom_of,
        members)` where `starts` are the sorted first code points of
        the stretches of the alphabet no set cuts, `atom_of[i]` is the
        atom the i-th stretch belongs to, and `members[k]` is one code
        point of atom `k`, a printable ASCII one where the atom has
        one. Two stretches are one atom when the same sets hold them.
    """
    cuts: set = set()
    for lo, hi in alphabet:
        cuts.update((lo, hi + 1))
    for ranges in sets:
        for lo, hi in ranges:
            cuts.update((lo, hi + 1))
    starts = [c for c in sorted(cuts) if _holds(alphabet, c)]
    ends = sorted(cuts)
    atom_of: list = []
    by_signature: dict = {}
    members: list = []
    for start in starts:
        signature = tuple(_holds(ranges, start) for ranges in sets)
        k = by_signature.setdefault(signature, len(by_signature))
        atom_of.append(k)
        end = ends[bisect_right(ends, start)] - 1
        shown = next((c for c in range(max(start, 0x21), min(end, 0x7E) + 1)), None)
        if k == len(members):
            members.append(shown if shown is not None else start)
        elif shown is not None and not 0x21 <= members[k] <= 0x7E:
            members[k] = shown
    return starts, atom_of, members


# ---- lowering to z3 ---------------------------------------------------

class _Lowering:
    """One question's nodes as z3 regular expressions over one symbol
    per atom."""

    def __init__(self, z3, alphabet: list, nodes: list) -> None:
        self.z3 = z3
        sets: list = []
        for node in nodes:
            _char_sets(node, sets)
        self.alphabet = alphabet
        self.starts, self.atom_of, self.members = _atoms(alphabet, sets)
        self.sort = z3.ReSort(z3.StringSort())
        if self.members:
            self.sigma = z3.Range(chr(_SYMBOL_BASE),
                                  chr(_SYMBOL_BASE + len(self.members) - 1))
            self.everything = z3.Star(self.sigma)
        else:
            # over no character at all the one string is the empty one
            self.sigma = z3.Empty(self.sort)
            self.everything = z3.Re(z3.StringVal(""))
        self._seen: dict = {}

    def _symbol(self, atom: int) -> str:
        return chr(_SYMBOL_BASE + atom)

    def _atoms_in(self, ranges: list) -> list:
        """The atoms the character set holds, each once, in order."""
        found: list = []
        for start, atom in zip(self.starts, self.atom_of):
            if _holds(ranges, start) and atom not in found:
                found.append(atom)
        return sorted(found)

    def _atom_at(self, code: int) -> "int | None":
        if not _holds(self.alphabet, code):
            return None
        return self.atom_of[bisect_right(self.starts, code) - 1]

    def regex(self, node: dict):
        """The z3 regular expression for a canonical node."""
        key = json.dumps(node, sort_keys=True)
        if key not in self._seen:
            self._seen[key] = self._regex(node)
        return self._seen[key]

    def _regex(self, node: dict):
        z3, op = self.z3, node["op"]
        if op == "empty":
            return z3.Empty(self.sort)
        if op == "epsilon":
            return z3.Re(z3.StringVal(""))
        if op == "literal":
            atoms = [self._atom_at(code) for code in node["codes"]]
            if any(a is None for a in atoms):
                return z3.Empty(self.sort)
            return z3.Re(z3.StringVal("".join(self._symbol(a) for a in atoms)))
        if op == "chars":
            atoms = self._atoms_in(node["ranges"])
            if not atoms:
                return z3.Empty(self.sort)
            runs: list = []
            for a in atoms:
                if runs and a == runs[-1][1] + 1:
                    runs[-1][1] = a
                else:
                    runs.append([a, a])
            parts = [z3.Range(self._symbol(lo), self._symbol(hi)) for lo, hi in runs]
            return parts[0] if len(parts) == 1 else z3.Union(*parts)
        if op == "complement":
            return z3.Intersect(z3.Complement(self.regex(node["arg"])), self.everything)
        if op == "repeat":
            inner, lo, hi = self.regex(node["arg"]), node["min"], node["max"]
            if hi is None:
                if lo == 0:
                    return z3.Star(inner)
                if lo == 1:
                    return z3.Plus(inner)
                return z3.Concat(z3.Loop(inner, lo, lo), z3.Star(inner))
            return z3.Loop(inner, lo, hi)
        parts = [self.regex(a) for a in node["args"]]
        build = {"concat": z3.Concat, "union": z3.Union, "inter": z3.Intersect}[op]
        return build(*parts)

    def decode(self, text: str) -> str:
        """A solver string as a string over the alphabet, each symbol
        read as its atom's member."""
        plain = re.sub(r"\\u\{([0-9a-fA-F]+)\}", lambda m: chr(int(m.group(1), 16)), text)
        return "".join(chr(self.members[ord(ch) - _SYMBOL_BASE]) for ch in plain)


def find_member(alphabet, inside, outside, *, timeout_ms: int = 5000) -> Found:
    """Intent:
        A string over `alphabet` (code point ranges) that every node in
        `inside` holds and no node in `outside` holds: `member` with
        the string, `none` when no such string exists, or `unknown`
        with the reason.

    Raises:
        InvalidTerm: a node or the alphabet is not of the schema.

    Notes:
        A complement is taken over `alphabet`. `none` is a proof: the
        question over atoms has the answer of the question over the
        whole alphabet.
    """
    alphabet = _ranges(alphabet, "alphabet")
    inside = [canonical(n) for n in inside]
    outside = [canonical(n) for n in outside]
    try:
        import z3
    except ImportError:
        return Found("unknown", reason="z3 is not installed (the mathema[smt] extra)")
    lowering = _Lowering(z3, alphabet, inside + outside)
    x = z3.String("member")
    solver = z3.Solver()
    solver.set("timeout", int(timeout_ms))
    solver.add(z3.InRe(x, lowering.everything))
    for node in inside:
        solver.add(z3.InRe(x, lowering.regex(node)))
    for node in outside:
        solver.add(z3.Not(z3.InRe(x, lowering.regex(node))))
    # the solver's own timeout is not always honoured inside one long
    # step, so the wall clock also interrupts it from outside
    import threading
    watchdog = threading.Timer(timeout_ms / 1000.0 + 1.0, solver.ctx.interrupt)
    watchdog.daemon = True
    watchdog.start()
    try:
        outcome = solver.check()
    finally:
        watchdog.cancel()
    if outcome == z3.unsat:
        return Found("none")
    if outcome != z3.sat:
        return Found("unknown", reason=f"z3 gave no answer within {timeout_ms} ms "
                                       f"({solver.reason_unknown()})")
    value = solver.model().eval(x, model_completion=True)
    return Found("member", member=lowering.decode(value.as_string()))


__all__ = ["Found", "InvalidTerm", "KIND", "MATCH_BUDGET", "VERSION", "alphabet_of", "atoms",
           "bounds", "canonical", "canonical_text", "MatchBudget", "matcher", "member",
           "node_matcher", "node_member", "places", "representatives", "shortest_member",
           "find_member", "is_definition", "term_hash", "validate"]
