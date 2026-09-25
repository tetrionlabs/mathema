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
  intent: "Principal square root; a negative input returns nan, never raises."
  claims:
    - name: is_defined
      statement: "x >= 0"

numpy.clip:
  claims:
    - name: clip_lower
      statement: "assuming a_min <= a_max, for a in [-1e6, 1e6], a_min <= f(a, a_min, a_max)"
```

The parameter names are the library's own (`inspect.signature`, so
numpy's `clip` takes `a`, `a_min` and `a_max`), and every row is a
claim like any other, with an `intent:` where the library's behaviour
needs saying in prose. mathema bundles such files for `math` and
`numpy` (numpy's 28 covered functions split into scalars, reductions
and bounds), and a project states its own anywhere its claims files
already live, `claims/numpy.claims.yaml` for instance, where a key
shadows the bundled entry for that function. A file applies only when
the library is importable at a version inside its range; otherwise it
contributes nothing, which is better than contributing stale facts.

An `is_defined` row with a stated region reads as "returns a value on
exactly this region", so `numpy.sqrt`'s `x >= 0` says that outside it
the call has no value, whether the library raises there (`math.sqrt`),
returns nan (`numpy.sqrt`) or overflows to an infinity. A `raises(f(x),
Exc)` row is added only where the exception type itself matters.

Consumption paths:

- Definedness regions become sampling hazards: their boundary values
  join the probe candidates for every caller, whether it spells the
  call `numpy.sqrt(x)` or `np.sqrt(x)`.
- `is_compendium_safe(numpy)` asserts a function never silently emits
  a non-finite value (nan/inf) through an unguarded call into a covered
  library function; the probe samples the hazard boundaries and the
  empty-sequence case, and falsifies on a nan/inf output.
- Claims may be named as premises: `assuming clip_lower holds`, or
  qualified, `assuming numpy.clip.clip_lower holds`.

A compendium row is testimony, and it never enters the evidence chain
silently. `mathema verify` adjudicates the rows of every library
function your project calls or rests a premise on against the library
you have installed, records the local verdict with the row's
provenance (`compendium:numpy-2.5`), and a premise then resolves at
that verdict; a project that never calls numpy verifies none of its
rows, and a row verify cannot settle here is reported rather than
failing the run. For such a row the resting claim stays `unknown` and
its note names the other path forward:

```bash
mathema accept numpy.clip clip_lower --as trusted
```

takes the row at the level its curator claims (the row's `meta:
{mathema.compendium_claimed: proven}`, `holds` when it states none),
and every conclusion resting on it caps there, with the provenance
(`compendium:numpy-2.5/clip_lower`) named in the record. Accepting is
a statement of trust, which a later verify that does settle the row
replaces with the local verdict.

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
{mathema.compendium_claimed: holds}`, so the file a downstream project
drops into its own `claims/` directory is read exactly like a bundled
one.

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
- **What never transfers is the implementation.** The safety families
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
