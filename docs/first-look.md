# A first look

*One function, walked through built-in laws, a domain, both evidence routes
and the stored record.*

<!-- example: ema run -->
```python
import mathema

def ema(x: list[float], alpha: float) -> float:
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
scalar parameter. This is an excerpt of the real result; the full record
has a block like these for every claim:

<!-- example: ema output match=subset -->
```text
mathema.Record(ema) · source, no side effects · form 0f61bbd9aa20
  monotonic_increasing[alpha]  d(f(x, alpha), alpha) >= 0   falsified at alpha = -6.1696206845951425 -> 5942.674653897138, alpha = 6.40985769094643 -> -3117.840364949426 at x = [9.714053089717606, -7.7201618735667354, 2.7365981655901717, -5.722321190852131] (not increasing)
    falsified  mathematics  d(f(x, alpha), alpha) >= 0   counterexample alpha = -6.1696206845951425 -> 5942.674653897138, alpha = 6.40985769094643 -> -3117.840364949426 at x = [9.714053089717606, -7.7201618735667354, 2.7365981655901717, -5.722321190852131] (not increasing)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
  proven    is_deterministic: f(x, alpha) = f(x, alpha)
  proven    is_state_safe: f(x, alpha) = f(x, alpha)
  holds     is_numerically_stable: let g = mathema.f.finite_no_error, g(f, x, alpha) = 1 (858 entries across 192 draws, sizes (1, 1) to (8, 1))
  holds     is_representation_safe[alpha]: is_representation_safe(alpha) (20 draws)
  bounded_lower  min(x) <= f(x, alpha)   falsified at x = [-654957.5039950067, 653524.6080129032], alpha = -2.0152816440503756
    falsified  mathematics  min(x) <= f(x, alpha)   counterexample x = [-654957.5039950067, 653524.6080129032], alpha = -2.0152816440503756: -654957.5039950067 vs -3291917.485892815
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
  permutation_invariant  let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)   falsified at x = [0, -571583.8558276, -540436.369308935, -223497.27964334848, -975167.3260584788], alpha = -9.494869493457017
    falsified  mathematics  let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)   counterexample x = [0, -571583.8558276, -540436.369308935, -223497.27964334848, -975167.3260584788], alpha = -9.494869493457017: 6870069267.105879 vs -8754961179.43428
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
  scale_equivariant  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)   falsified at x = [], alpha = 5.159088058806049
    proven     mathematics  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)
    holds      computation  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)   284 entries across 67 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
