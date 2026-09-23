# mathema

*Claim-Driven Development: turn software intent into verifiable evidence.*

## The problem this addresses

A test tells you a function behaved correctly on the specific inputs
the test author thought to write down. A type hint tells you the
*shapes* of the inputs and outputs line up. Neither tells you *why*
the function is trusted, in a form that survives the function being
rewritten, or that a reviewer (human or model) can check against the
real code in seconds rather than by re-reading the implementation.

Claim-driven development is a small, deliberately spec-first answer
to that gap: a **claim** is a specific, checkable statement about what
a function does (`f(-x) == -f(x)`, `min(x) <= f(x) <= max(x)`, `f`
raises on a shape mismatch), adjudicated against the *real* function,
not assumed from its signature. The claim, its verdict, and the
evidence behind that verdict are the durable artifact, not a
disposable test file that only proves something the day it was
written. The full specification, including the exact vocabulary and
the YAML record schema, lives in a sibling repository:
[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development)
on GitHub. mathema is one implementation of it, in Python.

The name is Greek: μάθημα, a thing learned. A function is trusted
exactly to the extent of its verified claims.

## A first look

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

### Step 1: the built-in laws, no claims stated

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
mathema.Record(ema) · tier 2 · form 1dda3a0d5a72
  FALSIFY monotonic_increasing[alpha]: d(f(x, alpha), alpha) >= 0
           counterexample alpha=1 -> 0.45118195841070374, alpha=3.09918 -> -349.0594689144083 (not increasing)
  FALSIFY monotonic_decreasing[alpha]: d(f(x, alpha), alpha) <= 0
           counterexample alpha=1e-09 -> 999999.9980000095, alpha=9.71405 -> 75934653.1750601 (not decreasing)
  FALSIFY affine[alpha]: d(f(x, alpha), alpha, alpha) == 0
           counterexample alpha=-2.00525, h=0.00401: curvature estimate 18.3289 does not settle affine
  FALSIFY convex[alpha]: d(f(x, alpha), alpha, alpha) >= 0
           counterexample alpha=-0.220263, h=0.002: curvature estimate -208.106 does not settle convex
  FALSIFY concave[alpha]: d(f(x, alpha), alpha, alpha) <= 0
           counterexample alpha=8.52571, h=0.0171: curvature estimate 3.64705e+06 does not settle concave
  proven  is_deterministic: f(x, alpha) = f(x, alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
  proven  is_state_safe: f(x, alpha) = f(x, alpha)
  holds   is_numerically_stable: g(f, x, alpha) == 1 (n=160)
  holds   is_representation_safe[alpha]: is_representation_safe(alpha) (n=12)
  FALSIFY bounded_lower: min(x) <= f(x, alpha)
           counterexample ([2.01488, 3.30692, -6.39418, 3.78355, 6.96564, 7.97935], -9.1034): -6.39418363288563 vs -45761.14174665739
  FALSIFY bounded_upper: f(x, alpha) <= max(x)
           counterexample ([2.59648, 2.09269], -7.84153): 6.5469484767516235 vs 2.596479621674405
  FALSIFY permutation_invariant: f(x, alpha) == f(g(x), alpha)
           counterexample ([6.22429, 5.95714, 3.98826, -6.56235, 7.20359, 1.66103, -8.45295], -5.87836): 78066.38231536481 vs -1129152.7241483687
  holds   scale_equivariant: c*f(x, alpha) == f(g(x, c), alpha) (n=160)
  holds   translation_equivariant: f(x, alpha) + c == f(g(x, c), alpha) (n=160)
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

### Step 2: declare a domain

```python
mathema.check(ema, domain={"alpha": (0, 1)})
```

Restricting `alpha` to where `ema` is actually meant to be used changes
the picture, not just the wording:

```text
  holds     bounded_lower
  holds     bounded_upper
  falsified permutation_invariant
  holds     scale_equivariant
  holds     translation_equivariant
```

Both bounds flip to `holds`. Sampled only inside `[0, 1]`, `ema` really
is bounded by `min(x)` and `max(x)`, and the same code that failed a
moment ago now passes, because the claim finally says where it applies.
`permutation_invariant` stays falsified, as it should: narrowing the
domain does not make an order-sensitive function order-insensitive.

A declared domain is documentation, not enforcement. Whether the code
itself *rejects* an out-of-domain argument is a separate question, and
a separate claim you opt into:

```python
mathema.check(ema, claims=["excluding"], domain={"alpha": (0, 1)})
```

```text
  falsified excluded_outside_domain[alpha]: excluded_outside_domain(alpha)
            counterexample alpha = -0.5 is outside the declared domain but was accepted (returned -8.497371670908786); the exclusion is asserted, not enforced
```

`ema` has no guard at all, so this is falsified, and the message says
exactly what that means: the exclusion is asserted, not enforced. If
you want the guard rather than the finding, the
[`enforce_domain` decorator](authoring.md) writes one from the domains
already declared on the function's claims.

### Step 3: state a claim of your own, on both evidence routes

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
mathema.Record(ema) · tier 2 · form 1dda3a0d5a72
  ...
  holds   collapses_probed: f(x, 1.0) == x[-1] (n=128)
  proven  collapses_derived: f(x, 1.0) = x[-1]
           ∀ x ∈ Seq(ℝ)
```

Both say the claim is true, but they are not the same kind of true.
`collapses_probed` ran `ema` 128 times on seeded random `x` and never
saw a counterexample: real evidence, but only for the lengths and
values it happened to sample. `collapses_derived` did not run `ema`
at all. It lifted the loop to a closed form over the whole sequence,
every length, every element, and simplified both sides of the claim
to the same expression internally (`when L = 1: x[0]; otherwise
1.0*x[L - 1]`, in plain terms rather than raw `sympy` syntax,
available via `p.sketch` on the returned `Probe`, not printed by
default). `proven` holds for every `x`, stated explicitly as
`∀ x ∈ Seq(ℝ)`, not just the ones sampled. That is what "the two sides
are the same expression" buys over "n samples agreed." The derive
route can do this here specifically because `ema`'s loop is a linear
fold, one of the [shapes it
recognizes](derive-route.md#linear-accumulator-folds). Most loops are
still not liftable, and probe stays the only route for them.

### Step 4: keep the record

```python
mathema.write_spec(ema, claims=[...])
```

writes the full set of results from every call above to
`.mathema/verified/ema.yaml`, the durable record a **provable codebase**
keeps instead of trusting the implementation alone:

```yaml
# machine record; binds to form 1dda3a0d5a72
ema:
  name: "ema"
  signature: "(x: list, alpha: float) -> float"
  intent: "Exponentially weighted moving average."
  identity:
    form: "1dda3a0d5a72"      # rename/format-invariant AST structure
    sig: "1fb43b08d3e9"       # parameter shape
    tier: 2
    pure: true
    claims_fingerprint: "dc934824ba7a"
  math: null
  claims:
    - name: "bounded"
      statement: "min(x) ≤ result ≤ max(x)"
      verdict: "falsified"
      n: 160
      counterexample: "x=[-8.09, 7.03, 1.96], alpha=9.22 -> result=-1060.46 < min(x)=-8.09"
      route: "probe"
      # note/sketch/condition/meta omitted here for brevity; every claim
      # carries all five fields, meta included whenever a built-in law
      # or the derive route has extra evidence to attach
    - name: "collapses_derived"
      statement: "f(x, 1.0) == x[-1]"
      verdict: "proven"
      n: null
      counterexample: null
      route: "derive"
    # ... one entry per claim above
  concepts: []
  references: []
  reasoning:
    - step: "refutation"
      claim: "NOT (min(x) ≤ result ≤ max(x))"
      basis: "counterexample x=[-8.09, 7.03, 1.96], alpha=9.22 -> result=-1060.46 < min(x)=-8.09"
    - step: "derivation"
      claim: "f(x, 1.0) == x[-1]"
      basis: "when L = 1: x[0]; otherwise x[L - 1] and x[L - 1] simplify identically"
    # one reasoning step per claim, in plain language: "evidence" for a
    # probed holds, "refutation" for a falsified claim on either route,
    # "derivation" for a proven one
  lineage:
    generated_by: "mathema 0.5.0"
    CDD_spec_version: "0.2.0"
    date: "2026-08-18"
```

The record binds to `form`, a hash of the function's structure, not
its text, so a rename or reformat does not invalidate it, but a real
behavior change does. `mathema.status()` reports which saved records
have gone stale against the code as it stands now.

## What it does

- **Structural analysis** (pure `ast`, no dependencies): loop shape,
  purity and effects, parameter kinds, per-parameter domain guards.
- **Probing**: runs the real function on seeded random inputs and
  checks built-in algebraic laws (commutativity, idempotence,
  boundedness, parity, monotonicity, equivariances) plus any claim you
  state yourself. `holds (n=...)` is evidence, not proof. `n` is a
  trial budget decided once per call from the function's own
  structure, never a flat constant, and `falsified` comes with the
  counterexample, permanently.
- **Symbolic proof (the derive route)**: lifts a function's body to a
  `sympy` expression and decides a claim algebraically. `proven` is
  strictly stronger than `holds`: not "n samples agreed," but "the two
  sides are the same expression." See [The derive route](derive-route.md)
  for exactly what is liftable.
- **The conjecture pipeline**: state a claim as one string
  (`"f(-x) == -f(x)"`) or a `Conjecture`. Laws are validated against a
  strict AST whitelist before they run, so proposals from an untrusted
  source (a human in review, or a model) are safe to check. The
  proposer never adjudicates its own claims.
- **Identity hashes**: `form` (rename/format-invariant AST structure)
  and `sig` (parameter shape). Every claim binds to them, so a record
  cannot silently outlive the code it describes.
- **The spec store**: `mathema.write_spec(fn, ...)` writes a standalone YAML
  record to `.mathema/verified/`. `mathema.status()` reports fresh vs.
  stale against the code as it is now.

## Exit codes

Every verb uses the same four, so a CI step can tell a failing gate
apart from a broken invocation without parsing output:

| Code | Meaning |
|---|---|
| 0 | ran, and nothing gated: claims adjudicated as stated, or the verb only reports |
| 1 | ran, and the gate failed: a claim is falsified, unknown in strict mode, or a conflict is unresolved |
| 2 | could not run: a target that does not resolve, an unreadable or malformed file, a bad argument, a missing optional extra |
| 130 | interrupted (Ctrl-C or EOF) |

The distinction that matters in CI is 1 against 2. A 1 is a real
finding about your code and the record will say which claim; a 2 means
mathema never got far enough to have an opinion, so treating the two
alike hides a broken invocation as a failing test. `--lenient` moves
accepted risks out of the gate and so can turn a 1 into a 0, but it
never turns a 2 into either (see [what fails the
run](modes/verify.md#what-fails-the-run)).

## Where to go next

**New here? Start with the [quick start](quickstart.md)**: five minutes,
one function, and a claim that goes from falsified to proven.

mathema can be run several different ways depending on what you are
trying to do. See [Modes of running mathema](modes/library.md) for
each one, or [CDD in one page](cdd.md) for the shared vocabulary
(claim verdicts, the two evidence routes) every mode assumes.

## Install

Run these inside an active virtual environment (`python3 -m venv .venv && source
.venv/bin/activate`, or your usual equivalent) rather than against a system or
global Python.

```bash
pip install -e .              # core: sympy (derive route) + pyyaml (the spec store)
```

## Network policy

mathema is fully offline. No core function makes a network call.

## The spec

Claim-driven development lays out the guiding principles this package
implements: the claim tuple, the claim families, and the YAML record
schema, both the authoring shape and the verified-record shape.
Anything that reads or writes that shape interoperates with mathema's
records without importing mathema's Python internals.
`mathema.SPEC_VERSION` states which version a release targets, and
every record stamps that value in `lineage.CDD_spec_version`. The
specification is published under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); its full vocabulary and
schema, which this package is checked against:

- [claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development):
  the repository itself, starting with its own README. Each published
  version has its own directory, holding the three documents mathema is
  checked against:
  - `cdd.md`, the core vocabulary (claim, verdict, evidence route).
  - `claim-anatomy.md`, what a claim is made of.
  - `record-schema.md`, the exact shape of the YAML record shown in
    step 4 above.
