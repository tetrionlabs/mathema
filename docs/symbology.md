# Symbology and rendering

mathema reads a claim in whatever spelling you find natural and writes
it back in a canonical one. This page covers what that rendering does,
how to switch between the two output alphabets, and how to make
mathema render your parameters as the symbols your field actually uses.

## One renderer, every surface

`spec.render_claim_text()` produces the claim text you see in a record,
an error message, a proof condition and the CLI, and
`domain.render_domain()` produces the region. There is deliberately one
renderer rather than one per surface, so a claim reads the same
character for character wherever it appears. That matters more than it
sounds: the `condition` string in a verified record *is* the canonical
region form, and repopulating a claim from its record parses that
string back, so rendering and parsing are two directions of one thing
rather than a display step bolted on the end.

## Two alphabets

The grammar has two equivalent output spellings, Unicode and ASCII:

```python
from mathema import claim, set_unicode_output
from mathema.spec import render_claim_text

c = claim("for theta in [0, 1], acceleration in [0, 100], f(theta, acceleration) >= 0")

set_unicode_output(True)
render_claim_text(c)
set_unicode_output(False)
render_claim_text(c)
```

```text
let x = acceleration, let θ = theta, ∀ θ ∈ [0.0, 1.0] ⊂ ℝ ∪ {∅}, x ∈ [0.0, 100.0] ⊂ ℝ ∪ {∅}, f(θ, x) ≥ 0
for theta in [0.0, 1.0]:float|missing, acceleration in [0.0, 100.0]:float|missing, f(theta, acceleration) >= 0
```

Both are the same claim and both parse back. Unicode is the default;
set `MATHEMA_UNICODE=0` in the environment before import, or call
`set_unicode_output(False)` at runtime, to get ASCII everywhere. The
preference is process-wide and takes effect immediately.

Notice what the Unicode form did beyond swapping `>=` for `≥`. It
renamed `theta` to `θ` because the name spells out a Greek letter, and
`acceleration` to `x` because a long name makes an expression hard to
read. Both renames are declared as `let` bindings in the claim itself,
so nothing is lost: the rendered line still says exactly which symbol
stands for which parameter, and reparsing it gives the claim back.

## Type suffixes and the missing value

The ASCII form writes `[0.0, 1.0]:float|missing` where the Unicode form
writes `[0.0, 1.0] ⊂ ℝ ∪ {∅}`. Both say the same two things: the
interval, and that a missing value is part of the declared input space.
A domain that states its type explicitly excludes missing by default,
and `∪ {missing}` puts it back; a domain that states no type allows it,
and `\ {∅}` excludes it. The rendering always shows which of those you
got, because a silently different input space is the kind of thing that
makes a proof mean less than a reader assumes.

## LaTeX

`grammar.to_latex()` renders a law for a paper, a notebook, or a docs
page:

```python
from mathema.grammar import to_latex
to_latex("f(x)^2 >= 0")
to_latex("d(f(x), x) >= 0")
```

```text
f^{2}{\left(x \right)} \geq 0
\frac{d}{d x} f{\left(x \right)} \geq 0
```

`mathema describe <target>` prints the LaTeX form of each claim
alongside its statement, which is the quickest way to pull a rendered
claim into something else you are writing.

## Custom symbols

Every field has its own notation, and a claim written in the reader's
own symbols is a claim the reader will actually check. A **symbology
capability** lets you supply the symbol for a parameter or a function
name, ahead of mathema's own Greek-word matching and its positional
pool.

Write a class with a `symbol_for_param` method:

```python
# my_package/symbology.py

class FinanceSymbology:
    """The symbols a derivatives desk expects to see."""

    _MAP = {"spot": "S", "strike": "K", "volatility": "sigma", "rate": "r"}

    @staticmethod
    def symbol_for_param(name: str) -> str | None:
        return FinanceSymbology._MAP.get(name)

    @staticmethod
    def symbol_for_func(name: str) -> str | None:
        return None
```

Register it as a `mathema.capabilities` entry point named `symbology`:

```toml
# pyproject.toml
[project.entry-points."mathema.capabilities"]
symbology = "my_package.symbology:FinanceSymbology"
```

With the package installed, a claim over `spot` and `strike` renders
in the desk's own notation:

```text
default        : ∀ spot ∈ [1.0, 500.0] ⊂ ℝ ∪ {∅}, strike ∈ [1.0, 500.0] ⊂ ℝ ∪ {∅}, f(spot, strike) ≥ 0
with provider  : let S = spot, let K = strike, ∀ S ∈ [1.0, 500.0] ⊂ ℝ ∪ {∅}, K ∈ [1.0, 500.0] ⊂ ℝ ∪ {∅}, f(S, K) ≥ 0
```

The `let` bindings come for free. mathema states every rename it made,
so a reader who does not know your notation can still follow the claim,
and the rendered text still round-trips through the parser.

A function symbol is introduced the same way, as an alias of the name
the claim already uses: with `symbol_for_func` returning `E` for `g`,
the claim `let g = numpy.exp, ...` shows as `let g = numpy.exp, let E =
g, ..., E(spot) ≥ 1`, and a scope-resolved function `budget_line` shows
as `let B = budget_line, ...`. Read back, the alias resolves to the
same function under the same name, so the display is the same claim.

### Both hooks are optional

| Method | Asked for | Return |
|---|---|---|
| `symbol_for_param(name)` | each real parameter of the function | the symbol, or `None` to decline |
| `symbol_for_func(name)` | each bound function name | the symbol, or `None` to decline |

Return `None` for anything you have no opinion about and mathema falls
back to its own choice, so a provider only needs to know about the
names it cares about.

A provider never crashes a render. One that fails to import is skipped
with a warning. One that raises from either hook while a claim renders
is skipped for that render: none of its answers for that claim are
used, the claim renders with mathema's own names, and a warning naming
the provider's entry point is issued the first time it fails in a
process. Only ordinary exceptions are caught this way; an interrupt
such as `KeyboardInterrupt` still stops the render.

### What mathema will not let you do

A returned symbol is accepted only if it is safe, and mathema checks
this rather than trusting the provider:

- **It cannot collide.** A provider that renders a parameter with
  another parameter's name, or gives two parameters the same symbol, is
  refused for that render: none of its answers are used, the claim
  renders with mathema's own names, and a warning naming the provider
  says which rename collided, as for a provider that raises. A symbol
  that clashes with any other name already in the claim is declined on
  its own. Either way a provider can never make two things in one
  claim share a spelling.
- **It has to survive a parse.** CPython normalises identifiers under
  NFKC at parse time, so `Mₛ` is a legal identifier that comes back as
  `Ms` once parsed. Written bare, a symbol like that would appear one
  way in the law text and another way in the `let` clause, producing a
  line that reparses into a genuinely different claim with no error
  raised anywhere. So a parameter symbol that is not a valid,
  NFKC-stable identifier is written backtick-quoted (`` `Mₛ` ``), which
  reparses exactly, and a function symbol that fails the test is
  declined, since a function name sits where backticks are not valid.

A declined symbol falls back to mathema's own, so the worst case for a
bad provider is that your notation is ignored or shown quoted.

### Rendering is presentation, never adjudication

A capability is a presentation hook. It changes how something already
computed is shown, and it cannot affect whether a claim proves, what
verdict it gets, or what evidence is recorded. Claim adjudication
extends through a separate mechanism with a separate entry-point group,
`mathema.claim_families`, precisely so the two can never be reached
through the same lookup. See [extending mathema](extending.md).

The canonical form used for identity and hashing ignores symbology
entirely, so installing or removing a provider never changes a
function's `form` hash or invalidates a record.
