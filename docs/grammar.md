# The claim grammar

Every example on this page is taken from `mathema.lexicon.LEXICON`, a
curated set of claims that is checked by the test suite, so nothing
here can drift away from what the parser actually accepts.

A claim is one string. At its simplest it is a relation between the
function under test, written `f`, and something else:

```
f(x) == x
```

Everything after that is optional detail: where the claim applies, what
the symbols mean, and what you are allowed to assume.

## Terse in, explicit out

The grammar accepts the shortest reasonable spelling of anything, and
several spellings of most things, because a claim you have to look up
the syntax for is a claim you will not write. ASCII and Unicode are
interchangeable, and equivalent spellings parse to exactly the same
claim:

| These are the same claim |
|---|
| `f(x) <= 1` and `f(x) ≤ 1` |
| `for x in [0, 1], f(x) >= 0` and `for x ∈ [0, 1], f(x) ≥ 0` |
| `for n in [0, 100] subset Z, f(n) >= 0` and `for n in [0, 100] ⊂ ℤ, f(n) >= 0` |
| `d(f(x), x) >= 0` and `f'(x) >= 0` |
| `integrate(f(x), x, 0, 1) == 1` and `∫(f(x), x, 0, 1) == 1` |
| `for x in [0, 1], f(x) >= 0` and `∀ x ∈ [0, 1], f(x) ≥ 0` |
| `for n in [0, 100] subset Z, f(n) >= 0` and `∀ n ∈ [0, 100] ⊂ ℤ, f(n) ≥ 0` |
| `f(x)^2 >= 0` and `f(x)² ≥ 0` |
| `for x in [0, 1], sqrt(f(x)) >= 0` and `∀ x ∈ [0, 1], √(f(x)) ≥ 0` |
| `for x in [0, 1], f(x) * 2 == 4*x` and `∀ x ∈ [0, 1], f(x) · 2 == 4*x` |
| `for x in [0, oo), f(x) >= 0` and `∀ x ∈ [0, ∞), f(x) ≥ 0` |
| `for x in [0, 1], f(x) >= 0` and `\forall x \in [0, 1], f(x) \geq 0` |

What you get back is never terse. Whatever mathema resolved your input
to is rendered explicitly in the record, the error message and the
proof condition, so a shorthand never quietly becomes something you did
not mean. Setting `MATHEMA_UNICODE=0` switches output to ASCII; see
[symbology and rendering](symbology.md).

## Mathematical notation, and how to read it

Every symbol below is accepted by the parser and means exactly what its
ASCII spelling means, so a claim can be written the way the mathematics is
written without becoming a different claim. Code points are given because
several of these have visually identical neighbours that are *not* the same
symbol, and a claim pasted out of a PDF is a common way to meet one.

| Symbol | Code point | Read it as | ASCII |
|---|---|---|---|
| `∀` | U+2200 | for all | `for` |
| `∈` | U+2208 | in, an element of | `in` |
| `⊂` | U+2282 | a subset of | `subset` |
| `ℝ` | U+211D | the reals | `R` |
| `ℤ` | U+2124 | the integers | `Z` |
| `ℕ` | U+2115 | the naturals | `N` |
| `ℂ` | U+2102 | the complex numbers | `C` |
| `≤` | U+2264 | less than or equal to | `<=` |
| `≥` | U+2265 | greater than or equal to | `>=` |
| `≠` | U+2260 | not equal to | `!=` |
| `≈` | U+2248 | approximately equal to, within a tolerance | `~=` |
| `≡` | U+2261 | equivalent to, as a whole function | `=:=` |
| `⟹` | U+27F9 | implies | `=>` |
| `·` | U+00B7 | times | `*` |
| `×` | U+00D7 | times | `*` |
| `−` | U+2212 | minus | `-` |
| `√` | U+221A | the square root of | `sqrt` |
| `∞` | U+221E | infinity | `oo` |
| `∂` | U+2202 | the partial derivative of | `d(` |
| `∫` | U+222B | the integral of | `integrate(` |
| `→` | U+2192 | tends to, inside a limit | `->` |
| `⌊ ⌋` | U+230A, U+230B | the floor of | `floor(` |
| `⌈ ⌉` | U+2308, U+2309 | the ceiling of | `ceil(` |
| <code>&#124; &#124;</code> | U+007C | the absolute value of | `abs(` |
| <code>&#124;&#124; &#124;&#124;</code> | U+007C | the norm of | `norm(` |
| `²` | U+00B2 | squared, and likewise `³` and the rest | `^2` |

