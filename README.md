# mathema

mathema checks Python functions against claims, short mathematical
statements of what a function is meant to do, and keeps each result as a
record bound to the exact code it was checked against. Where the body can
be read as mathematics, mathema proves the claim for every input in the
range the claim names, and where it cannot, it runs the real function on
inputs chosen to break the claim and reports what it found, evidence or a
counterexample, without upgrading one into the other.

AI-assisted development has made code cheaper to produce without making it
any cheaper to know whether that code is correct, and a claim gives the
reviewer something smaller and more precise to read than the diff. Every
verdict comes from mathematics or from running the real code rather than
from a model's judgement, so there is no account or API key and your code
stays on your machine. The name is Greek, μάθημα, a thing learned.

## A function with a pole in it

A discount factor written in a hurry, checked with no claim at all, so
only mathema's built-in claims apply:

<!-- example: pole run -->
```python
import mathema

def discount_factor(x: float) -> float:
    """A discount factor that divides by one minus the rate."""
    return 1 / (1 - x)

print(mathema.check(discount_factor))
```

<!-- example: pole output match=subset -->
```text
mathema.Record(discount_factor) · source, no side effects · form ebb4c9b87847
  proven    is_defined: 1 - x != 0
  falsified is_pole_safe[x]: is_pole_safe(x)
           counterexample x = 1 is admitted by the declared domain but sits at or beside a pole: the call raised ZeroDivisionError
```

Those are two of the record's fourteen built-in claims. Uniform random
sampling lands on `x = 1` with probability zero, so a property-based run
can pass a thousand trials here and report nothing, whereas mathema solves
the lifted expression for where its denominator vanishes and makes sure
that point is tried. `is_defined` states the region on which `f` returns,
and every falsification rests on an executed witness, never on a symbolic
argument alone.

## A claim proven over its domain

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

Put-call parity says this call minus put, both priced by Black-Scholes,
is `S - K*exp(-r*T)` whatever the volatility. In a claim everything before
the last comma is the domain and everything after it is the law, with `f`
standing for the function:

<!-- example: parity run -->
```bash
mathema check options.py --claim "for s in [50,150], k in [50,150], \
    r in [0.0,0.1], t in [0.1,2], sigma in [0.05,0.8], \
    f(s,k,r,t,sigma) == s - k*exp(-r*t)"
```

<!-- example: parity output -->
```text
ok   options.put_call_parity_gap: source, no side effects; claims 7/7 checked (1 proven, 6 holds, 0 falsified)
```

`[0.1,2]` is an interval of reals, and mathema lifted the body to an
expression in which both Gaussian terms cancel and `sigma` drops out, so
the mathematics is proven for the whole region. Of the six that hold, one
is the same identity run through the real code in float64 and five record
what the function does with a `nan` in each parameter. Without its domain
the claim covers every real input, a negative maturity where `math.sqrt(t)`
raises included:

<!-- example: parity run -->
```python
import mathema
from options import put_call_parity_gap

print(mathema.check(put_call_parity_gap, claims=[mathema.claim(
    "f(s,k,r,t,sigma) == s - k*exp(-r*t)", name="parity")]))
```

<!-- example: parity output -->
```text
mathema.Record(put_call_parity_gap) · source, no side effects · form a0c3d838b4f8
  falsified parity: f(s, k, r, t, sigma) = -k*exp(-r*t) + s
           counterexample s = 1, k = 1, r = 1, t = -1, sigma = 1
```

## Four verdicts

| Verdict | Means |
|---|---|
| `proven` | established mathematically over the claim's stated domain |
| `holds` | survived every trial mathema ran, which is evidence and not proof |
| `falsified` | an input inside the domain broke the claim, and that input is kept |
| `unknown` | nothing was settled, and the record keeps the reason |

