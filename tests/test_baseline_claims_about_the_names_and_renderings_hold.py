# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Claims, written in mathema's own claim language, about core's naming
and rendering functions; each is adjudicated here against the code and
must hold.

- `companion_name`: the companion's name is the claim's name followed by
  `[float]`, so it is seven characters longer, for every claim name;
- `companion_descriptor`: a name with no bracket carries no descriptor;
- rendering a claim text in ascii twice gives what rendering it once
  gives, and the claims fingerprint of a text equals the fingerprint of
  its ascii rendering, for every corpus text that renders as itself
  (`L[stable_claim_text]`, the corpus less the texts pinned as unstable
  in `test_the_shipped_claim_corpus_reads_as_pinned`).

The first two claims are about core's functions directly. The last two
are about small wrappers (`ascii_rendering`, `same_fingerprint`) that
compose core's functions, because core's own functions take a parsed
claim, not a text. The verdict is `holds`: the language is a set of
strings, which the derive route does not read.
"""
import string

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.gates import companion_descriptor, companion_name
from mathema.languages import StringLanguage, register_language, unregister_language
from mathema.spec import claims_fingerprint, render_claim_text

from tests.test_the_shipped_claim_corpus_reads_as_pinned import PARSING, UNSTABLE

_STABLE = sorted(set(PARSING) - UNSTABLE[False] - UNSTABLE[True])
_NAME_CHARS = string.ascii_lowercase + string.digits + "_"
CLAIMS = {
    "companion_name_appends_float":
        'for parent_name in L[claim_name], f(parent_name) == parent_name + "[float]"',
    "companion_name_adds_seven_characters":
        "for parent_name in L[claim_name], len(f(parent_name)) == len(parent_name) + 7",
    "a_bare_name_has_no_descriptor":
        "for name in L[claim_name], len(f(name)) == 0",
    "ascii_rendering_is_a_fixed_point":
        "for text in L[stable_claim_text], f(f(text)) == f(text)",
    "identity_ignores_the_spelling":
        "for text in L[stable_claim_text], f(text) == True",
}


def ascii_rendering(text: str) -> str:
    return render_claim_text(claim(text), unicode=False)


def same_fingerprint(text: str) -> bool:
    spelled = lambda t: claims_fingerprint([{"name": "c", "statement": t}])  # noqa: E731
    return spelled(text) == spelled(ascii_rendering(text))


@pytest.fixture(autouse=True)
def languages():
    register_language("claim_name", StringLanguage(
        "claim_name", char_ok=lambda c: c in _NAME_CHARS,
        pool=string.ascii_lowercase + "_"))
    members = set(_STABLE)
    register_language("stable_claim_text", StringLanguage(
        "stable_claim_text", accepts=members.__contains__,
        generate=lambda rng: rng.choice(_STABLE)))
    try:
        yield
    finally:
        unregister_language("claim_name")
        unregister_language("stable_claim_text")


def _verdict(fn, key):
    (probe,) = [p for p in check_conjectures(fn, [claim(CLAIMS[key], name="c")])
                if p.name == "c"]
    return probe


@pytest.mark.parametrize("fn,key", [
    (companion_name, "companion_name_appends_float"),
    (companion_name, "companion_name_adds_seven_characters"),
    (companion_descriptor, "a_bare_name_has_no_descriptor"),
    (ascii_rendering, "ascii_rendering_is_a_fixed_point"),
    (same_fingerprint, "identity_ignores_the_spelling"),
])
def test_the_claim_holds(fn, key):
    probe = _verdict(fn, key)
    assert probe.verdict == "holds", (probe.verdict, probe.note, probe.counterexample)
    assert probe.n and probe.n > 10
