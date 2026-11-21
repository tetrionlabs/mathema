# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What any implementation of the regular-language term algebra must
do, run on `mathema.regular`: the shared vectors (canonical text and
hash, the malformed documents refused), documents generated from a
fixed seed (every node kind, pairs of bounds, narrow alphabets, code
points on every plane), membership of every short string over the code
points a document names, and the readings implementations have
differed on: a text outside a narrow alphabet, a document stating both
a language and bounds, ranges written as tuples, a flag that
contradicts the keys present, and a long text under a bounded repeat.

The hashes of the generated documents are pinned in
`tests/data/regular_term_generated_hashes.json`. Membership is checked
against `_denoted`, a reading of a node as the set of strings it holds
among all strings up to a length over a few characters, built from the
node's meaning alone and sharing no code with the derivative matcher."""
import copy
import inspect
import itertools
import json
import random
from pathlib import Path

import pytest

from mathema import regular

DATA = Path(__file__).parent / "data"
VECTORS = json.loads((DATA / "regular_term_vectors.json").read_text())["vectors"]
VALID = [v for v in VECTORS if not v.get("invalid")]
FULL = [[0, 0x10FFFF]]
KEYS = ("language", "at_least", "at_most")


def _member(doc, text, bound):
    """Membership of `text` in a document, or in one of its bounds: the
    document-level `member` where it takes a bound, else the bound's
    node from `bounds` read by `matcher`."""
    if "bound" in inspect.signature(regular.member).parameters:
        return regular.member(doc, text, bound=bound)
    at_most, at_least = regular.bounds(doc)
    return regular.matcher(at_least if bound == "at_least" else at_most)(text)


def generated(count=300, seed=20261120):
    """Documents drawn from a fixed seed."""
    rng = random.Random(seed)
    points = [97, 98, 48, 10, 0x7F, 0xE9, 0x3B1, 0xD800, 0xDFFF, 0xFFFF, 0x10000, 0x1F600,
              0x10FFFF, 0]
    ranges = [[97, 122], [48, 57], [0, 127], [0x80, 0x10FFFF], [0xD800, 0xDFFF],
              [0x10000, 0x10FFFF], [97, 97], [98, 99], [0, 0x10FFFF]]
    alphabets = [FULL] * 6 + [[[0, 127]], [[97, 122]], [[0, 0xD7FF], [0xE000, 0x10FFFF]],
                              [[48, 57], [97, 102]]]

    def node(depth):
        if depth >= 3 or rng.random() < 0.3:
            kind = rng.choice(["empty", "epsilon", "literal", "literal", "chars", "chars",
                               "chars"])
            if kind == "literal":
                return {"op": kind, "codes": [rng.choice(points)
                                              for _ in range(rng.randint(0, 3))]}
            if kind == "chars":
                return {"op": kind, "ranges": [list(rng.choice(ranges))
                                               for _ in range(rng.randint(0, 3))]}
            return {"op": kind}
        kind = rng.choice(["concat", "concat", "union", "union", "inter", "complement",
                           "repeat", "repeat"])
        if kind == "complement":
            return {"op": kind, "arg": node(depth + 1)}
        if kind == "repeat":
            lo = rng.randint(0, 2)
            return {"op": kind, "arg": node(depth + 1), "min": lo,
                    "max": rng.choice([None, lo, lo + 1, lo + 2])}
        return {"op": kind, "args": [node(depth + 1) for _ in range(rng.randint(0, 3))]}

    out = []
    for i in range(count):
        doc = {"kind": "regular_language", "version": 1,
               "alphabet": copy.deepcopy(rng.choice(alphabets)), "source": {"generated": i}}
        if rng.random() < 0.25:
            doc.update(exact=False, at_least=node(0), at_most=node(0))
        else:
            doc.update(exact=True, language=node(0))
        out.append(doc)
    return out


GENERATED = generated()


def named_points(doc):
    """Up to seven characters a document tells apart: the ends of its
    ranges and its literal code points, and a newline."""
    found = [10]

    def walk(node):
        for lo, hi in node.get("ranges", []):
            found.extend((lo, hi))
        found.extend(node.get("codes", []))
        for arg in node.get("args", []) + ([node["arg"]] if "arg" in node else []):
            walk(arg)
    for key in KEYS:
        if key in doc:
            walk(doc[key])
    return [chr(c) for c in dict.fromkeys(found)][:7]


def short_strings(chars, longest=3):
    yield ""
    for n in range(1, longest + 1):
        for letters in itertools.product(chars, repeat=n):
            yield "".join(letters)


def _denoted(node, universe):
    """The strings of `universe` (every string up to a length over some
    characters, closed under taking pieces) that `node` holds, read from
    the node's meaning: a complement is every string outside its
    argument."""
    op = node["op"]
    if op == "empty":
        return frozenset()
    if op == "epsilon":
        return frozenset({""})
    if op == "literal":
        text = "".join(chr(c) for c in node["codes"])
        return frozenset({text}) & universe
    if op == "chars":
        return frozenset(s for s in universe if len(s) == 1
                         and any(lo <= ord(s) <= hi for lo, hi in node["ranges"]))
    if op == "complement":
        return universe - _denoted(node["arg"], universe)
    if op == "union":
        return frozenset().union(*(_denoted(a, universe) for a in node["args"]))
    if op == "inter":
        out = universe
        for arg in node["args"]:
            out = out & _denoted(arg, universe)
        return out

    def joined(left, right):
        return frozenset(a + b for a in left for b in right if a + b in universe)
    if op == "concat":
        out = frozenset({""})
        for arg in node["args"]:
            out = joined(out, _denoted(arg, universe))
        return out
    one = _denoted(node["arg"], universe)
    longest = max((len(s) for s in universe), default=0)
    copies, out, count = frozenset({""}), frozenset(), 0
    while True:
        if count >= node["min"]:
            out = out | copies
        if node["max"] is not None and count >= node["max"]:
            return out
        grown = joined(copies, one)
        if count > longest + node["min"] and grown <= out:
            return out
        copies, count = grown, count + 1


