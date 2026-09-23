# mathema

*Claim-Driven Development: turn software intent into verifiable evidence.*

More code is being written by AI than ever, faster than any human can review
it line by line, and the harder problem is not generating it but knowing what
it actually does. mathema gives a function a verification layer: it reads the
structure straight off the AST, probes real behaviour on seeded inputs against
built-in algebraic laws and any claim you state, and, where the mathematics
permits, proves a claim outright rather than sampling it. What comes back is a
durable record of what has been established about a function, how it was
established, and whether that evidence still applies to the code you have in
front of you today.

Nothing is asserted and nothing is quietly upgraded. A sampled result is
reported as evidence with its trial count, a mathematical result is reported
as proven, and a claim that neither route can settle stays unresolved and says
so. Every verdict binds to the exact code that earned it, so a record outlives
the implementation it describes without silently going stale under it.

The name is Greek: μάθημα, a thing learned. A function is trusted exactly to
the extent of its verified claims.

## Start with something hard

Here is a European call minus a European put on the same strike, both legs
priced by Black-Scholes, which is about as far from a toy as an ordinary
Python function gets. It has a square root, a logarithm, an exponential, a
lambda, and the Gaussian CDF expressed through `math.erf`.

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

Put-call parity says that difference collapses to `S - K*exp(-r*T)`, and that
it does so independently of volatility, which is a genuinely surprising
statement about a function where `sigma` appears five times. State it as a
claim, over the domain it is meant to hold on:

```bash
mathema check options.py --claim "for s in [50,150], k in [50,150], \
    r in [0.0,0.1], t in [0.1,2], sigma in [0.05,0.8], \
    f(s,k,r,t,sigma) == s - k*exp(-r*t)"
```

```text
ok   options.put_call_parity_gap: tier 2, claims 1/2 adjudicated (1 proven, 0 hold, 0 refuted, 1 unverifiable)
```

`proven`, not `holds`. mathema lifted the body to a symbolic expression, at
which point both Gaussian terms cancelled and `sigma` disappeared entirely,
leaving `s - k*exp(-r*t)`. The identity is established for every point in that
domain rather than checked at a few thousand of them, and no amount of
sampling would have told you the same thing.

The domain is doing real work there, and dropping it is instructive: without
it the same claim comes back `falsified`, because nothing then stops `sigma`
being zero, where `d1` divides by zero and the function is undefined. A claim
without its domain is a different claim, and mathema will tell you so rather
than quietly assuming the range you had in mind.

## Calculus, not just algebra

The derive route understands derivatives, limits and integrals, so a
specification can be written the way the mathematics is actually stated. The
standard logistic function is one line of Python:

```python
def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
```

and its defining properties are four claims:

```bash
mathema check sigmoid.py \
    --claim "d(f(x), x) == f(x)*(1 - f(x))" \
    --claim "f(-x) == 1 - f(x)" \
    --claim "lim(f(x), x, oo) == 1" \
    --claim "integrate(d(f(x), x), x, -oo, oo) == 1"
```

```text
ok   sigmoid.logistic: tier 2, claims 4/4 adjudicated (4 proven, 0 hold, 0 refuted)
```

All four proven, including a limit at infinity and an improper integral over
the whole real line, neither of which any amount of test-running could
establish. The notation accepts the symbols the domain actually uses, so `∂`
works wherever `d` does and a partial derivative reads as one.

## When the answer is no, and how it gets found

Proving a good function correct is the easy half. The interesting question is
whether a bad one gets caught, and this is where the probe route stops being
random sampling. Consider a discount factor with a pole hiding in it:

```python
def discount_factor(x: float) -> float:
    """A discount factor that divides by one minus the rate."""
    return 1 / (1 - x)
```

```python
print(mathema.check(discount_factor))
```

```text
mathema.Record(discount_factor) · tier 2 · form 8b1b8ec14a11
  FALSIFY monotonic_increasing[x]: d(f(x), x) >= 0
           counterexample x = 1
  FALSIFY convex[x]: d(f(x), x, x) >= 0
           counterexample x = 1
  FALSIFY even: f(-x) = f(x)
           counterexample x=-1.17273e+09
           [mathematics unsound, blame claim]
  proven  is_deterministic: f(x) = f(x)
  FALSIFY is_numerically_stable: let g = mathema.f.finite_no_error, g(f, x) = 1
           counterexample (1): 0 vs 1
  FALSIFY is_pole_safe[x]: is_pole_safe(x)
           counterexample x = 1 is admitted by the declared domain but sits at
           or beside a pole: the call raised ZeroDivisionError
  FALSIFY is_representation_safe[x]: is_representation_safe(x)
           counterexample x = 1 (the int spelling) is admitted by the declared
           domain but the call raised ZeroDivisionError
           [implementation:representation]
```

