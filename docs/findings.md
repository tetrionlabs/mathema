# See what mathema finds

Four short functions, each of the kind that passes review, and what mathema
reports about each one. Every output on this page is from a real run.

## A midpoint that only works on integers

<!-- example: finds file=mid.py -->
```python
def midpoint(a: float, b: float) -> float:
    """The point halfway between a and b."""
    return (a + b) // 2
```

A test with `assert midpoint(2, 8) == 5` passes. The claim that matters is
that a midpoint lies between its inputs, so mathema checks it over the
integers and over the reals:

<!-- example: finds run -->
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

<!-- example: finds output -->
```text
mathema.Record(midpoint) · source, no side effects · form cc66f89ce3e7
  proven    between_integers: for a in [0, 100] : int, b in [0, 100] : int, min(a, b) <= f(a, b) <= max(a, b)
           for a in [0, 100] : int, b in [0, 100] : int
  between_reals  for a in [0.0, 100.0] : float|missing, b in [0.0, 100.0] : float|missing, min(a, b) <= f(a, b) <= max(a, b)   falsified at link 1
    falsified  computation  for a in [0.0, 100.0] : float, b in [0.0, 100.0] : float, min(a, b) <= f(a, b) <= max(a, b)   counterexample link 1: min(a, b) <= f(a, b): a = 99.9999, b = 100: 99.9999 vs 99.0
    holds      policy       f(a=nan)   no missing policy stated; assumed propagates
    holds      policy       f(b=nan)   no missing policy stated; assumed propagates
```

Proven for every pair of integers in range, and falsified over the reals,
where floor division puts the midpoint of 99.9999 and 100 at 99. Under
the falsified claim, the `mathematics` line carries the counterexample,
and the two `policy` lines say what `midpoint` does with a `nan` in
either argument: nothing in the claim says, so mathema assumes the `nan`
propagates to the result, and it does. The same
claim, two domains, two different and equally definite answers, which is why a
claim always carries the domain it was checked over.

## A pole nobody sampled

<!-- example: finds run -->
```python
def discount_factor(x: float) -> float:
    """A discount factor that divides by one minus the rate."""
    return 1 / (1 - x)
```

With no claims at all, mathema runs the laws every function gets and the
safety checks that apply to this one:

<!-- example: finds run -->
```python
print(mathema.check(discount_factor))
```

<!-- example: finds output match=subset -->
```text
mathema.Record(discount_factor) · source, no side effects · form ebb4c9b87847
  falsified monotonic_increasing[x]: d(f(x), x) >= 0
           counterexample x = 1
  falsified even: f(-x) = f(x)
           counterexample x = -1
  proven    is_deterministic: f(x) = f(x)
           missing for x (float) means nan
  proven    is_defined: 1 - x != 0
  falsified is_pole_safe[x]: is_pole_safe(x)
           counterexample x = 1 is admitted by the declared domain but sits at or beside a pole: the call raised ZeroDivisionError
  falsified is_representation_safe[x]: is_representation_safe(x)
           counterexample x = 1 (the int spelling) is admitted by the declared domain but the call raised ZeroDivisionError
           [implementation:representation]
```

(trimmed from fourteen entries). Random sampling over the reals lands on
exactly `x == 1` with probability zero, so a property-based test can run this
function a thousand times and see nothing wrong. mathema solves the lifted
expression for where the denominator vanishes and then makes sure that point
is tried, which is what the route on each result records:

<!-- example: finds run -->
```python
for p in mathema.check(discount_factor).probes:
    print(f"{p.name:<26} {p.verdict:<10} {p.route}")
```

<!-- example: finds output -->
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
is_numerically_stable      holds      probe:algorithmic
is_defined                 proven     derive
is_pole_safe[x]            falsified  probe:algorithmic
is_representation_safe[x]  falsified  probe:algorithmic
```

Every falsification here carries a witness that was executed against the
function. The derive rows are witnessed by the call at the pole itself (`even`
fails at `x = -1` because `f(1)` raises), which says the claim has no value
there, not whether its mathematics holds, so they carry no tag.
`[implementation:representation]` means the mathematics was fine and the
computation fell over, here because the integer `1` is admitted by the
domain and raises. `is_defined` is the same pole seen from the other side: a
claim named `is_defined` states the region on which `f` returns, and it is
proven because `f` returns on exactly `1 - x != 0` and raises everywhere else.

## A claim that needed its domain

Put-call parity for a Black-Scholes pricer is a true identity, and mathema
[proves it](case-studies.md) over a realistic region of prices, rates,
maturities and volatilities. Stated with no domain at all:

<!-- example: parity file=options.py -->
```python
import math

