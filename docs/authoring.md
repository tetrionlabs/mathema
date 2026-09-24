# Authoring claims

Four surfaces, one precedence order (lowest to highest, a same-named
claim from a higher surface overrides a lower one), and one grammar
they all share.

## The claim grammar

Claims are written over the generic function name `f` and the
function's own parameter names, in a typeable superset of ordinary
math:

```
f(-x) == -f(x)                      # odd
f(x)^2 >= 0                         # ^ is power; == / <= / >= are the relations
f(x) ≤ f(y)                         # Unicode ≤ ≥ − · × π accepted, normalized
for x in [0, 1], f(x) <= 1          # domain quantifier
raises(f(x), ValueError)            # partiality: asserts the call raises
f(x) == g(x)                        # relate two implementations (funcs={"g": other_fn})
```

Shorthand: `|x|`/`||x||`/`⌊x⌋`/`⌈x⌉` for `abs`/`norm`/`floor`/`ceil`,
each wrapping any expression, so `|x + y - f(x, y)|` is the absolute value
of the whole difference; `!=`/`≈` as their own relations. Every claim renders to LaTeX
exactly (`mathema.grammar.to_latex`), going *through* sympy so it's
mathematically faithful, not typographically literal.

A domain quantifier's range only ever adds a *sign assumption*
(`positive`/`nonnegative`) for the derive route's proof, never a
substitution, `for x in [0, 5], ...` proves things true for *every*
`x` in that range, it doesn't pick one. The one exception is a
**degenerate, single-point range** (`for c in [0, 0], ...`, lower
bound equal to upper bound): that genuinely does pin `c` to the
literal `0` before the claim is decided, since there's only one value
left to assume anything about. To check a claim at any *other* specific
value, pass it as a literal argument to `f(...)` directly
(`f(a, b, 0)`) rather than declaring a domain for it, ordinary
symbolic substitution, unrelated to the domain mechanism.

Three more forms, **derive route only**, that turn ordinary claims into
calculus, PDE, and (mechanically) SDE claims:

```
d(f(t, x), t) == d(f(t, x), x, x)   # partial derivatives; this is the heat equation
lim(f(x)/x, x, 0) == 1              # limits (point: a constant, or oo / -oo)
integrate(f(x, mu, sigma), x, -oo, oo) == 1   # definite/indefinite integrals
Sum(f(i), i, 0, n) == n*(n+1)/2     # indexed sums/products
```

Shorter spellings for a single-parameter derivative, when there's no
variable to name at all: `d(<expr>)` (the argument's own single free
name is inferred) and prime notation, `f'(x)`/`f''(x)`/... (one
apostrophe per differentiation):

```
d(f(x)) == 2*x        # f has one parameter, x, same as d(f(x), x)
f'(x) == 2*x           # same claim again
f''(x) == 2            # d(f(x), x, x)
```

The traditional `df/dx` fraction spelling is also accepted, but only
*inside* a `d(...)`/`∂(...)` call (`d` and `∂` are interchangeable
throughout this sugar), where the intent (differentiate) is
unambiguous even though the variable isn't; `d(f(x)/dx)` is the same
claim once more. A bare, unscoped `df/dx` anywhere else in a law is
never read this way: at the text level it's ordinary division by a
variable that happens to be named `dx`, with no calling context to
disambiguate it. The variable guessed from a fraction's denominator is
checked against the function's own real parameters once they're known.
A genuine collision (`gibbs_free_energy(dh, t, ds)`, a real
parameter literally named `dh`) is `skipped:misspecified` rather than
silently guessed wrong, with a note naming the unambiguous `d(expr,
h)` form to use instead. A `∂`-marked denominator name is never
ambiguous this way (`∂` can't appear in a real Python identifier at
all), so `∂(f(dh,t,ds)/∂h) == -ds` never needs that check.

