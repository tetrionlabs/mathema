# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The acceptance sheet: one case for each ruling given with an example
on the cards for the language and solver work. Each case names the card
entry of its ruling, the claim text and the outcome ruled.

An expected outcome is never edited to match a build; a case is added
when a ruling is given. The kinds of expectation:

- `("renders", text)`: the claim parses and its ascii canonical text is
  `text`;
- `("refused", fragment)`: the claim is refused when it is parsed and
  the message holds `fragment`;
- `("refused at resolution", fragment)`: the claim parses and is
  refused when its languages are resolved, the message holding
  `fragment`;
- `("verdict", v)`: checking gives verdict `v`;
- `("verdict_note", v, fragment)`: verdict `v`, and the note or sketch
  holds `fragment`;
- `("verdict_proven_or_assuming",)`: verdict `proven`.

The cases use the words `mathema-language` registers (`matches`,
`starts with`, `within`, ...), so the module is skipped where they are
not registered. A case in `NOT_YET_BUILT` is ruled and not yet built:
it is expected to fail, strictly, so building it shows up here."""
import re
import warnings

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import predicate_word, resolve_language
from mathema.spec import render_claim_text

if predicate_word("matches") is None or predicate_word("within") is None:
    pytest.skip("mathema-language's predicate words are not registered",
                allow_module_level=True)

RS = "smt-regex-string-theory"
MS = "ml-ask-smt-membership"


def ident(x):
    return x


_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SLUG_Z = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}\Z")


def check_slug(slug: str) -> str:
    if not _SLUG.match(slug):
        raise ValueError(f"not a slug: {slug!r}")
    return slug


def check_slug_z(slug: str) -> str:
    if not _SLUG_Z.match(slug):
        raise ValueError(f"not a slug: {slug!r}")
    return slug


F = "for s in L[unicode{}], f(s) == s"

CASES = [
    # --- relations between domains, the same for numbers and text (MS #26, #27)
    (MS + " #27", "[0, 1] subset [0, 2]", ("verdict", "proven"), ident),
    (MS + " #27", "Z subset R", ("verdict", "proven"), ident),
    (MS + " #27", "R supset Z", ("renders", "Z subset R"), ident),
    (MS + " #27", "L[digit] subset L[unicode]", ("verdict_proven_or_assuming",), ident),
    (MS + " #27 numbers decided exactly", "[0, 0.1] subset [0, 1]", ("verdict", "proven"), ident),
    (MS + " #27 numbers decided exactly", "[0, 0.3] disjoint [0.7, 1]", ("verdict", "proven"), ident),
    (MS + " #27 numbers decided exactly", "[0, 1/3] subset [0, 1]", ("verdict", "proven"), ident),
    (MS + " #27 not subset by witness", "[0, 100] not subset [0, 99.9]", ("verdict", "proven"), ident),
    (MS + " #27 not subset by witness", "[0, 2] not subset [0, 1]", ("verdict", "proven"), ident),
    (MS + " #27", "[0, 1] disjoint [2, 3]", ("verdict", "proven"), ident),
    (MS + " #27 proper subset", "Z ⊊ R", ("renders", "Z subset R and Z != R"), ident),
    (MS + " #27 proper subset glyph refused", "L[ascii] ⊂ L[unicode]", ("refused", "reads two ways"), ident),
    (MS + " #27 cross-kind refused", "[0, 1] subset L[unicode]", ("refused", "kind"), ident),
    (MS + " #26 re-binding refused with suggestion", "for c in L[ascii], c in L[unicode]",
     ("refused", "L[ascii] subset L[unicode]"), ident),
    # --- kind under == and != (MS #35)
    (MS + " #35", "[0, 1] == [0, 1]", ("refused", ": real"), ident),
    (MS + " #35", "[0, 1] : real == [0, 1] : real", ("verdict", "proven"), ident),
    (MS + " #35", "[1, 0] : real == {}", ("verdict", "proven"), ident),
    (MS + " #35 unbound set names are sets", "Z != R", ("verdict", "proven"), ident),
    # --- predicates, words canonical, any case / spacing / underscore on input (RS #8, #9)
    (RS + " #9", F.format(', startsWith("http://")'),
     ("renders", 'for s in L[unicode, starts with ("http://")], f(s) = s'), ident),
    (RS + " #9", F.format(', starts_with("http://")'),
     ("renders", 'for s in L[unicode, starts with ("http://")], f(s) = s'), ident),
    (RS + " #9 sugar", F.format(', ^= "http://"'),
     ("renders", 'for s in L[unicode, starts with ("http://")], f(s) = s'), ident),
    (RS + " #9 sugar", F.format(', $= ".py"'),
     ("renders", 'for s in L[unicode, ends with (".py")], f(s) = s'), ident),
    (RS + " #9 sugar", F.format(', *= "x"'),
     ("renders", 'for s in L[unicode, contains ("x")], f(s) = s'), ident),
    (RS + " #9 == for a literal", F.format(', == "abc"'),
     ("renders", 'for s in L[unicode, matches ("abc")], f(s) = s'), ident),
    (RS + " #9 == with a pattern refused", F.format(', == re(r"a+")'), ("refused", "in re("), ident),
    # --- dialect inside re, python default shown (RS #16), javascript sidelined (RS #48)
    (RS + " #16", F.format(', matches (re(r"[a-z]+"))'),
     ("renders", 'for s in L[unicode, matches (re(r"[a-z]+", python))], f(s) = s'), ident),
    (RS + " #16 flags as words", F.format(', matches (re(r"[a-z]+", py, ignoreCase))'),
     ("renders", 'for s in L[unicode, matches (re(r"[a-z]+", python, ignore case))], f(s) = s'), ident),
    (RS + " #8 leading (?i) rendered as the word", F.format(', matches (re(r"(?i)[a-z]+"))'),
     ("renders", 'for s in L[unicode, matches (re(r"[a-z]+", python, ignore case))], f(s) = s'), ident),
    (RS + " #48", F.format(', matches (re(r"^a$", javascript))'), ("refused", "not available yet"), ident),
    (RS + " #39 version pin", F.format(', matches (re(r"\\d+", python 3.13))'),
     ("renders", 'for s in L[unicode, matches (re(r"\\d+", python 3.13))], f(s) = s'), ident),
    # --- did you mean (RS #11, #12)
    (RS + " #12", F.format(', within ("/workspace")'),
     ("refused at resolution", 'L[path, within ("/workspace")]'), ident),
    (RS + " #12 unknown word", F.format(', startwith ("http://")'), ("refused", 'starts with ("http://")'), ident),
    # --- within as the boundary word, bracket render (ml-interface-smt #12, #16)
    ("ml-interface-smt #16", 'for p in L[path, within "/ws"], f(p) == p',
     ("renders", 'for p in L[path, within ("/ws")], f(p) = p'), ident),
    ("ml-interface-smt #12", 'L[path, within ("/workspace/src")] subset L[path, within ("/workspace")]',
     ("verdict_proven_or_assuming",), ident),
    ("ml-interface-smt #12 CIDR", 'L[ipv4, within ("10.1.0.0/16")] subset L[ipv4, within ("10.0.0.0/8")]',
     ("verdict_proven_or_assuming",), ident),
    # --- alphabets by narrowing, + inside the brackets, one quoted character each (RS #37)
    (RS + " #37", 'for s in L[lower + digit + "_-", len in [3, 32]], f(s) == s',
     ("renders", 'for s in L[lower + digit + "-" + "_", len in [3, 32]], f(s) = s'), ident),
    (RS + " #37", 'L[lower + digit] subset L[alnum]', ("verdict_proven_or_assuming",), ident),
    # --- shapes: letters and digits are symbols, literal text quoted, bindings (RS #38)
    (RS + " #38", F.format(', matches (shape ("KEY-99"))'), ("refused", "'KEY'"), ident),
    (RS + " #38", F.format(", matches (shape (\"'KEY-'U{3}9{4}\", U = upper))"),
     ("renders", "for s in L[unicode, matches (shape (\"'KEY-'U{3}9{4}\", U = upper))], f(s) = s"), ident),
    (RS + " #38 a binding may override a built-in", F.format(', matches (shape ("AA99", A = upper))'),
     ("renders", 'for s in L[unicode, matches (shape ("AA99", A = upper))], f(s) = s'), ident),
    # --- bare pattern object as a language refused (MS #34)
    (MS + " #34", "for s in L[re.compile], f(s) == s",
     ("refused at resolution", "matches"), ident),
    # --- the validator proofs, with the assumption shown (MS #73)
    (RS + " #2 dollar validator falsified", 'for slug in L[unicode], raises(f(slug + "\\n"), ValueError)',
     ("verdict", "falsified"), check_slug),
    (MS + " #73 proven, assuming", 'for slug in L[unicode], raises(f(slug + "\\n"), ValueError)',
     ("verdict_note", "proven", "assuming"), check_slug_z),
]


#: ruled and not yet built, by claim text: the ruling and what stands
NOT_YET_BUILT = {
    "[0, 0.1] subset [0, 1]": MS + " #27: numbers decided exactly as written",
    "[0, 0.3] disjoint [0.7, 1]": MS + " #27: numbers decided exactly as written",
    "[0, 1/3] subset [0, 1]": MS + " #27: numbers decided exactly as written",
    "[0, 100] not subset [0, 99.9]": MS + " #27: numbers decided exactly as written",
    F.format(', == re(r"a+")'): RS + " #9: the refusal also offers `in re(...)`",
    F.format(', matches (re(r"\\d+", python 3.13))'): RS + " #39: a version pin",
    F.format(', startwith ("http://")'): RS + " #12: an unknown word is refused with what "
                                              "was meant",
    F.format(", matches (shape (\"'KEY-'U{3}9{4}\", U = upper))"):
        RS + " #38: shape rendered with a space before its brackets",
    F.format(', matches (shape ("AA99", A = upper))'):
        RS + " #38: shape rendered with a space before its brackets",
}


def _outcome(text, expect, fn):
    """`(as ruled, what was built)` for one case."""
    kind = expect[0]
    try:
        cj = claim(text)
    except Exception as e:
        said = f"{type(e).__name__}: {e}"
        return (kind == "refused" and expect[1] in said), f"refused: {said[:200]}"
    if kind == "refused":
        return False, f"accepted, renders: {render_claim_text(cj, unicode=False)}"
    if kind == "renders":
        got = render_claim_text(cj, unicode=False)
        return got == expect[1], f"renders: {got}"
    if kind == "refused at resolution":
        try:
            for bound in cj.domain.values():
                for piece in getattr(bound, "pieces", ()):
                    resolve_language(piece)
        except Exception as e:
            said = f"{type(e).__name__}: {e}"
            return expect[1] in said, f"refused at resolution: {said[:200]}"
        return False, "resolved"
    try:
        (row,) = check_conjectures(fn, [cj])
    except Exception as e:
        return False, f"check raised {type(e).__name__}: {str(e)[:160]}"
    note = " ".join(str(x) for x in (row.note, getattr(row, "sketch", "")) if x)
    got = f"{row.verdict} | {note[:160]}"
    if kind == "verdict":
        return row.verdict == expect[1], got
    if kind == "verdict_note":
        return row.verdict == expect[1] and expect[2] in note, got
    return row.verdict == "proven", got


def _params():
    for ref, text, expect, fn in CASES:
        marks = []
        if text in NOT_YET_BUILT and fn is ident:
            marks.append(pytest.mark.xfail(
                strict=True, reason=f"ruled, not yet built: {NOT_YET_BUILT[text]}"))
        yield pytest.param(text, expect, fn, id=f"{ref} | {text}"[:120], marks=marks)


@pytest.mark.parametrize("text,expect,fn", list(_params()))
def test_a_ruling_reads_as_it_was_ruled(text, expect, fn):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        as_ruled, built = _outcome(text, expect, fn)
    assert as_ruled, f"ruled {expect}; built: {built}"


def test_every_case_marked_not_yet_built_is_a_case():
    assert set(NOT_YET_BUILT) <= {text for _, text, _, _ in CASES}
