---
template: home.html
title: mathema
hide:
  - navigation
  - toc
---

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">The problem</span><span class="brk r"></span></span>

## AI made code cheap. Verification didn't.

Tests pass. CI is green. The agent says done. But what do you actually know?

Traditional metrics tell you how much code you have. Test coverage tells you
how much of it you executed. mathema tells you where your knowledge of the code
ends.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">The gap</span><span class="brk r"></span></span>

## Passing tests don't tell you what you know

A passing suite says the code did what the tests asked at the inputs the tests
chose, which is worth a great deal and is still a narrow slice of what anyone
reviewing the code actually wants to know. It says nothing, on its own, about:

- how the function behaves at the inputs nobody wrote a test for, which
  mathema samples and, where the mathematics permits, proves over the whole
  declared domain;
- the properties that follow from the implementation whether or not anyone
  intended them, such as symmetry, monotonicity or boundedness, which mathema
  checks with no claims written at all;
- the assumptions a result silently relies on, which a claim has to state as
  a domain or an `assuming` premise before it will check;
- where the behaviour becomes undefined, such as a pole, a raise or a
  non-finite result, which mathema looks for deliberately rather than hoping
  to stumble on;
- whether the docstring still describes the code, which
  [`mathema docsync`](modes/docsync.md) reports as drift;
- whether a change has invalidated something established earlier, including
  through a function it depends on, which [`mathema verify`](modes/verify.md)
  catches by re-checking every record whose code or dependencies moved;
- and what remains unverified, which mathema reports as plainly as what it
  has proven.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">How it works</span><span class="brk r"></span></span>

## Give your code an evidence layer

You state what a function is meant to do as a claim, a short mathematical
statement such as `f(-x) == -f(x)`. mathema adjudicates that claim against the
real function by the strongest route the function's shape allows, and keeps a
record of what was established, how, and against exactly which version of the
code.

<div class="mx-figure">
<svg class="mx-diagram" viewBox="0 0 700 170" role="img" aria-labelledby="pipe-title pipe-desc" xmlns="http://www.w3.org/2000/svg">
  <title id="pipe-title">The evidence layer</title>
  <desc id="pipe-desc">Intent becomes claims; claims are checked against the implementation by tests, probes and proofs; the result is an auditable record.</desc>
  <defs><marker id="pipe-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="mx-d-head"/></marker></defs>
  <g class="mx-d-rung"><rect x="10" y="55" width="110" height="60" rx="3"/><text x="65" y="90" text-anchor="middle">intent</text></g>
  <g class="mx-d-rung"><rect x="150" y="55" width="110" height="60" rx="3"/><text x="205" y="90" text-anchor="middle">claims</text></g>
  <g class="mx-d-rung"><rect x="290" y="10" width="130" height="40" rx="3"/><text x="355" y="35" text-anchor="middle">tests</text></g>
  <g class="mx-d-rung"><rect x="290" y="65" width="130" height="40" rx="3"/><text x="355" y="90" text-anchor="middle">probes</text></g>
  <g class="mx-d-rung mx-d-strong"><rect x="290" y="120" width="130" height="40" rx="3"/><text x="355" y="145" text-anchor="middle">proofs</text></g>
  <g class="mx-d-rung mx-d-strong"><rect x="520" y="55" width="170" height="60" rx="3"/><text x="605" y="84" text-anchor="middle">auditable</text><text x="605" y="102" text-anchor="middle">knowledge</text></g>
  <g class="mx-d-arrow">
    <line x1="120" y1="85" x2="146" y2="85" marker-end="url(#pipe-arrow)"/>
    <line x1="260" y1="85" x2="286" y2="30" marker-end="url(#pipe-arrow)"/>
    <line x1="260" y1="85" x2="286" y2="85" marker-end="url(#pipe-arrow)"/>
    <line x1="260" y1="85" x2="286" y2="140" marker-end="url(#pipe-arrow)"/>
    <line x1="420" y1="30" x2="516" y2="80" marker-end="url(#pipe-arrow)"/>
    <line x1="420" y1="85" x2="516" y2="85" marker-end="url(#pipe-arrow)"/>
    <line x1="420" y1="140" x2="516" y2="90" marker-end="url(#pipe-arrow)"/>
  </g>
