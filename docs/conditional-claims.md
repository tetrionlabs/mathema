# Conditional claims and lemmas

A claim is unconditional by default: `for x in [0, 1], f(x) >= 0`
quantifies over its whole declared region. An `assuming` clause makes
the claim conditional, and mathema gives the premise real semantics on
both routes: the region narrows, the evidence chain records what the
conclusion rests on, and a premise that cannot be established caps or
blocks the conclusion rather than being quietly ignored.

The clause leads the claim, before any quantifier:

```
assuming x > 0, for x in [-10, 10], f(x) > 0
```

## Relation premises

The simplest premise is a relation over the claim's own variables, or
several joined with `and`:

```
assuming b^2 - 4*a*c >= 0.01, f(a, b, c) <= f(a, -b, c)
assuming k != 0 and j > 0, for x in [1, 5], f(x, k, j) * k * j == x
```

A relation premise narrows the region actually adjudicated. On the
derive route the constraint reaches the prover as an assumption; on
the probe route sampling stays inside the assumed region. The rendered
record states the narrowed region explicitly, so a conditional claim
and its unconditional twin can never read alike, and never share an
identity.

A premise relating two parameters (`a <= b`) is handled by the
assumed-gap machinery rather than by interval narrowing, because that
region is not a box.

## `is_defined` as a claim: restriction or totality

Besides the premise below, `is_defined` is a claim in its own right,
and it carries two readings, told apart by whether the claim states a
region:

```yaml
- name: is_defined          # RESTRICTION: f returns on exactly this region
  statement: "x >= 0"
```

```
is_defined(f)               # TOTALITY: f returns everywhere, it never raises
f is defined                # the same claim, postfix spelling
```

One predicate, because the English reads correctly either way: "f is
defined on `x >= 0`" states a restriction, "f is defined" states that
there is none. A restriction claim proves when the stated region
matches the region mathema computes from the body's raise guards, and
falsifies when it differs (naming the fresh region) or when the
function is in fact total. The bare form proves when the body has no
raise region at all, and falsifies when it has one, naming the region
`f` actually returns on. mathema suggests the restriction form for a
partial function and never for a total one.

