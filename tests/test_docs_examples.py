# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every claim shown in the documentation parses.

The grammar page teaches the claim syntax by example, so an example
that no longer parses is worse than no example: a reader copies it,
gets an error, and stops trusting the page. These tests read the real
markdown and run every claim-shaped string in it through the same
parser `mathema check` uses, so a grammar change that invalidates a
documented spelling fails here rather than in a reader's terminal.

The grammar page's examples are additionally required to come from
`lexicon.LEXICON`, which is itself exercised by `test_lexicon.py`, so
the page, the curated set and the parser cannot drift apart in pairs.
"""
import os
import re

import pytest

from mathema.conjecture import claim
from mathema.lexicon import LEXICON

_DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "docs")

# a string is claim-shaped if it mentions the function under test or
# opens with one of the grammar's own leading keywords
_CLAIM_SHAPED = re.compile(
    r"(^|[^\w])f\(|^(for|let|assuming|raises|is_\w+\(|d\(|lim\(|integrate|"
    r"∫|Sum|Prod|P\.V\.)\b")

# a complete claim states a relation, which is the parser's own first
# requirement. Vocabulary words, grammar fragments shown to explain one
# form, and quoted Python all fail this and are not claims a reader
# would paste.
_HAS_RELATION = re.compile(r"==|!=|<=|>=|≤|≥|≠|~=|=:=|\bequiv\b|=>|[^<>=]<[^=]|[^<>=]>[^=]")
_PYTHON_LINE = re.compile(r":\s*$|^\s*(def|class|import|from|return|@)\b")


# a documented string is a copyable EXAMPLE only if it is complete.
# `...` marks a deliberate elision, `<var>` a syntax template, and a
# trailing `#` an explanatory aside rather than part of the claim.
_ELIDED = re.compile(r"\.\.\.|<\w+>|\{lo,|\blo\b|\bhi\b|\bparam\b|\bname\b|\bexpr\b")


def _claims_in(path):
    """Intent:
        Yield every complete, copyable claim in one markdown file: the
        single-backtick spans inside tables and prose, and each
        non-empty line of a bare (unlabelled) fenced block. Fences
        tagged with a language are code, not claims. Templates and
        elided fragments are skipped, since a reader cannot paste them
        and is not meant to.
    """
    text = open(path, encoding="utf-8").read()
    found = []
    for fence, body in re.findall(r"```(\w*)\n(.*?)```", text, re.S):
        if fence:
            continue
        found += [ln.strip() for ln in body.splitlines() if ln.strip()]
        text = text.replace(f"```{fence}\n{body}```", "")
    for span in re.findall(r"`([^`\n]+)`", text):
        found.append(span.replace("\\|", "|").strip())
    out = []
    for s in found:
        s = re.split(r"\s+#", s)[0].strip()          # drop a trailing aside
        if not s or _ELIDED.search(s) or _PYTHON_LINE.search(s):
            continue
        # the limit arrow is not a relation; strip it before deciding
        if not _CLAIM_SHAPED.search(s) or not _HAS_RELATION.search(
                s.replace("->", " ").replace("-->", " ")):
            continue
        out.append(s)
    return out


def _doc_files():
    return sorted(os.path.join(_DOCS, f) for f in os.listdir(_DOCS)
                  if f.endswith(".md"))


@pytest.mark.parametrize("path", _doc_files(), ids=os.path.basename)
def test_every_claim_shown_in_the_docs_parses(path):
    failures = []
    for text in _claims_in(path):
        try:
            claim(text)
        except Exception as e:
            failures.append(f"{text!r}: {type(e).__name__}: {e}")
    assert not failures, (
        f"{os.path.basename(path)} shows claim syntax that no longer parses:\n  "
        + "\n  ".join(failures))


def _grammar_page():
    return open(os.path.join(_DOCS, "grammar.md"), encoding="utf-8").read()


def _equivalence_section(text):
    """The 'Terse in, explicit out' table, which deliberately pairs a
    curated spelling with an equivalent one, so its right-hand entries
    are not themselves LEXICON members."""
    start = text.index("## Terse in, explicit out")
    return text[start:text.index("\n## ", start)]


def test_the_grammar_page_teaches_only_curated_claims():
    """Every claim on the grammar page comes from LEXICON, so the page
    and the curated set stay one source rather than two. The
    equivalent-spellings table is exempt and pinned separately by
    `test_documented_equivalent_spellings_are_equivalent`."""
    known = set(LEXICON.values())
    equiv = _equivalence_section(_grammar_page())
    shown = [s for s in _claims_in(os.path.join(_DOCS, "grammar.md"))
             if s not in equiv]
    stray = [s for s in shown if s not in known]
    assert not stray, (
        "docs/grammar.md shows claims that are not in lexicon.LEXICON; add "
        "them there (so they are parsed and rendered by the test suite) or "
        "use an entry that already exists:\n  " + "\n  ".join(stray))


def test_documented_equivalent_spellings_are_equivalent():
    """The grammar page claims certain spellings are the same claim.
    They have to actually parse to the same claim, or the page is
    teaching a false equivalence."""
    rows = re.findall(r"^\| `(.+?)` and `(.+?)` \|$",
                      _equivalence_section(_grammar_page()), re.M)
    assert rows, "the equivalent-spellings table was not found or changed shape"
    for left, right in rows:
        a = claim(left.replace("\\|", "|"))
        b = claim(right.replace("\\|", "|"))
        assert (a.lhs, a.rhs, a.relation, a.domain) == \
               (b.lhs, b.rhs, b.relation, b.domain), (
            f"docs/grammar.md says these are the same claim, but they parse "
            f"differently:\n  {left}\n  {right}")
    assert any(left in set(LEXICON.values()) or right in set(LEXICON.values())
               for left, right in rows), \
        "no side of any documented equivalence is a curated LEXICON entry"


def test_documented_api_signatures_match_the_real_ones():
    """`docs/modes/library.md` puts each public function's signature in
    its own heading. A signature that has moved on leaves a reader
    passing an argument the function no longer takes, which is exactly
    how `check(..., strict=True)` came to be documented for a year
    after the parameter was removed."""
    import inspect
    import re as _re

    import mathema

    doc = open(os.path.join(_DOCS, "modes", "library.md"), encoding="utf-8").read()
    drift = []
    for shown in _re.findall(r"^## `(\w+)\(([^`]*)\)`", doc, _re.M):
        name, params = shown
        fn = getattr(mathema, name, None)
        if fn is None:
            drift.append(f"{name}: documented but not in the public API")
            continue
        real = str(inspect.signature(fn))
        real = _re.sub(r":\s*'[^']*'", "", real)        # drop annotations
        real = _re.sub(r"\s*->.*$", "", real).strip("()")
        norm = lambda s: _re.sub(r"\s+", "", s).replace('"', "'")   # noqa: E731
        if norm(real) != norm(params):
            drift.append(f"{name}:\n      documented: ({params})\n      real:       ({real})")
    assert not drift, ("docs/modes/library.md documents a signature that no "
                       "longer matches:\n    " + "\n    ".join(drift))
