# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Whether one string is in a term's language is decided without a
solver, by derivatives: the term left after each character in turn
holds the empty string exactly when the string is a member. The matcher
is held to Python's `re` on hand-written terms, to the solver's answer
on every short string, to the canonical form (a term and its canonical
form hold the same strings), and to the matcher of the package that
compiles terms where that package provides one."""
import itertools
import json
import pathlib
import re

import pytest

from mathema import regular

ALL = [[0, 0x10FFFF]]


def ch(*ranges):
    return {"op": "chars", "ranges": [list(r) for r in ranges]}


def lit(text):
    return {"op": "literal", "codes": [ord(c) for c in text]}


def cat(*args):
    return {"op": "concat", "args": list(args)}


def alt(*args):
    return {"op": "union", "args": list(args)}


def rep(arg, lo=0, hi=None):
    return {"op": "repeat", "arg": arg, "min": lo, "max": hi}


A, B, AB = ch((97, 97)), ch((98, 98)), ch((97, 98))
ANY = rep(ch((0, 0x10FFFF)))
NOT_ALL_A = {"op": "complement", "arg": rep(A)}

TERMS = [
    (rep(AB, 2, 3), r"[ab]{2,3}"),
    (cat(lit("ab"), ANY), r"ab(.|\n)*"),
    (NOT_ALL_A, r"(?!a*\Z)(.|\n)*"),
    ({"op": "inter", "args": [rep(AB, 1), NOT_ALL_A]}, r"[ab]*b[ab]*"),
    (rep(alt(A, {"op": "epsilon"}), 2, 2), r"a{0,2}"),
    (rep(cat(A, rep(B, 0, 1)), 1, 2), r"(ab?){1,2}"),
    (cat(rep(AB), lit("c")), r"[ab]*c"),
    (rep(rep(A, 1, 2)), r"a*"),
    (cat(rep(A, 1), rep(lit("\n"), 0, 1)), r"a+\n?"),
    ({"op": "empty"}, r"(?!)"),
    ({"op": "epsilon"}, r""),
    (rep(alt(lit("ab"), lit("a"))), r"(ab|a)*"),
]
SHORT = ["".join(t) for n in range(5) for t in itertools.product("abc", repeat=n)]


@pytest.mark.parametrize("node,pattern", TERMS, ids=[p or "empty string" for _, p in TERMS])
def test_the_matcher_agrees_with_re_on_every_short_string(node, pattern):
    holds = regular.matcher(node)
    for text in SHORT + ["a\n", "ab\n", "\n", "abcabc"]:
        assert holds(text) == (re.fullmatch(pattern, text) is not None), text
        assert regular.contains(node, text) == holds(text)


@pytest.mark.parametrize("node,pattern", TERMS[:6], ids=[p for _, p in TERMS[:6]])
def test_the_matcher_agrees_with_the_solver_on_every_string_up_to_length_three(node, pattern):
    pytest.importorskip("z3")
    for text in ["".join(t) for n in range(4) for t in itertools.product("ab", repeat=n)]:
        asked = regular.find_member(ALL, inside=[lit(text), node], outside=[])
        assert (asked.status == "member") == regular.contains(node, text), text


def test_a_term_and_its_canonical_form_hold_the_same_strings():
    vectors = json.loads((pathlib.Path(__file__).resolve().parent / "data"
                          / "regular_term_vectors.json").read_text(encoding="utf-8"))["vectors"]
    compared = 0
    for vector in vectors:
        document = vector["document"]
        if vector.get("invalid") or document.get("kind") != regular.KIND \
                or document.get("version") != regular.VERSION:
            continue
        for key in ("language", "at_least", "at_most"):
            if key not in document:
                continue
            node = document[key]
            written, canonical = _plain_matcher(node), regular.matcher(node)
            letters = regular.representatives([node])[:4]
            for n in range(4):
                for t in itertools.product(letters, repeat=n):
                    text = "".join(t)
                    assert written(text) == canonical(text), (vector["name"], text)
                    compared += 1
    assert compared > 1000


def _plain_matcher(node):
    """A matcher over the node exactly as written, with no canonical
    form taken first: the reference the canonical one is held to."""
    def holds(n, text) -> bool:
        op = n["op"]
        if op == "empty":
            return False
        if op == "epsilon":
            return text == ""
        if op == "literal":
            return text == "".join(chr(c) for c in n["codes"])
        if op == "chars":
            return len(text) == 1 and any(lo <= ord(text) <= hi for lo, hi in n["ranges"])
        if op == "union":
            return any(holds(a, text) for a in n["args"])
        if op == "inter":
            return all(holds(a, text) for a in n["args"])
        if op == "complement":
            return not holds(n["arg"], text)
        if op == "concat":
            args = n["args"]
            if not args:
                return text == ""
            return any(holds(args[0], text[:i]) and holds({"op": "concat", "args": args[1:]},
                                                           text[i:])
                       for i in range(len(text) + 1))
        lo, hi = n["min"], n["max"]
        if text == "":
            return lo == 0 or holds(n["arg"], "")
        if hi == 0:
            return False
        fewer = {"op": "repeat", "arg": n["arg"], "min": max(lo - 1, 0),
                 "max": None if hi is None else hi - 1}
        return any(holds(n["arg"], text[:i]) and holds(fewer, text[i:])
                   for i in range(1, len(text) + 1)) or (lo == 0 and False)
    return lambda text: holds(node, text)


def test_the_matcher_agrees_with_the_package_that_compiles_terms():
    theirs = pytest.importorskip(
        "mathema_language.text._regular",
        reason="the installed mathema-language has no term matcher")
    if not hasattr(theirs, "member"):
        pytest.skip("the installed mathema-language has no term matcher")
    for node, _ in TERMS:
        document = {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
                    "language": node}
        for text in SHORT:
            assert regular.contains(node, text) == bool(theirs.member(document, text)), text