def put_call_parity_gap(s: float, k: float, r: float, t: float,
                        sigma: float) -> float:
    """A European call minus a European put on the same strike."""
    root_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * root_t)
    d2 = d1 - sigma * root_t
    phi = lambda z: 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    call = s * phi(d1) - k * math.exp(-r * t) * phi(d2)
    put = k * math.exp(-r * t) * phi(-d2) - s * phi(-d1)
    return call - put
```

<!-- example: parity run -->
```bash
mathema check options.py --claim "f(s,k,r,t,sigma) == s - k*exp(-r*t)"
```

<!-- example: parity output -->
```text
FAIL options.put_call_parity_gap: source, no side effects; claims 1/1 checked (0 proven, 0 holds, 1 falsified)  <- 1 falsified claim(s)
```

The counterexample is `s = 1, k = 1, r = 1, t = -1, sigma = 1`, a negative
maturity at which `math.sqrt(t)` raises. A claim with no domain covers every real input, and
mathema will not assume the range you had in mind; the domain is part of the
claim, and stating it is what turns this `falsified` into `proven`.

## An order that matters

<!-- example: finds run -->
```python
def ema(x: list[float], alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y
```

<!-- example: finds run -->
```python
print(mathema.check(ema))
```

Among the results, all found with no claims written:

<!-- example: finds output match=subset -->
```text
  bounded_lower  min(x) <= f(x, alpha)   falsified at x = [-9.289026277385481, -6.259440531196718, -5.362151093286329, 8.0426640110414], alpha = -1
    falsified  computation  min(x) <= f(x, alpha)   counterexample x = [-9.289026277385481, -6.259440531196718, -5.362151093286329, 8.0426640110414], alpha = -1: -9.289026277385481 vs -46.592809918765724
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  permutation_invariant  let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)   falsified at x = [1e+16, -1e+16], alpha = -0.5847481298766866
    falsified  computation  let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)   counterexample x = [1e+16, -1e+16], alpha = -0.5847481298766866: 2.1694962597533732e+16 vs -2.1694962597533732e+16
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  scale_equivariant  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)   falsified at x = [-1.7976931348623157e+308, -1.7976931348623157e+308, -1.7976931348623157e+308], alpha = -1.7976931348623157e+308, c = -5
    proven     mathematics  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)
    falsified  computation  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)   counterexample x = [-1.7976931348623157e+308, -1.7976931348623157e+308, -1.7976931348623157e+308], alpha = -1.7976931348623157e+308, c = -5
                            [mathematics sound, implementation:numerical-instability]
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  translation_equivariant  let g = mathema.f.shift_seq, let c be [-5.0, 5.0], c + f(x, alpha) = f(g(x, c), alpha)   falsified at x = [0.0, 0.0, 0.0], alpha = -1.7976931348623157e+308, c = -5
    proven     mathematics  let g = mathema.f.shift_seq, let c be [-5.0, 5.0], c + f(x, alpha) = f(g(x, c), alpha)
    falsified  computation  let g = mathema.f.shift_seq, let c be [-5.0, 5.0], c + f(x, alpha) = f(g(x, c), alpha)   counterexample x = [0.0, 0.0, 0.0], alpha = -1.7976931348623157e+308, c = -5
                            [mathematics sound, implementation:numerical-instability]
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
```

Scaling or shifting every input scales or shifts the average the same way:
the `mathematics` line of each equivariance is proven for sequences of any
length. The bound fails because nothing restricts `alpha` to `[0, 1]`, and
outside that range this is not a weighted average at all, which is a finding
about the missing domain rather than the loop. Reversing the input changes
the answer, as it should for an average that weights recent values more
heavily: mathema does not know that is intended, so it reports the
counterexample and leaves the judgement to a person. Every claim over `x`
also fails at the empty list, on its `policy` line, because `ema` reads
`x[0]` first.

The `computation` line under each equivariance runs the proven law through
the real code in floating point, where nothing bounds the inputs, so it
reaches elements and an `alpha` at float64's extremes, about `1.8e+308` in
size. There the loop's arithmetic overflows and subtracts one infinity from
another, so both sides of the law come out NaN, and a NaN is no value: it
agrees with nothing, not even the other side's NaN. The mathematics is sound
and the float code does not follow it out there; a domain for `alpha`, or a
`let |inf| be ...` binding, is the fix.

[A first look](first-look.md) takes `ema` through domains, both evidence
routes and the stored record.
