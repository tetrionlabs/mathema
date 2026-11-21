# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every claim of the shipped corpus reads back from its stored text.

For each text `t` of `tests/data/claim_corpus.json` that parses, the
stored text of `parse(t)` read back is the same claim: it has the same
identity text, the same relation and negation, the same chain
relations, and each side means the same expression as `parse(t)`'s.
Two sides mean the same expression when their sympy forms are equal,
or print alike (`Mod(n, 24)` read from the stored text and `n % 24`
read from the written one), with `None` read as `absent`, its
synonym in the claim grammar. A rendering that dropped needed
parentheses (`(a + b)*c` stored as `a + b*c`) reads back as another
expression and fails here even where the identity texts agree, since
identity is itself a rendering. The texts the pinned corpus test
lists as unstable are left out.
"""
import ast
import json
import pathlib

from mathema import grammar
from mathema._float_text import exact_literal_text
from mathema.conjecture import claim
from mathema.linalg import declared_matrix_names
from mathema.spec import canonical_claim_text, fingerprint_text
from tests.test_the_shipped_claim_corpus_reads_as_pinned import UNSTABLE

DATA = pathlib.Path(__file__).resolve().parent / "data" / "claim_corpus.json"
CORPUS = json.loads(DATA.read_text(encoding="utf-8"))
PARSING = sorted(t for t, v in CORPUS.items()
                 if v["parses"] and t not in UNSTABLE[False])


def _sides(cj) -> list:
    """Each side of `cj` (both sides, then every chain link's) as the
    sympy expression the renderer reads it as."""
    mats = declared_matrix_names(cj.domain) | grammar._BAR_MATRICES.get()
    over_c = {p for p, b in (cj.domain or {}).items()
              if b == "C" or getattr(b, "base_type", None) == "C"}
    funcs = frozenset(cj.funcs) | {"f"}
    texts = [cj.lhs, cj.rhs] + [t for link in (cj.links or []) for t in (link[0], link[2])]
    out = []
    with grammar.bars_over_matrices(mats), grammar.complex_in_view(over_c):
        token = grammar._ORDERED_MATRICES.set(frozenset(mats))
        try:
            for text in texts:
                out.append(None if not text else grammar._node_to_sympy(
                    ast.parse(exact_literal_text(text), mode="eval"), funcs))
        finally:
            grammar._ORDERED_MATRICES.reset(token)
    return out


def _same_expression(a, b) -> bool:
    if a == b:
        return True
    return str(a).replace("None", "absent") == str(b).replace("None", "absent")


def test_the_corpus_has_claims_to_read_back():
    assert len(PARSING) >= 3000


def test_every_claim_reads_back_from_its_stored_text_as_the_same_claim():
    wrong = []
    for text in PARSING:
        written = claim(text)
        back = claim(canonical_claim_text(written))
        why = []
        if fingerprint_text(back) != fingerprint_text(written):
            why.append("identity")
        if (written.relation, bool(getattr(written, "negated", False))) != \
                (back.relation, bool(getattr(back, "negated", False))):
            why.append("relation")
        if [link[1] for link in written.links or []] != \
                [link[1] for link in back.links or []]:
            why.append("chain")
        sides_written, sides_back = _sides(written), _sides(back)
        if len(sides_written) != len(sides_back) or not all(
                _same_expression(a, b) for a, b in zip(sides_written, sides_back)):
            why.append("sides")
        if why:
            wrong.append((text, why))
    assert not wrong, wrong[:20]


def test_a_rendering_that_drops_parentheses_is_caught():
    written = claim("for x in [0, 1], f(x) <= (x + 1)*x")
    stored = canonical_claim_text(written)
    assert "x*(x + 1)" in stored, stored
    back = claim(stored.replace("x*(x + 1)", "x*x + 1"))
    assert not all(_same_expression(a, b)
                   for a, b in zip(_sides(written), _sides(back)))
