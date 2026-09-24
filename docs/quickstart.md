# Quick start

Five minutes, one function, and a claim that goes from falsified to
proven. Everything below is real output from a fresh install, so you
can follow along by pasting it.

## Install

Work inside a virtual environment rather than against a system Python:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install mathema
```

mathema is fully offline. The one command that reaches the network is
`mathema init --agents`, which you run by name to fetch the optional agent
tooling with `git`. There is no account and no API key, and the only required dependencies are
sympy for the symbolic route and pyyaml for the record store.

## Write a function

Put this in `pricing.py`:

<!-- example: falsify file=pricing.py -->
```python
def discounted(price: float, rate: float) -> float:
    """The price after applying a discount rate."""
    return price * (1 - rate)
```

## State a claim about it

A claim is a specific, checkable statement about what the function
does. The obvious one here is that discounting never makes something
more expensive:

<!-- example: falsify run -->
```bash
mathema check pricing.py:discounted --claim "for rate in [0, 1], f(price, rate) <= price"
```

<!-- example: falsify output -->
```text
FAIL pricing.discounted: source, no side effects; claims 1/1 adjudicated (0 proven, 0 holds, 1 falsified)  <- 1 falsified claim(s)
```

Falsified, on the first try. That is not a bad start, it is the point.
Asking for the counterexample says why:

<!-- example: falsify run -->
```python
import mathema
from pricing import discounted

(p,) = mathema.claims.check_conjectures(
    discounted,
    [mathema.claim("for rate in [0, 1], f(price, rate) <= price",
                   name="never_raises_price")])
print(p.verdict, p.counterexample)
```

<!-- example: falsify output -->
```text
falsified price=-8.76733e+09, rate=0.363721
```

The claim is wrong, not the code. A negative price multiplied by
something smaller than one gets *larger*, and the claim never said
prices are positive. mathema found the gap by looking, not by being
told where to look.

## Fix the claim

Say the thing the claim was assuming:

<!-- example: falsify run -->
```python
(p,) = mathema.claims.check_conjectures(
    discounted,
    [mathema.claim("for price in [0, 1e6], rate in [0, 1], f(price, rate) <= price",
                   name="never_raises_price")])
print(p.verdict)
print(p.condition)
```

<!-- example: falsify output -->
```text
proven
where x=price, y=rate: ∀ x ∈ [0.0, 1000000.0] ⊂ ℝ ∪ {∅}, y ∈ [0.0, 1.0] ⊂ ℝ ∪ {∅}
```

`proven`, not `holds`. mathema did not run `discounted` on a thousand
random prices and shrug, it lifted the body to a symbolic expression
and decided the inequality algebraically, so the result covers every
price in that range rather than the ones a sampler happened to pick.
The region it proved over is printed back explicitly, including the
`∪ {∅}` that says a missing value is part of the declared input space.

That difference is the whole idea: `holds` is evidence, `proven` is
proof, and mathema always tells you which one you have. The full
ladder is in [verdicts and evidence](cdd.md).

## Move it into the code

A claim is worth more next to the function than in a shell history.
Put it in the docstring:

<!-- example: docstring file=pricing.py -->
```python
def discounted(price: float, rate: float) -> float:
    """The price after applying a discount rate.

    Claims:
        never_raises_price: for price in [0, 1e6], rate in [0, 1], f(price, rate) <= price
    """
    return price * (1 - rate)
```

<!-- example: docstring run -->
```bash
mathema check pricing.py
```

<!-- example: docstring output -->
```text
ok   pricing.discounted: source, no side effects; claims 2/2 adjudicated (1 proven, 1 holds, 0 falsified)
```

The second claim is the proof's `[float]` companion: every claim the derive
route proves also runs through the real code in floating point, since a
proof is about the mathematics and whether the implementation keeps up in
f64 is a separate question. See [the evidence ladder](evidence-ladder.md).

The docstring is one of four places a claim can live, alongside a
decorator, a claims file, and an annotation. See [authoring
claims](authoring.md) for the precedence order between them.

## Keep the record

<!-- example: docstring run -->
```python
import mathema
from pricing import discounted

mathema.write_spec(discounted)
print(open(".mathema/verified/pricing.discounted.yaml").read())
```

That writes `.mathema/verified/pricing.discounted.yaml`, which is the
durable artifact: the claim, its verdict, the region it was proved
over, the proof sketch, the float companion's row, and the identity hash
it binds to (an excerpt):

<!-- example: docstring output match=subset -->
```yaml
# machine record; binds to form d2ab6eef1b84
pricing.discounted:
  identity:
    form: "d2ab6eef1b84"
  claims:
    - name: "never_raises_price"
      statement: "for price in [0.0, 1000000.0]:float|missing, rate in [0.0, 1.0]:float|missing, f(price, rate) <= price"
      verdict: "proven"
      sketch: "interval evaluation over the declared domain: price*rate ∈ AccumBounds(0, 1000000), never negative"
      condition: "where x=price, y=rate: ∀ x ∈ [0.0, 1000000.0] ⊂ ℝ ∪ {∅}, y ∈ [0.0, 1.0] ⊂ ℝ ∪ {∅}"
      route: "derive"
      authored:
        surface: "docstring"
        ref: "pricing.discounted:docstring:L1"
        route: "best"
    - name: "never_raises_price[float]"
      statement: "for price in [0.0, 1000000.0]:float|missing, rate in [0.0, 1.0]:float|missing, f(price, rate) <= price"
      verdict: "holds"
      n: 44
      note: "the implementation of never_raises_price, executed in float at 44 points (every domain corner, then sampled interior points)"
      route: "probe"
```

The record binds to `form`, a hash of the function's *structure*, so
renaming a variable or reformatting the body leaves it valid while a
real change to behaviour marks it stale. Commit `.mathema/` along with
your code: the evidence should travel with the thing it is evidence
about.

## Check it in CI

```bash
mathema verify
```

`verify` re-adjudicates every recorded function whose form hash moved,
and exits 1 if a claim is falsified, unknown, skipped, or accepted as
risk (`--lenient` lets the last two through, named in the report), so
it drops into a pipeline exactly where
a test runner would. Exit code
2 means mathema could not run at all, which is worth keeping distinct
from a real finding. See [exit codes](cdd.md#exit-codes).

You do not have to write the workflow yourself:
`mathema init --ci` scaffolds the GitHub Actions verify gate (or
`--ci gitlab` the GitLab fragment) with the install step marked for
your project, see [mathema init](modes/init.md#the-ci-gate-ci).

## Where to go next

- [Tutorial: the CDD loop](tutorial.md) walks the full cycle, including
  what to do with a falsification you disagree with.
- [Writing claims](authoring.md) covers the four authoring surfaces.
- [The claim grammar](grammar.md) is the reference for everything you
  can say in a claim, with a runnable example of each.
- [The derive route](derive-route.md) explains exactly which function
  shapes can reach `proven`, and what happens to the ones that cannot.
