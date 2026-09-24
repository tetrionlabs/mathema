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
print(mathema.check(ema))
```

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
  FALSIFY is_deterministic[float]: f(x, alpha) = f(x, alpha)
           counterexample x=[-1e+308, -1e+308, -1e+308], alpha=-1e+308
           [mathematics sound, implementation:numerical-instability]
  proven  is_state_safe: f(x, alpha) = f(x, alpha)
  holds   is_numerically_stable: let g = mathema.f.finite_no_error, g(f, x, alpha) = 1 (n=160)
  holds   is_representation_safe[alpha]: is_representation_safe(alpha) (n=12)
  FALSIFY bounded_lower: min(x) <= f(x, alpha)
           counterexample ([2.01488, 3.30692, -6.39418, 3.78355, 6.96564, 7.97935], -9.1034): -6.39418363288563 vs -45761.14174665739
  FALSIFY bounded_upper: f(x, alpha) <= max(x)
           counterexample ([2.59648, 2.09269], -7.84153): 6.5469484767516235 vs 2.596479621674405
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([6.22429, 5.95714, 3.98826, -6.56235, 7.20359, 1.66103, -8.45295], -5.87836): 78066.38231536481 vs -1129152.7241483687
  proven  scale_equivariant: let g = mathema.f.scale_seq, let c be [-5.0, 5.0]:float|missing, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
  FALSIFY scale_equivariant[float]: let g = mathema.f.scale_seq, let c be [-5.0, 5.0]:float|missing, c*f(x, alpha) = f(g(x, c), alpha)
           counterexample x=[-1e+308, -1e+308, -1e+308], alpha=-1e+308, c=-5
           [mathematics sound, implementation:numerical-instability]
  proven  translation_equivariant: let g = mathema.f.shift_seq, let c be [-5.0, 5.0]:float|missing, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
  FALSIFY translation_equivariant[float]: let g = mathema.f.shift_seq, let c be [-5.0, 5.0]:float|missing, c + f(x, alpha) = f(g(x, c), alpha)
           counterexample x=[-1e+308, -1e+308, -1e+308], alpha=-1e+308, c=-5
           [mathematics sound, implementation:numerical-instability]
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

Each `proven` law also has a row with a `[float]` suffix. That is its
float companion, a separate claim that runs the same law through the
real code in floating point, at the domain's corners and at sampled
points inside it. Nothing here bounds `x` or `alpha`, so the corners
sit near `1e+308`, where `alpha * v` overflows to infinity and the next
step of the loop gives `nan`. The proofs stand, and the companions
record that the float code does not follow them out there, which is
what `[mathematics sound, implementation:numerical-instability]` says.
`is_deterministic[float]` fails for the same reason: both calls return
`nan`, which does not compare equal to itself.

## Step 2: declare a domain

<!-- example: ema run -->
```python
print(mathema.check(ema, domain={"alpha": (0, 1)}))
```

Restricting `alpha` to where `ema` is actually meant to be used changes
the picture, not just the wording (an excerpt, from the bounds on):

<!-- example: ema output match=subset -->
```text
  proven  bounded_lower: min(x) ≤ f(x, alpha)
  holds   bounded_lower[float]: min(x) <= f(x, alpha) (n=44)
  proven  bounded_upper: f(x, alpha) ≤ max(x)
  holds   bounded_upper[float]: f(x, alpha) <= max(x) (n=44)
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([-3.03564, -8.20143, -0.353355], 0.593337): -2.6905828069734596 vs -3.8384996201656314
  proven  scale_equivariant: let g = mathema.f.scale_seq, let c be [-5.0, 5.0]:float|missing, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [0, 1] ⊂ ℝ ∪ {∅}
  FALSIFY scale_equivariant[float]: let g = mathema.f.scale_seq, let c be [-5.0, 5.0]:float|missing, c*f(x, alpha) = f(g(x, c), alpha)
           counterexample x=[-1e+308, -1e+308, -1e+308], alpha=0, c=-5
           [mathematics sound, implementation:numerical-instability]
  proven  translation_equivariant: let g = mathema.f.shift_seq, let c be [-5.0, 5.0]:float|missing, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [0, 1] ⊂ ℝ ∪ {∅}
  holds   translation_equivariant[float]: let g = mathema.f.shift_seq, let c be [-5.0, 5.0]:float|missing, c + f(x, alpha) = f(g(x, c), alpha) (n=48)
```

Both bounds flip to `proven`. Inside `[0, 1]` each step of the loop is
a convex combination of the new element and the running value, so
`ema` really is bounded by `min(x)` and `max(x)`, and the same code
that failed a moment ago now passes, because the claim finally says
where it applies, and their float companions hold as well.
`permutation_invariant` stays falsified, as it should: narrowing the
domain does not make an order-sensitive function order-insensitive.
`scale_equivariant[float]` still fails, because `x` is still unbounded:
scaling a `1e+308` element by `-5` overflows, and `0 * inf` is `nan`.

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
  holds   collapses_derived[float]: f(x, 1.0) = x[-1] (n=44)
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
and it holds at all 44 points it ran, including elements near `1e+308`.

## Step 4: keep the record

<!-- example: ema run -->
```python
mathema.write_spec(ema, claims=collapses)
print(open(".mathema/verified/ema.yaml").read())
```

runs step 3's check again and writes the results to
`.mathema/verified/ema.yaml`, the durable record a **provable codebase**
keeps instead of trusting the implementation alone (trimmed):

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
      n: 44
      note: "the implementation of collapses_derived, executed in float at 44 points (every domain corner, then sampled interior points); unbounded directions (x) run to magnitude 1e+308, sampled log-uniformly (no |inf| declared)"
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
      basis: "probed, n=44"
    - step: "situating"
      claim: "instantiates: summation, folded-sum"
      basis: "deterministic concept tagging"
  lineage:
    generated_by: "mathema 0.6.0"
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
