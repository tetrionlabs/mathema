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

The parameter names are the library's own (`inspect.signature`, so
numpy's `clip` takes `a`, `a_min` and `a_max`), and every row is a
claim like any other, with a `note:` on the row where the library's
behaviour needs saying in prose. A library function's intent is its
own, read from its docstring like any function's, so a compendium file
states none. mathema bundles such files for `math` and
`numpy` (numpy's 28 covered functions split into scalars, reductions
and bounds), and a project states its own anywhere its claims files
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
  is the other row's fact), and inside the carrier's range otherwise.
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
publish that evidence as a compendium others consume:

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
