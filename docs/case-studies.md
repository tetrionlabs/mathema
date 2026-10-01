# Case studies: real formulae, real verdicts

Two worked examples on formulae you can look up, taken from openly
licensed references. Every claim on this page is in the claim lexicon
and is executed by the test suite, so what follows is what mathema
actually returns, including where it declines.

The point of both is the same: the interesting result is rarely one
claim. It is what a small set of claims says together, and what the
disagreements between them tell you.

## Put-call parity and the Greeks

An option's price is not a simple formula. The Black-Scholes call
involves a logarithm, a square root, an exponential and the normal
CDF, which is itself an error function. Put-call parity says that
however complicated each leg is, the difference between a call and a
put on the same strike collapses to something elementary:

    C - P = S - K*exp(-r*T)

No volatility term survives. That is a strong statement about a
function whose body mentions volatility five times, and it is exactly
the kind of claim worth checking against the implementation rather
than against a textbook.

<!-- example: parity verdicts fn=mathema.lexicon:put_call_parity_gap expect=proven -->
```
for s in [50,150], k in [50,150], r in [0.0,0.1], t in [0.1,2], sigma in [0.05,0.8], f(s,k,r,t,sigma) == s - k*exp(-r*t)
```

On `put_call_parity_gap` that is **proven**, not sampled. The two
legs, with all their error functions, cancel symbolically.

### The Greeks are partial derivatives, so state them as partial derivatives

Delta is the sensitivity of the price to the spot, which is to say it
is the partial derivative of the price in `s`. The grammar says that
directly:

<!-- example: delta-lower verdicts fn=mathema.lexicon:black_scholes_call expect=proven -->
```
for s in [50,150], k in [50,150], r in [0.0,0.1], t in [0.1,2], sigma in [0.05,0.8], ∂(f(s,k,r,t,sigma), s) >= 0
```

<!-- example: delta-upper verdicts fn=mathema.lexicon:black_scholes_call expect=proven -->
```
for s in [50,150], k in [50,150], r in [0.0,0.1], t in [0.1,2], sigma in [0.05,0.8], ∂(f(s,k,r,t,sigma), s) <= 1
```

Both are **proven** against `black_scholes_call`. Together they
establish the textbook fact that a call's delta lies in `[0, 1]`, and
they establish it from the code you are shipping rather than from the
paper the code was meant to implement. Nothing was differentiated by
hand: the claim names the partial derivative and the derive route
takes it.

Both spellings work, so `d(f(...), s)` and `∂(f(...), s)` are the same
claim. Use whichever your readers will check.

## The sigmoid: calculus as a specification

The logistic function is one line of code and a great deal of
mathematics:

```python
def logistic_standard(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
```

Its defining properties are calculus facts, and each is a claim.

**Its derivative is expressible in the function itself.** This is the
identity backpropagation is built on:

<!-- example: sigmoid-derivative verdicts fn=mathema.lexicon:logistic_standard expect=proven -->
```
for x in [-700, 700], d(f(x), x) == f(x)*(1 - f(x))
```

**It is symmetric about the origin:**

<!-- example: sigmoid-symmetry verdicts fn=mathema.lexicon:logistic_standard expect=proven -->
```
for x in [-700, 700], f(-x) == 1 - f(x)
```

**It saturates, which limits state:**

<!-- example: sigmoid-limit-upper verdicts fn=mathema.lexicon:logistic_standard expect=proven -->
```
lim(f(x), x -> oo) == 1
```

<!-- example: sigmoid-limit-lower verdicts fn=mathema.lexicon:logistic_standard expect=proven -->
```
lim(f(x), x -> -oo) == 0
```

**Its derivative is a probability density,** which an integral over
the whole line states exactly:

<!-- example: sigmoid-density verdicts fn=mathema.lexicon:logistic_standard expect=proven -->
```
∫(d(f(x), x), x, -oo, oo) == 1
```

All five are **proven**. The derivative identity, the limits and the
integral are settled symbolically, which is the difference between
knowing a property and having sampled it. The two identities carry a
range for the sake of the computation rather than the mathematics:
stated over the whole line both are proven all the same, and the
difference shows one row down, on the symmetry identity's `[float]`
companion, which runs this code at the corners of the domain and is
falsified where `math.exp(-x)` overflows, below about `x = -709.78`
(the derivative identity, a calculus form, spawns no companion):

<!-- example: sigmoid-whole-line run -->
```python
import mathema
from mathema.lexicon import logistic_standard

rec = mathema.check(logistic_standard, claims=["f(-x) == 1 - f(x)"])
for p in rec.probes:
    print(f"{p.name:22} {p.verdict:9} {p.counterexample or p.condition or ''}")
```

<!-- example: sigmoid-whole-line output -->
```text
f_x_eq_1_f_x           proven    ∀ x ∈ ℝ
f_x_eq_1_f_x[float]    falsified x = -1.79769e+308
missing[x]             holds
```

