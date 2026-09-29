# A first look

*One function, walked through built-in laws, a domain, both evidence routes
and the stored record.*

<!-- example: ema run -->
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

<!-- example: ema run -->
```python
print(mathema.check(ema, domain={"x": (-1e6, 1e6), "alpha": (-10, 10)}))
```

The `domain=` states a plausible range for the data and the smoothing
factor. Without one, every claim ranges over all of the reals, out to the
largest double, and the computation in float64 overflows long before it
gets there (see [operational infinity](grammar.md#operational-infinity-let-inf-be)).
With no `claims=` argument, mathema still runs the probes every
function gets (`is_deterministic`, `is_state_safe`,
`is_numerically_stable`, `is_representation_safe`), plus whichever
built-in algebraic laws apply to `ema`'s actual shape. Here that means
one sequence parameter feeding a numeric result, so the bounds,
`permutation_invariant`, `scale_equivariant` and
`translation_equivariant` all run too, alongside shape claims over the
scalar parameter. This is the real, unedited result:

<!-- example: ema output -->
```text
mathema.Record(ema) · source, no side effects · form 5108dc8b5d5c
  FALSIFY monotonic_increasing[alpha]: d(f(x, alpha), alpha) >= 0
           counterexample alpha=-5.44324 -> -504886.9526187774, alpha=10 -> -2491080.279764588 (not increasing)
  FALSIFY monotonic_decreasing[alpha]: d(f(x, alpha), alpha) <= 0
           counterexample alpha=-8.34575 -> 1100.270649780719, alpha=10 -> 1138.3250235869998 (not decreasing)
  FALSIFY affine[alpha]: d(f(x, alpha), alpha, alpha) = 0
           counterexample alpha=8.52571, h=0.02: curvature estimate 3.64706e+06 does not settle affine
  FALSIFY convex[alpha]: d(f(x, alpha), alpha, alpha) >= 0
           counterexample alpha=1.55438, h=0.02: curvature estimate -49.227 does not settle convex
  FALSIFY concave[alpha]: d(f(x, alpha), alpha, alpha) <= 0
           counterexample alpha=7.32889, h=0.02: curvature estimate 4463.56 does not settle concave
  proven  is_deterministic: f(x, alpha) = f(x, alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [-10, 10] ⊂ ℝ
  proven  is_state_safe: f(x, alpha) = f(x, alpha)
  holds   is_numerically_stable: let g = mathema.f.finite_no_error, g(f, x, alpha) = 1 (n=192)
  holds   is_representation_safe[alpha]: is_representation_safe(alpha) (n=20)
  FALSIFY bounded_lower: min(x) <= f(x, alpha)
           counterexample ([-993714, 311292, -166437, 620054, 0, 999998, -999998], 6.79181): -999998.0 vs -53425523112.88785
  FALSIFY bounded_upper: f(x, alpha) <= max(x)
           counterexample ([551081, 0, 0, 937864, -860102, -288141, 726070], -4.23217): 10840391161.550304 vs 937863.7282631358
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([567047, -597790, -1e+06, 223930, 683724, -934060, -933610], -1.67919): 425108676.6026794 vs -181372134.92932475
  proven  scale_equivariant: let g = mathema.f.scale_seq, let c be [-5.0, 5.0] : float|absent|missing, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [-10, 10] ⊂ ℝ
  holds   scale_equivariant[float]: let g = mathema.f.scale_seq, let c be [-5.0, 5.0] : float|absent|missing, c*f(x, alpha) = f(g(x, c), alpha) (n=53)
  proven  translation_equivariant: let g = mathema.f.shift_seq, let c be [-5.0, 5.0] : float|absent|missing, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [-10, 10] ⊂ ℝ
  holds   translation_equivariant[float]: let g = mathema.f.shift_seq, let c be [-5.0, 5.0] : float|absent|missing, c + f(x, alpha) = f(g(x, c), alpha) (n=53)
```

Every counterexample names the inputs that produced it, so a failure is
a thing you can paste into a REPL rather than a claim to take on faith.
Two of these are genuinely informative rather than noise. The bounds
fail because nothing here constrains `alpha` to `[0, 1]`, and outside
that range `ema` is not a weighted average at all, which the sampler
demonstrates at `alpha=-3.8`. `permutation_invariant` fails because
`ema` is order-sensitive by design, which is what "exponentially
weighted" means. mathema does not know that is intentional, so it
reports the counterexample and lets a reader judge it.

Note `is_deterministic` came back `proven`, not `holds`. It did not need
sampling: the body lifts to a closed symbolic form, and a closed form
has no state to vary with. `n=192` elsewhere is not a flat constant
either, it is a trial budget decided once per call from `ema`'s own
structure and the domain it is checked over (128 by default, +32 for
the loop, +32 for a domain as wide as `x`'s). See [mathema check](modes/check.md#the-trial-budget)
for how that is decided, and `--trials-scale` for turning it down in a
fast dev loop. Every verdict reports the exact `n` it used, plus a
`meta["mathema.confidence"]` score capped below the derive route's own,
since sampling is never proof.

Each proven algebraic law (the two equivariances) also has a row with a
`[float]` suffix; a family fact such as `is_deterministic` is already a
statement about the code, so it has none. That `[float]` row is the law's
float companion, a separate claim that runs the same law through the
real code in floating point, at the domain's corners and at sampled
points inside it. Both hold here. Drop the `domain=` and they do not:
the corners then sit at float64's maximum, about `1.8e+308`, where `alpha * v` overflows to
infinity and the next step of the loop gives `nan`, so each companion is
falsified with that point as its witness, tagged `[mathematics sound,
implementation:numerical-instability]`, while the proofs stand. A claim
over all of the reals means all of them.

## Step 2: declare a domain

<!-- example: ema run -->
```python
print(mathema.check(ema, domain={"x": (-1e6, 1e6), "alpha": (0, 1)}))
```

Narrowing `alpha` to where `ema` is actually meant to be used changes
the picture, not just the wording (an excerpt, from the bounds on):

<!-- example: ema output match=subset -->
```text
  proven  bounded_lower: min(x) ≤ f(x, alpha)
  holds   bounded_lower[float]: min(x) <= f(x, alpha) (n=47)
  proven  bounded_upper: f(x, alpha) ≤ max(x)
  holds   bounded_upper[float]: f(x, alpha) <= max(x) (n=47)
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([-999998, 978369, 111462, -869239, -926712, -999998, -1e+06, 894282], 0.499951): -11445.14869760722 vs -341186.2123510968
  proven  scale_equivariant: let g = mathema.f.scale_seq, let c be [-5.0, 5.0] : float|absent|missing, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [0, 1] ⊂ ℝ
  holds   scale_equivariant[float]: let g = mathema.f.scale_seq, let c be [-5.0, 5.0] : float|absent|missing, c*f(x, alpha) = f(g(x, c), alpha) (n=53)
  proven  translation_equivariant: let g = mathema.f.shift_seq, let c be [-5.0, 5.0] : float|absent|missing, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [0, 1] ⊂ ℝ
  holds   translation_equivariant[float]: let g = mathema.f.shift_seq, let c be [-5.0, 5.0] : float|absent|missing, c + f(x, alpha) = f(g(x, c), alpha) (n=53)
```

Both bounds flip to `proven`. Inside `[0, 1]` each step of the loop is
a convex combination of the new element and the running value, so
`ema` really is bounded by `min(x)` and `max(x)`, and the same code
that failed a moment ago now passes, because the claim finally says
where it applies, and their float companions hold as well.
`permutation_invariant` stays falsified, as it should: narrowing the
domain does not make an order-sensitive function order-insensitive.

A declared domain is documentation, not enforcement. Whether the code
itself *rejects* an out-of-domain argument is a separate question, and
a separate claim you opt into:

<!-- example: ema run -->
```python
print(mathema.check(ema, claims=["excluding"], domain={"alpha": (0, 1)}))
```

<!-- example: ema output -->
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

<!-- example: ema run -->
```python
collapses = [
    mathema.claim("f(x, 1.0) == x[-1]", name="collapses_probed", route="probe"),
    mathema.claim("f(x, 1.0) == x[-1]", name="collapses_derived", route="derive"),
]
print(mathema.check(ema, claims=collapses))
```

<!-- example: ema output -->
```text
mathema.Record(ema) · source, no side effects · form 5108dc8b5d5c
  holds   collapses_probed: f(x, 1.0) = x[-1] (n=160)
  proven  collapses_derived: f(x, 1.0) = x[-1]
           ∀ x ∈ Seq(ℝ)
  holds   collapses_derived[float]: f(x, 1.0) = x[-1] (n=45)
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

The third row is the proof's float companion, as in step 1. With
`alpha` fixed at `1.0` the loop only copies elements, nothing overflows,
and it holds at all 42 points it ran, including elements at float64's maximum.

## Step 4: keep the record

<!-- example: ema run -->
```python
mathema.write_spec(ema, claims=collapses)
print(open(".mathema/verified/ema.yaml").read())
```

runs step 3's check again and writes the results to
`.mathema/verified/ema.yaml`, the durable record a **provable codebase**
keeps instead of trusting the code alone (trimmed):

<!-- example: ema output match=subset -->
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
    integrity: "v2:082d761b8dba056b"
  math: null
  claims:
    - name: "collapses_derived"
      statement: "f(x, 1.0) = x[-1]"
      verdict: "proven"
      note: "inferred alpha=1 from the claim's own literal argument"
      sketch: "when L = 1: x[0]; otherwise x[L - 1] and x[L - 1] simplify identically"
      condition: "∀ x ∈ Seq(ℝ)"
      route: "derive"
    - name: "collapses_derived[float]"
      statement: "f(x, 1.0) = x[-1]"
      verdict: "holds"
      n: 45
      note: "the computation of collapses_derived in float64, executed at 45 points (every domain corner, then sampled interior points); unbounded directions (x) run to magnitude 1.79769e+308, sampled log-uniformly (no |inf| declared)"
      route: "probe"
    - name: "collapses_probed"
      statement: "f(x, 1.0) = x[-1]"
      verdict: "holds"
      n: 160
      note: "inferred alpha=1 from the claim's own literal argument"
      route: "probe"
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
    - step: "evidence"
      claim: "f(x, 1.0) = x[-1]"
      basis: "probed, n=45"
    - step: "situating"
      claim: "instantiates: summation, folded-sum"
      basis: "deterministic concept tagging"
  lineage:
    generated_by: "mathema 0.6.1"
    CDD_spec_version: "0.2.0"
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
