# The derive route: what's liftable

The `derive` route lifts a function's body to a symbolic expression and
decides a claim algebraically. `proven` is strictly stronger evidence
than `holds (n=...)`, not "n samples agreed," but "the relation holds
for every input in the declared domain", in exact real arithmetic. It's also only available for the functions it
can actually lift, which is a real subset. This page is the complete,
current reference for what that subset is.

Lifting is honest, not clever: it never guesses at a closed form.
Anything not covered below is `underivable` on the derive route
(the record's note names the likely reason), never a false `proven`,
and the claim falls through to the probe route. Probe-route claims
remain viable regardless of any of this, see [CDD in one page](cdd.md).

## What's liftable

| Shape | Liftable? |
|---|---|
| A loop-free, branch-free, non-recursive, all-scalar body | ✅ base case |
| A single accumulator folded over one sequence parameter (or none at all; `for i in range(n):`, a bare fixed-iteration-count fold), updated by an expression affine in the element and the accumulator | ✅; closes to a sum over the sequence, see below |
| A purely additive accumulator (`acc = acc + <anything>`, however nonlinear) over zero or more sequences, nested loops, `enumerate()`, or multiple sequential passes | ✅, no telescoping needed, see "General sum accumulation" below |
| A self-recursive linear recurrence (fibonacci, doubling, factorial) over one scalar parameter | ✅ via its `rsolve` closed form, gated to integer domains, see "Recurrences" below |
| Any other recursion (multiple parameters, mutual recursion, memoized wrappers) | ❌ |
| A read-only method on a dataclass or simple class: `self.field` reads expand to field symbols, `self.helper(...)` sibling calls inline, `for self.field in [lo, hi]` quantifies the field | ✅, stateful (a write to `self`, or `self` escaping) stays out |
| `sum(<generator>)`, `sum(xs)`, `sum(map(g, xs))`, `sum(filter(p, xs))`; filters become exact conditional summands | ✅, desugared to the accumulator loop above |
| A comprehension VALUE (`return [v*2 for v in xs]`, dict/set comps) | ❌ vector-valued |
| A body-local `g = lambda t: ...` called in the same body, or a lambda bound via `funcs=` | ✅ applied by substitution |
| A branch, condition over a signature parameter | ✅ if a claim's declared domain settles which side runs |
| A branch, condition over a local variable, or an equivalent expression written directly in the `if` | ✅ if it's *affine* in unmodified parameters (`denom = x + y`, or `if x + y == 0:` inline) |
| A branch, condition over a *non-affine* local or expression (`denom = x * y`) | ❌ |
| A ternary (`x if cond else y`) | ✅ if the condition is a comparison or a boolean combination of them |
| A ternary with a bare boolean-name condition (`x if flag else y`) | ✅ if the declared domain pins the name to exactly `True` or `False`, see below |
| `return a, b` (a tuple) | ✅, compare elementwise or index a single element |
| A parameter that's a flat `@dataclass`, or a dict read by literal string keys | ✅, expands into one symbol per field/key |
| `min`/`max`/`np.minimum`/`np.maximum`/`np.clip` | ✅ against a declared domain |
| A call to a plain function this one calls (`_scale(x)`, not a method or module-qualified call) | ✅ up to 3 levels deep by default, including a callee with its own branch if the caller's domain settles it, see below |
| A claim relating two (or more) functions, `f(x) == g(x)`, `d(f(x, g(x,I,px,py), a), x) == 0` | ✅ each bound function lifts to its own closed form and substitutes like `f`, see "Multi-function claims" below |
| A non-scalar parameter | ❌ for `lift()` itself, with two independent exceptions: a whole body that's exactly `return np.dot(a, b)` (see "Dot products"), or a loop that sums over it; any loop, nested or sequential, whose accumulator is purely additive (see "General sum accumulation") |
| A parameter typed as a matrix/vector | ❌ for lifting the body; a matrix claim declares its domain as `R^(m,n)` and is adjudicated by probing and the linear-algebra identities in [Matrix structure](matrix-structure.md) |
| A *local* array built from `np.linspace`/`np.arange`, transformed elementwise, returned bare or as one element of a tuple | ✅; index it in claim text via `f(...)[i]`, see "Local symbolic arrays" below |

## Callees

A call to a name that isn't a known math function but does resolve to a
real, plain Python function this one calls is inlined rather than
refused outright: the callee is itself lifted (recursively, a callee
can call its own callees), and its parameters are substituted with this
call site's argument expressions.

```python
def _scale(x: float) -> float:
    return 2.0 * x

def _offset(y: float, c: float) -> float:
    return y + c

def uses_helper(x: float) -> float:
    return _offset(_scale(x), 1.0)
```

```
f(x) == 2*x + 1   # proven
```

Capped at 3 levels deep by default (`symbolic.lift()`'s own
`max_callee_depth` parameter, the same concept, and the same default,
as `docstring.docstring_sync()`'s own callee resolution, applied here
to proof instead of docstring/code sync). A cycle through calls (`A`
calls `B` calls `A`, not a bare self-call) is refused outright rather
than chasing the depth budget down to exhaustion. Declines rather than
guessing whenever the callee itself isn't cleanly liftable (references
a module-level global, has a loop, takes a composite `@dataclass`/dict
parameter), the call uses keyword arguments, or it's a method or
module-qualified call (`obj.method(x)`, `mod.helper(x)`), only a bare
`name(...)` call to a plain function is ever attempted.