The proof is over ℝ, with infinity as infinity, and the companion says
what the computation does out at the corner it was run to. The range
in the claims above is one way to make both rows hold; `let |inf| be
700` on the whole-line claim is the other, since the companion then
runs the unbounded directions out to `700`, where this code still
returns, and the proof is the same proof over ℝ either way.

### Where it gets interesting: a true claim that falsifies

The sigmoid is bounded strictly between zero and one. Every textbook
says so, and it is true of the mathematics. State it unquantified and
mathema disagrees:

| claim | verdict | witness |
|---|---|---|
| `f(x) > 0` | falsified | `x = -1e6` raised `OverflowError` |
| `f(x) < 1` | falsified | `x = 1e6` returned exactly `1.0` |
| `for x in [0, 1e6], f(x) < 1` | falsified | `x = 1e6` returned exactly `1.0` |

None of these is a mathematical error, and none of them is a proof
either, which is where they part from the identities above: the strict
bounds are the one thing on this page the derive route cannot close
(sympy does not settle the strict positivity of `exp(x)/(exp(x) + 1)`
over the whole line, and the record lists what it tried), so each falls
through to the probe route, where a claim is decided by running the
code and the computation answers for itself. At `x = -1e6`,
`math.exp(1e6)` overflows before any division happens, and a raise is
no value, so the lower bound is falsified with that witness. The upper
bound fails a different way: at `x = 1e6`, `exp(-x)` underflows to zero
and the result saturates to exactly `1.0`, so the strict inequality
fails in float64 while remaining true in the reals, and it does so from
about `x = 36.7` onward, which is the region the bounds below stay
clear of.

This is the distinction the record is built to preserve: the
mathematics is sound and the computation is not total over the inputs
the claim quantified, and the record says which of the two it
established. Where the derive route closes the mathematics, as it does
for the identities, the proof stands over ℝ and the computation's
verdict sits on the `[float]` row beneath it; where it cannot, the
claim carries the computation's verdict, with the route that decided it
named in the record. The remedy is claims-side in both cases, an
operational infinity where the code merely stops short of infinity, or
a domain, which is usually what you meant anyway:

<!-- example: sigmoid-above-zero verdicts fn=mathema.lexicon:logistic_standard expect=proven -->
```
for x in [-30, 30], f(x) > 0
```

<!-- example: sigmoid-below-one verdicts fn=mathema.lexicon:logistic_standard expect=proven -->
```
for x in [-30, 30], f(x) < 1
```

Both **proven**, and both `[float]` companions hold, since nothing in
`[-30, 30]` overflows or saturates. A bounded domain is not a weaker
claim, it is an honest one, and the record now states the range over
which the bound was established rather than implying the whole line.

### Gradient descent, and a claim that composes

Fixed-step gradient descent on the quadratic bowl `0.5*q*t^2`
multiplies the iterate by `r = 1 - alpha*q` each step, so it converges
exactly when `|r| < 1`. That condition is a claim about the step size:

<!-- example: descent verdicts fn=mathema.lexicon:gd_convergence_factor expect=proven -->
```
for alpha in [0.01,1.9], q in [0.5,1.0], |f(alpha,q)| < 1
```

**Proven** on `gd_convergence_factor`. The claim is more useful than
the sentence it encodes, because it is attached to the code: change
the step-size policy and the claim is re-adjudicated.

## Composing: lemmas over case studies

Each claim above stands alone, which is the weakest way to use them. A
claim can rest on another through an `assuming` premise, and then the
evidence composes:

```python
from mathema.claims import check_conjectures, claim
from mathema.lexicon import logistic_standard

check_conjectures(logistic_standard, [
    claim("for x in [-30, 30], f(x) > 0", name="positive", route="derive"),
    claim("assuming positive is proven, for x in [-30, 30], f(x)*(1 - f(x)) >= 0",
          name="derivative_nonneg"),
])
```

`derivative_nonneg` is not re-deriving positivity; it is resting on it,
and the record says so. If `positive` were only sampled, a premise
that demands `is proven` would have nothing to rest on and
`derivative_nonneg` would come back `unknown`; written
`assuming positive holds`, the conclusion would be capped at `holds`
and `meta["mathema.capped_by"]` would name it. That is the property that
makes a chain trustworthy: evidence never gets stronger as it
propagates. See [Lemmas](lemmas.md) for the full behaviour.

## Finding a spelling

Every claim here is a lexicon entry, and the lexicon is browsable, so
you do not have to remember the grammar:

```python
from mathema import lexicon

lexicon.show("sigmoid_derivative")     # one entry, both renderings
lexicon.get("parity_identity")         # just the claim text
```

The entries are grouped by what they demonstrate (calculus, assuming,
domains, case studies), which makes the lexicon a reasonable first
stop when you know what you want to say but not how to spell it.

## Sources

The formulae are standard and the implementations here are mathema's
own. The references are openly licensed:

- Put-call parity, Black-Scholes model, Greeks (finance), and Logistic
  function: Wikipedia, CC BY-SA 4.0.
- Fixed-step gradient descent on a quadratic: Scientific Python
  Lectures, CC BY 4.0, "Mathematical optimization: finding minima of
  functions".