(trimmed: fourteen claims were adjudicated in total). Each probe also carries
the route that settled it, which the summary render leaves out:

```python
for p in mathema.check(discount_factor).probes:
    print(f"{p.name:<26} {p.verdict:<10} {p.route}")
```

```text
monotonic_increasing[x]    falsified  derive
is_deterministic           proven     examine
is_numerically_stable      falsified  probe:semi_analytical
is_pole_safe[x]            falsified  probe:algorithmic
is_representation_safe[x]  falsified  probe:algorithmic
```

The pole was not found by luck, which is the part worth dwelling on. Uniform
random sampling over the reals lands exactly on `x == 1` with probability zero,
so a property-based run can pass a thousand trials on this function and report
nothing at all, whereas mathema solves the lifted expression for where the
denominator vanishes and then guarantees that point is sampled in its own right
rather than diluted among the ordinary draws. That collaboration is what the
`probe:semi_analytical` route is naming, namely symbolic work deciding where to
look and execution confirming what actually happens when you get there.

The naming carries more weight than it first appears, because a falsification
in mathema always rests on an executed witness. When the derive route
symbolically disproves a claim the proof's own witness is used to seed a search
against the real function, and only a counterexample that genuinely reproduces
earns the verdict `falsified`; a symbolic disproof that nothing can reproduce
comes back as `unknown` and flagged instead, on the reasoning that it points at
a bug in the engine rather than a fault in your code, and the record should
neither assert the falsification nor quietly drop the fact that it was claimed.

The int spelling is a smaller point but the same instinct, since the integer
`1` and the float `1.0` are the same number and not the same call, and the
declared domain admits both, so `is_representation_safe` checks it as a case of
its own rather than assuming the float stands in for it.

Then there are the bracketed tags, which are the record's two strata and exist
to keep a false claim apart from a broken function. `[mathematics unsound,
blame claim]` on `even` means the code is fine and the claim was simply untrue
of it, this function being nothing like an even function; `[implementation:
representation]` on the int spelling means the mathematics was fine and the
implementation fell over. Running those two together is how a verification
report turns into noise, so the record keeps them separate rather than leaving
it to you.

Four routes appear in that single run, namely `derive`, `examine`,
`probe:semi_analytical` and `probe:algorithmic`, because each claim goes to
whichever one can actually settle it, and the record says which one did.

## The everyday case

Most functions are not option pricers, and mathema is meant to be useful on
the ordinary ones too. Given an exponentially weighted moving average:

```python
import mathema

def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y

mathema.check(ema)                                     # built-in algebraic laws
mathema.check(ema, claims=["f(x, 1.0) == x[-1]"])      # your own claim
mathema.check(ema, domain={"alpha": (0, 1)})           # probe inside a domain
mathema.check(ema, claims=["excluding"], domain={"alpha": (0, 1)})
                                    # and check the code actually rejects
                                    # out-of-domain input
mathema.write_spec(ema, claims=[...])   # check, then write the record
mathema.analyze(ema)                    # machine-derived facts, no probing
```

Without you reading the code, mathema reports that the result is deterministic
and numerically stable across 120 seeded trials, that scaling or shifting every
element of `x` scales or shifts the result the same way, and that reordering
`x` does *not* leave the result unchanged, keeping the counterexample that
proves it, because this is a story over time rather than a set.

## Acceptance is a human act, and a function can be frozen

When an agent is writing the code this is the part that matters most, because
mathema adjudicates claims mechanically but the decisions that turn a verdict
into an accepted fact about your codebase are deliberately reserved for a
person.

No tool exposed over MCP accepts a verdict from its caller. An agent may state
a claim and mathema will adjudicate it against the real function, but the agent
cannot declare the answer, and the proposer never adjudicates its own claims:
claim expressions are validated against a strict AST whitelist before they run,
so a claim arriving from an untrusted source is safe to check without letting
the source execute anything.

`mathema accept` is the human decision layer, and it prints the exact write
before making it. Evidence can be accepted as sufficient, a residual risk can
be explicitly owned, and a falsification can be diagnosed as a discovery about
the specification rather than a defect in the code, in which case the corrected
claim is itself adjudicated against the live function before anything is
written, and a correction that falsifies is refused.

`mathema lock` pins a function's form hash, so verification fails the moment
the body changes, though docstring edits stay allowed. An agent is permitted to
lock a function; only a person can unlock one. `mathema unlock` is prompted,
verified against a PIN when one is set, and has deliberately no `--yes` flag.
The PIN is exactly what it sounds like, namely a credential a person knows and
an agent does not, and it gates both acceptance and unlock.