Greek letters are accepted as themselves (`α`, `σ`, `Δ`), and so are the
mathematical-italic Greek letters in U+1D6E2 to U+1D7FF, which is what many
PDF and LaTeX renders paste instead. Both spell the same parameter. Where a
symbol has a plain LaTeX command with no braces, that is accepted typed
literally too, so `\forall x \in [0,1], f(x) \geq 0` is the same claim as
its Unicode and ASCII forms.

### The look-alikes worth knowing about

`⊂` (U+2282) is the subset operator the grammar accepts. **`⊆` (U+2286) is
deliberately rejected**, with an error rather than a silent reinterpretation,
because a proper subset and a subset-or-equal are different mathematical
statements and treating them as spellings of one another would quietly change
what you claimed.

Two pairs go the other way and *are* merged, since they are typesetting
variants of one symbol rather than distinct ones: `⩽`/`⩾` (U+2A7D, U+2A7E) are
the ISO-style slanted forms of `≤`/`≥`, and `𝜋` (U+1D70B, mathematical italic)
is the same constant as `π` (U+03C0).

And keep `≡` and `≈` apart, since they sit next to each other on this page and
mean very different things. `≡` claims two implementations are the same
function, adjudicated on its own ladder. `≈` claims equality within a
tolerance.

### Symbols beyond this set

This table is the notation the core grammar knows. For domain-conventional
symbols, the notation a particular field expects for its own quantities, see
[mathema-symbology](symbology.md), which supplies those names and renders
claims in them.

## Relations

| Spelling | Meaning |
|---|---|
| `f(x) == x` | equality |
| `f(x) ≤ 1` | inequality, in either ASCII or Unicode |
| `f(x) ~= x` | approximate equality, within a tolerance |
| `f =:= g` | function equivalence: two implementations of the same mathematics |
| `f equiv g` | the word alias for the same relation |
| `for a in [0.1,10], b in [0.1,10], 2/(1/a+1/b) <= f(a,b) <= (a+b)/2` | a chained comparison, both bounds in one claim |

### How close counts as equal

On the derive route every relation is decided exactly: `==` and `~=` both
ask whether the two sides are the same over the whole domain, in exact real
arithmetic.

On the probe route, which runs the real function in floating point, `==`
and `~=` are the same comparison: the two sides count as equal when they
agree within a relative tolerance of 1e-6 or an absolute tolerance of 1e-9,
whichever is larger. So `x * (1 + 1e-8)` equals `x` everywhere, while a
constant offset of `1e-7` is caught near zero, where the relative allowance
shrinks below it. A claim sets its own absolute tolerance with the
`tolerance` field of a claims file, or `tolerance=` on `mathema.claim()`,
and that value replaces the whole allowance: the two sides must agree within
it, with no relative tolerance on top.

Inside the claim text, `ε` (also `eps`, `epsilon` or `\epsilon`) names that
tolerance directly: the declared value when there is one, and the 1e-9
default otherwise, on both routes. It is never a free variable to sample, and
a function parameter that happens to be called `eps` or `ε` stays a
parameter. With two functions in `gaps.py`, one off by `1e-10` and one by
`1e-7`:

```python
def nearly_identity(x: float) -> float:
    return x + 1e-10


def small_gap(x: float) -> float:
    return x + 1e-7
```

```bash
mathema check gaps.py --claim "for x in [0, 1], abs(f(x) - x) <= ε"
```

```text
ok   gaps.nearly_identity: source, no side effects; claims 1/1 adjudicated (1 proven, 0 holds, 0 falsified)
FAIL gaps.small_gap: source, no side effects; claims 1/1 adjudicated (0 proven, 0 holds, 1 falsified)  <- 1 falsified claim(s)
```

The first gap is within the default tolerance and proves for every `x` in the
range; the second is a hundred times larger than it and is falsified.

The other relations use the same allowance where it makes sense: `<=` and
`>=` accept a difference within the absolute tolerance, `<` and `>` accept
none, since equality must not pass for strictly less, and `!=` with no
declared tolerance fails only where the two sides are exactly equal.

## Expressions

| Spelling | Meaning |
|---|---|
| `f(x)^2 >= 0` | powers with a caret |
| <code>&#124;f(x)&#124; &lt;= 1</code> | absolute value with bars |
| <code>for x in [0, 1], y in [0, 1], &#124;x + y - f(x, y)&#124; &lt;= ε</code> | bars around any expression; on matrices, the determinant |
| `for n in [1, 5] subset Z, f(n) <= n!` | postfix factorial |
| `f(x, 1.0) == x[-1]` | indexing into a sequence parameter |
| `f(\alpha) ≤ 1` | a Greek name written as a LaTeX escape |
| `for x in [1, 5], f(x) == exp(1)` | the mathematical constants and functions |

