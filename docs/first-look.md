# A first look

*One function, walked through built-in laws, a domain, both evidence routes
and the stored record.*

```python
import mathema

def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y
```

`ema` has a real loop in it. That matters later (see
[The derive route](derive-route.md)), but not yet: the simplest way to
use mathema needs nothing special about the function at all.

## Step 1: the built-in laws, no claims stated

```python
mathema.check(ema)
```

With no `claims=` argument, mathema still runs the probes every
function gets (`is_deterministic`, `is_state_safe`,
`is_numerically_stable`, `is_representation_safe`), plus whichever
built-in algebraic laws apply to `ema`'s actual shape. Here that means
one sequence parameter feeding a numeric result, so the bounds,
`permutation_invariant`, `scale_equivariant` and
`translation_equivariant` all run too, alongside shape claims over the
scalar parameter. This is the real, unedited result:

```text
mathema.Record(ema) · source, no side effects · form 5108dc8b5d5c
  FALSIFY monotonic_increasing[alpha]: d(f(x, alpha), alpha) >= 0
           counterexample alpha=1 -> 0.45118195841070374, alpha=3.09918 -> -349.0594689144083 (not increasing)
  FALSIFY monotonic_decreasing[alpha]: d(f(x, alpha), alpha) <= 0
           counterexample alpha=1e-09 -> 999999.9980000095, alpha=9.71405 -> 75934653.1750601 (not decreasing)
  FALSIFY affine[alpha]: d(f(x, alpha), alpha, alpha) = 0
           counterexample alpha=-2.00525, h=0.00401: curvature estimate 18.3289 does not settle affine
  FALSIFY convex[alpha]: d(f(x, alpha), alpha, alpha) >= 0
           counterexample alpha=-0.220263, h=0.002: curvature estimate -208.106 does not settle convex
  FALSIFY concave[alpha]: d(f(x, alpha), alpha, alpha) <= 0
           counterexample alpha=8.52571, h=0.0171: curvature estimate 3.64705e+06 does not settle concave
  proven  is_deterministic: f(x, alpha) = f(x, alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
  proven  is_state_safe: f(x, alpha) = f(x, alpha)
  holds   is_numerically_stable: let g = mathema.f.finite_no_error, g(f, x, alpha) = 1 (n=160)
  holds   is_representation_safe[alpha]: is_representation_safe(alpha) (n=12)
  FALSIFY bounded_lower: min(x) <= f(x, alpha)
           counterexample ([2.01488, 3.30692, -6.39418, 3.78355, 6.96564, 7.97935], -9.1034): -6.39418363288563 vs -45761.14174665739
  FALSIFY bounded_upper: f(x, alpha) <= max(x)
           counterexample ([2.59648, 2.09269], -7.84153): 6.5469484767516235 vs 2.596479621674405
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([6.22429, 5.95714, 3.98826, -6.56235, 7.20359, 1.66103, -8.45295], -5.87836): 78066.38231536481 vs -1129152.7241483687
  proven  scale_equivariant: let g = mathema.f.scale_seq, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
  proven  translation_equivariant: let g = mathema.f.shift_seq, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
```

Every counterexample names the inputs that produced it, so a failure is
a thing you can paste into a REPL rather than a claim to take on faith.
Two of these are genuinely informative rather than noise. The bounds
fail because nothing here constrains `alpha` to `[0, 1]`, and outside
that range `ema` is not a weighted average at all, which the sampler
demonstrates at `alpha=-9.1`. `permutation_invariant` fails because
`ema` is order-sensitive by design, which is what "exponentially
weighted" means. mathema does not know that is intentional, so it
reports the counterexample and lets a reader judge it.