```

Each claim prints as a headline (its name, its statement and its
verdict, with the witness when it is falsified) and the lines the
verdict rests on, indented under it. A `mathematics` line is the claim
over the real numbers. A `computation` line runs the same claim through
the real code in float64. A `policy` line covers an input that is not an
ordinary number, here the empty list. The headline is falsified when any
line under it is.

Every counterexample names the inputs that produced it, so a failure is
a thing you can paste into a REPL rather than a claim to take on faith.
Three of these are genuinely informative rather than noise.

- Every claim over `x` is falsified at `x = []`. `ema` reads `x[0]`
  before anything else, so an empty list raises `IndexError`, and the
  policy line says the body stumbles into it rather than handling it.
- The bounds' mathematics fails because nothing here constrains `alpha`
  to `[0, 1]`, and outside that range `ema` is not a weighted average at
  all, which the witness shows at `alpha = -2.0`.
- `permutation_invariant` fails because `ema` is order-sensitive by
  design, which is what "exponentially weighted" means. mathema does not
  know that is intentional, so it reports the counterexample and lets a
  reader judge it.

The equivariances show the layout at its clearest: the mathematics line
is proven for every input, the computation line holds at every float64
input it ran, and the headline is still falsified, by the empty list
alone.

Note `is_deterministic` and `is_state_safe` came back `proven` with no
trial count. mathema never runs a function to answer them: it reads
`ema`'s source and found nothing it reads beyond its arguments and
nothing it writes outside the call. The `192 draws` on
`is_numerically_stable` is not a flat constant either, it is a trial
budget decided once per call from `ema`'s own structure and the domain
it is checked over (128 by default, +32 for the loop, +32 for a domain
as wide as `x`'s). A computation line runs on its own, smaller set of
points: the corners of the domain and sampled points inside it. See [mathema check](modes/check.md#the-trial-budget)
for how that is decided, and `--trials-downscale` for turning it down in a
fast dev loop. Every verdict reports the exact `n` it used, plus a
`meta["mathema.confidence"]` score capped below the derive route's own,
since sampling is never proof.

A family fact such as `is_deterministic` is already a statement about
the code, so it has no lines under it. Drop the `domain=` and the
equivariances' computation lines no longer hold: the corners then sit at
float64's maximum, about `1.8e+308`, where `alpha * v` overflows to
infinity and the next step of the loop gives `nan`, so each computation
line is falsified with that point as its witness, tagged `[mathematics
sound, implementation:numerical-instability]`, while the mathematics
stands. A claim over all of the reals means all of them.

## Step 2: declare a domain

<!-- example: ema run -->
```python
print(mathema.check(ema, domain={"x": (-1e6, 1e6), "alpha": (0, 1)}))
```

Narrowing `alpha` to where `ema` is actually meant to be used changes
the picture, not just the wording (an excerpt, from the bounds on):

<!-- example: ema output match=subset -->
```text
  bounded_lower  min(x) <= f(x, alpha)   falsified at x = [], alpha = 0.7579544029403025
    proven     mathematics  min(x) <= f(x, alpha)
    holds      computation  min(x) <= f(x, alpha)   240 entries across 49 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 0.7579544029403025 with no emptiness guard in the body: the empty input is stumbled into, not handled
  bounded_upper  f(x, alpha) <= max(x)   falsified at x = [], alpha = 0.7579544029403025
    proven     mathematics  f(x, alpha) <= max(x)
    holds      computation  f(x, alpha) <= max(x)   240 entries across 49 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 0.7579544029403025 with no emptiness guard in the body: the empty input is stumbled into, not handled
  permutation_invariant  let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)   falsified at x = [-999998, -310560.8672498255, -198139.7334726196, 1e+06], alpha = 1
    falsified  mathematics  let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)   counterexample x = [-999998, -310560.8672498255, -198139.7334726196, 1e+06], alpha = 1: 1000000.0 vs -999998.0
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 0.7579544029403025 with no emptiness guard in the body: the empty input is stumbled into, not handled
  scale_equivariant  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)   falsified at x = [], alpha = 0.7579544029403025
    proven     mathematics  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)
    holds      computation  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)   284 entries across 67 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 0.7579544029403025 with no emptiness guard in the body: the empty input is stumbled into, not handled
```

Both bounds' mathematics lines flip to `proven`. Inside `[0, 1]` each
step of the loop is a convex combination of the new element and the
running value, so `ema` really is bounded by `min(x)` and `max(x)`, and
the same code that failed a moment ago now passes, because the claim
finally says where it applies; their computation lines hold as well.
The headlines stay falsified at `x = []`: narrowing `alpha` says nothing
about the empty list. `permutation_invariant` stays falsified, as it
should: narrowing the domain does not make an order-sensitive function
order-insensitive.

A declared domain is documentation, not enforcement. Whether the code
itself *rejects* an out-of-domain argument is a separate question, and
a separate claim you opt into:

<!-- example: ema run -->
```python
print(mathema.check(ema, claims=["excluding"], domain={"alpha": (0, 1)}))
```

<!-- example: ema output -->
```text
mathema.Record(ema) · source, no side effects · form 0f61bbd9aa20
  falsified excluded_outside_domain[alpha]: excluded_outside_domain(alpha)
           counterexample alpha = -0.5 is outside the declared domain but was accepted (returned -13.779332172714163); the exclusion is asserted, not enforced
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
`proven` when it can. The same claim, checked on both, with a premise
that says it is about lists of at least one element (step 1 showed what
`ema` does with an empty one), so it gets no empty-list line:

<!-- example: ema run -->
```python
collapses = [
    mathema.claim("assuming len(x) >= 1, f(x, 1.0) == x[-1]", name="collapses_probed", route="probe"),
    mathema.claim("assuming len(x) >= 1, f(x, 1.0) == x[-1]", name="collapses_derived", route="derive"),
]
print(mathema.check(ema, claims=collapses))
```

<!-- example: ema output -->
```text
mathema.Record(ema) · source, no side effects · form 0f61bbd9aa20
  collapses_probed  assuming len(x) >= 1, f(x, 1.0) = x[-1]   holds
    holds      mathematics  assuming len(x) >= 1, f(x, 1.0) = x[-1]   624 entries across 134 draws, sizes (1, 1) to (8, 1)
    holds      policy       f(x=[..., nan, ...])   no missing policy stated; assumed propagates
  collapses_derived  assuming len(x) >= 1, f(x, 1.0) = x[-1]   proven
    proven     mathematics  assuming len(x) >= 1, f(x, 1.0) = x[-1]
    holds      computation  assuming len(x) >= 1, f(x, 1.0) = x[-1]   236 entries across 42 draws, sizes (1, 1) to (8, 1)
    holds      policy       f(x=[..., nan, ...])   no missing policy stated; assumed propagates
```