</svg>
</div>

Tests you already have count toward what is known about each line of code,
probes run the real function on inputs chosen to find trouble, and proofs
settle a claim for every input at once where the function can be read as
mathematics. The record that comes out is plain YAML, bound to a hash of the
function's structure, so it can be reviewed, diffed and re-checked long after
the conversation that produced the code has gone.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">Strength of evidence</span><span class="brk r"></span></span>

## Evidence isn't binary

A claim that held on a thousand random inputs and a claim that holds on every
input are different kinds of knowledge, and mathema never lets one pass for the
other. Every verdict carries the route that reached it:

| Verdict | What it means |
|---|---|
| `proven` | settled mathematically, for every input in the declared domain |
| `holds (n=...)` | survived exactly `n` trials against the real function, with inputs chosen by analysis where possible |
| `falsified` | a counterexample, found by running the function and kept permanently |
| `unknown` / `skipped` | not settled, with the reason in the record |

Nothing is asserted and nothing is quietly upgraded. Evidence remains evidence,
proof remains proof, and an unresolved claim remains unresolved.
[The evidence ladder](evidence-ladder.md) sets out every rung. The same rule
holds for this site: every output on it was produced by a real run, and the
test suite parses every claim these pages show, so a claim cannot quietly fall
out of the grammar.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">A worked finding</span><span class="brk r"></span></span>

## See what mathema finds

Here is a midpoint function of the kind that gets written, reviewed and
merged every day, and the test someone wrote for it:

```python
def midpoint(a: float, b: float) -> float:
    """The point halfway between a and b."""
    return (a + b) // 2
```

```python
def test_midpoint():
    assert midpoint(2, 8) == 5
    assert midpoint(0, 10) == 5
```

```text
1 passed in 0.00s
```

The developer's claim is that the midpoint lies between its two inputs, which
is the whole point of a midpoint. mathema checks that claim twice, once over
the integers the test happened to use and once over the real numbers the type
hints promise:

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
mathema.Record(midpoint) · source, no side effects · form 3f045b3e5b8d
  proven  between_integers: for a in [0, 100]:int|missing, b in [0, 100]:int|missing, min(a, b) ≤ f(a, b) ≤ max(a, b)
           for a in [0, 100]:int|missing, b in [0, 100]:int|missing
  FALSIFY between_reals: for a in [0.0, 100.0]:float|missing, b in [0.0, 100.0]:float|missing, min(a, b) <= f(a, b) <= max(a, b)
           counterexample link 1: min(a, b) <= f(a, b): (99.9999, 100): 99.9999 vs 99.0
```

So the test established that the function works at two integer points. mathema
established that over the integers it is correct everywhere in range, as a
proof rather than a sample, and that over the reals it is wrong: floor
division throws away the fraction, so the "midpoint" of 99.9999 and 100 is 99,
below both of them. Nothing about this bug is exotic, and nothing in the test
suite could have found it, because the suite only ever asked about integers.
The fix is one character, and mathema proves it:

```python
def midpoint(a: float, b: float) -> float:
    """The point halfway between a and b."""
    return (a + b) / 2