The effect is that an agent can do the work, propose the claims, and even
protect a function it has finished, while the decisions that would let it mark
its own homework stay on your side of the line.

## What it does

- **Structural analysis**, pure `ast` with no dependencies: loop shape, purity
  and effects, parameter kinds, per-parameter domain guards.
- **Probing**: runs the real function on seeded random inputs and checks
  built-in algebraic laws (commutativity, idempotence, boundedness, parity,
  monotonicity, equivariances) plus anything you state yourself. `holds (n=...)`
  is evidence rather than proof and `n` is reported exactly, not assumed; the
  trial budget starts higher for a structurally riskier function and drops once
  other laws checked against the same function in the same call have come back
  clean, resetting the moment any of them is falsified. A `falsified` verdict
  keeps its counterexample permanently.
- **The derive route**: where a function lifts to a closed-form sympy
  expression, a claim is proven rather than sampled, including a case-split
  fallback across a pole or domain boundary sympy cannot resolve in one shot.
  `extensive=True` widens the search at real, opt-in cost and is off by default
  everywhere.
- **The conjecture pipeline**: state a claim as one string (`"f(-x) == -f(x)"`)
  or as a `Conjecture`, with the AST whitelist described above.
- **Identity hashes**: `form`, a rename- and format-invariant view of the AST
  structure, and `sig`, the parameter shape. Every claim binds to both.
- **The spec store**: `mathema.write_spec(fn, ...)` writes a standalone YAML
  record to `.mathema/verified/`, and `mathema.status()` reports fresh against
  stale as the code is now.
- **Structured failure reports**: when a function does not lift,
  `mathema describe --issue` builds an offline, versioned report carrying a
  stable reason code, the blocking constructs with their lines, and the
  environment context needed to debug it. It never touches the network.

## The four verdicts, which are not interchangeable

`proven` means the claim was established mathematically on the derive route,
`holds (n=...)` that it survived the stated number of behavioural trials,
`falsified` that mathema found a counterexample and kept it, and `skipped` that
the available route could not settle the question, which is reported plainly
rather than dressed up as either of the first two. Keeping those apart is most
of what Claim-Driven Development is for.

## Where this sits next to testing you already do

- **Test-driven development** checks input and output pairs you chose ahead of
  time. mathema checks a property, an odd function, a monotonic one, a bounded
  one, across every input the property claims to hold for rather than the
  examples you thought to write down.
- **Property-based testing** (Hypothesis and similar) already does that, and
  mathema's probe route is exactly this. What it adds is the record: a claim
  binds to the function's identity hash, so it is re-checked when the code
  changes and never silently goes stale the way a test result does the moment
  nobody re-runs it.
- **Spec-driven development** writes intent as a machine-checkable artifact
  instead of a comment, and mathema's record *is* that artifact, a standalone
  YAML file in claim-driven-development's own schema that outlives the Python
  implementation and can be re-verified against a regeneration of it.
- **Symbolic and formal proving** (Coq, Dafny, an SMT solver) proves a claim
  outright, but usually asks for a dedicated specification language and real
  upfront investment. mathema's derive route does real symbolic proof through
  sympy, automatically, for whatever subset of an ordinary Python function's
  shape actually lifts, and says `skipped` the moment it cannot, rather than
  pretending probing is a proof or refusing to run at all.

mathema does not replace any of these. It is the place a property-based check,
a durable spec and a real proof attempt meet on the same claim, routed
automatically to whichever one the function's own shape supports.

## API shape

```python
mathema.claim("f(-x) == -f(x)")               # state a claim
mathema.check(fn, claims=[...])               # verify it, return a Record
mathema.write_spec(fn, claims=[...])          # verify and write the record
mathema.status()                              # fresh/stale sweep
mathema.track_claims                          # optional bare tag, zero overhead

mathema.claims.check(fn, [...])               # the conjecture pipeline directly
mathema.registry.load_specs(root)             # read the whole spec store
mathema.registry.load_claims(path)            # parse an authoring claims file
```

## Command line and CI

```bash
mathema check model.py --domain alpha=0:1 --strict     # CI gate: exit 1 on failure
mathema check model.py --format json --output claim-coverage.json
mathema check model.py --format junit --output claims.xml   # GitLab test widget
mathema check model.py --format github                      # Actions annotations
mathema verify --status model.py                            # fresh/stale sweep
mathema describe --issue mypackage.model:my_function        # structured report
                                                            # for a function
                                                            # that did not lift
```

Worked pipeline configs for GitHub Actions and GitLab are in
[examples/ci/](examples/ci/).

## Network policy

