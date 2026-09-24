# mathema

*Know what your code actually guarantees.*

AI has changed the cost of producing code without changing the cost of knowing
whether that code is correct, and so more of it now arrives than anyone can
review line by line. **mathema** adds a verification layer between generated
code and accepted code: you state what a function is supposed to do as an
explicit claim, and mathema checks it against the real function, proving it
outright where the mathematics permits and gathering reported evidence where
it does not. What comes back is a durable record of what has been established,
how, and whether it still applies to the code in front of you.

Nothing is asserted and nothing is quietly upgraded. Evidence remains
evidence, proof remains proof, and a claim that nothing could settle remains
unresolved and says so.

The name is Greek: μάθημα, a thing learned.

## See it in action

Here is a European call minus a European put on the same strike, both legs
priced by Black-Scholes, with a square root, a logarithm, an exponential and
the Gaussian CDF expressed through `math.erf`:

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

Put-call parity says that difference collapses to `S - K*exp(-r*T)`, whatever
the volatility, which is a surprising thing to say about a function where
`sigma` appears five times. State it as a claim over the region it should hold
on:

```bash
mathema check options.py --claim "for s in [50,150], k in [50,150], \
    r in [0.0,0.1], t in [0.1,2], sigma in [0.05,0.8], \
    f(s,k,r,t,sigma) == s - k*exp(-r*t)"
```

```text
ok   options.put_call_parity_gap: source, no side effects; claims 1/1 adjudicated (1 proven, 0 holds, 0 falsified)
```