```

```bash
mathema check mid.py:midpoint --claim "for a in [0, 100], b in [0, 100], min(a, b) <= f(a, b) <= max(a, b)"
```

```text
ok   mid.midpoint: source, no side effects; claims 1/1 adjudicated (1 proven, 0 holds, 0 falsified)
```

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">A whole codebase</span><span class="brk r"></span></span>

## The Monday-morning audit

`mathema audit` answers the question anyone asks on their first morning with a
codebase, namely where to start, without running a single test. Every function
it can find gets a row: where it lives as a ready-made `sed -n` range, how
branchy it is, whether it carries any claims, whether the derive route could
prove things about it, what state outside its parameters it reads or writes,
whether any test report covers it, and how well its docstring states its
intent. Here is one module of mathema's own source:

```bash
mathema audit mathema.intent --root .
```

```text
                         ||             || derive route                                                        || typing                || globals                                                                  ||           || docs    ||
key           | span     || claims      || derives | cx | reason                         | code                || typed | finite_domain || vars                      | mutates | funcs                              || tested    || quality || docsync
mathema.intent
 ._references | 93:146p  || {6 | 0 | -} || no      | 15 | 9 branches, 3 loops (1 nested) | loop:multiple-loops || yes   | -             || _REF_SECTIONS, _URL, _DOI | -       | re                                 || no-report || 0/4     || 58%
 ._sections   | 68:74p   || {5 | 0 | -} || no      | 2  | 1 loop                         | loop:not-a-fold     || yes   | -             || _SECTION                  | -       | -                                  || no-report || 0/3     || 58%
 ._summary    | 77:81p   || {5 | 0 | -} || no      | 2  | 1 loop                         | loop:not-a-fold     || yes   | -             || _SECTION, _GOOGLE_HEADER  | -       | -                                  || no-report || 0/2     || 53%
 .parse_doc   | 149:163p || {5 | 0 | -} || no      | 4  | 2 branches, 1 loop             | loop:not-a-fold     || yes   | -             || KEYWORDS                  | -       | DocIntent, _sections, _summary, +1 || no-report || 2/3     || 48%

