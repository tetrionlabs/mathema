# Claims transfer

Evidence is earned about one implementation. This page is about the
three ways it travels: **in**, from curated knowledge about libraries
your code calls; **across**, between implementations shown equivalent,
in another language included; and **out**, publishing your own verified
claims as a compendium others consume.

## In: the compendium

A compendium is an ordinary claims file whose keys are a library's
functions rather than your own, with two file-level fields beside the
optional `grammar`: `compendium`, naming the library, and `versions`,
the range of its installed versions the claims apply to (`"*"`,
`">=X"` or `">=X,<Y"`, and the standard library always counts as
`"*"`):

```yaml
compendium: numpy
versions: ">=1.24,<3"

numpy.sqrt:
  claims:
    - name: is_defined
      statement: "x >= 0"
      note: "Principal square root; a negative input returns nan with a RuntimeWarning, never raises."

numpy.clip:
  claims:
    - name: clip_lower
      statement: "assuming a_min <= a_max, for a in [-1e6, 1e6], a_min <= f(a, a_min, a_max)"
```

A third, optional file-level field, `aliases`, lists other names the
library goes by. The installed version is looked up under the library
name and then under each alias, so a file about an import name whose
distribution is called something else still applies:

```yaml
compendium: yaml
aliases: [PyYAML]
versions: ">=6"
```

An alias is also a key prefix: a key written under one (`np.cbrt` in a
file with `compendium: numpy` and `aliases: [np]`) is the library's key
(`numpy.cbrt`), and two keys naming the same function that way are
refused.