Everything before the last comma is the domain and everything after it is the
law, with `f` standing for the function under test. `[0.1,2]` is a
mathematical interval rather than a two-element Python list, so the claim
covers every real value in it, and mathema lifted the body to a symbolic
expression in which both Gaussian terms cancel and `sigma` disappears,
establishing the identity for the whole region at once. The
[claim grammar](https://mathema.tetrionlabs.com/grammar/) has the full
notation.

The domain is doing real work: drop it and the same claim comes back
`falsified`, with a counterexample at a negative maturity where `math.sqrt(t)`
raises, because a claim with no domain covers every real input, including ones
the function was never meant to take. A claim without its domain is a
different claim, and mathema says so rather than assuming the range you had in
mind.

## Proof is not the same as testing

A test demonstrates behaviour at the inputs you chose, and a property-based
test at many inputs you did not, but neither can say anything about the
uncountably many points of `[0.1,2]` it never visited. mathema keeps four
verdicts apart so you always know which kind of answer you have:

| Verdict | Means |
|---|---|
| `proven` | established mathematically over the claim's stated domain |
| `holds (n=...)` | survived exactly `n` behavioural trials, which is evidence, not proof |
| `falsified` | a counterexample was found by running the function, and is kept |
| `skipped` | no available route could settle it, and the record says so |

The same distinction reaches claims no amount of test-running could establish.
Four defining properties of the logistic function include a limit at infinity and an
improper integral over the whole real line, and all four come back proven:

```python
def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
```

```bash
mathema check sigmoid.py \
    --claim "d(f(x), x) == f(x)*(1 - f(x))" \
    --claim "f(-x) == 1 - f(x)" \
    --claim "lim(f(x), x -> oo) == 1" \
    --claim "∫(d(f(x), x), x, -oo, oo) == 1"
```

```text
ok   sigmoid.logistic: source, no side effects; claims 4/4 adjudicated (4 proven, 0 holds, 0 falsified)
```

## When the code is wrong

Proving a good function correct is the easy half, and the question that
matters more is whether a bad one gets caught. Here is a discount factor with a
pole hiding in it, checked with no claims at all, only mathema's built-in laws:

```python
def discount_factor(x: float) -> float:
    """A discount factor that divides by one minus the rate."""
    return 1 / (1 - x)

print(mathema.check(discount_factor))
```

```text
mathema.Record(discount_factor) · source, no side effects · form 8b1b8ec14a11
  FALSIFY monotonic_increasing[x]: d(f(x), x) >= 0
           counterexample x = 1
  FALSIFY even: f(-x) = f(x)
           counterexample x=-1.17273e+09
           [mathematics unsound, blame claim]
  proven  is_deterministic: f(x) = f(x)
  FALSIFY is_pole_safe[x]: is_pole_safe(x)
           counterexample x = 1 is admitted by the declared domain but sits at or beside a pole: the call raised ZeroDivisionError
  FALSIFY is_representation_safe[x]: is_representation_safe(x)
           counterexample x = 1 (the int spelling) is admitted by the declared domain but the call raised ZeroDivisionError
           [implementation:representation]
```

(trimmed from fourteen claims). The pole was not found by luck: uniform random
sampling lands exactly on `x == 1` with probability zero, so a property-based
run can pass a thousand trials here and report nothing, whereas mathema solves
the lifted expression for where the denominator vanishes and makes sure that
point is tried. Every falsification rests on an executed witness, never on a
symbolic argument alone, and the bracketed tags keep a claim that was simply
untrue (`even`) apart from an implementation that fell over (the integer `1`
raising where the domain admits it).

## Built for AI-assisted development

An agent can write the code and propose the claims, but mathema reserves the
decisions that turn a verdict into an accepted fact for a person, so the agent
never gets to mark its own homework:

```text
agent proposes a claim
        ↓
mathema adjudicates it against the real function
        ↓
a person accepts the verdict            (mathema accept)
        ↓
the function is locked                  (mathema lock)
```

No tool exposed over MCP accepts a verdict from its caller, and claim
expressions are validated against a strict AST whitelist before they run, so
a claim from an untrusted source is safe to check. `mathema accept` prints the
exact write before making it, and lets a person accept evidence as sufficient,
own a residual risk explicitly, or correct a claim the falsification showed
was wrong (the correction is itself adjudicated first). An agent may lock a
function it has finished; only a person can unlock one, behind a prompt and
optionally a PIN, with deliberately no `--yes` flag.

## Verification that survives code changes

Every verdict binds to the exact code that earned it, through two identity
hashes: `form`, over the AST structure with names and formatting normalised
away, and `sig`, over the parameter shape. `mathema.write_spec` writes the
record as standalone YAML under `.mathema/verified/`, and `mathema verify`
later re-checks every record whose function, or a function it depends on, has
changed since, so a verification result cannot quietly outlive the
implementation it describes the way a test result does the moment nobody
re-runs it. A locked
function fails verification the moment its body changes, though docstring
edits stay allowed.

mathema is fully offline and no core function makes a network call, so none of
this sends your source or your claims anywhere.

## Audit a codebase you didn't write

`mathema audit` reads a whole package without running anything and gives every
function a row: its location as a ready-made `sed -n` line range, its
branching, whether it carries claims, whether the derive route could prove
things about it, the state outside its parameters it reads or writes, whether
a test report covers it, and how well its docstring states its intent. Over
mathema's own source (`mathema audit mathema --root .`) the summary line is
honest about where things stand:

```text
0/1258 claimed, 26/1258 derivable, 26/1258 lift unconditionally, 516/1258 fully typed, 3096/6101 docstring quality criteria met, no coverage.json/.coverage report found (try `python -m coverage run -m pytest && python -m coverage json`), 277/1258 depend on state outside their own parameters (see the global_vars/unresolved columns), mean docsync 45%.
```

`mathema audit --index` writes the same map to `.mathema/index.yaml`, with each
module's stated intent and every function's file, line and span, which is the
fastest way to hand an agent a codebase without letting it grep its way around.

## Beyond tests

| | Unit tests | Property-based testing | Proof assistants and SMT solvers | mathema |
|---|:-:|:-:|:-:|:-:|
| Checks the examples you chose | ✓ | ✓ | | ✓ |
| Checks many generated inputs | | ✓ | | ✓ |
| Proves a claim over its whole domain | | | ✓ | ✓ where the function lifts |
| Works on ordinary Python, no separate specification language | ✓ | ✓ | | ✓ |
| Keeps a record bound to the exact code it verified | | | ✓ | ✓ |
| Routes each claim to whatever method can settle it | | | | ✓ |

None of these replaces the others, and mathema's probe route is the same idea
as Hypothesis. What mathema adds is the place where a property check, a real
proof attempt and a durable record meet on the same claim, with the claim
routed automatically to whichever method the function's shape can support, and
`skipped` reported plainly the moment none can.

## Measuring a codebase

A codebase can have every line exercised by tests while having very little of
its intent stated or verified, so mathema measures those separately rather
than folding them into one coverage number. `mathema badges` reports
implementation (how much code a test, probe or proof actually reached), intent
(how much of what the docstrings promise is claimed and verified) and clarity
(how much is known about the behaviour, falsifications included), drawn as a
triangle whose area is the overall score. An illustrative example:

```text
        CLARITY 44
              ◆
             · ·
            ·   ·
           ·     ·
          ·       ·
         ·         ·
        ·           ·
       ·             ·
      ·       ●       ·
     ·      ···        ·
    ·     ······        ·
   ·   ·········         ·
  ·  ············         ·
 · ···············         ·
●·············+···●·········◆
  IMPL 100           INTENT 26
        overall 28
```

That project reaches every line and still leaves most of what it
promises unpinned, which the area shows as 28 where an average would have
said 57. The [badges reference](https://mathema.tetrionlabs.com/modes/badges/)
covers how each score is computed and what to expect of them.

## API

```python
import mathema

def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y

mathema.check(ema)                                  # built-in algebraic laws
mathema.check(ema, claims=["f(x, 1.0) == x[-1]"])   # your own claim
mathema.check(ema, domain={"alpha": (0, 1)})        # probe inside a domain
mathema.write_spec(ema, claims=[...])               # check, then write the record
mathema.status()                                    # fresh or stale, per tracked function
```

Without anyone reading the code, the first call reports that the result is
deterministic and numerically stable, that scaling or shifting every element
of `x` scales or shifts the result the same way, and that reordering `x` does
*not* leave it unchanged, with the counterexample kept. The
[API reference](https://mathema.tetrionlabs.com/api/) has the rest.

## CI

```bash
mathema check model.py --domain alpha=0:1 --strict     # exit 1 on failure
mathema check model.py --format junit --output claims.xml
mathema verify                                         # re-check what changed
```

`--format github` and `--format json` are also available, and worked pipeline
configs for GitHub Actions and GitLab are in [examples/ci/](examples/ci/).

## Install

mathema needs Python 3.10 or newer. Install it inside an active virtual
environment (`python3 -m venv .venv && source .venv/bin/activate`, or your
usual equivalent) rather than against a system Python:

```bash
pip install mathema           # core: the derive route and the spec store
pip install "mathema[all]"    # numpy, z3, MCP server, coverage
```

The extras can also be taken one at a time: `mcp` exposes mathema's tools to
an agent, `smt` adds z3 as a fallback decision procedure, `numpy` enables
array-shaped claims and `symbology` adds conventional notation.

## Documentation

- **[Quick start](https://mathema.tetrionlabs.com/quickstart/)**: five minutes,
  one function, and a claim that goes from falsified to proven.
- [Claim-driven development](https://mathema.tetrionlabs.com/cdd/): the
  vocabulary every mode assumes, including what separates `proven` from `holds`.
- [The claim grammar](https://mathema.tetrionlabs.com/grammar/): everything you
  can say in a claim, with a runnable example of each.
- [The derive route](https://mathema.tetrionlabs.com/derive-route/): which
  function shapes can reach `proven`, and what happens to the ones that cannot.
- [Case studies](https://mathema.tetrionlabs.com/case-studies/): put-call
  parity, the Greeks, and the sigmoid worked end to end.

The full documentation, including the command reference, is at
**[mathema.tetrionlabs.com](https://mathema.tetrionlabs.com)**.

mathema is at 0.6.0 and pre-1.0, feature-complete for its current scope and
covered by over 2,500 tests; the claim grammar and record format are settled by
the spec, but the Python API is likely to change before 1.0.

## Related projects

[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development)
is the specification mathema implements (v0.2: the claim tuple, the claim
families and the YAML record schema), maintained independently under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), so anything
that reads or writes that shape interoperates with mathema's records without
importing it. `mathema.SPEC_VERSION` states the targeted version and every
record stamps it. [mathema-symbology](https://github.com/tetrionlabs/mathema-symbology)
renders claims in a field's conventional notation, and
[mathema-agents](https://github.com/tetrionlabs/mathema-agents) teaches coding
agents to drive the claim loop properly, vendored by an explicit, opt-in
`mathema init --agents`.

See also [CHANGELOG.md](CHANGELOG.md), [CONTRIBUTING.md](CONTRIBUTING.md),
[SECURITY.md](SECURITY.md) and [SUPPORT.md](SUPPORT.md).

## Licensing

mathema is source-available under the [Business Source License
1.1](LICENSE.md). Production use is free for organisations under USD 10M
revenue or using it in at most three repositories, and for research, teaching
and evaluation, and every released version converts to AGPL-3.0-or-later four
years after its release. See [LICENSING.md](LICENSING.md) for the
plain-language version.