Both say the claim is true, but they are not the same kind of true.
`collapses_probed` ran `ema` on 134 seeded random lists and never saw
a counterexample: real evidence, but only for the lengths and values it
happened to sample. `collapses_derived` did not run `ema` to reach its
mathematics line. It lifted the loop to a closed form over the whole
sequence, every length, every element, and simplified both sides of the
claim to the same expression internally (`when L = 1: x[0]; otherwise
x[L - 1]`, in plain terms rather than raw `sympy` syntax, available via
`p.sketch` on the returned `Probe`, and kept in the record below).
`proven` holds for every `x`, stated in the record as `∀ x ∈ Seq(ℝ)`,
not just the ones sampled. That is what "the two sides are the same
expression" buys over "n samples agreed." The derive route can do this
here specifically because `ema`'s loop is a linear fold, one of the
[shapes it recognizes](derive-route.md#linear-accumulator-folds). Most
loops are still not liftable, and probe stays the only route for them.

The computation line under `collapses_derived` runs the proven claim
through the real code in float64. With `alpha` fixed at `1.0` the loop
only copies elements, nothing overflows, and it holds at every point it
ran, including elements at float64's maximum. The policy line covers
`nan`: a `list[float]` may hold one, nothing in the claim says what
`ema` should do with it, so mathema assumes the `nan` reaches the result
(it propagates) and checks that it does.

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
# machine record; binds to form 0f61bbd9aa20
ema:
  schema_version: "0.2.0"
  name: "ema"
  signature: "(x: list[float], alpha: float) -> float"
  intent: "Exponentially weighted moving average."
  grammar: "mathema"
  tolerance: 1.0e-09
  identity:
    form: "0f61bbd9aa20"
    sig: "60eacde6c064"
    tier: 2
    source_available: true
    pure: true
    claims_fingerprint: "c1cd39184d20"
    pin: "none"
    integrity: "v2:3313778d4cb4e4b1"
  math: null
  claims:
    - name: "collapses_derived"
      statement: "assuming len(x) >= 1, f(x, 1.0) = x[-1]"
      verdict: "proven"
      note: "inferred alpha=1 from the claim's own literal argument"
      sketch: "when L = 1: x[0]; otherwise x[L - 1] and x[L - 1] simplify identically"
      condition: "∀ x ∈ Seq(ℝ)"
      route: "derive"
    - name: "collapses_derived[float]"
      statement: "assuming len(x) >= 1, f(x, 1.0) = x[-1]"
      verdict: "holds"
      n: 42
      note: "the float64 computation of collapses_derived ran at 42 points: every corner and 40 interior points; unbounded directions (x) run to magnitude 1.79769e+308, sampled log-uniformly (no |inf| declared)"
      route: "probe"
    - name: "collapses_probed"
      statement: "assuming len(x) >= 1, f(x, 1.0) = x[-1]"
      verdict: "holds"
      n: 134
      note: "inferred alpha=1 from the claim's own literal argument; at x = [nan, nan, nan, nan, nan, nan, ...] f gave nan back"
      route: "probe"
    - name: "missing[x]"
      statement: "missing(f, x) propagates"
      verdict: "holds"
      n: 38
      note: "default for a list[float] slot that may be nan; confirmed on the draws of collapses_probed and collapses_derived[float]. Keep it by writing it (mathema claims ema --write), or change the word to raises or drops if f should do otherwise"
      route: "probe:counterfactual"
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
      claim: "assuming len(x) >= 1, f(x, 1.0) = x[-1]"
      basis: "probed, n=134"
    - step: "derivation"
      claim: "assuming len(x) >= 1, f(x, 1.0) = x[-1]"
      basis: "when L = 1: x[0]; otherwise x[L - 1] and x[L - 1] simplify identically"
    - step: "evidence"
      claim: "assuming len(x) >= 1, f(x, 1.0) = x[-1]"
      basis: "probed, n=42"
    - step: "evidence"
      claim: "missing(f, x) propagates"
      basis: "probed, n=38"
    - step: "situating"
      claim: "instantiates: summation, folded-sum"
      basis: "deterministic concept tagging"
  lineage:
    generated_by: "mathema 0.6.1"
    CDD_spec_version: "0.2.0"
```

The record keeps each line as a row of its own: the computation line
as `collapses_derived[float]`, and the policy line as `missing[x]`, the
default mathema assumed, with a note saying how to keep it. The
`reasoning` section restates each claim in plain language:
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
