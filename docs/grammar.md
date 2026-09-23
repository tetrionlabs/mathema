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

What you get back is never terse. Whatever mathema resolved your input
to is rendered explicitly in the record, the error message and the
proof condition, so a shorthand never quietly becomes something you did
not mean. Setting `MATHEMA_UNICODE=0` switches output to ASCII; see
[symbology and rendering](symbology.md).

## Relations

| Spelling | Meaning |
|---|---|
| `f(x) == x` | equality |
| `f(x) ≤ 1` | inequality, in either ASCII or Unicode |
| `f(x) ~= x` | approximate equality, within a tolerance |
| `f =:= g` | function equivalence: two implementations of the same mathematics |
| `f equiv g` | the word alias for the same relation |
| `for a in [0.1,10], b in [0.1,10], 2/(1/a+1/b) <= f(a,b) <= (a+b)/2` | a chained comparison, both bounds in one claim |

## Expressions

| Spelling | Meaning |
|---|---|
| `f(x)^2 >= 0` | powers with a caret |
| <code>&#124;f(x)&#124; &lt;= 1</code> | absolute value with bars |
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

One more binding uses bars around the name, and sets the finite
magnitude that stands in for `oo` when a domain is unbounded, so a
claim quantified over the whole half-line can still be probed:

```
let |inf| be 1e12, for x in [0, oo], f(x) >= 0
```

It is not an ordinary name binding: nothing in the claim refers to
`|inf|`, it only changes how far out the probe route samples.

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

`mathema check` reports an unparseable claim as a clean error with the
position, and exits 2 rather than 1, because nothing was adjudicated.
If you are working through an agent, the MCP surface exposes the same
check as a `parse_claim` tool so a claim can be validated before paying
for a full adjudication. See [the MCP interface](modes/mcp.md).