### A callee with its own branch

A callee's branch isn't an automatic refusal either, when the caller's
own declared domain settles it:

```python
def guarded(y: float) -> float:
    if y > 0:
        return y
    return -y

def caller(x: float) -> float:
    return guarded(x) + 1.0
```

```
for x in [1, 5], f(x) == x + 1     # proven
for x in [-5, -1], f(x) == -x + 1  # proven
```

Only a **bare-parameter-passthrough** call-site argument contributes a
domain for the callee; `guarded(x)`, where `x` is exactly the caller's
own domain-bounded parameter. A computed argument (`guarded(x + 1.0)`)
is skipped rather than approximated; there's no attempt to work out the
image of a domain under an arbitrary expression, only the exact case
where the value literally is the caller's own parameter. This threads
through further calls too, a branch-free function calling a callee
that itself calls a branchy one still resolves, as long as the whole
chain is bare-parameter-passthrough and within `max_callee_depth`.

## Branches, in more detail

A branch is refused unconditionally by the base lifter. A claim can
still resolve one two ways:

- **Domain-conditioned**: the branch condition compares an unmodified
  signature parameter against a literal, and the claim's own declared
  domain settles which side always runs.

  ```python
  def strength_to_distance(r: float, scale: str = "info") -> float:
      if scale == "info":
          return math.sqrt(1.0 - r ** 2)
      return 1.0 - r
  ```

  ```
  for r in [0, 1], scale in {"info"}, f(r, scale) == sqrt(1.0 - r^2)   # proven
  ```

- **Affine-local**: the condition is over a *local* variable, not a
  bare parameter, traced back to unmodified parameters via a
  straight-line chain of simple assignments.

  ```python
  def divides(x: float, y: float) -> float:
      denom = x + y
      if denom == 0.0:
          return 0.0
      return x / denom
  ```

  ```
  for x in [1, 1], y in [-1, -1], f(x, y) == 0.0   # proven
  ```

  A **non-affine** local (`denom = x * y`) can't be resolved this way;
  corner-evaluation over a domain box is only exact for affine
  expressions.

  The condition doesn't have to be bound to a name first, an
  expression written directly in the `if` resolves exactly the same
  way a named affine local does, via the identical mechanism:

  ```python
  def voltage_divider(vin: float, r1: float, r2: float) -> float:
      if r1 + r2 <= 0:
          raise ValueError("invalid resistances")
      return vin * r2 / (r1 + r2)
  ```

  ```
  for r1 in [-1, -1], r2 in [0, 0], raises(f(vin, r1, r2), ValueError)   # proven
  ```

- **Boolean and identity guards, and the finite-set split**: a
  parameter annotated `bool` states its entire domain the same way a
  `Literal[...]`/`Enum` annotation does, the real `{False, True}`
  objects, never the numerically-equal `0`/`1` (code comparing with
  `is True` genuinely distinguishes them, and probe sampling draws
  the stated values too). Every spelling of a boolean guard resolves:
  bare truthiness (`if flag:`), equality (`== True`, `== 1`,
  `!= 0`), identity (`is True`, `is not True`, decided exactly,
  per element, over a discrete domain; an interval domain leaves
  identity undecided by design), negation (`not flag`), and either
  ordering inside `and`/`or` compounds. And when the declared (or
  stated) domain spans both branches, a small finite domain (up to 8
  values) splits into its individual values and the claim proves on
  each piece separately, so this proves with nothing declared in
  the claim at all:

  ```python
  def gate(flag: bool, x: float) -> float:
      if flag is True:
          return x + 1.0
      return x - 1.0
  ```

  ```
  for x in [1, 5], f(flag, x) >= x - 1   # proven (split into {False}, {True})
  ```

  An *authored* int domain keeps honest identity semantics: under
  `for flag in {1}`, the guard `flag is True` decides `False`
  (`1 is not True` in Python), so a then-branch claim falsifies
  rather than being waved through as equality.