mathema is fully offline and no core function makes a network call, so
verification runs against a proprietary codebase without source or claims
leaving the machine.

## Documentation

- **[Quick start](https://mathema.tetrionlabs.com/quickstart/)**: five minutes,
  one function, and a claim that goes from falsified to proven.
- [Claim-driven development](https://mathema.tetrionlabs.com/cdd/): the
  vocabulary every mode assumes, including what separates `proven` from `holds`.
- [Case studies](https://mathema.tetrionlabs.com/case-studies/): put-call
  parity, the Greeks, and the sigmoid worked end to end.
- [The claim grammar](https://mathema.tetrionlabs.com/grammar/): everything you
  can say in a claim, with a runnable example of each.
- [Writing claims](https://mathema.tetrionlabs.com/authoring/): the four places
  a claim can live and the precedence between them.
- [The derive route](https://mathema.tetrionlabs.com/derive-route/): exactly
  which function shapes can reach `proven`, and what happens to the ones that
  cannot.

The full documentation, including the command reference and the API, is at
**[mathema.tetrionlabs.com](https://mathema.tetrionlabs.com)**.

## Project

- [CHANGELOG.md](CHANGELOG.md): what changed in each release.
- [CONTRIBUTING.md](CONTRIBUTING.md): how to propose a change, and the
  contributor licence agreement.
- [SECURITY.md](SECURITY.md): how to report a vulnerability privately.
- [LICENSING.md](LICENSING.md): a plain-language summary of what the licence
  permits, and when it converts to AGPL.
- [SUPPORT.md](SUPPORT.md): where to ask, and what to expect.
- [Versioning and stability](https://mathema.tetrionlabs.com/stability/): what
  may change, and which versions are supported.

mathema is at 0.6.0 and pre-1.0: it is feature-complete for its current scope
and heavily tested (over 2,000 tests), and the claim grammar and record format
are settled by the spec, but the Python API is likely to change before 1.0. It
is deliberately explicit about its own limits, so where a claim cannot be
settled you get that answer rather than a confident one.

## Companion projects

mathema is the engine. Three projects sit alongside it:

- **[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development)**
  is the specification mathema implements: the claim tuple, the claim families,
  and the record schema. It is independently maintained and separately
  licensed, so the vocabulary is not mathema's to change unilaterally, and
  anything that reads or writes that shape interoperates without importing
  mathema.
- **[mathema-symbology](https://github.com/tetrionlabs/mathema-symbology)**
  supplies conventional notation. A claim written in the reader's own symbols
  is a claim the reader will actually check, so this provides
  domain-conventional symbols for parameter and function names when claims are
  rendered. `pip install "mathema[symbology]"`.
- **[mathema-agents](https://github.com/tetrionlabs/mathema-agents)** is the
  agent-facing setup: skills and per-tool adapters that teach a coding agent to
  drive the claim loop properly rather than guessing at it, which is what makes
  the acceptance boundary above workable in practice. `mathema init --agents`
  vendors the right adapter for whichever tool it finds. The fetch is explicit
  and opt-in; mathema itself makes no network calls.

## Install

mathema needs Python 3.10 or newer. Run these inside an active virtual
environment (`python3 -m venv .venv && source .venv/bin/activate`, or your
usual equivalent) rather than against a system or global Python.

```bash
pip install mathema           # core: sympy (derive route) + pyyaml (spec store)
```

The core install is deliberately small. Optional extras add capabilities
without becoming everyone's dependencies:

```bash
pip install "mathema[all]"    # numpy, z3, MCP server, coverage
pip install "mathema[mcp]"    # expose mathema's tools to an agent over MCP
pip install "mathema[smt]"    # z3 as a fallback decision procedure
pip install "mathema[numpy]"  # array-shaped claims
```

To work on mathema itself, clone the repository and use an editable install
with the test extra: `pip install -e '.[test]'`. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licensing

mathema is source-available under the [Business Source License
1.1](LICENSE.md). Production use is free for organisations under USD 10M
revenue or using it in at most three repositories, and for research, teaching
and evaluation, and every released version converts to AGPL-3.0-or-later four
years after its release. See [LICENSING.md](LICENSING.md) for the
plain-language version.

## The spec

This package implements **claim-driven development v0.2**, a sibling project
rather than a dependency: the claim tuple, the claim families, and the YAML
record schema, in both the authoring shape and the verified-record shape.
Anything that reads or writes that shape interoperates with mathema's records
without importing mathema's Python internals. `mathema.SPEC_VERSION` states
which version a given release targets, and every record stamps that value in
`lineage.CDD_spec_version`, so a record always says which vocabulary it was
adjudicated under.

The specification lives at
[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development)
and is published under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
