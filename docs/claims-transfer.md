# Claims transfer

Evidence is earned about one implementation. This page is about the
three ways it travels: **in**, from curated knowledge about libraries
your code calls; **across**, between implementations shown equivalent,
in another language included; and **out**, publishing your own verified
claims as a compendium others consume.

## In: the compendium

The compendium is a curated file of claims ABOUT a library: raise and
nan regions, known limitations, and bound claims. mathema bundles
entries for `math` and `numpy` (numpy's ~28 covered functions split by
hazard category: domain-nan, overflow, division, empty-reductions,
bounds); a project adds or overrides under `.mathema/compendium/`. Each
file declares its own `package` and `versions`, and lives either as a
flat `<package>.yaml` or, for a growing library, in a per-package
subdirectory `<package>/*.yaml` split by category. An entry applies
only when the installed package version falls inside its stated range;
a stale entry contributes nothing, and several version-specific files
coexist by a `<package>-<version>.yaml` filename suffix.

Consumption paths:

- **Raise regions** register into the partiality machinery, so a
  claim about a CALLER of a covered function adjudicates against the
  callee's raising region exactly as it does against `math.sqrt`'s.
- **nan regions** become sampling hazards: their boundary values join
  the probe candidates for every caller.
- **`is_compendium_safe(numpy)`** asserts a function never silently
  emits a non-finite value (nan/inf) through an unguarded call into a
  covered library function; the probe samples the hazard boundaries and
  the empty-sequence case, and falsifies on a nan/inf output.
- **Claims** may be named as premises: `assuming clip_lower holds`,
  or qualified, `assuming numpy.clip.clip_lower holds`.

A compendium verdict never enters the evidence chain silently. On
first reference the row materialises into the verified store at
`declared` status; the resting claim stays `unknown` and its note
names both paths forward:

```
$ mathema accept numpy.clip clip_lower --as trusted
```

takes the row at the level its curator claims, and every conclusion
resting on it caps there, with the provenance
(`compendium:numpy-2.2/clip_lower`) named in the record. Running
`mathema verify` instead re-adjudicates the row against the installed
library, and the local verdict replaces the testimony. Accepting is a
statement of trust; reverifying removes the need for it.

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
as `mathema.previous_verdict: "falsified"` in the claim's meta. The falsification was
never wrong: it was true of the unguarded code, and remains the reason
the guard exists.

## Out: exporting your own verified claims

A library author who has run `mathema verify` on their own package can
publish that evidence as a compendium others consume:

```
$ mathema compendium export mylib --out compendium/mylib/
```

reads the verified store, filters to `mylib`'s functions, and writes a
partial SKELETON: verified bound claims become `claims`, verified
`raises(...)` contracts become `raises_when`, and any nan/inf a
function returns through a recognisable guard (`if ...: return
float('nan')`) becomes `nan_when`. What cannot be read from positive
claims, the prose limitations and the nan regions no guard spells out,
is left as an explicit `TODO`, and the header says the file is a
skeleton to complete. The filename carries the installed version as a
suffix so several version-specific packs coexist.

This is the same rule as the compendium consumption side, run in
reverse: the export moves rows from one project's VERIFIED layer into
another's DECLARED layer. The downstream consumer still has to verify
or trust them; nothing is promoted to proof by being published.

## Across: equivalence, and other languages

The equivalence relation (`f =:= g`, and the call-form law
`f(x) == g(x)`) accepts any callable for `g`, so the other
implementation need not be Python.
[`examples/cpp-equivalence/`](https://github.com/) checks a C++ `ema`
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