Note `is_deterministic` came back `proven`, not `holds`. It did not need
sampling: the body lifts to a closed symbolic form, and a closed form
has no state to vary with. `n=160` elsewhere is not a flat constant
either, it is a trial budget decided once per call from `ema`'s own
structure (128 by default, more for a structurally riskier function,
here one loop, so +32). See [mathema check](modes/check.md#the-trial-budget)
for how that is decided, and `--trials-scale` for turning it down in a
fast dev loop. Every verdict reports the exact `n` it used, plus a
`meta["mathema.confidence"]` score capped below the derive route's own,
since sampling is never proof.

## Step 2: declare a domain

```python
mathema.check(ema, domain={"alpha": (0, 1)})
```

Restricting `alpha` to where `ema` is actually meant to be used changes
the picture, not just the wording:

```text
  ...
  proven  bounded_lower: min(x) ≤ f(x, alpha)
  proven  bounded_upper: f(x, alpha) ≤ max(x)
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([-3.03564, -8.20143, -0.353355], 0.593337): -2.6905828069734596 vs -3.8384996201656314
  proven  scale_equivariant: let g = mathema.f.scale_seq, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [0, 1] ⊂ ℝ ∪ {∅}
  proven  translation_equivariant: let g = mathema.f.shift_seq, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [0, 1] ⊂ ℝ ∪ {∅}
```

Both bounds flip to `proven`. Inside `[0, 1]` each step of the loop is
a convex combination of the new element and the running value, so
`ema` really is bounded by `min(x)` and `max(x)`, and the same code
that failed a moment ago now passes, because the claim finally says
where it applies.
`permutation_invariant` stays falsified, as it should: narrowing the
domain does not make an order-sensitive function order-insensitive.

A declared domain is documentation, not enforcement. Whether the code
itself *rejects* an out-of-domain argument is a separate question, and
a separate claim you opt into:

```python
mathema.check(ema, claims=["excluding"], domain={"alpha": (0, 1)})
```

```text
mathema.Record(ema) · source, no side effects · form 5108dc8b5d5c
  FALSIFY excluded_outside_domain[alpha]: excluded_outside_domain(alpha)
           counterexample alpha = -0.5 is outside the declared domain but was accepted (returned -8.497371670908786); the exclusion is asserted, not enforced
```

`ema` has no guard at all, so this is falsified, and the message says
exactly what that means: the exclusion is asserted, not enforced. If
you want the guard rather than the finding, the
[`enforce_domain` decorator](authoring.md) writes one from the domains
already declared on the function's claims.

## Step 3: state a claim of your own, on both evidence routes

Every claim is adjudicated on one of two routes. **probe** calls the
real function on seeded random inputs and reports `holds (n=...)`,
evidence, not proof. **derive** lifts the function's body to a
symbolic expression and decides the claim algebraically, reporting
`proven` when it can. The same claim, checked on both:

```python
mathema.check(ema, claims=[
    mathema.claim("f(x, 1.0) == x[-1]", name="collapses_probed", route="probe"),
    mathema.claim("f(x, 1.0) == x[-1]", name="collapses_derived", route="derive"),
])
```

```text
mathema.Record(ema) · source, no side effects · form 5108dc8b5d5c
  holds   collapses_probed: f(x, 1.0) = x[-1] (n=160)
  proven  collapses_derived: f(x, 1.0) = x[-1]
           ∀ x ∈ Seq(ℝ)
```

Both say the claim is true, but they are not the same kind of true.
`collapses_probed` ran `ema` 160 times on seeded random `x` and never
saw a counterexample: real evidence, but only for the lengths and
values it happened to sample. `collapses_derived` did not run `ema`
at all. It lifted the loop to a closed form over the whole sequence,
every length, every element, and simplified both sides of the claim
to the same expression internally (`when L = 1: x[0]; otherwise
x[L - 1]`, in plain terms rather than raw `sympy` syntax,
available via `p.sketch` on the returned `Probe`, not printed by
default). `proven` holds for every `x`, stated explicitly as
`∀ x ∈ Seq(ℝ)`, not just the ones sampled. That is what "the two sides
are the same expression" buys over "n samples agreed." The derive
route can do this here specifically because `ema`'s loop is a linear
fold, one of the [shapes it
recognizes](derive-route.md#linear-accumulator-folds). Most loops are
still not liftable, and probe stays the only route for them.

## Step 4: keep the record

```python
mathema.write_spec(ema, claims=[...])
```

runs step 3's check again (with step 3's two claims in place of
`[...]`) and writes the results to `.mathema/verified/ema.yaml`, the
durable record a **provable codebase** keeps instead of trusting the
implementation alone (trimmed):

```yaml
# machine record; binds to form 5108dc8b5d5c
ema:
  schema_version: "0.2.0"
  name: "ema"
  signature: "(x: list, alpha: float) -> float"
  intent: "Exponentially weighted moving average."
  grammar: "mathema"
  tolerance: 1.0e-09
  identity:
    form: "5108dc8b5d5c"
    sig: "1fb43b08d3e9"
    tier: 2
    source_available: true
    pure: true
    claims_fingerprint: "222d9f293690"
    pin: "none"
    integrity: "c78cf4a191d01a7e"
  math: null
  claims:
    - name: "collapses_derived"
      statement: "f(x, 1.0) = x[-1]"
      verdict: "proven"
      note: "inferred alpha=1 from the claim's own literal argument"
      sketch: "when L = 1: x[0]; otherwise x[L - 1] and x[L - 1] simplify identically"
      condition: "∀ x ∈ Seq(ℝ)"
      route: "derive"
      # ...
    - name: "collapses_probed"
      statement: "f(x, 1.0) = x[-1]"
      verdict: "holds"
      n: 160
      note: "inferred alpha=1 from the claim's own literal argument"
      route: "probe"
      # ...
  concepts:
    - "summation"
    - "folded-sum"
  references: {}
  reasoning:
    - step: "intent"
      claim: "Exponentially weighted moving average."
      basis: "documented; the author's stated purpose"
    - step: "structure"
      claim: "a left fold over x[1:] with accumulator 'y'"
      basis: "read off the AST"
    - step: "evidence"
      claim: "f(x, 1.0) = x[-1]"
      basis: "probed, n=160"
    - step: "derivation"
      claim: "f(x, 1.0) = x[-1]"
      basis: "when L = 1: x[0]; otherwise x[L - 1] and x[L - 1] simplify identically"
    - step: "situating"
      claim: "instantiates: summation, folded-sum"
      basis: "deterministic concept tagging"
  lineage:
    generated_by: "mathema 0.6.0"
    CDD_spec_version: "0.2.0"
    date: "2026-09-24"
    commit: null
  # ...
```

The `reasoning` section restates each claim in plain language:
`evidence` for a probed `holds`, `refutation` for a falsified claim on
either route, `derivation` for a proven one.

The record binds to `form`, a hash of the function's structure, not
its text, so a rename or reformat does not invalidate it, but a real
behavior change does. `mathema verify` re-checks every saved record
whose function, or a function it depends on, has changed since.

## Where to go next

[Claim-driven development](cdd.md) is the method underneath, with the full
verdict vocabulary, and [the evidence ladder](evidence-ladder.md) ranks the
routes you have just seen. [Library usage](modes/library.md) covers the
Python API in full.