See `mathema audit`'s blocked detail (in
[mathema audit](modes/audit.md))
for a precise diagnosis of exactly why a specific branch is or isn't
resolvable in your own code; the same diagnosis a *live claim's* own
failure sketch now names too, rather than one generic message for
every reason branch pruning could fail: "this condition shape isn't
recognized at all" reads differently from "the shape is fine, but the
domain doesn't cover the parameters it needs", and `raises(...)`
specifically says so directly when there's no explicit `raise`
anywhere in the function to find in the first place; see
[Authoring claims](authoring.md)'s own note on `raises(...)`.

## Ternaries

A ternary (`x if cond else y`) whose condition is a comparison or a
boolean combination of comparisons always lifts, to a domain-agnostic
`sympy.Piecewise`, no domain needed at lift time, since `try_prove()`'s
own sign-decidability chain resolves it later, the same way a `min`/
`max` clamp does.

A **bare boolean-name condition** (`x if flag else y`) is different: on
its own, an ordinary real-valued sympy symbol isn't a sympy Boolean, so
there's nothing to build a `Piecewise` *from* without already knowing
`flag`'s truth value. This resolves the same way a domain-conditioned
branch does, if the declared domain pins `flag` to exactly `True` or
exactly `False`, the matching side is evaluated directly, no `Piecewise`
involved at all:

```python
def pick(flag: bool, x: float, y: float) -> float:
    return x if flag else y
```

```
for flag in {True}, x in [0, 1], y in [0, 1], f(flag, x, y) == x   # proven
for flag in {False}, x in [0, 1], y in [0, 1], f(flag, x, y) == y  # proven
```

A domain that admits *both* `True` and `False` stays exactly as
unresolved as before, genuinely ambiguous, not guessed at. And a
`flag` that's *reassigned* anywhere in the function body before the
ternary is never trusted against its original declared domain either,
even if the domain would otherwise pin it, the same
never-reassigned-anywhere check `lift_conditioned()` already applies
before trusting a domain against an `if` *statement*.

## Tuple returns

```python
def to_cartesian(r: float, theta: float) -> tuple:
    return r * cos(theta), r * sin(theta)
```

```
f(r, theta) == (r * cos(theta), r * sin(theta))    # proven, elementwise
f(r, theta)[0] == r * cos(theta)                   # proven, single element
```

## Bundled parameters

A parameter that bundles many scalars, a flat `@dataclass`, or a dict
accessed only via literal string keys, expands into one symbol per
field/key instead of being refused outright:

```python
@dataclass
class Config:
    a: float
    b: float

def sum_fields(cfg: Config) -> float:
    return cfg.a + cfg.b
```

```
f(cfg) == cfg.a + cfg.b   # proven
```

A claim can address a field the same way regardless of whether the
function itself used attribute or subscript syntax (`cfg.a` or
`cfg["a"]`). There's no way to substitute "a different Config
instance" in this grammar, an `f(...)` call's argument for a bundled
parameter's slot must be a bare reference to the same parameter name.

## Clamps

```python
def clamp01(x: float) -> float:
    return min(1.0, x)
```

```
for x in [0, 1], f(x) == x        # proven
for x in [2, 5], f(x) == 1.0      # proven
```

`np.minimum(x, y)`/`np.maximum(x, y)`, numpy's elementwise two-argument
min/max, not the array-reducing `np.min`/`np.max`, lift the same way
as bare `min`/`max`. `np.clip(x, lo, hi)` is recognized the same way
too (mapped to nested `min`/`max`). Only the 3-argument, both-bounds
form; a one-sided clip needs the bound spelled as plain `min`/`max`
instead.

## Linear accumulator folds

One specific loop shape is recognized on its own, without any general
loop-folding: a scalar accumulator initialized to a sequence
parameter's first element, then updated once per remaining element by
an expression affine in that element and the accumulator,

```python
def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y
```

closes directly to a sum over the sequence (no recurrence-solving,
just unrolling), with the update's own `alpha`/`1 - alpha` read
straight off the code, not assumed:

```
y_n = (1 - alpha)^n * x[0] + alpha * x[n] + Sum_{k=1}^{n-1} alpha * (1 - alpha)^(n-k) * x[k]
```

verified against 200+ random `(x, alpha)` pairs matching the real
function's output exactly, including `alpha = 1` (collapses to
`x[-1]`) and length-1 sequences (the loop body never runs, result is
`x[0]`).

A claim can reference the folded sequence directly, a literal index
(`x[0]`, `x[-1]`) or `len(x)` resolves against the fold's own closed
form, so `f(x, 1.0) == x[-1]`; untestable at any single trial count on
the probe route, since it's about *every* length and *every* other
element, not one sampled case, is `proven`:

```
f(x, 1.0) == x[-1]     # proven, alpha=1 collapses the fold to the last element
f(x, alpha) == x[-1]   # falsified, correctly: it's false for most alpha
```

### A transformed return, not just the bare accumulator

The function doesn't have to return the accumulator itself, a
transformation on top of it (dividing by the count, taking a square
root, ...) is fine too:

```python
def mean_of_list(x: list) -> float:
    total = 0.0
    for v in x:
        total += v
    return total / len(x)
```

`len(x)` resolves against the fold's own symbolic length the same way
it does in a claim; the accumulator's own closed form is computed
first, then the return expression is applied on top of it, so a claim
combining the two, a scalar substitution that collapses the
accumulator's own recurrence *and* a transformation on the return,
composes correctly:

```python
def ema_scaled(x: list, alpha: float, scale: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y * scale
```

```
f(x, 1.0, 2.0) == 2 * x[-1]   # proven
```

Only when the return expression itself isn't liftable at all (an
unbound name, an unsupported call) does this still decline, the
accumulator update being perfectly fine doesn't rescue an unliftable
return on top of it.

Two starting shapes are recognized; the accumulator can start at the
sequence's own first element (folding over the rest, `x[1:]`), or at a
separate value entirely, typically another parameter (folding over the
whole sequence):

```python
def running_total(xs: list, y0: float) -> float:
    total = y0
    for v in xs:
        total = v + total
    return total
```

Anything that doesn't match one of these two shapes exactly (a guard
inside the loop, more than one statement in the loop body, an initial
value that partly but not fully depends on the sequence, a non-affine
update, an additive constant) declines rather than guessing,
`mathema audit`'s blocked detail names the specific reason as a stable
code (e.g. `loop:first-element-init-wrong-iteration` is actionable;
change the loop to iterate `x[1:]`; `loop:non-affine-update` is a
mathema limitation), with the full meaning/fixability/hint table in
[Reason codes](reason-codes.md), see [mathema
audit](modes/audit.md).

### No sequence at all: a bare fixed-iteration-count fold

