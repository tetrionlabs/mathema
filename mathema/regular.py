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
string), `chars` (one character from inclusive code point ranges),
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

def _ranges(raw, where: str) -> list:
    """Inclusive code point ranges, checked, sorted and merged."""
    if not isinstance(raw, list):
        raise InvalidTerm(f"{where}: ranges must be a list of [lo, hi] pairs")
    pairs = []
    for pair in raw:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) for v in pair)
                or not 0 <= pair[0] <= pair[1] <= MAX_CODE_POINT):
            raise InvalidTerm(f"{where}: {pair!r} is not a code point range [lo, hi]")
        pairs.append((pair[0], pair[1]))
    merged: list = []
    for lo, hi in sorted(pairs):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged


def canonical(node) -> dict:
    """Intent:
        The canonical form of a node: ranges sorted and merged, a
        `concat`, `union` or `inter` never nesting its own kind, no
        `epsilon` inside a `concat`, a `concat` holding `empty` reduced
        to `empty`, repeated arguments of a `union` or `inter` kept
        once in first-seen order, and a one-argument `concat`, `union`
        or `inter` reduced to that argument.

    Raises:
        InvalidTerm: the node is not of the schema.
    """
    if not isinstance(node, dict) or not isinstance(node.get("op"), str):
        raise InvalidTerm(f"{node!r} is not a node (an object with an 'op')")
    op = node["op"]
    if op in _LEAVES:
        return {"op": op}
    if op == "literal":
        text = node.get("text")
        if not isinstance(text, str):
            raise InvalidTerm("literal: 'text' must be a string")
        return {"op": "literal", "text": text} if text else {"op": "epsilon"}
    if op == "chars":
        ranges = _ranges(node.get("ranges"), "chars")
        return {"op": "chars", "ranges": ranges} if ranges else {"op": "empty"}
    if op == "complement":
        return {"op": "complement", "arg": canonical(node.get("arg"))}
    if op == "repeat":
        lo, hi = node.get("min", 0), node.get("max")
        if not isinstance(lo, int) or isinstance(lo, bool) or lo < 0 or not (
                hi is None or (isinstance(hi, int) and not isinstance(hi, bool) and hi >= lo)):
            raise InvalidTerm(f"repeat: min {lo!r} and max {hi!r} are not a count range")
        return {"op": "repeat", "arg": canonical(node.get("arg")), "min": lo, "max": hi}
    if op in _MANY:
        raw = node.get("args")
        if not isinstance(raw, list) or not raw:
            raise InvalidTerm(f"{op}: 'args' must be a list of nodes")
        args: list = []
        for arg in (canonical(a) for a in raw):
            args.extend(arg["args"] if arg["op"] == op else [arg])
        if op == "concat":
            if any(a["op"] == "empty" for a in args):
                return {"op": "empty"}
            args = [a for a in args if a["op"] != "epsilon"]
            if not args:
                return {"op": "epsilon"}
        else:
            kept: list = []
            for a in args:
                if a not in kept:
                    kept.append(a)
            args = kept
        return args[0] if len(args) == 1 else {"op": op, "args": args}
    raise InvalidTerm(f"{op!r} is not a regular-language operation")


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
    """`(alphabet, exact, at_most, at_least)` of a checked document,
    the nodes canonical."""
    if not isinstance(document, dict) or document.get("kind") != KIND:
        raise InvalidTerm(f"not a {KIND} definition")
    if document.get("version") != VERSION:
        raise InvalidTerm(f"{KIND} version {document.get('version')!r} is not read; "
                          f"this reads version {VERSION}")
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
        `(at_most, at_least)` for a definition, as canonical nodes that
        read the same over any alphabet holding the definition's own:
        a language holding only members, and one holding every member.
        They are one node when the definition is exact.

    Raises:
        InvalidTerm: the document is not of the schema.
    """
    alphabet, _, at_most, at_least = _read(document)
    return _closed(at_most, alphabet), _closed(at_least, alphabet)


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


def term_hash(document) -> str:
    """Intent:
        The identity of a definition's meaning, a sha256 hex digest of
        its alphabet, its exact flag and its canonical nodes; `source`
        and any other key are not read, so the same language compiled
        from another spelling or on another runtime hashes the same.

    Raises:
        InvalidTerm: the document is not of the schema.
    """
    alphabet, exact, at_most, at_least = _read(document)
    meaning: dict = {"kind": KIND, "version": VERSION, "alphabet": alphabet, "exact": exact}
    if exact:
        meaning["language"] = at_most
    else:
        meaning["at_least"], meaning["at_most"] = at_least, at_most
    text = json.dumps(meaning, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


# ---- atoms ------------------------------------------------------------

def _char_sets(node: dict, into: list) -> None:
    """Every distinct character set a node tells characters apart by:
    the ranges of each `chars` node and each character of a literal."""
    op = node["op"]
    if op == "chars":
        if node["ranges"] not in into:
            into.append(node["ranges"])
    elif op == "literal":
        for ch in node["text"]:
            one = [[ord(ch), ord(ch)]]
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
        count = max(len(self.members), 1)
        self.sigma = z3.Range(chr(_SYMBOL_BASE), chr(_SYMBOL_BASE + count - 1))
        self.everything = z3.Star(self.sigma)
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
            atoms = [self._atom_at(ord(ch)) for ch in node["text"]]
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
           "find_member", "is_definition", "term_hash"]