A row can also carry its own `versions:` range, overriding the file's
for that row alone. A row whose range excludes the installed version is
never used as a fact, and is still adjudicated when the project calls
the function, so [`mathema compendium update`](modes/compendium.md#update-rows-for-the-calls-the-project-makes)
can widen its range once it holds on the installed version.

The parameter names are the library's own (`inspect.signature`, so
numpy's `clip` takes `a`, `a_min` and `a_max`), and every row is a
claim like any other, with a `note:` on the row where the library's
behaviour needs saying in prose. A library function's intent is its
own, read from its docstring like any function's, so a compendium file
states none. mathema bundles such files for `math`, `numpy`
(numpy's 41 covered functions split into scalars, reductions, bounds
and definitions), `pandas` and `polars.Series` (their
[definition rows](#definition-rows)), and a project states its own
anywhere its claims files
already live, `claims/numpy.claims.yaml` for instance, where a key
shadows the bundled entry for that function. A file applies only when
the library is importable at a version inside its range; otherwise it
contributes nothing, which is better than contributing stale facts. A
file whose `compendium:` names your project's own package is ignored:
those are your own claims, stated in your ordinary claims files, and
`mathema verify` prints a note naming the file.

The bundled compendium applies to every `check`, from the command line
or the Python API alike, without being asked: it is part of what
mathema knows, the way `math.sqrt` raising below zero is. Your
project's own compendium files apply wherever mathema reads the
project (`mathema check`, `mathema verify`, `write_spec`).

A row about a library function passes the parameters it does not
bind at the library's own defaults, rather than sampling them:
`for a in R^n, min(a) <= f(a) <= max(a)` on `numpy.mean` samples `a`
and leaves `axis`, `dtype`, `out`, `keepdims` and `where` as numpy
defines them. The record says so: each row carries the values it
passed in `mathema.defaults`, keyed by the function they were passed
to, since one claim can call several library functions (`{numpy.mean:
{axis: None, keepdims: <no value>, ...}}`, and a `let g = numpy.sqrt`
binding the claim calls adds `numpy.sqrt`'s own), and its note lists
them as `held at their defaults: axis=None, ...`. A different value is
a pin, `let axis be 0` (see [the grammar](grammar.md)), shown as `0
(pinned)`. `mathema verify` compares those values with the
installed library on every sweep, so a release inside the declared
`versions` range that changes a default of any function the row
calls marks the row stale and it is
adjudicated again, and a pin naming a parameter the library no longer
has makes the row misspecified. Your own functions are not affected:
their defaulted parameters are sampled like any other.

### Row kinds, by stratum

A compendium row belongs to one of the two strata
[the guarantees](guarantees.md#mathematics-and-computation) separate,
and the stratum decides what mathema does with it.

**Mathematics.** An `is_defined` row with a stated region reads as
"has a value on exactly this region", so `numpy.sqrt`'s `x >= 0` says
that outside it the call has no value, whether the library raises there
(`math.sqrt`) or returns nan (`numpy.sqrt`); the bare `is_defined(f)`
says the function is total. Such a row is a fact about the function
as a mathematical object: it enters the derive route as a guard, so a
caller's claim over a region that reaches the no-value region is
falsified with an executed witness, exactly as it would be over an
explicit raise. A `raises(f(x), Exc)` row with an ordinary type
(`ValueError`) is mathematics too, added only where the exception type
itself matters.

A region stated with an ordering (`x >= 0`, `-1 <= x <= 1`) is a
statement over real inputs, since the complex numbers have no order:
at a call whose argument is complex (a parameter the claim binds in
`C`, a `complex` annotation, or an expression the derive route knows is
complex) it does not apply. Where a library computes a function over
the complex plane, its row for complex input is a bare `is_defined(f)`
over `C`, less the points where it has no value there, and those
points are a guard at complex arguments only:

```yaml
numpy.log:
  claims:
    - name: is_defined
      statement: "x > 0"
    - name: is_defined_over_complex
      statement: "for x in C \\ {0}, is_defined(f)"
```

numpy's square root, inverse sine, inverse cosine and inverse
hyperbolic cosine are defined on the whole plane; its logarithms have
no value at 0, `log1p` at -1 and `arctanh` at 1 and -1.

**Computation.** A computation-safety family in restriction form
states the region where one implementation is safe in that respect:
`is_overflow_safe: x <= 709.782712893384` on `numpy.exp` says numpy's
exponential on float64 stays inside float range exactly there (an
infinity past it). A `raises` row whose type is a machine failure
(`OverflowError`, `MemoryError`, `RecursionError`,
`FloatingPointError`) is computation as well. These rows never enter a
proof: `exp(x) >= 0` on a numpy caller is proven over the reals
whatever the threshold, and the overflow shows on the computation side
(the `[float]` companion, the probe route). They feed the hazard
points, `is_compendium_safe`'s diagnosis, the reach of the key's own
`is_defined` row and the companion's sketch.

`numpy.exp` carries one row of each kind:

```yaml
numpy.exp:
  claims:
    - name: is_defined
      statement: "is_defined(f)"
    - name: is_overflow_safe
      statement: "x <= 709.782712893384"
      note: "Exponential; overflows to inf above roughly x = 709.78, with a RuntimeWarning."
```

Consumption paths:

- Definedness and overflow-safe regions become sampling hazards: their
  boundary values join the probe candidates for every caller, whether
  it spells the call `numpy.sqrt(x)` or `np.sqrt(x)`.
- `is_compendium_safe(numpy)` asserts a function never silently emits
  a non-finite value (nan/inf) through an unguarded call into a covered
  library function; the probe samples the hazard boundaries and the
  empty-sequence case, and falsifies on a nan/inf output. When the
  covered call states a computation region, the counterexample names
  it: `the covered call numpy.exp is overflow-safe only for x <=
  709.782712893384, and x = 1000 lies outside it`.
- A `[float]` companion falsified by a call into a covered function
  names the same region in its sketch.
- A library key's own bare `is_defined` row is adjudicated inside its
  `is_overflow_safe` region (the function is total; where it overflows
  is the other row's fact), and inside the number representation's range otherwise.
  The same rule holds for every function checked by execution, your own
  included: an `is_overflow_safe` claim in its claims file keeps the
  `is_defined` sampling inside that region, and without one an overflow
  at the reach is no value, with a note pointing at `is_overflow_safe`.
- Claims may be named as premises: `assuming clip_lower holds`, or
  qualified, `assuming numpy.clip.clip_lower holds`.

A compendium row is testimony, and it never enters the evidence chain
silently. `mathema verify` adjudicates the rows of every library
function your project calls or rests a premise on by executing them
against the library you have installed, records the local verdict with
the row's provenance (`compendium:numpy-2.5`), and a premise then
resolves at that verdict; a project that never calls numpy verifies
none of its rows. That default is lazy: only the library functions the
project uses are adjudicated. To adjudicate a whole file up front,
name it:

```bash
mathema verify claims/numpy.claims.yaml
mathema verify mathema/compendium/numpy/scalars.claims.yaml
```

The second names a bundled file by the path records give it. Every
entry in the named file is adjudicated and recorded, whether or not
your code calls it; a file whose library is not importable, or is
installed outside the file's `versions`, says so on one line (see
[`mathema verify`](modes/verify.md#library-claims-lazy-by-default-a-file-up-front)). Library rows gate the run exactly like your own
claims: a row verify cannot settle here fails it, with a line naming
both ways to settle it, and the resting claim stays `unknown` with the
same two paths in its note. One is a fresh local verdict; the other is:

```bash
mathema accept numpy.clip clip_lower --as trusted
```

takes the row at the level it claims (the row's `meta:
{mathema.compendium_claimed: proven}`, `holds` when it states none),
and every conclusion resting on it caps there, with the provenance
(`compendium:numpy-2.5/clip_lower`) named in the record. Accepting is
a statement of trust. A later verify replaces it only with a local
verdict that contradicts it (`falsified`) or is at least as strong (a
`proven` replaces a trusted `proven` or `holds`, a `holds` a trusted
`holds`). A weaker local verdict that agrees leaves the trust standing
at its level, and the row says what was seen: `trusted as: proven,
strongest evidence seen: holds`.

### Definition rows

A **definition row** is a row named `definition` that states what a
library function computes, in the grammar's own words, over inputs
with nothing missing:

```yaml
compendium: pandas
versions: ">=2,<4"

pandas.Series.std:
  claims:
    - name: definition
      statement: "for a in R^n \\ {∅}, assuming dim(a) >= 2, f(a) ~= std(a, ddof=1)"
    - name: definition@ddof=0
      statement: "let ddof be 0, for a in R^n \\ {∅}, f(a) ~= std(a, ddof=0)"
```

A method's key names its class (`pandas.Series.std`,
`numpy.ndarray.T`), and its receiver is the row's first parameter `a`,
sampled as that class; the method's other parameters keep their names
and defaults. A row for a call that pins a parameter away from its
default is named `definition@<parameter>=<value>` and pins it with
`let`, so `np.std(x, ddof=1)` reads through `numpy.std`'s
`definition@ddof=1`. Each row is an ordinary claim: `mathema verify`
executes it against the installed library, so a wrong row
(`std(a, ddof=0)` for pandas) is falsified like any other claim.

The bundled pandas rows cover, for `pandas.Series`: `mean`, `std`,
`var`, `sum`, `prod`, `cumsum`, `cumprod` and `count`; the running
extrema `cummax` and `cummin`; `min`, `max` and `abs`; `median` and
`quantile` (at `q` 0.5, 0.25 and 0.75); the arithmetic methods `add`,
`sub`, `mul`, `div`, `truediv` and `pow`, with a number or a Series of
the same length; `size`; and `shift`, `diff` and `pct_change`, which
leave their first positions missing and so are stated over the
positions that carry a value (`f(a)[1:] == a[:-1]`). For
`pandas.DataFrame` they cover `sum` and `mean` per column; a column
read (`df.w`, `df["w"]`) is grammar, and a Series method called on a
column reads through the Series rows. A bundled compendium ships its
rows, not verified records: mathema's own test suite verifies every
row against the installed library, and a project's run takes each row
at the evidence that run gives it.

How the library treats a missing value is a separate matter from what
it computes, and the rows leave it out. As installed today: numpy
propagates a missing element (nan) to the result; pandas skips nan,
None and `pd.NA` in its reductions and keeps a missing position
missing in `cumsum` and `cumprod`; polars skips a null but carries a
NaN through as a float (a Series holding NaN has mean NaN, and `count`
counts it).

The derive route reads a function's library calls through these rows
(see [runtime types](runtime-types.md#proofs-on-pandas-and-numpy-code)),
so a row is part of a proof, and which rows may be used depends on
where they come from:

- a row **bundled with mathema** is used at once: mathema's own test
  suite verifies every bundled row against the libraries it installs;
- a row from **your project's claims files**, or from a third party,
  is used only once `mathema verify` has recorded it `holds` or
  `proven` in this project, or it was accepted with `mathema accept
  <key> definition --as trusted`; until then it guides sampling only,
  and a claim resting on it stays `holds`, its note naming the row and
  the two ways to settle it;
- a row `mathema verify` recorded `falsified` is never used, bundled
  or not.

A proof through definition rows stays `proven`. Its record lists each
row it read through in `meta["mathema.definitions"]`: the key, the
row, its statement, the file it came from, its status here (`bundled`,
`holds`, `proven` or `trusted`) and the library version. The function's
record also stamps the rows its body could read through
(`mathema.definition_rows`), so a row verified, falsified, re-stated or
moved out of its library's `versions` since makes the record stale, and
`mathema verify` adjudicates it again.

### Guarding a numpy hazard, and superseding the finding

`is_compendium_safe(numpy)` catches a silent nan/inf leaking through a
covered numpy call. On an unguarded body it FALSIFIES, with the input
that produced the non-finite value:

```
def to_angle(x):
    return numpy.arcsin(x)          # nan for abs(x) > 1

is_compendium_safe(numpy)   ->   falsified   (-8.76733): output np.float64(nan) is a silent non-finite value from an unguarded numpy call
```

Two fixes make it hold, and each supersedes the falsification once
re-verified:

- a **bound** that excludes the nan region as a claim domain,
  `for x in [-1, 1], is_compendium_safe(numpy)`, so the sampler never
  leaves the safe region;
- a **guard** that rejects it in the body, `if abs(x) > 1: raise
  ValueError`, so the covered call is never reached out of range.

Re-running `mathema verify` after the fix records `holds`, and the new
verdict supersedes the earlier falsification, which the record keeps
as `mathema.previous_verdict: "falsified"` in the claim's meta (one
step back; the full history is in git, through `mathema review` and
`git log .mathema/verified`). The falsification was never wrong: it was true of the unguarded code, and remains the reason
the guard exists.

## Out: exporting your own verified claims

A library author who has run `mathema verify` on their own package can
publish that evidence as a compendium others consume
([`mathema compendium`](modes/compendium.md)):

```bash
mathema compendium export mylib
```

reads the verified store, keeps the proven and held rows of `mylib`'s
functions (the built-in battery and the other rows mathema generates
for every function stay behind), and writes them as a claims file in
the shape above, `compendium: mylib` and `versions: ">=<installed
major.minor>"`, by default to `claims/mylib.claims.yaml` under the
project root (`--out PATH` puts it elsewhere). Each row carries the
verdict it reached as its claimed level, `meta:
{mathema.compendium_claimed: holds}`, and the `note:` your claims file
states on it, so the file a downstream project drops into its own
`claims/` directory is read exactly like a bundled one.

This is the consumption side run in reverse: the export moves rows from
one project's verified layer into another's declared layer, and the
downstream consumer still verifies or trusts them, since nothing is
promoted to proof by being published.

An export is how claims travel with a package: to the projects
downstream that install and call it. In the package's own repository
the file has no effect. A compendium file whose `compendium:` names the
project's own package is ignored there, since during that package's
own development its claims live in its ordinary claims files and its
verified store, and a second, exported copy of them would state the
same claims twice. `mathema verify` prints a note naming the ignored
file.

## Across: equivalence, and other languages

The equivalence relation (`f =:= g`, and the call-form law
`f(x) == g(x)`) accepts any callable for `g`, so the other
implementation need not be Python.
[`examples/cpp-equivalence/`](https://github.com/tetrionlabs/mathema/tree/main/examples/cpp-equivalence) checks a C++ `ema`
reached through a ctypes shim over the C ABI against the Python
reference: `holds`, on shared draws, with no special integration.

Read such a result honestly:

- **Sampling never proves.** A C++ side has no Python source, so the
  form-hash and symbolic rungs cannot run; shared-draw execution
  carries it, and its ceiling is `holds`.
- **What transfers is the mathematics.** A claim like
  `for x in [0,1], f(x) <= 1` is about the function's behaviour, and
  equivalence at evidence level E lets it stand for the other
  implementation at level E, never higher.
- **What never transfers is the computation.** The safety families
  (`is_state_safe`, representation, extremity, determinism) are facts
  about one implementation in one language. C++ has hazards Python
  cannot exhibit: signed-integer overflow is undefined behaviour, not
  wraparound; `-ffast-math` deletes the NaN semantics a nan-region
  entry describes; `float` truncates where `double` was claimed. Each
  implementation earns its own safety verdicts.
- **Language-level claims get their own grammar name.** A record row
  in a foreign grammar (`mathema-cpp`) is fingerprinted as verbatim
  bytes and skipped by a Python adjudicator with reason
  `foreign-grammar`, so mixed records are well-behaved today; the
  name reserves the place where a C++-side tool writes claims a
  Python parser must not read. Transfer rows themselves (a record
  gaining another implementation's mathematical claims with the
  equivalence named as provenance) are designed and land with the
  claim-schema work.

The compendium and equivalence transfer are two ends of one rule:
**evidence carries its provenance, and testimony is never silently
promoted to proof.**