def _over_alphabet(texts, alphabet):
    return frozenset(t for t in texts if all(any(lo <= ord(c) <= hi for lo, hi in alphabet)
                                             for c in t))


def test_each_vector_has_its_canonical_text_and_hash():
    for vector in VALID:
        assert regular.canonical_text(vector["document"]) == vector["canonical"], vector["name"]
        assert regular.term_hash(vector["document"]) == vector["hash"], vector["name"]


def test_each_malformed_vector_is_refused():
    for vector in VECTORS:
        if vector.get("invalid"):
            with pytest.raises(ValueError):
                regular.term_hash(vector["document"])


def test_generated_documents_have_their_pinned_hashes():
    pinned = json.loads((DATA / "regular_term_generated_hashes.json").read_text())["hashes"]
    assert len(pinned) == len(GENERATED)
    wrong = [doc["source"]["generated"] for doc, digest in zip(GENERATED, pinned)
             if regular.term_hash(doc) != digest]
    assert wrong == []


def test_membership_of_every_short_string_agrees_with_the_meaning():
    wrong = []
    documents = [v["document"] for v in VALID
                 if v["document"]["alphabet"] != [[0, 0xFFFF]] and v["document"]["version"] == 1
                 and v["document"]["kind"] == "regular_language"] + GENERATED
    for doc in documents:
        universe = frozenset(short_strings(named_points(doc)))
        alphabet = regular.alphabet_of(doc)
        for bound in ((None,) if doc["exact"] else ("at_least", "at_most")):
            node = doc["language" if bound is None else bound]
            # a complement inside a narrow alphabet is taken inside it
            inside = _over_alphabet(universe, alphabet)
            expected = _over_alphabet(_denoted(node, inside), alphabet)
            for text in sorted(universe):
                if _member(doc, text, bound) != (text in expected):
                    wrong.append((json.dumps(doc)[:200], bound, text))
                    break
    assert wrong[:5] == []


def exact(language, alphabet=None):
    return {"kind": "regular_language", "version": 1, "alphabet": alphabet or FULL,
            "exact": True, "language": language, "source": {}}


def test_a_text_outside_a_narrow_alphabet_is_no_member():
    not_a = {"op": "complement", "arg": {"op": "literal", "codes": [97]}}
    doc = exact(not_a, [[97, 122]])
    assert _member(doc, "b", None) and _member(doc, "", None)
    assert not _member(doc, "a", None)
    assert not _member(doc, "!", None) and not _member(doc, "b\n", None)
    assert _member(exact(not_a), "!", None)


@pytest.mark.parametrize("length", [100, 300, 999, 3000])
def test_a_long_text_under_a_bounded_repeat_is_answered(length):
    doc = exact({"op": "concat", "args": [
        {"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 98]]}, "min": 2, "max": 4000},
        {"op": "repeat", "arg": {"op": "chars", "ranges": FULL}, "min": 0, "max": None}]})
    assert _member(doc, "a" * length, None)
    assert not _member(doc, "c" + "a" * length, None)


def test_membership_is_not_answered_for_another_version_or_kind():
    later = {**exact({"op": "literal", "codes": [97]}), "version": 2}
    other = {**exact({"op": "literal", "codes": [97]}), "kind": "other"}
    for doc in (later, other):
        assert len(regular.term_hash(doc)) == 64
        with pytest.raises(ValueError):
            _member(doc, "a", None)


MALFORMED = {
    "a language and both bounds": {**exact({"op": "empty"}), "at_least": {"op": "empty"},
                                   "at_most": {"op": "empty"}},
    "bounds and a language, not exact": {**exact({"op": "empty"}), "exact": False,
                                         "at_least": {"op": "empty"},
                                         "at_most": {"op": "empty"}},
    "alphabet ranges as tuples": {**exact({"op": "empty"}), "alphabet": [(0, 127)]},
    "chars ranges as tuples": exact({"op": "chars", "ranges": [(97, 98)]}),
    "the version is true": {**exact({"op": "empty"}), "version": True},
    "exact is 1": {**exact({"op": "empty"}), "exact": 1},
    "exact with only the bounds": {"kind": "regular_language", "version": 1, "alphabet": FULL,
                                   "exact": True, "at_least": {"op": "empty"},
                                   "at_most": {"op": "empty"}},
    "not exact with only a language": {**exact({"op": "empty"}), "exact": False},
    "only a language": {"language": {"op": "epsilon"}},
    "no alphabet": {k: v for k, v in exact({"op": "empty"}).items() if k != "alphabet"},
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_a_document_that_is_not_well_formed_is_refused(name):
    with pytest.raises(ValueError):
        regular.term_hash(MALFORMED[name])
