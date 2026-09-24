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
import html
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
    # A shell fence is code, not claims, except for the claim it passes
    # to `--claim`, which is the very thing a reader copies. Shell line
    # continuations are joined first so a wrapped claim arrives whole,
    # and runs of whitespace collapse, since wrapping a claim across
    # lines does not make it a different claim.
    joined = re.sub(r"\\\n\s*", " ", text)
    for fence, body in re.findall(r"```(\w*)\n(.*?)```", joined, re.S):
        if not fence:
            continue
        found += [re.sub(r"\s+", " ", c).strip()
                  for c in re.findall(r'--claim\s+"([^"]+)"', body)]
    for fence, body in re.findall(r"```(\w*)\n(.*?)```", text, re.S):
        if fence:
            continue
        found += [ln.strip() for ln in body.splitlines() if ln.strip()]
        text = text.replace(f"```{fence}\n{body}```", "")
    for span in re.findall(r"`([^`\n]+)`", text):
        span = span.replace("\\|", "|").strip()
        # a claim shown as the Python string literal it would be passed
        # as is still that claim; the quotes are the call, not the claim
        if len(span) > 1 and span[0] == span[-1] and span[0] in "\"'":
            span = span[1:-1]
        found.append(span)
    # A claim containing a bar cannot be written as a backtick span
    # inside a table: the escape a table needs (`\|`) survives into the
    # rendered page, and an HTML entity inside a code span is escaped
    # too. Such a row is written as a literal <code> element with
    # &#124;, which renders correctly and is scanned here so the row
    # keeps earning its place in this check.
    for span in re.findall(r"<code>([^<\n]+)</code>", text):
        found.append(html.unescape(span).strip())
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


_README = os.path.join(os.path.dirname(_DOCS), "README.md")


def _doc_files():
    """Every page that shows a reader a claim, which includes the
    README: it is the most-read surface of the project and carries the
    worked examples, so it is held to the same standard as the docs."""
    return sorted(os.path.join(_DOCS, f) for f in os.listdir(_DOCS)
                  if f.endswith(".md")) + [_README]


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


def test_the_readme_shows_only_curated_claims():
    """The README's worked examples are the first thing anyone runs, so
    every claim in them comes from LEXICON and is therefore executed by
    the suite rather than merely written down once and trusted."""
    known = set(LEXICON.values())
    stray = [s for s in _claims_in(_README) if s not in known]
    assert not stray, (
        "README.md shows claims that are not in lexicon.LEXICON; add them "
        "there so they are parsed, rendered and adjudicated by the test "
        "suite:\n  " + "\n  ".join(stray))


def _notation_rows():
    """The (symbol, code points) pairs from the grammar page's notation
    table, which is the only place the project writes code points down
    by hand."""
    text = _grammar_page()
    start = text.index("## Mathematical notation")
    table = text[start:text.index("\n### ", start)]
    rows = []
    for line in table.splitlines():
        m = re.match(r"^\| (?:`(.+?)`|<code>(.+?)</code>) \| (U\+[0-9A-F ,+U]+) \|",
                     line)
        if not m:
            continue
        symbol = html.unescape(m.group(1) or m.group(2))
        points = [int(p.strip()[2:], 16) for p in m.group(3).split(",")]
        rows.append((symbol, points))
    return rows


def test_the_notation_table_is_documented_for_every_symbol_it_shows():
    rows = _notation_rows()
    assert len(rows) > 20, f"the notation table was not found or shrank: {rows}"


def test_every_documented_code_point_is_the_symbol_it_claims_to_be():
    """A hand-written code point is exactly the sort of thing that rots
    silently, and the table exists specifically so a reader can tell two
    look-alike glyphs apart. If it is wrong it is worse than absent."""
    wrong = []
    for symbol, points in _notation_rows():
        distinct = sorted({ord(c) for c in symbol if not c.isspace()})
        if distinct != sorted(set(points)):
            wrong.append(
                f"{symbol!r}: documented "
                + ", ".join(f"U+{p:04X}" for p in points)
                + " but is "
                + ", ".join(f"U+{c:04X}" for c in distinct))
    assert not wrong, ("docs/grammar.md's notation table misstates a code "
                       "point:\n  " + "\n  ".join(wrong))


def test_the_rejected_subset_symbol_really_is_rejected():
    """The page tells a reader that U+2286 is refused rather than
    silently read as U+2282, because the two are different claims. That
    promise has to hold."""
    assert claim("for n in [0,100] ⊂ ℤ, f(n) >= 0").domain
    with pytest.raises(Exception):
        claim("for n in [0,100] ⊆ ℤ, f(n) >= 0")


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


# --- runnable examples ------------------------------------------------------

def test_the_cdd_workflow_example_runs_to_completion(tmp_path):
    # `examples/README.md` presents cdd_workflow.py as runnable; a reader
    # who runs it and gets a traceback stops trusting the rest. It writes
    # its record beside itself, so it runs from a copy.
    import shutil
    import subprocess
    import sys

    repo = os.path.dirname(_DOCS)
    script = tmp_path / "cdd_workflow.py"
    shutil.copy(os.path.join(repo, "examples", "cdd_workflow.py"), script)
    env = dict(os.environ, PYTHONPATH=repo)
    r = subprocess.run([sys.executable, str(script)], cwd=str(tmp_path),
                       capture_output=True, text=True, env=env, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "All claims hold. Accept version 2." in r.stdout