A third shape needs no sequence parameter whatsoever, a plain `for i
in range(n):` (or `for _ in range(n):`), `n` an ordinary scalar
parameter (or any liftable expression built from one, e.g. `range(n +
1)`), still folding with a genuine recurrence (the accumulator's own
coefficient isn't 1):

```python
def compound_balance(P: float, r: float, n: float) -> float:
    balance = P
    for _ in range(n):
        balance = balance * (1 + r)
    return balance
```

closes the same telescoping way as the sequence-based shapes above,
absent a sequence, the "item at iteration k" is simply `k` itself, the
loop's own index, needing no `IndexedBase` at all:

```
f(P, r, n) == P*(1+r)**n   # proven
```

The trip count is referenceable directly in claim text, exactly like
any other scalar parameter (`n`, or `n + 1` if that's what the loop
itself iterates), no `len(...)`-style indirection needed the way a
real sequence's own length requires. Only `mode = "external_init"` is
possible here (there's no `seq[0]` to start an accumulator from
without a sequence); everything else about what counts as affine,
what declines, and why, is identical to the sequence-based shapes.

## Dot products

A non-scalar (sequence-typed) parameter is refused everywhere else in
the derive route, with one narrow, independent exception: a whole
function body that's nothing but a dot product between exactly two of
its own sequence parameters,

```python
def dot_weights(weights: list, features: list) -> float:
    return float(np.dot(weights, features))
```

lifts directly to `Sum(features[k]*weights[k], (k, 0, L - 1))`, no loop
involved at all; `float(...)`/`int(...)` wrapping the call is
unwrapped first, the same way a bare numeric cast already is elsewhere
in the derive route. `L` implicitly assumes `len(weights) ==
len(features)` (never verified symbolically, a real call with
mismatched lengths raises long before any claim about it is checked,
so this is a disclosed assumption, not a soundness gap).

This is deliberately narrow, not a step toward a general vector type:
only the literal `np.dot(a, b)` call is recognized, and only as the
*entire* body, `np.dot(a, b) + 1.0` declines. The identical reduction
hand-written as a loop (`total = 0.0; for i in range(len(a)): total +=
a[i] * b[i]`) also declines *here*, but is liftable overall; see
"General sum accumulation" below, which recognizes it directly from
loop structure instead. A claim's own `f(...)` call must use the two
sequence parameters in their real declared order (`f(weights,
features)`, not `f(features, weights)`); swapping them would mean
substituting a genuinely different call, not just commuting, and isn't
attempted.

## General sum accumulation

`lift_fold()` (above) requires the accumulator's own update to be
affine in *both* the loop item and the accumulator, because closing a
`coeff_acc != 1` recurrence (EMA-style decay) to a closed form needs
that. But when the accumulator's own coefficient is exactly 1, the
update is `acc = acc + <anything>`, pure addition, never multiplying
the accumulator by anything; there's nothing to telescope at all:
`acc` after the loop is *structurally* `init + Sum(<that anything>,
...)`, true for any expression in the loop item, however nonlinear.
`lift_sum()` recognizes that broader, simpler shape independently,
tried only after `lift_fold()` declines, never replacing it, and
extends it three ways at once:

**Non-affine updates**, closed as a plain, uncollapsed `Sum` rather
than refused:

```python
def rms(signal: list) -> float:
    total = 0.0
    for v in signal:
        total += v * v
    return math.sqrt(total / len(signal))
```

```
f(signal) == f(signal)   # proven, sqrt(Sum(signal[k]**2, (k, 0, L_signal - 1))/L_signal)
```

**A dot product recognized directly from loop structure**, not only
via a literal `np.dot(...)` call, an index-bound loop
(`for i in range(len(a)):`) can subscript *any* of the function's
sequence parameters by that index, which is what makes this
recognizable at all:

```python
def dot_product(a: list, b: list) -> float:
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total
```

```
f(a, b) == f(a, b)   # proven, Sum(a[i]*b[i], (i, 0, L_a - 1))
```

A third loop-header form, `for i, item in enumerate(seq):`, binds both
at once, closing the `enumerate()`-based iteration gap too:

```python
def present_value_series(cashflows: list, r: float) -> float:
    pv = 0.0
    for i, cf in enumerate(cashflows):
        pv += cf / (1 + r) ** i
    return pv
```

**No sequence at all**, a fourth loop-header form, `for i in
range(n):` (`n` an ordinary scalar parameter, or any liftable
expression built from one), needs no sequence parameter whatsoever:

```python
def arithmetic_series_sum(a1: float, d: float, n: float) -> float:
    total = 0
    for i in range(n):
        total += a1 + i * d
    return total
```

```
f(a1, d, n) == n*(2*a1 + (n-1)*d)/2   # proven, Gauss's formula
```

**Nested loops** (one level of `Sum` per loop) and **multiple
sequential accumulator passes**, including a genuine two-pass shape
where an ordinary scalar local sits between them and the second pass
uses it:

```python
def sample_variance_two_pass(xs: list) -> float:
    total = 0.0
    for x in xs:
        total += x
    mean = total / len(xs)
    sq = 0.0
    for x in xs:
        sq += (x - mean) ** 2
    return sq / len(xs)
```

```
f(xs) == f(xs)   # proven
```

Two sequential passes with an intermediate scalar between them
surfaced a real, confirmed sympy bug: `sympy.simplify()` can raise a
bare `StopIteration` on a `Sum` whose own summand contains another,
already-simplified `Sum` (the second pass's summand references `mean`,
itself `Sum(...)/L`). Simplification is cosmetic, never required for
correctness, so `lift_sum()` falls back to the unsimplified expression
rather than letting that surface as a crash.

Declines rather than guessing on: a loop body with more than one
statement (an extra local computed before the accumulator update, or
multiple accumulators updated together in one loop, both still open,
see the real-world catalog's own `polygon_area_shoelace`/
`sample_second_moment_single_pass`); an update that isn't purely
additive in its own accumulator (`total = total * v`); and a sequence
subscripted by anything other than the loop's own bound index or item.

## Finite sets: non-numeric values

Every other section above lifts *numeric* values; sympy is a numeric-
algebra system, and every constant `_expr_to_sympy` accepts is a plain
`int`/`float` by default. A branch or ternary that resolves down to
picking one of several *non-numeric* literals (a string, `None`, an
`Enum` member) had nowhere to go: the value itself was refused outright,
even once the condition selecting it was fully resolved.

```python
def status_message(ok: bool) -> str:
    return "success" if ok else "failure"
```

```
for ok in {True}, f(ok) == "success"   # proven
for ok in {True}, f(ok) == "failure"   # falsified
```

Each *distinct* non-numeric value (`str`, `None`, an `Enum` member,
not `bool`, already numeric elsewhere in this codebase) is registered
into a small, per-lift registry (`mathema/finite_sets.py`) as an
opaque `sympy.Dummy`, the same string appearing twice, whether in the
function body or in a claim's own law text, always resolves to the
identical symbol, which is what makes `==`/`!=` provable at all: two
occurrences of the same value simplify identically (`sym - sym == 0`);
two *different* known values are recognized as unequal too, via
sympy's own `.equals()` fallback, already used for the ordinary
numeric case, and it turns out to already generalize correctly here,
no dedicated inequality machinery needed. `None`-returning branches
work the same way; `f(x) == None` is an ordinary claim, not special
syntax.

**Ordering (`<=`/`>=`) is always refused**, deliberately, even in the
degenerate case where both sides happen to be the *same* value (which
would otherwise "prove" via bare reflexivity; `x <= x` is trivially
true, but claiming an order exists for a string was never a meaningful
thing to do in the first place, proven or not).

Wired into every route above (base `lift()`, `lift_fold()`, `lift_dot()`,
`lift_sum()`) and their own claim grammars, a fold's transformed
return, a dot product, or a general-sum result can resolve to a
non-numeric value just as well as the base route can.

**Deliberately not built**: a genuine *set-algebra* facility, union,
intersection, membership, or reasoning about an actual Python
`set`/`frozenset`/tuple *value* flowing through code, as opposed to a
scalar that merely *ranges over* a small number of distinct values
(what's built here). A constant *tuple* specifically is not registered
as a single opaque value, even though the underlying registry could
support it (`finite_sets.is_opaque_eligible()` already recognizes a
tuple of eligible elements); wiring it in would collide with two
already-established, tested meanings a source-level tuple literal has
elsewhere: a multi-return-value shape (`return a, b`) in a function
body, and elementwise comparison against a tuple-returning function in
claim-law text (`f(x) == (a, b)`). Neither conflict has a clean
resolution without a real motivating example to design against, so
this stays deferred rather than guessed at.

## Local symbolic arrays: `np.linspace`/`np.arange`

A common plotting/geometry shape has no explicit Python loop at all,
numpy vectorization stands in for it:

```python
def ellipse_path(cx, cy, a, b, n):
    phi = np.linspace(0.0, 2.0 * np.pi, n)
    x = cx + a * np.cos(phi)
    y = cy + b * np.sin(phi)
    return x, y
```

`np.linspace(start, stop, num)`/`np.arange(start, stop[, step])` each
build an array whose i-th element has a known closed form (`start +
i*step`), not an elementwise numeric function (there's no scalar
input to map over), so it's recognized on its own rather than added to
the `_SYMPY_FUNCS` table. Every already-mapped elementwise operation
applied to that array afterward (`np.cos`, `+`, `*`, ...) is just the
same operation applied to the closed form, propagated through
explicit checks in `_expr_to_sympy`'s own arithmetic/call handling,
never through Python's operator-dunder fallback, since this codebase
has already hit one real, surprising sympy-internal-arithmetic bug
(the `lift_sum()` `StopIteration` above) and isn't about to trust
another one implicitly. Since none of this involves an explicit loop,
`ellipse_path` never trips `lift()`'s existing loop/branch/sequence-
parameter gate; this is an extension of the base `lift()` path
itself, not a new `lift_XXX()` sibling.

`f(...)[i]`; the same subscript syntax "Tuple returns" already uses,
indexes into an array-valued result: a literal int for a boundary
claim, or a bare name for a claim over the whole array (bound as a
fresh variable, the same pattern `lim(...)`'s own bound variable
already uses). No new claim-grammar syntax, no domain declaration
needed for the index (the count `n` still needs one, since
`np.linspace` raises for a negative or non-integer count); the closed form is a single uniform formula,
never piecewise per position, so it holds for any real index, not just
an integer one:

```
for n in [2, 50] ⊂ Z, f(cx, cy, a, b, n)[0][i] == cx + a*cos(2*pi*i/(n-1))   # proven
for n in [2, 50] ⊂ Z, f(cx, cy, a, b, n)[0][0] == cx + a                     # proven (boundary)
```

Declines rather than guessing on: two independently built arrays
combined (`np.linspace(...) + np.linspace(...)`, two separate calls,
never assumed aligned just because they happen to share a length); a
reduction over a local array (`np.sum`/`np.dot`, as opposed to
returning it elementwise; that's `lift_sum()`/`lift_dot()`'s own
territory, and only for a *parameter*, not a local); indexing an array
by anything other than the claim's own `[i]` subscript (in the
function body itself, or by anything other than a literal int or a
bare name in claim text); and a claim that references an array-valued
`f(...)` without ever indexing it at all.

A *sequence parameter* is a different, still-unbuilt gap, see "What's
not built at all" below.

## Calculus, PDEs, and SDEs

`d(...)`/`lim(...)`/`integrate(...)` turn an already-liftable body into
calculus/PDE/SDE claims, see [Authoring claims](authoring.md) for the
grammar. A sample of what's actually proven, run against real function
bodies:

| Function | Claim | Verdict |
|---|---|---|
| `cube(x) = x**3` | `d(f(x), x) >= 0` | `proven`; x³ is monotone increasing |
| `heat_sol(t, x) = x**2 + 2*t` | `d(f(t,x),t) == d(f(t,x),x,x)` | `proven`, genuinely solves the heat equation |
| `not_heat_sol(t, x) = x**2 + 3*t` | `d(f(t,x),t) == d(f(t,x),x,x)` | `unknown`: derive shows it doesn't (`3 ≠ 2`), but a derivative claim has no executed witness, and a falsification needs one |
| `sinx(x) = sin(x)` | `lim(f(x)/x,x,0) == lim(d(f(x),x)/d(x,x),x,0)` | `proven`, L'Hôpital's rule as a consistency check |
| `dot2d` (2D dot product) | `f(...)**2 <= (ax**2+ay**2)*(bx**2+by**2)` | `proven`, Cauchy-Schwarz, squared form |
| `dot2d` | `abs(f(...)) <= sqrt(ax**2+ay**2)*sqrt(bx**2+by**2)` | `proven` (`derive:extensive`), same claim, direct sqrt/Abs form, squared back to the form above |
| `gram_schmidt_2d` | `for v1x in [1,2], v1y in [1,2], f(...) == 0` | `proven`, Gram-Schmidt orthogonality |
| `gauss_pdf` | `for sigma in [1e-6,1e6], integrate(f(x,mu,sigma),x,-oo,oo) == 1` | `proven`, normalizes to 1 |
| `projectile_range(v0,theta,g)` | `for g in [9,10], d(f(v0,theta,g),theta)@{theta=pi/4} == 0` | `proven`; range is maximized at 45° |

`d(...)` accepts an evaluation marker, `@{v=val, ...}` (or the word
`at`), for a claim at one specific point rather than across a whole
domain (`d(<expr>, <vars...>)@{v=val, ...}`), plus shorter spellings
for a single-parameter derivative (`d(<expr>)`, prime notation
`f'(x)`, and the fraction form `d(<expr>/d<var>)`); `integrate(...)`
accepts a LaTeX-style evaluation-bar shorthand for its own bounds
(`integrate(<expr>, <var>)|_{a}^{b}`, `∫`/`integral` synonyms, and a
bracket-free multivariable form), see [Authoring
claims](authoring.md)'s own grammar section.

Two rows above are worth reading together: the squared Cauchy-Schwarz
form proves directly, and the `abs`/`sqrt` form of the *same
mathematical fact* proves only because both sides are shown
nonnegative on the domain first, which is what makes squaring them
sound. The sketch states that step, and the route says `extensive`.
Two rows need a domain: `gram_schmidt_2d` divides by the squared norm
of `v1`, and `projectile_range` divides by `g`. Unbounded, each claim
is `falsified`: `projectile_range` reaches the division by zero at
`g = 0`, and a raise is not a value, while `gram_schmidt_2d` returns
`0.00011723145853181904` instead of `0` at `v1x = -1e6, v2x = 1e6`,
where floating-point cancellation leaves a residue the exact formula
does not have.

## Multi-function claims

A claim can relate several functions, and the derive route lifts each
of them: every bound function gets its own closed form, and the law's
calls to it substitute positionally exactly like `f(...)` does,
nested inside `f`'s own arguments included, so the Cobb-Douglas
first-order condition can be written the natural way, utility and
budget as two separate functions:

```python
def cobb_douglas_utility(x, y, a):
    return x ** a * y ** (1 - a)

def budget_line(x, I, px, py):
    return (I - px * x) / py

# proves: utility along the budget line is stationary at x* = a*I/px
"let I be [10,1000], let px be [0.5,20], let py be [0.5,20], "
"for a in [0.1,0.9], d(f(x, budget_line(x,I,px,py), a), x) @ {x = a*I/px} == 0"
```

There are three ways to bind a name, and the shortest one is usually
enough:

1. **Nothing at all.** A bare call name (`budget_line(...)` above)
   binds automatically, first from `f`'s own module, then from the
   calling scope's local variables (a notebook cell's helper, a test
   function's nested def). Every automatic binding is named in the
   result's note (`bound budget_line = functions.budget_line (f's
   module)`), so nothing resolves silently.
2. **`let g = pkg.mod.func`** in the claim text, a dotted reference,
   resolved like a spec key. (`let g = budget_line` with a bare name
   also works: the alias substitutes through and the name then binds
   as in 1.)
3. **`funcs={"g": budget_line}`** on `claim()`, the explicit binding,
   which always wins over scope resolution, and the only form that
   accepts an arbitrary callable.

A bound function that doesn't lift makes the derive route report
`underivable` with the blocking function named ("bound function g
(loopy) is not derivable, likely reason: ..."), never a silent skip,
and the probe route then adjudicates the claim; `raises(...)` claims still require a
bare `f(...)` call. On the probe route the same bindings are simply
called. Only a plain Python function ever binds automatically, a
class or other callable needs the explicit `funcs=` form.

## Recurrences

A self-recursive function isn't a loop at all; closing it means
solving the actual recurrence relation, and that is what the
recurrence lifter does. The recognized shape: one scalar parameter,
optional leading raise guards, base cases comparing the parameter
against integer literals, and one final return combining self-calls at
fixed positive integer shifts:

```python
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
```

`rsolve` closes the recurrence from the base cases read out of the
body, so `for n in [2, 30] subset Z, f(n) == f(n-1) + f(n-2)` proves
(mechanism meta `recurrence:rsolve`), as do `2^n` doubling, the
triangular accumulator's `n*(n+1)/2`, and factorial's `n * f(n-1)`
(polynomial coefficients are fine). The returned closed form is a
candidate, never an authority: it's verified against the recurrence
itself and every base value before anything adjudicates with it, and a
nonlinear recurrence declines cleanly.

Three gates keep the closed form honest about the implementation:

- **Integers only.** The closed form describes the integer lattice;
  the runtime recursion on a non-integer argument walks a different
  lattice entirely. The claim's domain must be an integer subset
  (`subset Z`), and every call argument must be provably
  integer-valued; anything else is undecided, with the `subset Z`
  remedy named.
- **Stack depth.** The closed form settles the mathematics, but the
  implementation still recurses about one frame per index step, so a
  domain whose top implies a depth beyond the interpreter's recursion
  limit refuses to prove, `fib(100000)` raises `RecursionError`
  however true Binet is. The claim is then run once at the top of
  the domain, and the RecursionError it raises there is the executed
  witness of a falsification (a raise inside a value claim's domain).
  The domain is never swept point by point past the limit. The
  sketch names the safe bound, the iterative rewrite, and the
  `raises(...)` claim as ways out.
- **Non-termination is a raise region.** Isolated base points
  (`if n == 0: ... if n == 1: ...`) leave the recursion descending
  forever below them; that region is treated exactly like an explicit
  raise guard, so a value claim quantifying over it is falsified with
  a witness.

Not handled yet: multiple parameters, mutual recursion (A calls B
calls A), accumulator-parameter styles, and memoized wrappers.

## Certificates: how a proof justifies itself

A `proven` verdict's `sketch` names the mechanism that closed it, and
several of those mechanisms are certificates: sound rules whose side
conditions are each verified, never a "probably".

- **Interval evaluation.** The expression's hull over the declared
  box already settles the relation (`2*r ∈ [0, 2], never negative`).
  The cheapest certificate, and the first one tried.
- **Positivity certificates.** For a strict inequality the hull often
  straddles zero even when the claim is true. The strict certificate
  proves `expr > 0` outright for specific shapes: a sum of
  nonnegative terms with one bounded away from zero (the resonance
  denominator `(k - m*w^2)^2 + (c*w)^2` with `c` nonzero), a product
  of strictly positive factors, a one-variable quadratic with
  positive leading coefficient and negative discriminant. Its
  non-strict sibling covers `>=` the same way.
- **The write-free certificate.** `is_state_safe(f)` is proven
  structurally when the body contains no external-write site and
  every name resolves; an unresolved or global read leaves room for
  state the walk cannot see, so it falls to trials instead. The
  sketch says which of the two happened.
- **Piecewise proof.** A claim over a finite value set is proven by
  splitting the domain into its stated values and proving each piece;
  the sketch lists the pieces.

The certificate text in the sketch is the reader's audit trail: a
`proven` never rests on an unnamed mechanism, and anything a
certificate cannot close falls through to the empirical route rather
than being asserted.

## What's not built at all

**Lifting a function body over a matrix or vector parameter**, and
everything downstream of that (general time-series recurrences, most
of linear algebra inside a body). Matrices themselves are partly
supported: structure predicates and linear-algebra identities prove,
and probing samples matrices by shape and structure, see
[Matrix structure](matrix-structure.md).
The dot-product/general-sum machinery above is
narrow by design, not a first step toward this, and neither is "Local
symbolic arrays" below: a function whose *parameter* is a sequence and
whose *return* is derived from it elementwise (`normalize_by_max(xs):
m = max(xs); return [x / m for x in xs]`) still has nowhere to go,
`lift()` refuses any non-scalar parameter outright, unaffected by
either. Only a *locally built* array (from `np.linspace`/`np.arange`,
never a parameter) is handled.

**Multiple accumulators updated within the same loop body** (a
classic single-pass optimization, computing a sum and a sum-of-squares
together in one pass, say) and **an extra local statement inside a
loop body before the accumulator update**, `lift_sum()` requires
exactly one statement per loop body, so both stay refused even though
sequential *multiple* loops and an intermediate scalar *between* loops
are both fine (see "General sum accumulation" above).
