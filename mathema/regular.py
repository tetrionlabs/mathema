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
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise InvalidTerm(f"{where}: {pair!r} is not a code point range [lo, hi]")
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


def term_hash(document) -> str:
    """Intent:
        The identity of a definition's meaning: the SHA-256, in lower
        case hex, of its `canonical_text`. The same language compiled
        from another spelling or on another runtime hashes the same.

    Raises:
        InvalidTerm: the document is not of the schema.
    """
    return hashlib.sha256(canonical_text(document).encode("ascii")).hexdigest()


# ---- atoms ------------------------------------------------------------

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


__all__ = ["Found", "InvalidTerm", "KIND", "VERSION", "alphabet_of", "bounds", "canonical",
           "canonical_text",
           "find_member", "is_definition", "term_hash"]