A proof is about real numbers and whether float64 keeps up is a separate
question, so a record shows each claim's headline above a `mathematics`
line and a `computation` line, each with its own verdict, as
[reading a record](https://mathema.tetrionlabs.com/verdicts/#reading-a-record)
shows; [guarantees](https://mathema.tetrionlabs.com/guarantees/) says what
each verdict establishes and what it leaves open.

## Install

mathema supports Python 3.10 to 3.14, runs offline, and is best installed
into a virtual environment:

```bash
pip install "mathema[all]"    # recommended, with numpy, z3, MCP, coverage and mathema-language
pip install mathema           # the core alone
```

## Record, verify, gate

`mathema.write_spec` writes a function's record as YAML under
`.mathema/verified/`, with a `form` hash over the code's structure and a
`sig` hash over its parameters, and `mathema verify` re-checks every record
whose function, or a function it depends on, has since changed. A falsified
claim or an unaccepted `unknown` exits 1 and a run that could not start
exits 2, so a pipeline can tell a finding from a broken job.
`mathema init --ci` scaffolds the GitHub Actions or GitLab step, and
[gate a pipeline](https://mathema.tetrionlabs.com/gate-a-pipeline/) shows
each case from a real run.

## Text, and coding agents

A string is drawn from a named language (`L[unicode]`, `L[ascii]`,
`L[json]`) that the `mathema-language` package supplies. With it installed:

<!-- example: lang file=names.py requires=mathema_language -->
```python
def display_name(username: str) -> str:
    """The name shown beside a comment, trimmed and capped at 32 characters."""
    return username.strip()[:32]
```

<!-- example: lang session requires=mathema_language -->
```console
$ mathema check names.py --claim "for username in L[unicode], len(f(username)) <= 32"
ok   names.display_name: source, no side effects; claims 1/1 checked (0 proven, 1 holds, 0 falsified)
```

Without it the claim is `unknown` and names the package it needs, and a
plain claim over a `str` parameter is `unknown` as well:

<!-- example: core-only session after=lang wrap=85 -->
```console
$ mathema check names.py --claim "for username in L[unicode], len(f(username)) <= 32"
FAIL names.display_name: source, no side effects; claims 0/1 checked (0 proven, 0
    holds, 0 falsified, 1 unknown)  <- dim_f_username_0_le_32 unknown: needs
    mathema-language: unknown language L[unicode]: known languages are none in this
    process
```

[Language domains](https://mathema.tetrionlabs.com/language/) has the
rest. The mathema-agents skills teach a coding agent to propose claims and
read verdicts, and arrive through an explicit, opt-in
`mathema init --agents`, the one command that fetches anything. Accepting a
verdict and unlocking a locked function stay with a person
([working with coding agents](https://mathema.tetrionlabs.com/agents/)).

## Where next

[Start here](https://mathema.tetrionlabs.com/start/) offers a reading
order for each job, from a numerical function to a CI pipeline, and the
[quick start](https://mathema.tetrionlabs.com/quickstart/) takes one
function from falsified to proven. mathema is pre-1.0, with its claim
grammar and record format fixed by the
[claim-driven development](https://github.com/aaronbyrnephd/claim-driven-development)
specification and its Python API likely to change, as
[stability](https://mathema.tetrionlabs.com/stability/) sets out. See also
[CHANGELOG.md](https://github.com/tetrionlabs/mathema/blob/main/CHANGELOG.md), [CONTRIBUTING.md](https://github.com/tetrionlabs/mathema/blob/main/CONTRIBUTING.md),
[SECURITY.md](https://github.com/tetrionlabs/mathema/blob/main/SECURITY.md) and [SUPPORT.md](https://github.com/tetrionlabs/mathema/blob/main/SUPPORT.md).

mathema is source-available under the [Business Source License 1.1](https://github.com/tetrionlabs/mathema/blob/main/LICENSE.md),
and each release converts to AGPL-3.0-or-later four years after it is published.
[LICENSING.md](https://github.com/tetrionlabs/mathema/blob/main/LICENSING.md) sets out the grant in plain language.