A mixed or higher-order denominator concatenates one marker per
variable, each with its own optional exponent (superscript digits or
`^<n>`, matching how `\frac{\partial^3 f}{\partial x^2 \partial y}` is
conventionally written):

```
d(f(x,y)/dx^2dy) == 0       # d(f(x,y), x, x, y), order 2 in x, order 1 in y
∂(f(x,y)/∂x²∂y) == 0        # the same claim, curly and superscript
```

The call's own opening symbol may carry a restated total order
(`d^3(...)`/`d³(...)`), purely decorative unless it disagrees with what
the denominator's own exponents sum to, in which case the whole call is
left unexpanded as a likely typo:

```
d^3(f(x,y)/dx^2dy) == 0     # 2 + 1 == 3, consistent
```

An evaluation marker, `@{v=val, ...}` (or the word `at` instead of
`@`, either with optional whitespace around it), states a claim at a
specific point rather than across a whole domain: `d(<expr>,
<vars...>)@{v=val, ...}` differentiates first, then substitutes each
named variable (an extremum/critical-point claim; "the derivative is
exactly zero here", not just "nonnegative everywhere"). Composes with
every other `d(...)` spelling above:

```
d(f(v0, theta, g), theta)@{theta=pi/4} == 0       # range is maximized at 45°
d(f(v0, theta, g)/dtheta) at {theta=pi/4} == 0    # same claim again
d(f(x)/dx^2)@{x=1} == 6                           # differentiates twice, then substitutes
f'(x) at {x=1} == 3                               # prime notation, one free variable
```

Prime notation takes its variable from the call's single free name, so
it only reads on a one-variable call. `f'(v0, theta, g)` has three, and
`claim()` refuses it with an `InvalidConjecture` that names the
explicit spelling, `d(f(v0, theta, g), <var>)`.

`integrate(<expr>, <var>)|_{a}^{b}` (matching LaTeX's own `\big|_a^b`
convention) is pure sugar for the already-existing bounded 4-argument
form. A bound needs braces only when it contains its own space or
comma, a plain token, however long, doesn't:

```
integrate(f(x, mu, sigma), x)|_{-oo}^{oo} == 1    # same as the 4-arg form above
integrate(f(x), x)|_0^oo == oo                    # a bound needs no braces on its own
```

`∫` and the word `integral` are synonyms for `integrate`, and a
bracket-free form drops the parens entirely, chaining one bound-bar per
differential (each variable may itself be omitted when the expression
has exactly one free name):

```
integral f(x)|_0^1 == 1/2                         # var omitted, no parens
integral f(x,y) dx|_0^1 dy|_0^2 == 1              # sympy's own multi-bound integrate()
```

A bracket-free form of `lim` drops the parens: `lim f(x), x -> a`, or
`lim f(x) as x -> a` ("as" reads the way this is conventionally
spoken, and is a pure synonym for the comma). Unlike `d`/`integrate`,
`lim`'s variable is always named explicitly; `lim f(x) -> a` reads
ambiguously without it, so that shorter spelling isn't accepted.

`raises(...)` only ever proves an *explicit* `raise` reachable through a
domain-conditioned branch, never an exception implicit in an arithmetic
operation (`1/(1+r)` genuinely raising `ZeroDivisionError` at `r = -1`,
with no `if` guard anywhere). It also needs the domain declared on the
**guard's own parameter**, not just a literal call argument that happens
to trigger it, branch pruning evaluates the guard condition against the
function's own declared parameter domains, before any `f(...)` call-site
substitution even happens:

<!-- example: raises-guard run -->
```python
def f(a, b, c):
    if a == 0:
        raise ValueError("a must be nonzero")
    return b / a + c
```

<!-- example: raises-guard verdicts fn=f -->
```
raises(f(a, b, 0), ValueError)              # falsified, a's own domain isn't declared, so a sampled a != 0 returns
for a in [0, 0], raises(f(a, b, c), ValueError)   # proven
```

## Set-notation domains: exclusion, union, type refinement, missing values

A quantifier binding leans on ordinary set notation, and accepts several
spellings of each operator, all canonicalize to the same domain
internally, so pick whichever reads best:

```
for x in [0, 1], ...            # membership: in / ∈ / \in / \elem
for x ∈ (-oo, 0]: ...           # same operator, different spelling
```

**Exclusion** (`\` set-minus, or the `exclude={...}` keyword form) removes
specific points; a pole, say, from an otherwise ordinary interval:

```
for r in [-1, 1] \ {1}, ...                    # excludes the single point r=1
for r in [-1, 1], exclude={1}, ...             # same thing, keyword form
```

**Union** (`|` or `∪`) combines two or more pieces into one domain, for a
genuinely piecewise range:

```
for x in [-10, -1) | (1, 10], ...              # two disjoint intervals
for x in [-10, -1) | (1, 10] \ {5}, ...        # a union, with a point excluded from it
```

**Type refinement** (`⊂`, or the text spellings `\sub`/`\subset`) narrows
a domain to integers or naturals; omitted, a real (`R`) domain is
assumed, matching how an unrestricted parameter already needs no domain
entry at all:

```
for n in [0, 10] ⊂ Z, ...                      # a bounded integer domain
for n in Z, ...                                # bare, unbounded, still a stated type
```

### Missing values

A sequence-typed parameter (a `list`/array/Series, not a scalar) can
contain a missing value, `None`, NaN, or another library's own null
sentinel. Whether that's allowed is governed by one rule, applied the
same way regardless of which library produced the vector: **stating a
type at all is a deliberate, precise choice, and defaults to excluding
missing values; saying nothing about type leaves them allowed.**

```
for x in [0, 100], ...              # no type stated, missing allowed by default
for x in [0, 100] ⊂ Z, ...          # explicit type, missing excluded by default
```

Either default can be overridden explicitly, using the same exclusion/
union operators applied to the missing-value sentinel (`∅`, or the ASCII
spellings `missing`/`NA`/`nan`):

```
for x in [0, 100] \ {∅}, ...              # no type stated, but missing explicitly excluded
for x in [0, 100] ⊂ Z ∪ {missing}, ...    # explicit type, but missing explicitly allowed back in
```

Detection is dependency-free: `None`, a Python/numpy/pandas float NaN
(all ordinary IEEE-754 under the hood, caught by one self-inequality
check with no import of any of them), and a small, extensible set of
other known missing-sentinel type names (pandas' `pd.NA`/`pd.NaT`,
neither of which is NaN-like), never a hard dependency on any one
data-science library.

Input stays terse, nothing above is required beyond an ordinary
interval, but every place mathema *renders* a domain back (a proof
sketch's `∀ x ∈ ...` clause, `enforce_domain()`'s own violation message)
always states the resolved missing-value policy explicitly, via the same
`∪ {∅}` / `\ {∅}` notation, never left for a reader to infer from what's
absent:

```
∀ x ∈ [0.0, 100.0] ⊂ ℝ ∪ {∅}     # missing allowed
∀ x ∈ [0, 100] ⊂ ℤ \ {∅}     # missing excluded
```

`enforce_domain()` (and, in `strict=True` probing, the `domain_enforced`
prober) checks a sequence argument element by element against its
declared domain, including this missing-value policy, an out-of-bounds
or unexpectedly-missing element is rejected the same way a scalar
argument outside its own domain already is.

## Calling the derive route directly

A bare string claim leaves the route to the cascade
(`mathema.claims.claim(law)` defaults to `best`: derive where the
function lifts, seeded sampling otherwise, and the record names
whichever mechanism actually decided). To ask for a proof first, pass
`route="derive"`:

```python
import mathema

r = mathema.check(my_function,
                  claims=[mathema.claims.claim("f(-x) == -f(x)", route="derive")])
```

`mathema.check()` accepts a pre-built claim object in `claims=` exactly
as it accepts a string, nothing else about the call changes. To call
the derive route standalone, without `check()`'s own built-in-law
probing:

```python
results = mathema.claims.check_conjectures(
    my_function, [mathema.claims.claim("f(-x) == -f(x)", route="derive")])
```

Either way, a decided proof comes back `proven`, or `falsified` with
a witness. A claim the derive route cannot decide falls back to
probing rather than stopping at `unknown`, so it can still come back
`holds`, and `Probe.route` then names `probe`, the mechanism that
actually decided. The derive diagnosis stays on the record, and covers
two different things: a genuinely unliftable function, or one the
derive route lifted fine but the specific claim stayed undecided.
`Probe.meta["mathema.derive_status"]` (`"unliftable"` or `"undecided"`)
tells the two apart programmatically, rather than parsing `.note`/
`.sketch` text.

### Case-split retry for an undecided claim

When the ordinary single-context proof comes back undecided, the derive
route tries once more: if the function's own body has a pole, a
stationary point, or a domain-transition point (a `sqrt`/`log`/`abs`
argument crossing zero) strictly inside the declared domain, it splits
the domain there and re-proves the claim on each piece separately. This
is strictly a retry, never a first attempt, an already-decidable proof
pays no extra cost. A claim over `abs(x - 2) - (x - 2) >= 0` on
`x in [-5, 8]` is a real example: undecided in one shot, `proven` once
split at the kink `x = 2`, with the sketch stating the split point
explicitly. A pole is excluded from both pieces and never separately
checked, since the function is undefined there; the sketch says so
rather than silently treating it as covered.

`mathema.critical_points(fn)` exposes the same detection directly:
every pole, stationary point, inflection point, and domain-transition
point mathema can find analytically in `fn`'s own body, as a list of
`{"kind", "variable", "at", ...}` dicts. Never raises, an unliftable
function returns `[]`.

### `extensive`: widening the analysis at real, opt-in cost

`mathema.check(fn, ..., extensive=True)` (also accepted by `probe()`
and `check_conjectures()` directly) widens the critical-point analysis
behind sampling hints, `is_pole_safe[...]`, and the case-split fallback
to also consider a fold/dot/sum-lifted function, not just a directly
liftable one. This can make a partially-liftable function's own
sampling genuinely hybrid, part real symbolic resolution, part
empirical, not just the same analysis run slower. Off by default
everywhere; results are cached by the function's form, so the cost,
when paid, is paid at most once per distinct function shape per
process.

On the derive route, extensive is a strategy ladder, not just a wider
budget: exact real-root isolation (Sturm), adaptive interval
refinement over the domain box, change-of-variable substitutions
(t = sqrt(x)/erf(x)/tanh(x), atan compactification for unbounded
claims), residue contour evaluation for trigonometric integrals, and
finally a widened single-shot retry of the base procedure. With the
optional `mathema[smt]` extra installed, an nlsat rung joins after
interval refinement: z3's nonlinear-real-arithmetic procedure decides
polynomial/rational sign questions (radicals encoded exactly,
Abs/Min/Max as if-then-else) completely, a proof names the oracle in
the sketch, and a candidate counterexample is re-confirmed by exact
arithmetic before any disproof is reported. Without the extra the
ladder simply skips the rung. Each rung
runs under the extensive wall-clock budget, which also reaches the
lowering-time limit/antiderivative evaluation inside law parsing.

The two wall-clock budgets are environment-tunable for a whole
process, the same read-once-at-import pattern as `MATHEMA_UNICODE`:
`MATHEMA_FAST_TIMEOUT` (default 3 seconds) and
`MATHEMA_EXTENSIVE_TIMEOUT` (default 15 seconds), whole seconds;
the knob for a claim whose computation is long but finite.

### `is_pole_safe(param)` / `is_builtin_safe(param)`

Two family-derive-only predicates (`route="derive"` always, neither
has a probe-route meaning), suggested automatically wherever they
apply: `is_pole_safe(param)` asks whether param's declared domain
provably excludes every pole mathema can find in the function's own
body (including gamma/loggamma's own pole at every non-positive integer
of their argument, not just an ordinary denominator's finite root set);
`is_builtin_safe(param)` asks whether param's declared domain is safe
for every restricted-domain math function it's actually passed to
(`factorial`/`sqrt`/`log`/`asin`/`acos`/`gamma`/`lgamma`, sympy's own
symbolic generalization is often wider than the real function's own
accepted domain, e.g. `factorial` generalizing continuously via `gamma`
while `math.factorial` itself only accepts a non-negative integer).
Both report `proven`/`falsified`, an exact symbolic check, not a
sampled one, or `skipped:unsure` when genuinely undecidable, never a
guess. Only suggested for a parameter where it's actually relevant (a
real pole found, or a real restricted call using that parameter), the
same always-surfaced-when-relevant spirit as the rest of the
safety family. Whether the code REJECTS out-of-domain input is the
declared `excluded_outside_domain(p)` claim, stated explicitly,
opted into with the `excluding` keyword, or auto-declared by
`@enforce_domain` (the decorator that makes it true).

### `mathema.suggest_claims(fn)`

Suggests candidate claims for `fn` without checking any of them:
monotonicity, affine-ness, and convexity/concavity per real scalar
parameter (each already expressible via the `d(...)` sugar above,
including `d(f(x)/dx^2)` for a second derivative), plus a
`raises(...)` claim per parameter guarded by an
`if ...: raise ExcType(...)`, the stateless cluster
(`is_deterministic`/`is_state_safe`, plus `is_reproducible` where
randomness is structurally detected), and the gated safety
predicates. Suggested routes are `best` (the cascade decides at
check time); safety predicates always adjudicate on the `examine`
route whatever was declared; they are facts about the
implementation. A suggestion may still come back
`unliftable`/`undecided` when actually checked; that's expected for
a declared, unverified claim. Battery keywords are the terse way to
opt in: `check(fn, claims=["defined", "excluding", "stable",
"stateless"])`, each expands to the structurally relevant members
(see the notebook's safety-family section).

```python
mathema.check(fn, claims=mathema.suggest_claims(fn))   # use directly
mathema.suggest_claims(fn, write=True)                 # or persist as declared
```

`write=True` appends to `claims/<key>.claims.yaml`, merging by claim
name with anything already declared there rather than overwriting it.

## Exploring a function symbolically

Beyond checking a specific claim, `lift()`, the same function the
derive route uses internally, is directly callable to see what a
function reduces to symbolically, useful when developing a claim
interactively (a notebook, a REPL) rather than running the whole check:

```python
import mathema

facts = mathema.analyze_source(my_function)
lifted = mathema.lift_symbolic(my_function, facts)
lifted.expr        # a real sympy.Expr (or tuple of them, for a tuple return)
```

`lifted.unicode`/`lifted.latex` are the same rendered forms a claim
failure message shows; `mathema.grammar.to_canonical(lifted.expr)`
renders it in mathema's own claim-grammar spelling (`abs(x)`, `max(x,
y)`) rather than sympy's own (`Abs(x)`, `Max(x, y)`), the same text a
claim law would actually be written in. If `lift()` returns `None`,
`mathema.inventory.derivability_report(my_function)` explains why (the
same diagnosis `mathema audit`'s blocked detail uses), a loop, a branch,
recursion, or a non-scalar parameter, with a specific reason rather
than a generic refusal. `inventory` is a submodule, not re-exported at
the top level: `import mathema.inventory` first.

## 1. Inferred from types (lowest precedence)

Automatic, no claim actually typed, via `typing.Annotated` or a
docstring shorthand:

```python
from typing import Annotated
from mathema.types import Probability, Shape

def bayes_update(prior: Annotated[float, Probability],
                 likelihood: Annotated[float, Probability]) -> Annotated[float, Probability]:
    ...   # prior/likelihood/return all auto-sampled inside [0, 1]

def matmul(a: Annotated[list, Shape("m", "n")],
          b: Annotated[list, Shape("n", "p")]) -> Annotated[list, Shape("m", "p")]:
    ...   # auto-checks: real output shape matches (m, p) for whatever m/n/p got sampled
```

The signature is the one place a type belongs: there is no docstring
spelling for markers (an earlier `Types:` block was removed as
superfluous to the typing system). A bound for a name the signature
can't carry, a fold's own accumulator or item variable; goes in
the claim that needs it, as a `let name be [lo, hi]` binding. An
`Annotated` hint always wins on a name collision.

## 2. Docstring `Claims:` block

```python
def f(x):
    """Claims:
        odd: f(-x) == -f(x)
        nonneg [derive]: f(x) >= 0
    """
```

`name [route]: statement` per line, `route` optional (`probe`/`derive`,
defaults to `best`, the cascade decides, same as a bare claims-file
row; a tag transfers through conflict resolution only when you wrote
one). The block ends at the first line that dedents
back to column zero. Google/Napoleon-style header (one line ending in
`:`), not a numpydoc dash-underlined section; a claims block is
list-like, one claim per line, not prose.

## 3. Decorator

```python
@mathema.claims_decorator("f(-x) == -f(x)")
def f(x):
    ...
```

Structured data, parsed at decoration time, a typo in the law string
surfaces immediately, as an exception right at import. On a name
collision with a docstring claim, the decorator wins: structured-and-
eagerly-checked beats freeform-and-silently-stale.

## 4. A claims file on disk

`*.claims.yaml`, `claims/*.yaml`, `claimspec.yaml`, anywhere in the
tree. Several files can declare claims for the same function, even in
different grammars; they merge by claim *name*, not whole-file
replace.

```yaml
# claims/softmax.claims.yaml
functions.softmax:
  claims:
    - name: sums_to_one
      statement: "sum(f(scores)) == 1"
      route: probe
```

A hand-written file is the most deliberate, most reviewable place to
override a claim, so it always wins over anything the function itself
declares.

A claim with no `name:` is named from its statement, with its relation
as a word: `f(x) >= 0` is `f_x_ge_0` and `f(x) <= 0` is `f_x_le_0`. The
name keys the claim's pins, locks and verified row, so it never depends
on where the claim sits in a list. Two different claims that would take
the same name (two domains of one law, say) are refused, asking for an
explicit `name:` on each.

Claims files are the declared layer, and every field in one is a field
mathema reads. A field it does not know is refused (exit 2, one line
naming the file, the key and the field), with a "did you mean" when it
is a near miss of a real one. Annotations have fields of their own:

| Field | Where | Holds |
|---|---|---|
| `note:` | on a claim | free text |
| `meta:` | on a claim or the entry | structured data |
| `references:` | on the entry | links (`title`, `url`, `via`) |
| `meta: {concepts: [...]}` | on the entry | tags |

```yaml
functions.softmax:
  meta: {concepts: [probability]}
  claims:
    - name: sums_to_one
      statement: "sum(f(scores)) == 1"
      route: probe
      note: "agreed with the modelling team; see the design doc"
```

Prefer `note:` to a YAML `#` comment. Some commands rewrite a claims
file from its parsed form (`docsync --yes` resolving a conflict, an
acceptance retiring a claim), and a comment does not survive that; a
`note:` is part of the claim and persists through every rewrite.
`docsync` warns before it rewrites a file that has comments.

## Experiment before you declare

Try a spelling before it reaches an authoring surface. Both of these
adjudicate a claim against the live function and write nothing to the
store:

```bash
mathema check mypkg.mod.fn --claim "for x in [0, 5], f(x) >= 0"
```

```python
mathema.check(fn, claims=["for x in [0, 5], f(x) >= 0"])
```

This matters because a DECLARED claim that falsifies is permanent
evidence. The verified layer never silently shrinks: deleting the
claim from your claims file does not remove it, because the record
repopulates it by name, so a failed experiment leaves a falsification
that only a human decision clears (fix the code, accept it
`--as discovery`, or supersede it). That is deliberate, it is what
stops an inconvenient result from being quietly deleted, but it means
the cheap place to be wrong is `check`, not a claims file. `verify`
says so the first time a claim falsifies on its first adjudication.

## All four funnel into the same shape

Every surface resolves through `spec.declare()`, so nothing downstream
cares which surface a claim came from. `mathema.write_spec()`'s worked example below
shows claims from three different sources adjudicated together with
zero manual wiring, for this softmax:

<!-- example: write-spec run -->
```python
import math
from typing import Annotated

import mathema
from mathema.types import Shape


def softmax(scores: Annotated[list, Shape("n")]) -> Annotated[list, Shape("n")]:
    """Normalised exponentials of a list of scores.

    Claims:
        sums_to_one: sum(f(scores)) == 1
    """
    top = max(scores)
    exps = [math.exp(s - top) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]
```

<!-- example: write-spec repl -->
```
>>> mathema.write_spec(softmax, root='.')
mathema.Record(softmax) · source, no side effects · form 7302d34f1904
  holds   shape: shape(softmax(scores)) == ('n',), for shared dims ['n'] (n=32)
  holds   is_deterministic: f(scores) = f(scores) (n=192)
  holds   is_state_safe: f(scores) = f(scores) (n=48)
  holds   is_numerically_stable: let g = mathema.f.finite_no_error, g(f, scores) = 1 (n=192)
  holds   preserves_length: dim(f(scores), 0) = dim(scores, 0) (n=192)
  FALSIFY is_permutation_of_input: sorted(f(scores)) = sorted(scores)
           counterexample ([0, 6.12225]): [0.0021887084924676944, 0.9978112915075322] vs [0.0, 6.122252531363742]
  holds   preserves_type: type(f(scores)) = type(scores) (n=192)
  FALSIFY is_sorted_output: is_sorted_output(f(scores))
           counterexample ([4.86304, 8.4521, -9.06059, -3.61645]): output [0.02688154996295693, 0.9731128430407592, 2.412672431510259e-08, 5.582869559580238e-06] fails is_sorted_output
  holds   sums_to_one: sum(f(scores)) = 1 (n=192)
```

`shape` came from the `Annotated[list, Shape("n")]` hints,
`sums_to_one` came from the docstring `Claims:` block, and the rest are
mathema's built-in battery: every function gets the determinism, state
and stability probes, and a list-in, list-out function also gets the
sequence laws. Two of those rightly falsify, because softmax neither
permutes nor sorts its input.

## Shape markers and their shorthand

A nested-list parameter's dimensions are declared with a `Shape`
marker, and `Vec`/`Mat` are shorthand for the common spellings:

```python
from mathema.types import Vec, Mat

def matvec(a: Mat("m", "n"), x: Vec("n")) -> Vec("m"):
    return [sum(a[i][j] * x[j] for j in range(len(x)))
            for i in range(len(a))]
```

`Vec("n")` is exactly `Annotated[list, Shape("n")]` and `Mat` is the
same factory under a name that reads better for two dimensions. A
dimension name shared across parameters (`n` above) is drawn to one
size every trial, so the arguments are conformable, and each name is
a first-class symbol a claim can reference in a premise or a
law over its dimensions.

A claim may also state a parameter's space in its own domain
(`for a in R^(p,q), ...`). Where a claim and a marker both describe
the same parameter, the marker is authoritative on RANK: a claim that
gives it a different number of axes is a conflict, skipped with the
reason. A different NAME at the same axis is not a conflict, it aliases
the claim's name to the signature's, so the two are one dimension.
