# See what mathema finds

Four short functions, each of the kind that passes review, and what mathema
reports about each one. Every output on this page is from a real run.

## A midpoint that only works on integers

```python
def midpoint(a: float, b: float) -> float:
    """The point halfway between a and b."""
    return (a + b) // 2
```

A test with `assert midpoint(2, 8) == 5` passes. The claim that matters is
that a midpoint lies between its inputs, so mathema checks it over the
integers and over the reals:

```python
import mathema
from mid import midpoint

print(mathema.check(midpoint, claims=[
    mathema.claim("for a in [0, 100] subset Z, b in [0, 100] subset Z, "
                  "min(a, b) <= f(a, b) <= max(a, b)", name="between_integers"),
    mathema.claim("for a in [0, 100], b in [0, 100], "
                  "min(a, b) <= f(a, b) <= max(a, b)", name="between_reals"),
]))
```

```text
mathema.Record(midpoint) · source, no side effects · form cc66f89ce3e7
  proven  between_integers: for a in [0, 100]:int|missing, b in [0, 100]:int|missing, min(a, b) ≤ f(a, b) ≤ max(a, b)
           for a in [0, 100]:int|missing, b in [0, 100]:int|missing
  FALSIFY between_reals: for a in [0.0, 100.0]:float|missing, b in [0.0, 100.0]:float|missing, min(a, b) <= f(a, b) <= max(a, b)
           counterexample link 1: min(a, b) <= f(a, b): (99.9999, 100): 99.9999 vs 99.0
```

Proven for every pair of integers in range, and falsified over the reals,
where floor division puts the midpoint of 99.9999 and 100 at 99. The same
claim, two domains, two different and equally definite answers, which is why a
claim always carries the domain it was checked over.

## A pole nobody sampled

```python
def discount_factor(x: float) -> float:
    """A discount factor that divides by one minus the rate."""
    return 1 / (1 - x)
```

With no claims at all, mathema runs the laws every function gets and the
safety checks that apply to this one:

```python
print(mathema.check(discount_factor))
```

```text
mathema.Record(discount_factor) · source, no side effects · form ebb4c9b87847
  FALSIFY monotonic_increasing[x]: d(f(x), x) >= 0
           counterexample x = 1
  FALSIFY even: f(-x) = f(x)
           counterexample x = -1
  proven  is_deterministic: f(x) = f(x)
  proven  is_defined: 1 - x != 0
  FALSIFY is_pole_safe[x]: is_pole_safe(x)
           counterexample x = 1 is admitted by the declared domain but sits at or beside a pole: the call raised ZeroDivisionError
  FALSIFY is_representation_safe[x]: is_representation_safe(x)
           counterexample x = 1 (the int spelling) is admitted by the declared domain but the call raised ZeroDivisionError
           [implementation:representation]
```

(trimmed from fourteen entries). Random sampling over the reals lands on
exactly `x == 1` with probability zero, so a property-based test can run this
function a thousand times and see nothing wrong. mathema solves the lifted
expression for where the denominator vanishes and then makes sure that point
is tried, which is what the route on each result records:

```python
for p in mathema.check(discount_factor).probes:
    print(f"{p.name:<26} {p.verdict:<10} {p.route}")
```

```text
monotonic_increasing[x]    falsified  derive
monotonic_decreasing[x]    falsified  derive
affine[x]                  falsified  derive
convex[x]                  falsified  derive
concave[x]                 falsified  derive
even                       falsified  derive
odd                        falsified  derive
idempotent                 falsified  derive
is_deterministic           proven     examine
is_state_safe              proven     examine
is_numerically_stable      falsified  probe:semi_analytical
is_defined                 proven     derive
is_pole_safe[x]            falsified  probe:algorithmic
is_representation_safe[x]  falsified  probe:algorithmic
```

Every falsification here carries a witness that was executed against the
function. The derive rows are witnessed by the call at the pole itself (`even`
fails at `x = -1` because `f(1)` raises), which says the claim has no value
there, not whether its mathematics holds, so they carry no tag.
`[implementation:representation]` means the mathematics was fine and the
implementation fell over, here because the integer `1` is admitted by the
domain and raises. `is_defined` is the same pole seen from the other side: a
claim named `is_defined` states the region on which `f` returns, and it is
proven because `f` returns on exactly `1 - x != 0` and raises everywhere else.

## A claim that needed its domain

Put-call parity for a Black-Scholes pricer is a true identity, and mathema
[proves it](case-studies.md) over a realistic region of prices, rates,
maturities and volatilities. Stated with no domain at all:

```bash
mathema check options.py --claim "f(s,k,r,t,sigma) == s - k*exp(-r*t)"
```

```text
FAIL options.put_call_parity_gap: source, no side effects; claims 1/2 adjudicated (0 proven, 0 holds, 1 falsified, 1 skipped)  <- 1 falsified claim(s)
```

The counterexample is `s = 1, k = 1, r = 1, t = -1, sigma = 1`, a negative
maturity at which `math.sqrt(t)` raises. A claim with no domain covers every real input, and
mathema will not assume the range you had in mind; the domain is part of the
claim, and stating it is what turns this `falsified` into `proven`.

## An order that matters

```python
def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y
```

```python
print(mathema.check(ema))
```

Among the results, all found with no claims written:

```text
  FALSIFY bounded_lower: min(x) <= f(x, alpha)
           counterexample ([2.01488, 3.30692, -6.39418, 3.78355, 6.96564, 7.97935], -9.1034): -6.39418363288563 vs -45761.14174665739
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([6.22429, 5.95714, 3.98826, -6.56235, 7.20359, 1.66103, -8.45295], -5.87836): 78066.38231536481 vs -1129152.7241483687
  proven  scale_equivariant: let g = mathema.f.scale_seq, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
  proven  translation_equivariant: let g = mathema.f.shift_seq, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
```

Scaling or shifting every input scales or shifts the average the same way,
proven for sequences of any length. The bound fails because nothing restricts
`alpha` to `[0, 1]`, and outside that range this is not a weighted average at
all, which is a finding about the missing domain rather than the loop. And
reversing the input changes the answer, as it should for an average that
weights recent values more heavily: mathema does not know that is intended, so
it reports the counterexample and leaves the judgement to a person.

[A first look](first-look.md) takes `ema` through domains, both evidence
routes and the stored record.
