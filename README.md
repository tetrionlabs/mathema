# mathema

*Claim-Driven Development: turn software intent into verifiable evidence.*


More code is being written by AI than ever, faster than any human can
review it line by line. mathema is built for that world: point it at a
function and it tells you what the function actually does and how much
to trust it, without you reading the code yourself. It reads the
structure straight off the AST, probes real behavior on seeded random
inputs against built-in algebraic laws and any claim you state, and,
where the math allows, proves a claim outright instead of only sampling
it. Nothing is asserted; everything is checked, and every verdict binds
to the exact code that earned it, so the record can outlive the
disposable implementation, and can't silently go stale under it either.

The name is Greek: μάθημα, a thing learned. A function is trusted
exactly to the extent of its verified claims.

mathema is source-available under the [Business Source License
1.1](LICENSE.md); production use is free for organisations under
USD 10M revenue or using it in at most three repositories (and for
research, teaching, and evaluation), and every released version
converts to AGPL-3.0-or-later four years after its release; see
[LICENSING.md](LICENSING.md) for the plain-language version.

```python
import mathema

def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y

mathema.check(ema)                                    # built-in algebraic laws
mathema.check(ema, claims=["f(x, 1.0) == x[-1]"])      # your own claim, too
mathema.check(ema, domain={"alpha": (0, 1)})           # probe inside a declared domain
mathema.check(ema, claims=["excluding"], domain={"alpha": (0, 1)})
                                # and check the code actually rejects
                                # out-of-domain input
mathema.write_spec(ema, claims=[...])   # check, then write the record to .mathema/verified/
mathema.analyze(ema)              # just the machine-derived facts, no probing
```

For `ema`, mathema tells you, without you reading the code: the result is
deterministic and numerically stable across 120 seeded trials; scaling or
shifting every element of `x` scales or shifts the result the same way;
reordering `x` does *not* leave the result unchanged, and it keeps the
counterexample that proves it (this is a story over time, not a set). Every
verdict binds to the function's identity hash.

## What it does

- **Structural analysis** (pure `ast`, no dependencies): loop shape, purity
  and effects, parameter kinds, per-parameter domain guards.
- **Probing**: runs the real function on seeded random inputs and checks
  built-in algebraic laws (commutativity, idempotence, boundedness, parity,
  monotonicity, equivariances) plus any claim you state yourself. `holds
  (n=...)` is evidence, not proof, and `n` is reported exactly, not
  assumed, the trial budget starts higher for a structurally riskier
  function (more branches, more loops, a wider declared domain) and
  drops once *other* laws checked against the same function in the same
  call have already come back clean, resetting the moment any of them
  is falsified; `falsified` comes with the counterexample, permanently.
- **The derive route**: where a function lifts to a closed-form sympy
  expression, a claim is proven, not sampled, `d(f(x), x) >= 0` for
  monotonicity, a PDE identity, a case-split fallback across a pole or
  domain boundary sympy can't resolve in one shot. `extensive=True`
  widens the search (critical-point-informed sampling, a longer
  case-split attempt) at real, opt-in cost; off by default everywhere.
- **The conjecture pipeline**: state a claim as one string
  (`"f(-x) == -f(x)"`) or a `Conjecture`; laws are validated against a strict
  AST whitelist before they run, so proposals from an untrusted source (a
  human in review, or a model) are safe to check. The proposer never
  adjudicates its own claims.
- **Identity hashes**: `form` (rename/format-invariant AST structure) and
  `sig` (parameter shape). Every claim binds to them, so a record can't
  silently outlive the code it describes.
- **The spec store**: `mathema.write_spec(fn, ...)` writes a standalone YAML
  record to `.mathema/verified/`; `mathema.status()` reports fresh vs. stale
  against the code as it is now.
- **Structured failure reports**: when a function doesn't lift,
  `mathema describe --issue` builds an offline, versioned report, a stable
  reason code, the blocking constructs with their lines, and the
  environment context to actually debug it, ready to attach to a
  GitHub issue.
  Never touches the network.

## Where this sits next to testing you already do

- **Test-driven development** checks specific input/output pairs you
  chose ahead of time. mathema checks a *property*, an odd function,
  a monotonic one, a bounded one, across every input the property
  claims to hold for, not just the examples you thought to write down.
- **Property-based testing** (Hypothesis and similar) already does
  that: state a property, the tool generates inputs and looks for a
  counterexample. mathema's `probe` route is exactly this. What it adds
  on top is a record: a claim binds to the function's identity hash, so
  it's re-checked automatically when the code changes and never
  silently goes stale, the way a test run's result does the moment
  nobody re-runs it.