## Domains: where the claim applies

A claim with no domain is a claim about every input, which is usually
stronger than you mean. The `for` clause narrows it:

| Spelling | Meaning |
|---|---|
| `for x in [0, 1], f(x) >= 0` | a closed interval |
| `for x in (0, 1), f(x) >= 0` | an open interval, and `(0, 1]` for half-open |
| `for n in [0, 100] subset Z, f(n) >= 0` | restricted to the integers |
| `for n in N, f(n) >= 0` | the naturals, with `Z`, `R` and `C` likewise |
| `for z in C, f(z) == z` | the complex plane |
| `for x in [-1, 1] \ {1}, f(x) >= 0` | an interval with a point excluded |
| `for scale in {"info", "linear"}, f(r, scale) >= 0` | a finite set of strings |
| `for v in R^n, f(v) >= 0` | a real vector of length `n`, never empty |
| `for A in R^(m,n), f(A) == f(A)` | an `m`-by-`n` real matrix, rows then columns |

A matrix space is written `R^(m,n)`, the order of a numpy shape. The
spellings `R^{m,n}`, `R^(m×n)`, `R^{m×n}`, `R^(m*n)` and the superscript
`ℝᵐˣⁿ` are the same space, as are `ℝ³ˣ³` and `ℝ^{3×3}` for a fixed size,
and all of them are written back as `R^(m,n)`. The unicode display uses
superscripts wherever they read back as the same space; a dimension
named with an `x` (the superscript `ˣ` is the separator) or with a
letter that has no superscript form is shown as `ℝ^(x,n)` instead.

The excluded-point form is how you state a claim around a pole. The
finite-set form is how a string-valued parameter that selects a branch
becomes something the derive route can reason about, since it can then
check every case rather than guessing.

## Calculus

| Spelling | Meaning |
|---|---|
| `d(f(x), x) >= 0` | first derivative |
| `f'(x) >= 0` | the same thing, prime notation |
| `∂(f(x, y), x) == y` | partial derivative |
| `d(f(x, y), x, y) == 0` | a second, mixed derivative |
| `d(f(x), x) @ {x = 1} == 2` | evaluated at a point |
| `d(f(x), x) at {x = 1} == 2` | the word form of the same |
| `lim(f(x), x, oo) == 0` | a limit |
| `lim(f(x), x -> 0) == 0` | the arrow form |
| `integrate(f(x), x, 0, 1) == 1` | a definite integral |
| `∫(f(x), x, 0, 1) == 1` | the symbol form |
| <code>integrate(f(x), x)&#124;_{0}^{1} == 1</code> | with an evaluation bar |
| `Sum(f(i))_{i=1}^n == n*(n+1)` | a sum, subscript form |
| `Prod(f(i), i, 1, n) >= 0` | a product |
| `P.V.(integrate(1/(x - c), x, -1, 1)) == f(c)` | a Cauchy principal value |

## Safety predicates

Some questions come up so often that they have names. These adjudicate
by examining the function rather than by algebra:

| Spelling | Asks |
|---|---|
| `is_pole_safe(x)` | does the code guard the points where the maths blows up |
| `is_extremity_safe(x)` | does it survive the far ends of its domain |
| `is_representation_safe(x)` | does floating point represent these values faithfully |
| `is_empty_safe(xs)` | does it handle an empty sequence |
| `is_missing_safe(f)` | the whole function's policy on a missing value |

## Partiality: claims about raising

Raising is behaviour, so it is claimable:

```
raises(f(x), ValueError)
raises(f(50, 0), ValueError)
```

The second form infers the domain from the literal arguments, so you do
not restate what you already wrote. A function that raises inside a
region a claim quantifies over falsifies that claim, on either evidence
route, because a claim about a value is not satisfied by an exception.

## `let`: naming things

`let` binds a name before the claim uses it, which keeps long claims
readable and lets you talk about things that are not parameters:

| Spelling | Binds |
|---|---|
| `let g = math.sqrt, for x in (0,100], g(x) >= 0` | a real function, by dotted path |
| `let g = budget_line, d(g(x, I, px, py), x) == -px/py` | another function in the same module, by bare name |
| `let c be [-1e6,1e6], for x in [0,10], f(x) + c >= 0` | a free variable over a range |
| `let c be [1,100] subset integer, for x in [0,10], f(x) + c >= 0` | a typed free variable |
| `let compute_square_root = numpy.sqrt, for x in [0, 100], compute_square_root(x) >= 0` | a long name, kept readable |

A free variable is the difference between "this holds for the inputs"
and "this holds for the inputs and any constant you care to add", which
is often the claim you actually meant.