When there is no body to compute a region from (a builtin, a numpy
ufunc), or the comparison does not decide (a library function whose
region reads `det(a)` or `dim(a)`), the claim is adjudicated by
execution: every sampled point inside the region must return a value
and every point outside it must not, where a raise, a nan and an
infinity for a finite input are all no value. Where the computation
leaves float range is not a definedness fact but a computation one,
stated by an `is_overflow_safe` row (see
[claims transfer](claims-transfer.md#row-kinds-by-stratum)), and a
library function's bare `is_defined` is adjudicated inside that
region. A region over `det(a)`
draws square matrices, singular ones on its boundary; one over
`dim(a)` draws sequences, the empty one below it. An indexed row
(`is_defined[2]`, one conjunct of a region with several) only asks
for no value outside it, since inside it the other conjuncts decide.
The verdict is `holds` at best, and the note says how many points were
executed on each side.

## The definedness premise

```
assuming is_defined(f), abs(f(x, y)) <= 1
assuming f is defined, abs(f(x, y)) <= 1
```

Both spellings mean the same thing: the claim quantifies over exactly
the region where every call to `f` returns. mathema computes that
region from the function's own raise guards and from registered
partiality lemmas (below), then states it in the record behind an
arrow:

```
assuming f is defined --> b != 0, b*f(a, b) = a
```

The region after `-->` is the resolved fact the claim was adjudicated
under. On a later run the pin is validated, never trusted: while the
code still agrees, the pin is kept byte-for-byte, so the record is
stable; when the code has moved out from under it, the region is
recomputed and the note says so, naming both. A function with no raise
region at all keeps the premise arrow-free (`assuming f is defined`),
because there is nothing to state.

## Dimension premises

A premise may relate the shapes of a function's arguments, not just
their values. `dim(x, axis)` is the canonical spelling for a
dimension; `len(x)`, `rows(A)` and `cols(A)` are sugar for
`dim(x, 0)`, `dim(A, 0)` and `dim(A, 1)`.

```
assuming len(x) == len(y), f(x, y) == f(y, x)
assuming dim(x, 0) >= 3, f(x) >= x[2]
```

On the probe route a dimension premise is drawn to hold **by
construction**: an equality between two dimensions shares one drawn
size across them, and a bound against a constant constrains the draw,
so a claim about a function that legitimately requires equal lengths
no longer falsifies on synthesised mismatches. The four spellings
share one identity, so a record is stable however the premise was
written.

### Matrices, and named dimensions

The mechanism is axis-general. A parameter carrying a `Shape` marker
(`types.Shape("m", "n")`) has as many axes as the marker names, and
`dim(A, 1)` reads the second one:

```python
def matvec(a: Annotated[list, Shape("m", "n")],
           x: Annotated[list, Shape("n")]) -> Annotated[list, Shape("m")]:
    ...
```

```
assuming n >= 2, dim(f(a, x), 0) == dim(a, 0)
```

Two things follow from the marker. First, a marked matrix parameter
is synthesised as a nested list of the right shape, so ordinary claims
run against matrix functions (an unmarked nested-list parameter stays
a plain one-dimensional sequence, mathema never invents a second axis
it was not told about). Second, a marker dimension name is a
first-class symbol in a premise or law: a premise may bound it
(`assuming n >= 2, ...`), a law may relate it (`dim(a, 1) == n`), and
a name shared between two parameters (`Shape("m", "n")` and
`Shape("n")` both naming `n`) is drawn once, so the arguments are
conformable every trial. `len`, `rows` and `cols` remain sugar for
`dim` on axes 0, 0 and 1.

A parameter's domain can also state the SPACE directly, rather than
its element domain: `for v in R^n` is a real vector of length `n`,
`for xs in [0, 1]^n` a vector with elements in `[0, 1]`, and
`for A in R^(m,n)` an `m`-by-`n` matrix (rows, then columns, the
order of a numpy shape). The element domain is the base and the
dimensions the exponent; in unicode the exponent renders as a
superscript (`ℝⁿ`, `ℝᵐˣⁿ`, `ℝ²ˣ³`), the missing-value clause trailing
the whole space. A dimension whose name the superscripts cannot carry
(one containing an `x`, which would read as the `ˣ` separator, or a
letter with no superscript form such as `q`) renders as the plain
exponent instead (`ℝ^(x,n)`). The matrix space is also accepted as
`R^{m,n}`, `R^(m×n)`, `R^{m×n}`, `R^(m*n)`, `ℝᵐˣⁿ` and, for a fixed
size, `ℝ³ˣ³` or `ℝ^{3×3}`; every one of these is the same claim and
is written back as `R^(m,n)`. A dimension NAME is the constraint: `R^n` on two
parameters draws them to one length every trial, so a claim about a
function that requires equal-length inputs holds without a separate
premise. `len`/`rows`/`cols` remain the axis-0/0/1 sugar for reading a
dimension back.

To enforce a dimension premise at RUNTIME, the shape analogue of
`@enforce_domain` is `@enforce_dimensions`:

<!-- example: enforce-dimensions run inline -->
```python
from mathema import claims_decorator, enforce_dimensions

@enforce_dimensions()
@claims_decorator("assuming len(x) == len(y), f(x, y) == f(y, x)")
def dot(x, y):
    return sum(a * b for a, b in zip(x, y))

dot([1, 2], [3])   # ValueError: dot: dim(x, 0)=2 violates the declared premise dim(x, 0) == dim(y, 0)=1
```

`@enforce_domain` guards a parameter's VALUE domain; `@enforce_
dimensions` guards the relations between argument SHAPES. Neither
makes a claim true by fiat: each makes the function reject inputs the
claim was never about, so a premise and its runtime guard are one
precondition stated once.

Beyond shape, a matrix parameter can declare its STRUCTURE (symmetric,
positive definite, and so on) and state linear-algebra identities over
it. See [Matrix structure and linear algebra](matrix-structure.md).

## Prerequisite claims

A claim may rest on a sibling claim from the same batch or file:

```
assuming positive holds, for x in [0, 10], f(2*x) >= f(x)
assuming real_roots is proven, f(a, b, c) <= f(a, -b, c)
```

The referenced claim must reach the named verdict first. mathema
orders the batch by dependency (a forward reference works), reports a
cycle as a skip naming both claims, and enforces the evidence ladder:
a prerequisite that only `holds` empirically caps the resting claim at
`holds` too, with `meta["mathema.capped_by"]` naming the premise. A
proof cannot stand on sampling.

A bare sibling name (`assuming real_roots, ...`) borrows that claim's
relation as a region constraint instead of consulting its verdict.

## Partiality lemmas

The definedness machinery reads raise guards from the function's own
body, and, for functions it calls, from registered lemmas:

```python
import sympy
import mathema.partiality

def stable_kernel(u, tol):
    ...   # raises for u <= tol

mathema.partiality.register_raises_when(
    stable_kernel, lambda u, tol: sympy.Le(u, tol), "ValueError")
```

A claim about any function that calls `stable_kernel` then treats
`u <= tol` exactly like an explicit raise guard: a value claim
quantifying over that region is falsified with a witness, and a
definedness premise excludes it. The `math` module's own partiality
(`sqrt`, `log`, `asin`, ...) ships registered out of the box.

## The compendium

The registration generalises to claims files about libraries: a file
that declares `compendium: numpy` (and a `versions:` range) holds
claims whose keys are the library's functions, and mathema bundles such
files for `math` and `numpy`. A project states its own in any claims
file (`claims/numpy.claims.yaml`), shadowing the bundled entry per
function. An `is_defined` row there states the region where the
function returns a value, so a caller's claim is read against it the
way it is read against an explicit raise guard, and a compendium claim
may be named as a premise, by bare name or by its qualified spelling
(`assuming numpy.clip.clip_lower holds`). The bundled files apply to
every `check`, the Python API included, with nothing to install; a
project's own compendium files apply wherever mathema reads the
project. Outside an `is_defined` region the call has no value: a
raise, a nan, and an infinity returned for a finite input all count
the same, and each falsifies a value claim that reaches it.

A compendium verdict never enters the evidence chain silently: `mathema
verify` adjudicates the library rows your project calls or rests on by
executing them against the installed library, and the premise resolves
at the verdict recorded there. Those rows gate the run like the
project's own claims. A row verify cannot settle fails it and leaves
the resting claim `unknown`, both naming `mathema accept <key> <claim>
--as trusted`, which takes the row at the level it claims (the
conclusion caps there, provenance named). A file whose `versions`
range does not match the installed library contributes nothing. The
wider story, including transfer between implementations, is
[Claims transfer](claims-transfer.md).

## What the record carries

The premise is part of the claim's canonical text, so it survives
every store round trip and participates in the claim's identity: a
conditional claim is never superseded by its unconditional twin. The
resolved definedness region is recorded for the reader but stripped
from the identity, because it is recomputed evidence, not something
the author asserted.