- **Spec-driven development** writes intent as a machine-checkable
  artifact instead of a comment. mathema's record *is* that artifact,
  a standalone YAML file (claim-driven-development's own schema) that
  outlives the Python implementation and can be re-verified against a
  regeneration of it.
- **Symbolic/formal proving** (Coq, Dafny, an SMT solver) proves a
  claim outright, but usually asks for a dedicated specification
  language and real upfront investment. mathema's `derive` route does
  real symbolic proof too, via sympy, automatically, for whatever real
  subset of an ordinary Python function's shape actually lifts to a
  closed form, and says `skipped`, honestly, the moment it can't,
  rather than pretending probing is a proof or refusing to run at all.

mathema doesn't replace any of these; it's the place a property-based
check, a durable spec, and a real proof attempt meet on the same claim,
automatically routed to whichever one the function's own shape actually
supports.

## API shape

```python
mathema.claim("f(-x) == -f(x)")              # state a claim
mathema.check(fn, claims=[...])               # verify it, return a Record
mathema.write_spec(fn, claims=[...])                # verify + write the record
mathema.status()                              # fresh/stale sweep
mathema.track_claims                          # optional bare tag, zero overhead

mathema.claims.check(fn, [...])               # the conjecture pipeline directly
mathema.registry.load_specs(root)             # read the whole spec store
mathema.registry.load_claims(path)            # parse an authoring-shape claims file
```

## Command line and CI

```bash
mathema check model.py --domain alpha=0:1 --strict     # CI gate: exit 1 on failure
mathema check model.py --format json --output claim-coverage.json
mathema check model.py --format junit --output claims.xml   # GitLab test widget
mathema check model.py --format github                      # Actions annotations
mathema verify --status model.py                            # fresh/stale sweep
mathema describe --issue mypackage.model:my_function        # structured failure report
                                                             # for a function that didn't lift
```

Worked pipeline configs for GitHub Actions and GitLab are in
[examples/ci/](examples/ci/).

## Network policy

mathema is fully offline. No core function makes a network call.

## Documentation

- **[Quick start](https://mathema.tetrionlabs.com/quickstart/)**: five minutes, one function, and
  a claim that goes from falsified to proven.
- [Claim-driven development](https://mathema.tetrionlabs.com/cdd/): the vocabulary every mode
  assumes, including what separates `proven` from `holds`.
- [The claim grammar](https://mathema.tetrionlabs.com/grammar/): everything you can say in a
  claim, with a runnable example of each.
- [Writing claims](https://mathema.tetrionlabs.com/authoring/): the four places a claim can live
  and the precedence between them.
- [The derive route](https://mathema.tetrionlabs.com/derive-route/): exactly which function
  shapes can reach `proven`, and what happens to the ones that cannot.

The full documentation, including the command reference and the API,
is at **[mathema.tetrionlabs.com](https://mathema.tetrionlabs.com)**.

## Project

- [CHANGELOG.md](CHANGELOG.md): what changed in each release.
- [CONTRIBUTING.md](CONTRIBUTING.md): how to propose a change, and the
  contributor licence agreement.
- [SECURITY.md](SECURITY.md): how to report a vulnerability privately.
- [LICENSING.md](LICENSING.md): a plain-language summary of what the
  licence permits, and when it converts to AGPL.
- [SUPPORT.md](SUPPORT.md): where to ask, and what to expect.
- [Versioning and stability](https://mathema.tetrionlabs.com/stability/):
  what may change, and which versions are supported.

mathema is at 0.6.0 and pre-1.0: it is feature-complete and heavily
tested (over 2,000 tests), and the claim grammar and record format are
settled by the spec, but the Python API is likely to change before
1.0.

## Companion projects

mathema is the engine. Three projects sit alongside it:

- **[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development)**
  is the specification mathema implements: the claim tuple, the claim
  families, and the record schema. It is independently maintained and
  separately licensed, so the vocabulary is not mathema's to change
  unilaterally, and anything that reads or writes that shape
  interoperates without importing mathema.
- **[mathema-symbology](https://github.com/tetrionlabs/mathema-symbology)**
  supplies conventional notation. A claim written in the reader's own
  symbols is a claim the reader will actually check, so this provides
  domain-conventional symbols for parameter and function names when
  claims are rendered. `pip install "mathema[symbology]"`.
- **[mathema-agents](https://github.com/tetrionlabs/mathema-agents)**
  is the agent-facing setup: skills and per-tool adapters that teach a
  coding agent to drive the claim loop properly rather than guessing
  at it. `mathema init --agents` vendors the right adapter for
  whichever tool it finds. The fetch is explicit and opt-in; mathema
  itself makes no network calls.

## Install

mathema needs Python 3.10 or newer. Run these inside an active virtual
environment (`python3 -m venv .venv && source .venv/bin/activate`, or your
usual equivalent) rather than against a system or global Python.

```bash
pip install mathema           # core: sympy (derive route) + pyyaml (the spec store)
```

The core install is deliberately small. Optional extras add capabilities
without becoming everyone's dependencies:

```bash
pip install "mathema[all]"    # numpy, z3, MCP server, coverage
pip install "mathema[mcp]"    # expose mathema's tools to an agent over MCP
pip install "mathema[smt]"    # z3 as a fallback decision procedure
pip install "mathema[numpy]"  # array-shaped claims
```

To work on mathema itself, clone the repository and use an editable
install with the test extra: `pip install -e '.[test]'`. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## The spec

This package implements **claim-driven development v0.2**, a sibling
project, not a dependency: the claim tuple, the claim families, and the
YAML record schema, both the authoring shape and the verified-record
shape. Anything that reads or writes that shape interoperates with
mathema's records without importing mathema's Python internals.
`mathema.SPEC_VERSION` states which version a given release targets,
and every record stamps that value in `lineage.CDD_spec_version`, so a
record always says which vocabulary it was adjudicated under.

The specification lives at
[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development)
and is published under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