### Operational infinity: `let |inf| be ...`

One more binding uses bars around the name. It sets an operational
infinity, the finite magnitude that stands in for `oo` wherever a
claim's domain is unbounded, and it exists because code running on
doubles does not reach infinity. Past about `1.34e154`, `x ** 2` raises
`OverflowError`, and a value claim is false wherever the code raises.
With no operational infinity declared, infinity means infinity, so an
unbounded pointwise claim meets that overflow.

The standard normal density shows both halves of the rule:

```python
import math

import mathema


def gauss(x: float) -> float:
    """The standard normal density."""
    return math.exp(-x ** 2 / 2) / math.sqrt(2 * math.pi)

for law in ["∫(f(x), x, -oo, oo) == 1",
            "f(x) >= 0",
            "let |inf| be 1e100, f(x) >= 0"]:
    (p,) = mathema.claims.check(gauss, [law])
    print(f"{law:31} {p.verdict:9} {p.counterexample or p.condition or ''}")
```

```text
∫(f(x), x, -oo, oo) == 1        proven
f(x) >= 0                       falsified x = 2.6815615859885194e+154
let |inf| be 1e100, f(x) >= 0   proven    ∀ x ∈ [-1e+100, 1e+100] ⊂ ℝ ∪ {∅}
```

The integral over the whole line is proven: an integral, like a limit,
is a statement about the mathematics, and an overflow in the far tail
does not change what it equals. The pointwise claim is a statement
about the code at every `x`, and at `x = 2.68e154` the code raises
before it returns anything. Declaring `let |inf| be 1e100` says that
for this claim, "every `x`" means every `x` up to `1e100` in magnitude,
and the proof then holds, with the region it holds over stated in the
record rather than implied.

The bound applies to both routes: the derive route proves over it, and
the probe route samples out to it. A claim can also state a half-line
explicitly, `let |inf| be 1e12, for x in [0, oo], f(x) >= 0`, where the
`oo` endpoint stops at `1e12`. Nothing in the claim refers to `|inf|`
by name, so it is not an ordinary binding, and in Python the same
setting is `claim(..., pseudo_infinity=1e100)`.

## `assuming`: stating a premise

`assuming` says what the claim takes for granted, which is how a claim
that is only true in part of the input space stays honest without being
watered down:

| Spelling | Assumes |
|---|---|
| `assuming k != 0, f(x, k) == x/k` | a simple side condition |
| `assuming b^2 - 4*a*c >= 0.01, for a in [1,10], b in [-10,10], c in [-10,10], d(f(a,b,c), c) <= 0` | an inequality over the parameters |
| `assuming real_roots, for a in [1,10], b in [-10,10], c in [-10,10], d(f(a,b,c), c) <= 0` | another claim, by name |
| `assuming grows holds, for x in [0,10], f(x) == 2*x` | that claim reached at least `holds` |
| `assuming base_case is proven, for n in [2, 30] subset Z, f(n) == f(n-1) + f(n-2)` | that claim reached `proven` specifically |
| `assuming is_defined(f), for w in [-50, 50], f(F0,k,m,-w,c) == f(F0,k,m,w,c)` | that the function is defined there at all |
| `assuming f is defined, for w in [-50, 50], f(F0,k,m,-w,c) == f(F0,k,m,w,c)` | the postfix spelling of the same |

The last of these is how compositional claims are built: prove that a
function is defined on a region, then assume it in the claims that
depend on it, and the record keeps the dependency.

## Several functions in one claim

`f` is the function under test, but it is not the only one you can
mention:

```
f(x) == g(x)
d(budget_line(x, I, px, py), x) == -px/py
let g = budget_line, d(g(x, I, px, py), x) == -px/py
```

A second function named this way is a full participant, lifted and
reasoned about like `f` rather than treated as an opaque call.

## Outcome references

```
f(x) > 0 => self.stays_positive
```

This links a condition to a named outcome, which is how a claim
connects to the vocabulary your codebase already uses rather than
living in its own world.

## Recurrences

```
for n in [2, 30] subset Z, f(n) == f(n-1) + f(n-2)
```

A self-recursive linear recurrence over one scalar parameter is solved
to its closed form rather than unrolled, so a Fibonacci-shaped function
can reach `proven` over a stated integer range. See [the derive
route](derive-route.md) for the exact shapes this covers.

## When a claim will not parse

`mathema check` reports an unparseable claim as a clean error naming
the part it could not read, and exits 2 rather than 1, because nothing
was adjudicated.
If you are working through an agent, the MCP surface exposes the same
check as a `parse_claim` tool so a claim can be validated before paying
for a full adjudication. See [the MCP interface](modes/mcp.md).
