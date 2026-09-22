# The mathema docstring

A second, opinionated docstring convention, stricter than the loose
quality checklist [`mathema audit`'s `quality` column](modes/audit.md#the-quality-score)
scores. The idea: a function's own docstring becomes the *complete*
authoring surface for intent, domain, and claims, no separate YAML
file or decorator required to get real, checked evidence.

```python
def ema(x: list, alpha: Annotated[float, Probability]) -> float:
    """Exponentially weighted moving average.

    Intent:
        Blends each new value with the running mean.

    Claims:
        bounded: for x in [0, 1], f(x) <= 1
    """
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y
```

This is additive, a docstring with none of these sections behaves
exactly as before, and every existing authoring surface (a claims file,
`@claims_decorator`, `Annotated` type hints) still works unchanged.

## The sections

| Section | What it declares |
|---|---|
| `Intent:` | one or two sentences of prose, what the function computes |
| `Claims:` | ordinary claims, see [Authoring claims](authoring.md#2-docstring-claims-block) |
| `Notes:` | free-form limitations or design rationale, optional, see below |
| `Concepts:` (or `Tags:`) | plain concept tags, comma- or newline-separated, optional, see below |
| `Analysis:` / `Evidence:` / `Policy:` / `References:` (or `Refs:`) | role-labeled links, optional, see below |

All five are Google-style blocks (a bare `Header:` line, body indented
underneath, ending at the first line that dedents back to column zero),
the same scanning shape `Claims:` already used.

### `Concepts:` and role-labeled links

Concepts are TAGS: plain tokens naming what the function is about,
normalized to kebab form (`Great Circle` becomes `great-circle`).
`Tags:` is an accepted spelling for the same thing; internally
everything is a concept. They land in the record's own `concepts`
field and, per the CDD spec's meta example, in `meta.concepts` (the
flat union) with the full provenance beside it under
`mathema.concept_sources`, your declared tags never mixed
indistinguishably with the mechanism-derived ones (what the proof
machinery itself touched: a fold lift tags summation, an nlsat proof
tags polynomial-arithmetic) or the inferred keyword hints. Entirely
optional and never scored.

References are LINKS, each labeled with the role its section states:
`References:`/`Refs:` for citations, `Analysis:` for working notes (a
notebook documenting a model assumption, say), `Evidence:` and
`Policy:` for exactly what they sound like. One `- Title: URL` line
per link (numpydoc `.. [1]` entries and bare DOIs also parse), landing
in the record's `references` list with `via` carrying the role.

```python
def power_uncertainty(x, sigma_x, n):
    """First-order uncertainty of x**n.

    Concepts:
        error-propagation, metrology

    Analysis:
        - Assumption notebook: https://nb.example.com/gum.ipynb
    """
```

Both are also authorable from the declared spec: an entry-level
`meta: {concepts: [...]}` and `references:` list beside the claims,
and a per-claim `meta: {concepts: [...]}` that passes through to the
recorded claim untouched, exactly as the spec's pass-through rule
requires.

### `Notes:`

Prose, same shape as `Intent:`, for anything worth recording that isn't
itself intent, a domain, or a claim, a known limitation, why a
particular approach was chosen, a caveat about the evidence. Never
scored: an absent `Notes:` section costs nothing, unlike an absent
`Intent:`. Written through to the verified record's `meta.notes` field
(`mathema.write_spec(fn)`), record-schema.md's namespaced extension slot,
nothing else currently lives there.

```python
def half(x: float) -> float:
    """Halves x.

    Notes:
        Only tested for finite inputs. NaN handling is unspecified.
    """
    return x / 2
```

Inline `# note:` comments (any capitalisation, `# Note:`, `# NOTE:`)
feed the same channel: every one in the function's body, plus the
comment lines immediately following it, joins the docstring's own
`Notes:` prose in `meta.notes`, deduped so a comment restating what the
docstring already says never double-appends. The structured form (each
note with its file line) is on `Facts.comment_notes` for anything that
wants provenance rather than prose.

```python
def scale(x: float) -> float:
    # note: precision loss above 1e15.
    return 2.0 * x
```

### Where a domain goes (there is no `Domain:` block)

A domain is stated in the claim that needs it, as that claim's own
quantifier:

```python
"for alpha in (0, 1], f(x, alpha) <= max(x)"
```

For an ordinary parameter, an `Annotated` marker in the signature
(`Probability`, `Positive`, `Nonnegative`) states a bound once for
every claim. The signature is the one place a type belongs; there is
no docstring `Types:` block either.

A `Domain:` docstring block used to sit beside these. It was removed:
measured at zero real uses across a 313-file corpus, against 96% of
claims carrying an inline quantifier, and it was a second declaration
of the same fact that nothing ever adjudicated, free to disagree with
the claims beneath it.

One thing it could express that a signature marker cannot: a bound on
a name with no signature slot at all, such as a fold's accumulator or
a loop item. State that with a claim-level `let`:

```python
"let total be [0, 1e6], for x in [0, 10], f(x) >= total"
```

### Symbol coverage

Every real parameter, plus every `for`/comprehension loop variable, is
expected to appear literally somewhere in the docstring. This isn't
mainly about readability; it's what feeds the derive route: `Domain:`
declaring a bound for a fold's accumulator or item name gives the
prover a sign/range assumption to work with that it otherwise has none
of. An ordinary scratch local (a running total's starting value, an
indexing-only loop counter) is exempt, only names whose *range* could
plausibly matter to a proof are required.

```python
def total(xs: list) -> float:
    """Sums a sequence.

    Claims:
        nonneg: for xs in [0, ...], f(xs) >= 0
    """
    t = 0.0        # ok: t is never checked for coverage
    for v in xs:   # v is checked; it's a loop variable
        t += v
    return t
```

## Checking a docstring against the schema

```python
>>> import mathema
>>> from mathema.docstring import parse_mathema_docstring
>>> parsed = parse_mathema_docstring(ema)
>>> parsed.score, parsed.applicable
(2, 3)
>>> parsed.conforms
False
>>> parsed.errors
["'v' used but not documented"]
```

`score`/`applicable` follow the same "N/M" pattern as
`mathema.docstring_report()`; `conforms` requires a perfect score *and*
zero structural `errors` (a malformed `Domain:` line, a `Claims:`
header with nothing valid parsed underneath it, a real authoring
mistake, not just an incomplete docstring). `ema`'s own docstring never
mentions `v`, the loop variable, anywhere in its text, so [symbol
coverage](#symbol-coverage) genuinely fails for this example; that's
the deliberate point, not an oversight.

## `docstring_sync()`: how well the docstring tracks the code

`parse_mathema_docstring()` above checks the docstring's own internal
shape, is `Intent:` there, does `Claims:` parse. It has no opinion on
whether what's *declared* still matches the function it's attached to.
`docstring_sync()` (`mathema.docstring.docstring_sync`) is the metric
that does: it wraps `parse_mathema_docstring()` (as `.parsed`) and adds
dimensions that compare the docstring against the function's actual
structure; its branches, the exceptions it raises, its parameters and
internal loop variables, the functions it calls, and (when one exists)
its verified spec record. A docstring can satisfy every check above
and still drift out of sync with the code as the code changes around
it; this is the metric meant to catch that.

```python
>>> from mathema.docstring import docstring_sync, docstring_sync_checklist
>>> sync = docstring_sync(ema)
>>> sync.score, sync.applicable
(6, 9)
>>> print("\n".join(docstring_sync_checklist(sync)))
✓ Intent: present
✓ Claims: present (1 parsed)
· claims: 1 actual, 1 structural floor (not scored)
✓ domain declared (1/1)
✗ domain enforced
✗ symbol coverage (2/3)
✓ params typed (2/2)
✗ internal vars typed (0/1)
✓ return typed
! 'v' used but not documented
```

What each dimension checks:

| Dimension | Scored? | What it compares |
|---|---|---|
| Intent / Claims / symbol coverage | yes | same as `parse_mathema_docstring()`, folded in as-is |
| claims `{floor \| actual \| expected}` | **no** | the floor is one claim per relevant claim family per target (`inventory.claim_floor()`), the actual is what the function carries, and the expected, how many a function of this shape typically carries; needs a corpus and reads `-`. Informational only, never subtracted from `score` |
| domain declared / enforced | yes | declared: a bound exists (in `Domain:` or a signature `Annotated` marker) for each real scalar/int parameter; enforced: the function is wrapped in `authoring.enforce_domain()`, checked at runtime, not just documented |
| raises declared | yes | each exception the function's body can actually raise, covered by a `raises(f(x), ExcType)` claim, a prose `Raises:` mention, or a guard raise ENFORCING a declared domain (the declaration plus its own boundary check states the raise condition formally), counted once however many apply |
| params / return typed | yes | every real parameter and the return value, each backed by *some* type information (annotation, `Annotated`, or `Domain:`) |
| callees doc quality / docsync | yes | two points per direct callee: it documents itself (docstring plus a documented return), and its own layers are in sync (Claims: names known, record form fresh), a caller's docsync genuinely contains its callees' docsync, one hop deep and cycle-safe |

`domain_enforced` is only applicable when at least one domain is
declared in the first place (enforcing a domain nobody wrote down isn't
meaningful); `ema` declares `alpha`'s domain via its `Annotated[float,
Probability]` hint but never wraps itself in `enforce_domain()`, hence
the `✗`. The "claims" line is deliberately never a checkmark; it's a
hint, not a requirement. The floor is a real lower bound (a function
carrying zero claims is always under it), but it is a floor and not a
target: carrying more than it asks for is not an overrun, and there is
nothing to divide by until a corpus can say what a function of this
shape typically carries.

Run this across a whole codebase with `mathema audit`: `docsync` is
an ordinary analysis in the grid by default (`--exclude docsync` to
skip it, like any analysis). The wide table adds one compact
`docsync` column (`N/M`, from `docstring_sync()`);
`mathema audit --docs` additionally prints a **second, separate
table** underneath the loose `docs` checklist grid, not appended to
the same row, since the two measure different things:

```
$ mathema audit mypkg --docs
key           || has_docstring | has_summary | params | returns | raises | claims   | docs_score
mypkg.ema.ema || yes           | yes         | 2/2    | no      | -      | 1 parsed | 4/5

4/5 docstring best-practice criteria met (1 function).

docsync:
key           || intent | notes | claims   | {min_expected|actual|est_applicable} || declared | enforced || raises || params_typed | internal_typed | return_typed | callees_doc || sync_score
mypkg.ema.ema || yes    | -     | 1 parsed | {1 | 1 | -}    || 1/1      | no       || -      || 2/2          | 0/1            | yes          | -             || 6/9

mean docsync 58% (weighted CDD-compliance measure) (1 function).
```

`declared`/`enforced` sit under a `domain` group heading, and `raises`
under its own single-column group, the `||` marks a group boundary,
`|` a column boundary within one, same convention the loose `docs`
table already uses. the claims column is `{min_expected|actual|est_applicable}`:
`ema` has no branching beyond its `for` loop and no declared domain
guards to add to the floor, so its one parsed claim already clears the
floor of one, and `expected` reads `-` until a corpus can say what a
function of this shape typically carries.

## The docsync percentage

One 0-100 number per function: how much of what the function actually
does is surfaced as context a developer can read, intent at every
level, domains, raise conditions, types, and the same for the
immediate call surface. Deliberately NOT proveability: whether the
claims themselves are enough is one dimension the score doesn't own.
The claim floor stays a separate flag instead, the claims triplet
cell renders red when the actual count sits under the floor and amber
once it clears it, never green, since without a corpus nobody can say
the count is *enough*. Weighted and renormalized over whichever
components apply to the function at hand:

| Component | Weight |
|---|---|
| Claims: block in sync with declared∪verified | 12 |
| intent present / concise / in sync | 16 / 5 / 5 |
| module intent present / system intent present | 5 / 3 |
| domain declared | 15 |
| raises declared (a guard enforcing a declared domain counts) | 12 |
| params / return typed | 10 / 4 |
| callees documented / callees docsync | 5 / 8 |

Conciseness is a ramp, not a cliff: full credit through 40 words,
fading linearly to zero by 80. Domain *enforcement* has no separate
weight; it shows up through the raise-coverage rule, where a guard
enforcing a declared domain covers its own exception. `callees
docsync` is the mean of the direct callees' own percentages, each
computed shallow (without THEIR callee dims) so a call cycle can't
loop and a hop only ever counts once, a caller's docsync genuinely
contains its callees'. The percentage is what the audit grid's
`docsync` column, the compact/MCP `docsync` value, and the
`sync_score` column all report.

## Writing it back from a verified record

Once a function has been checked and recorded (`mathema.write_spec(fn)`),
its `Claims:` (and `Intent:`, if the docstring doesn't already state
one) can be regenerated from what was actually verified, only claims
that held or were proven are written back, each tagged `[derive]` when
the verdict came from the derive route:

```python
>>> from mathema.docstring import render_docstring
>>> mathema.write_spec(ema, domain={"alpha": (0.0, 1.0)})
>>> print(render_docstring(ema))
Exponentially weighted moving average.

Claims:
    bounded: f(x) <= 1
```

`render_docstring()` returns text only; it never writes to the `.py`
file. `Domain:` is left untouched: it's an authoring input mathema
reads, never an adjudicated output the verified record stores, so
there's nothing to write back for it.

## Creating a docstring that isn't there yet

The other direction of the same loop: a function with **no** docstring
at all can have one generated from its declared and verified layers.
A claims entry may carry an `intent:` field alongside its `claims:`
list (it rides through the merge like any other field); that intent,
plus the entry's claims (verified `held`/`proven` claims preferred,
declared claims otherwise), is enough to write a complete docstring,
summary line, `Intent:` block, `Claims:` block:

```yaml
mypkg.funcs.bare:
  intent: Passes x through unchanged.
  claims:
    - name: identity
      statement: "f(x) == x"
      route: derive
```

`docstring.generate_docstring(fn)` returns the proposed text (`None`
when a docstring already exists, generation only ever creates, a
present docstring is the human source of truth) and
`docstring.write_docstring(fn, text)` inserts it into the source file,
refusing outright if one is present. The CLI face is `mathema docsync
<target>`: functions with a docstring get their sync checklist,
functions without get the proposal printed, and `--write` offers each
insertion behind a per-function y/N prompt, never a silent write,
same posture as `mathema describe --issue`.

## Intent above the function

`Intent:` is the load-bearing marker, and it isn't only a per-function
one: a module docstring can carry its own `Intent:` block (or its
first line stands in), and a project README can state codebase-level
intent under an `## Intent` heading or an `Intent:` block.
`docstring.intent_context(fn)` reports all three levels, each tagged
with the SHAPE the intent was authored in: `explicit` for the
paragraph following an `Intent:` marker (or a marked README section),
`implicit` when the first paragraph stands in. Shape is not rung:
every stated intent sits at the `declared` rung until a human accepts
it (`mathema accept <key> --intent`), which is what writes
`meta["mathema.intent_provenance"]: documented` to the verified
record; intent is its own function-level section of the record, never
a claim. `docstring_sync()`'s checklist shows the hierarchy as an
unscored context line.
Context is reported, never inherited: a function with no intent of its
own is still a gap, whatever its module or README says; the point is
to see where intent is missing, not to paper over it.


## Evidence rungs and the docsync verb

Any stated intent; the explicit `Intent:` block included; sits at
the `declared` rung; `documented` is earned only through
`mathema accept <key> --intent` (a human act, bound to signature +
raises + the text). Claim NAMES in a `Claims:` block are the keys
that join the declared layer; the statement prose is yours to
humanize; the record is the truth, `mathema docsync` reports drift,
and writing missing names into a block is the explicit
`--write-docstrings` opt-in. Inline `#tag` spellings anywhere in the
docstring author concepts. See [docsync](modes/docsync.md).