0/4 claimed, 0/4 derivable, 0/4 lift unconditionally, 4/4 fully typed, 2/12 docstring quality criteria met, no coverage.json/.coverage report found (try `python -m coverage run -m pytest; python -m coverage json`), 4/4 depend on state outside their own parameters (see the global_vars/unresolved columns), mean docsync 54%.
```

`sed -n 149,163p mathema/intent.py` prints `parse_doc` and nothing else, which
is what makes the table useful to an agent as much as to a person: it can go
from "where is the function that parses a docstring" to the exact lines in one
step. `mathema audit --index` writes the same map for a whole codebase to
`.mathema/index.yaml`, with each module's stated intent, every function's
file, line and span, and a pointer to its verified record where one exists.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">Agents and people</span><span class="brk r"></span></span>

## Let AI write the code. Don't let it define what correct means.

A claim outlives the implementation it describes: when an agent rewrites a
function, the claims about it are re-checked against the new code, and if one
breaks you know which, where and with what counterexample. Where behaviour
cannot be established, mathema says where it stopped rather than guessing.

What an agent may not do is decide what counts as correct. No tool mathema
exposes to an agent accepts a verdict from its caller, and the decisions that
turn a verdict into an accepted fact about your codebase, accepting evidence as
sufficient, owning a residual risk, or declaring that a falsification revealed
a wrong claim rather than a bug, go through [`mathema accept`](modes/accept.md),
which is a person at a terminal. With a [PIN set](modes/pin.md), every such
decision is stamped in the record as having been made by someone who knew it,
which an agent does not.

Settled code can be frozen at the level that matters, the individual function.
[`mathema lock`](modes/lock.md) pins a function's structure, after which any
change to its body fails the sweep, while docstring edits and every other
function in the file stay free:

```bash
mathema lock pricing.discounted
```

```text
locked pricing.discounted at form 3c02ba9abd15
the body can no longer change under a CDD loop; docstring edits are unaffected. A human unlocks with: mathema unlock pricing.discounted
```

and after someone changes `1 - rate` to `1 + rate`:

```text
FAIL pricing.discounted: locked at form 3c02ba9abd15 but the code is now 1e43fc87752e; the record is unchanged. Restore the function, or a human runs: mathema unlock pricing.discounted
```

An agent is allowed to lock a function it has finished, which narrows what it
can break on its next pass. Only a person can unlock one, behind a prompt with
no `--yes` flag and, when set, the PIN.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">Who it's for</span><span class="brk r"></span></span>

## One engine, several jobs

- **If you work alongside a coding agent**, mathema is the part of the loop the
  agent cannot talk its way past: it states claims, mathema checks them, you
  accept or reject, and the functions you have signed off stay locked. The
  [MCP interface](modes/mcp.md) gives the agent the checking tools and none of
  the deciding ones.
- **If you have just inherited a codebase**, [`mathema audit`](modes/audit.md)
  is the first hour of reading done for you: every function, where it lives as
  a ready-made `sed -n` line range, what it touches, whether anything tests or
  claims it, and whether it could be proven, with `--index` writing the whole
  map to a file you can keep.
- **If you write numerical or financial code**, the derive route proves
  identities, bounds, derivatives, limits and integrals about ordinary Python
  functions, and the probe route goes looking for poles, overflow and
  non-finite results where random testing would not.
- **If you run CI**, [`mathema verify`](modes/verify.md) gates the whole
  store and re-checks only what changed, [`mathema check`](modes/check.md)
  speaks JUnit and GitHub annotations, and the exit codes keep a failing claim
  apart from a broken invocation.
- **If you review changes**, [`mathema review`](modes/review.md) shows the
  claim-level difference since any git ref: which verdicts flipped, which
  claims appeared or went away.
- **If you answer to an auditor**, every acceptance, unlock and lock is in the
  record with who made it and when, PIN-stamped when a PIN is set.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">Case study</span><span class="brk r"></span></span>

## A harder case

The same machinery reaches much further than a midpoint. Here is a European
call minus a European put on the same strike, both priced by Black-Scholes,
with a square root, a logarithm, an exponential and the Gaussian CDF:

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

Put-call parity says that difference is `s - k*exp(-r*t)` whatever the
volatility, a surprising thing to claim about a function in which `sigma`
appears five times:

```bash
mathema check options.py --claim "for s in [50,150], k in [50,150], \
    r in [0.0,0.1], t in [0.1,2], sigma in [0.05,0.8], \
    f(s,k,r,t,sigma) == s - k*exp(-r*t)"
```

```text
ok   options.put_call_parity_gap: source, no side effects; claims 1/1 adjudicated (1 proven, 0 holds, 0 falsified)
```

`proven`, over every point of a five-dimensional region of prices, rates,
maturities and volatilities: mathema read the body as mathematics, both
Gaussian terms cancelled, and `sigma` disappeared. No number of test cases
could establish that. The [case studies](case-studies.md#put-call-parity-and-the-greeks)
go on to the Greeks, stated as the partial derivatives they are.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">Direction</span><span class="brk r"></span></span>

## Where this goes

!!! note "Direction, not current capability"
    This section describes where mathema is heading. Nothing in it should be
    read as a feature of the current release beyond what the linked pages
    document.

Evidence is earned about one implementation, and the natural next step is
letting it travel. Today, [claims transfer](claims-transfer.md) carries
evidence in from curated knowledge about the libraries your code calls, across
between implementations shown to be equivalent, and out as a compendium others
can consume. The direction is to make that routine across languages, so the
claims written once about a pricing function hold the Python prototype and the
production port to the same statement, and to connect claims upward to the
policies and requirements they exist to satisfy, so that a line of code can be
traced to the reason it has to behave the way it does.

<span class="brkw eyebrow"><span class="brk l"></span><span class="bin">Start</span><span class="brk r"></span></span>

## Stop measuring how much code you have. Measure how much you know about it.

```bash
pip install mathema
```

<p class="mx-actions">
  <a href="install/" class="md-button md-button--primary">Install</a>
  <a href="quickstart/" class="md-button">Read the quickstart</a>
</p>
