# Language domains

A claim over a function of text needs a domain the way a claim over a
function of numbers does. A language is that domain: the set of strings
a name stands for, or of structured values a schema stands for, written
`L[<name>]` where a numeric claim writes `R` or `[0, 1]`.

```
for s in L[unicode], f(f(s)) == f(s)
for s in L[unicode] \ {""}, len(f(s)) >= 1
for s in L[unicode], len(f(s)) <= len(s)
```

## Three words

An **alphabet** is a set of characters (`ascii`, `latin-1`, `digit`). A
**language** is a set of strings, or more generally of values: `L[ascii]`
is every string over the ascii alphabet, the way a Kleene star reads, so
the empty string is a member and `\ {""}` removes it; `L[json]` is every
string `json.loads` accepts; a schema names the language of its
documents. **Text** is the carrier, Python's `str`, the way the reals are
the carrier of `R`. `L` is rendered in both output alphabets; `𝕃` is
accepted on input.

Union with a finite set of members, exclusion and the missing-value
policy read exactly as they do for a numeric domain, and a finite set of
strings is itself the simplest language, the one mathema always had:

```
for scale in {"info", "linear"}, f(r, scale) >= 0
```

## What mathema does with a language

The probe draws members of the language and never a value outside it:
the language's own hazards first (the empty string, whitespace, NUL and
the other control code points, an alphabet's boundary, a long member, a
lone surrogate, a byte-order mark), every one of them once before any
random member is drawn, then random members. The hazards count toward
the trial budget the way a wide interval does (see
[the trial budget](modes/check.md#the-trial-budget)), and the
confidence score is marked down for them the same way. A function that
raises on a member falsifies the claim with that member as the witness,
the rule a numeric domain follows. The derive route has no reading of a
string, so it declines with the reason rather than proving real-only
facts about a symbol standing in for one; a finite language is the
exception, swept point by point and proven or falsified with the member.
`@enforce_domain()` reads a language binding and rejects a non-member at
call time.

Every record states what a name resolved to, in `meta["mathema.language"]`:
the name, its source (an in-process registration, a package's entry
point, a dotted object, an adaptor), its level (finite, alphabet,
regular, predicate, schema) and its persisted form. A family that
resolves something of its own writes it beside the parameters, so
`output_in_language` records the language it held the output to under
`return`, with where that came from. A claim over a
language is stamped `grammar: mathema/language`, the dialect of the claim
grammar that reads language vocabulary; a claim over a finite set stays
plain `mathema`. In that dialect a length renders as `len(s)`, while the
canonical form underneath keeps `dim(s, 0)`, mathema's one spelling of a
dimension, so the rendered text parses back to the same claim.

## Refinements

A refinement narrows a language inside its brackets, a key and a bound
on the whole number it measures:

```
for s in L[ascii, len <= 80], len(f(s)) <= 80
for s in L[unicode, len > 20], len(f(s)) <= len(s)
for s in L[unicode, len in [1, 80]], f(s) in L[unicode, len in [1, 80]]
```

mathema reads the shape, `key <= n`, `key < n`, `key >= n`, `key > n` or
`key in [lo, hi]`, renders the keys in one order and records each under
its own name, and owns no key itself: what a key measures is the
refinement registered under it, in the process or under the
`mathema.language_refinements` entry-point group, and a key nothing
serves is refused when the claim is checked, with the keys that are
known. The `mathema-language` package serves `len`, a count of code
points (Python's `len`, not bytes, and not the characters a reader sees,
since `"é"` can be one code point or two). A refined language is a
language of its own: every member the probe draws fits the bound, the
members at each bound are the first hazards it visits, as plain as the
language allows (`"a" * 80`), and a member one past the bound is its
outside draw, so `excluded_outside_domain(s)` checks that the function
refuses the 81st character. `L[unicode, len >= 1]` is the same set as
`L[unicode] \ {""}`. A parameter annotated `Annotated[str, MaxLen(80)]`
(annotated_types, pydantic) infers `L[unicode, len <= 80]` through the
package's text adaptor, and the record's note says so.

A language domain spells a missing value as a word in both modes: to a
reader of formal languages `∅` is the empty language, a different set.
A string has no hole of its own, so the missing value of a string
parameter is its absence, `L[unicode]|None`, which an `Optional[str]`
admits and a `str` does not; `for s in {missing}` over a `str` is
refused with the reason.

## Paths into a member

A binding can name a path into a member of a language, through fields
and indices, at any depth:

```
for o in L[myapp.Order], o.address.zip in L[digit, len <= 5], ...
for o in L[myapp.Order], o.lines[0].sku in L[slug], ...
for o in L[myapp.Order], o.lines[*].qty in [1, 10], total(o) >= 0
```

`[*]` means every element. A path binding narrows the members the probe
draws: every value the path reaches is in the bound. A path through a
missing field or past the end of a list is absent, and a bare bound
already means the value is there; `| {absent}` on the bound keeps such a
record in. A `None` list element and a `nan` are holes, not absences. The derive route
reads a numeric leaf at any depth the body reads (`o.lines[0].qty`,
`o["address"]["zip"]`) with the bound the language states for it, and a
claim's own path binding, the `[*]` form included, overrides that bound.

## Membership and containment

The output side has two spellings of its own. `f(s) in L[slug]` says
every output is a member of a language (or a finite set, or a named
number set); `∈` and `∉` are the Unicode forms, and a plain numeric
interval on the right is read as the chain it means, so
`f(x) in [0, 1]` is recorded as `0 <= f(x) <= 1`. `"<" not in f(s)`
says the value on the left is never found in the value on the right,
Python's own containment, which is how a claim states that an escaper
never emits a character. Both are decided by execution: a member is a
member or it is not, a missing value is a member of nothing unless the
right-hand side names it explicitly, and the derive route
declines with the reason.

```
for s in L[slug], f(s) in L[slug]
for s in L[unicode], f(s) ∉ L[ascii]
for s in L[unicode], "<" not in f(s)
for x in [0, 1], f(x) in [0, 1]
```

In order: closure into the language, an output that always leaves
ASCII, a token that is never emitted, and the chain `0 <= f(x) <= 1`.

## Installing the languages

mathema itself parses, renders and records `L[...]` and resolves no name.
The names come from the `mathema-language` package:

```bash
pip install "mathema[language]"
```

It provides the alphabets (`ascii`, `latin-1`, `unicode`, `printable`,
`digit`, `alpha`, `alnum`), the predicate languages with an exact
standard-library test behind each (`identifier`, `json`, `uuid`,
`iso_date`, `iso_datetime`, `ipv4`, `ipv6`, `base64`, `hex`, `slug`,
`shell_safe`), the hazard sub-alphabets a probe mixes in (control and
format characters, combining marks, surrogates, the characters whose
NFKC form differs, the astral planes), the built-in claims
`is_length_safe` and `is_encoding_safe`, and the schema adaptors that
turn a dataclass, a `TypedDict`, a pydantic model or a JSON Schema into
the language of its rows (a SQLAlchemy table and a Django model too).
Without it, a claim over `L[unicode]` is `unknown`, and its note says it
needs mathema-language.

The package keeps its own reference, published on this site as
[the language reference](/language/reference/): every language and its
membership test, the hazards, a page for each row adaptor with what it
reads and which validator decides membership, how to write an adaptor
of your own, and a catalogue of claims worth writing about a function
over text, each one run by the package's tests and held to the verdict
printed beside it. This page stays with the grammar and with what a
record states.

## Writing your own

A language is any object satisfying `mathema.languages.Language`: a
`name`, a `kind` (what a member is), a `level` (how far the engine can
decide it), and `contains`, `explain`, `sample`, `members`, `hazards`,
`outside`, `shrink`, `fields`, `render` and `to_json`.
`mathema.languages.StringLanguage` assembles one from a per-character
test or a whole-string predicate, and `language_problems(obj)` says what
an object is missing. Three ways to make it resolvable:

- `register_language("slug", obj)` in the process that checks the claims.
- A `mathema.languages` entry point in your package, the name being the
  language name.
- A dotted path, `L[myapp.text.SLUG]`, to a `Language` object, or to
  anything a `mathema.language_adaptors` adaptor accepts.

[Extending mathema](extending.md) documents the two entry-point groups.

A language may also supply a derive strategy for claims quantified over
it, a `derive` method taking `param`, `lhs`, `relation`, `rhs`,
`functions` (the target as `f` and under its own name, with every
function the claim binds) and `refinements` (each key in force mapped
to the whole-number range it keeps), and returning a `ProofResult` or
None. It is found through any refinements wrapped around the language
and runs under the wall-clock cap. A proof it returns is the claim's
derive verdict, on the route `derive:<mechanism>` named by the result's
`mathema.derive_route`; anything else leaves the claim to the probe,
and a disproof it claims is read as undecided, since only an executed
witness falsifies. mathema-language's recursive row languages prove
fold claims this way, on `derive:induction`.

## Refusal and a defined answer

Two built-in claims ask how a function treats its language.
`excluded_outside_domain(s)` asks that every value outside the domain is
refused, and by default any raise refuses. `is_language_defined(s)` asks
that every member gets an answer, and by default an answer is anything
but an unguarded crash (a `TypeError`, an `IndexError` and the like). A
command-line program says both things differently: it refuses a bad
argument list by exiting with code 2, and it answers with exit code 0
or 1. A language can declare both, and the two claims then read the
declaration instead of the default:

- `refusal`, a `Refusal`: a raise of the exception classes it names,
  optionally narrowed by a test on the exception, or a return its
  `returns` test accepts. `Refusal.exit(2)` is `SystemExit` with exit
  code 2.
- `defined_answer`, a `DefinedAnswer`: a return (every return, or those
  its `returns` test accepts), or a raise of the exception classes it
  names. `DefinedAnswer.exit(0, 1)` is a return, or `SystemExit` with
  exit code 0 or 1.

An outside draw then has to be refused the declared way, and a member
has to get the declared answer; the witness names the declaration and
what the call did instead. The record's `meta["mathema.language"]`
entry for the parameter states the declarations under `refusal` and
`defined answer`, in the same words, so a `holds` says what it held to.
A language that declares neither is read as before, and its entry is
unchanged. `StringLanguage` takes both as keywords, a refined language
keeps its base's, and a language object of your own sets them as
attributes:

<!-- example: refusal run -->
```python
import sys

import mathema
from mathema.languages import DefinedAnswer, Refusal, StringLanguage, register_language

register_language("count", StringLanguage(
    "count", char_ok=lambda c: c in "0123456789", pool="0123456789",
    outside_pool="x-", refusal=Refusal.exit(2),
    defined_answer=DefinedAnswer.exit(0, 1)))


def parity(s: str) -> None:
    """Exit 0 for an even count, 1 for an odd one."""
    if not s.isdigit():
        sys.exit(2)
    sys.exit(int(s) % 2)


def parity_by_hand(s: str) -> None:
    """Exit 0 for a count divisible by three, else the remainder."""
    sys.exit(int(s) % 3)


for fn in (parity, parity_by_hand):
    for p in mathema.check_conjectures(fn, [
            'for s in L[count] \\ {""}, excluded_outside_domain(s)',
            'for s in L[count] \\ {""}, is_language_defined(s)']):
        print(fn.__name__, p.name, p.verdict)
        if p.counterexample:
            print("   ", p.counterexample)
```

<!-- example: refusal output -->
```text
parity excluded_outside_domain[s] holds
parity is_language_defined[s] holds
parity_by_hand excluded_outside_domain[s] falsified
    s = 'á' (outside L[count] at [0]: count alphabet) is outside the declared domain and was not refused the way the language declares (SystemExit (exit code 2)): the call raised ValueError
parity_by_hand is_language_defined[s] falsified
    s = '77' (inside L[count] \ {""}) raised SystemExit (exit code 2), not the defined answer the language declares (a return, or SystemExit (exit code 0 or 1))
```

`parity` refuses anything that is not a count with exit code 2 and
answers every count with 0 or 1, so both claims hold. `parity_by_hand` lets `int` raise a
`ValueError` on a value outside the language, which is a crash rather
than the refusal the language declares, and exits 2 on `"77"`, a
member, which is not an answer.
