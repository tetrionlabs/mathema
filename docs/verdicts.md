# Verdicts and exit codes

Every claim mathema adjudicates ends in one verdict, and every command
ends in one of four exit codes. This page is the reference for both.
[Guarantees and limits](guarantees.md) gives the reasoning behind each
verdict, [the evidence ladder](evidence-ladder.md) ranks them, and
[`mathema verify`](modes/verify.md) lists everything that fails the gate.

## Verdicts

| Verdict | Route | What it establishes | What it does not |
|---|---|---|---|
| `proven` | derive | The claim holds for every input in the declared domain, established by algebra in exact real arithmetic. On a finite integer domain, `derive:brute_force` has instead evaluated every point, each decided exactly (the body read exactly, its literals as written). A decision the body takes on a value the computation holds as a float (a comparison, a branch, a rounding, a dict key) keeps the point exact only where the function's own float run at that point takes it the same way. Where a point of that domain has no exact value (a library's float, a module constant), the sweep is `proven` on `derive:brute_force:within_float64` only when every point ran in float64, the claim held at each, and at each point with no exact value the float64 result misses the relation by no more than float64's own precision there (8 unit roundoffs of the value compared against, plus the function's relative condition number times the magnitude of the value it returned there, where both can be read); the record line adds `(all N points in float64, largest delta ...)`, and the note states that a difference below that delta would not show. A larger miss at a point with no exact value rests on the default allowance alone, so it is not counted, as on the probe route, and the claim is `unknown`; under a declared tolerance it counts, and the claim `holds` on `derive:brute_force`, the note naming the point, its miss and float64's precision there. The record keeps the route and a sketch naming the mechanism. | That floating point reproduces what the reals prove. A proof of a relation between values spawns a `<name>[float]` companion, the same relation run through the real code, whose verdict is its own. A claim proven as a fact about the function rather than at points (a derivative sign, a shape) spawns none, and the record's `mathema.float_companion` field says so: `none (the claim has no point evaluation against the code)`. A point inside the domain where the mathematics is undefined, or where the source raises, falsifies the claim itself. |
| `holds (n=...)` | probe | The real function survived exactly `n` executed trials without a counterexample, on seeded inputs biased toward domain edges, corners, poles and special values. A trial the computed values pass only within the default allowance is decided again in exact arithmetic; where the body cannot be read exactly it is not counted in `n`, and a claim with no counted trial is `unknown`. A declared tolerance makes such a trial count, and binds the computation line only: the mathematics line decides `==`, `<=`, `>=` and `!=` exactly. The record keeps `n`, the sampling plan with its seed, and the confidence breakdown. | A probability of failure. No statistical bound is computed or implied. |
| `falsified` | either | The real function, called at an in-domain point, violates the claim. That point is the **witness**, and a `falsified` always has one; it is kept permanently and replayed on every later run. A raise, a NaN computed from inputs that are not missing, or an infinity returned for a finite input is no value, so it falsifies every relation, `!=` included. On `route: derive` the probe falsifies the mathematics only: an overflow or a float miss where the claim read exactly holds is a finding in the note, and an infinity at a point with no exact reading is no counterexample, while a NaN, a raise, or a miss with no exact reading still falsifies. | Why. A falsification may mean the code is wrong or the claim is, and [the CDD loop](tutorial.md) exists to tell those apart. |
| `unknown` | either | Adjudication ran and decided nothing; the record keeps why each route stopped (unliftable, undecided, timed out). A claim pinned to `route: derive` that derive cannot settle and the probe's draws do not falsify ends here, never at `holds`: the note gives derive's reason and how many draws found no counterexample. On every route a miss found by sampling derive's reconstruction (`probe:lifted_numeric`) falsifies only where the code, run at that point, fails the claim exactly; otherwise the claim ends here and the note names the point and why it is no witness. A finite-domain sweep on that route that passes only inexactly, or runs part of the domain, ends here too, where the default route reports `holds`. A sweep that runs every point exactly over a function the examination cannot show pure is `holds` on `derive:brute_force` on every route, the note naming what stops the proof and what would make the sweep one. A symbolic disproof that no executed point reproduces lands here, flagged as a probable engine fault rather than reported as a bug in your code. | A pass. `verify` fails on an `unknown` in every mode. Accepted as risk, it passes in both modes and is reported as accepted risk. |
| `skipped` | either | The claim could not be adjudicated as stated: misspecified, or a form the chosen route cannot evaluate. The record keeps the reason, with a [reason code](reason-codes.md). | A pass in strict mode. `--lenient` reports it and proceeds. |
| `documented` | none | Of intent, not of a claim: stated intent a person has accepted with `mathema accept --intent`. | Anything about behaviour; it is the human rung of the evidence ladder. |
| `declared` | none | Of a claim: authored and stored, awaiting adjudication. Of intent: stated, not yet accepted by a person. | Anything at all yet; it is the lowest rung. |

A verdict may carry a colon subroute refining its base family,
`skipped:misspecified` when the claim itself is malformed rather than
the function unadjudicable, which `verify` and a printed record name as
`misspecified`; a record whose value claims are all misspecified carries
no policy rows. Everything before the colon is the base
family, and the fold into supported, refuted, blocked and undecided uses
only the base, so a subroute never changes what a verdict counts as, only
says more precisely why. The `route` field follows the same convention:
`derive:extensive`, `probe:semi_analytical`, `derive:brute_force` and
`derive:brute_force:within_float64` name the mechanism that decided, the
last also the representation the proof is capped at.

**Accepted risk** is not a verdict. It is a person's recorded decision to
own an `unknown` or `skipped` gap, with their name, the date and their
note. It stays visible in every report, and `verify` passes it in both
strict and lenient mode. See [`mathema accept`](modes/accept.md).

## Reading a record

`print(mathema.check(...))` shows each claim as a block: a headline, then
the lines its verdict rests on. A pricing helper that clamps a rate into
`[0, 1]`:

<!-- example: reading file=pricing.py -->
```python
def clamp_discount(rate: float) -> float:
    """A discount rate clamped into [0, 1]."""
    return max(0.0, min(1.0, rate))
```

<!-- example: reading run -->
```python
import mathema
from pricing import clamp_discount

print(mathema.check(clamp_discount, claims=[mathema.claim(
    "for rate in R, 0 <= f(rate) <= 1", name="in_unit")]))
```

<!-- example: reading output -->
```text
mathema.Record(clamp_discount) · source, no side effects · form py:bc9fa73b5bd1
  in_unit  for rate in R|missing, 0 <= f(rate) <= 1   falsified at f(nan)
    proven     mathematics  for rate in R, 0 <= f(rate) <= 1
    holds      computation  for rate in R, 0 <= f(rate) <= 1   43 draws
    falsified  policy       f(nan)   f(nan) returns 1.0
                            no missing policy stated
                            possible fixes:
                              (i) if dropping nan is intended, run: mathema accept pricing.clamp_discount missing[rate] --as discovery --corrected "missing(f, rate) drops"
                              (ii) exclude nan
                              (iii) handle nan at entry
```

<!-- illustration -->
```text
in_unit  <claim as resolved>               falsified at f(nan)        headline: name, claim, verdict, witness
  proven     mathematics  <claim over R>                              the claim over the real numbers
  holds      computation  <claim : float>  43 draws                   the same claim run in float64
  falsified  policy       f(nan)           f(nan) returns 1.0         an input that is not an ordinary value
                          no missing policy stated
                          possible fixes: (i) ... (ii) ... (iii) ...
```

- The **headline** shows the claim as mathema resolved it (here
  `rate in R|missing`, since a float may be `nan`) and its verdict. It is
  falsified when any line under it is, and carries that line's witness.
- A **`mathematics`** line is the claim over the numbers, decided by the
  derive route when it can be, and by sampling when it cannot.
- A **`computation`** line runs a proven claim through the real code in
  floating point, at the domain's corners and at sampled points inside
  it. It can fail where the mathematics holds (an overflow, a NaN), and
  then it carries the tag `[mathematics sound,
  implementation:numerical-instability]`.
- A **`policy`** line covers an input that is not an ordinary value: a
  missing one (`nan`, a `None` element, pandas' `NA`), an absent one
  (`None` for an `Optional` parameter), or an empty container. With no
  policy stated, mathema assumes the default and says so (`no missing
  policy stated; assumed propagates`); a call that breaks it is the
  witness. Under a falsified policy line, `possible fixes` lists the
  ways forward: state the policy, take the value out of the claim's
  domain, or handle it at the function's entry. In this release
  `mathema claims KEY --adopt` does not yet accept the policy name the
  first fix prints; state the policy as a claim instead, here
  `missing(f, rate) drops`. [Missing values](missing-values.md) covers
  the policies and how to state one.

A claim with nothing to say beyond its verdict, such as a family fact
like `is_deterministic` or a claim over integers, prints on one line.

## Shapes

A container is never its element. `[378.0]` against `378.0` is a
different shape, so `==` and `~=` are falsified and `!=` holds, whatever
the library: a list, an array, a pandas or polars Series, and the column
of a one-row table are all containers. The number 0 is no exception, so
`[0.0, 0.0] == 0` is falsified and the zero vector is written `[0, 0]`;
a claim's own `f(x) != 0` over a vector always holds. A premise reads 0
differently, as the zero of the other side's shape on every route:
as a premise, `f(x) != 0` says f(x) is not the zero vector, and any other
number is a different shape, so `x != 5` as a premise admits every point. A premise on
an element (`x[0] == 0`, `sum(x) == 0`, `norm(x) == 0`) is an ordinary premise.
A premise that pins a whole vector or matrix parameter to a value (`x == 0`,
`x == 5`, `x == [5, 5, 5]`) is not read yet: the claim is `unknown` on every
route, says so in its note, and no point is drawn. A band such as `x ~= 0`
over a vector is `skipped:misspecified`.

An ordering reads a number at each element, so `f(x) >= 0` over `[1.0,
2.0]` holds. Over an empty value (a list, an array, a dict, a set, a
string, a range) it does not hold, since there is no element at which it
could: empty is not 0 and is not `>= 0`. An empty string against a
string keeps the order of strings, the empty string first, so `"" <=
"a"` holds and `"" < ""` does not; an ordering between two strings that
are both non-empty is not read. `[] == []` holds and `[] != 5` holds.

A claim that fails on one of these shapes says so in its note, and gives
as corrections the claims that say what it may have meant: the element
(`f(a)["x"][0] ~= sum(a.x)`), the whole (`f(a)["x"] ~= [sum(a.x)]`) or the
narrowed domain (`assuming n >= 1, ...`). Each is the whole claim as
written, its domain included, and is given only after it has been
adjudicated and holds. A claim read back from a record, whose domain is
stored apart from its law, states the mismatch and gives no correction.

Bindings that fix one shared dimension to two sizes (`a` in `[0, 1]^2` and
`b` in `[0, 1]^3` under one name) leave no value, so the claim is
`skipped:misspecified` on every route.

## Transitions, and what `invalidated` names

A claim's verdict is what its latest adjudication found. When that is
weaker than the previous record's, the record keeps the move beside
the claim, in `mathema.transitions`: the verdict it fell from and to,
the kind, the cause, the date and the commit. The kinds are
`regressed` (`proven` or `holds` to `falsified`), `weakened` (`proven`
to `holds`, or a supported claim to `unknown` or `skipped`),
`strengthened` (to a stronger verdict; `falsified` to `unknown` or
`skipped` is not one), and `fixed` (`falsified` to supported when the
function changed). A claim that was never supported and is now falsified is a
finding, not a transition. The cause is `this function changed`, `a
callee changed` or `nothing changed`; the last means two runs disagree
about unchanged code (the engine, a library version, the seed or a
timeout), and the line says so: a regression with nothing changed is a
contradiction, and a fall to `unknown` with nothing changed is
suspicious. A move after a code change also keeps what changed: the
triggers that fired, in `invalidated_by`, and for a callee change the
roots of the moved chain, in `chain_moved`. The line for a fall to
`unknown` or `skipped` names both:

<!-- illustration -->
```text
nonneg weakened proven to unknown (a callee changed); triggers: dependency; chain moved at shop.Base
```

A move stays open until a person acknowledges it with `mathema accept
KEY CLAIM --transition`, or a later run brings the claim back to the
level it fell from. The gate acts on open moves by kind and mode (see
[what fails the run](modes/verify.md#what-fails-the-run)), and the
project's `.mathema/meta/policy.yaml` can set that per kind.

A `weakened` move from `proven` to `holds` is still supported, and a
plain acknowledgement closes it. A supported claim that fell to
`unknown` or `skipped` is no longer supported at all: a `skipped` one
most likely lost a resource it needs (a solver, an optional library),
and an `unknown` one either changed or, with nothing changed, points at
two runs disagreeing. Either fails the gate in both modes until a
person accepts the risk at the level it fell from, and the
acknowledgement records it as a risk acceptance, `as: risk` and
`level`, under the project's acceptance policy. The claim is then
accepted risk, as `mathema accept --as risk` makes it: both modes pass
it, named in the row. The sign-off stays on the record while
the claim is below the level it fell from, and closes as recovered when
the claim is back. `--lenient` tolerates
only a claim that was always `skipped`; `skipped` to `skipped` is no
move.

`invalidated` is a word about a function, not a claim. A function is
invalidated when it changed since its record: its form, its body's
provenance, a parameter default, its own claims, the pseudo-infinity a
claim runs to, a library version, a definition row, a premise, or
anything along its dependency chain. The record names the triggers that
fired in `mathema.invalidated_by` (empty when the function is current),
and the roots of a moved chain in `mathema.chain_moved`. Reverify is the
action, and it lives on that function. A record written before 0.6.5
stored a regression as the verdict `invalidated`; it is read as the
verdict the claim fell to, with the move open and its cause `recorded
before 0.6.5`.

## What fails the gate

`falsified` and an unaccepted `unknown` fail `mathema verify` in
every mode, and so does an open `regressed` transition and an open
`weakened` one to `unknown` or `skipped`, until a person accepts the
risk; an open `weakened` one from `proven` to `holds` fails strict and
warns under `--lenient`. A `skipped` claim nobody accepted fails in the
default strict mode and is reported, not failed, under `--lenient`.
Accepted risk passes in both modes and is named in the row. The full
table, including tripped locks, unresolved names and acceptances the
policy rejects, is on [`mathema verify`](modes/verify.md#what-fails-the-run).

## Exit codes

Every verb uses the same four, so a CI step can tell a failing gate
apart from a broken invocation without parsing output:

| Code | Meaning |
|---|---|
| 0 | ran, and nothing gated: claims adjudicated as stated, or the verb only reports |
| 1 | ran, and the gate failed: a claim is falsified or unknown, a transition is open and the mode fails it, a claim nobody accepted as risk is skipped in strict mode, a lock is tripped, or an acceptance fails the policy |
| 2 | could not run: a target that does not resolve, an unreadable or malformed file, a bad argument, a missing optional dependency |
| 130 | interrupted (Ctrl-C or EOF) |

The distinction that matters in CI is 1 against 2: a 1 is a finding about
your code and the report names the claim; a 2 means mathema never got far
enough to have an opinion. `--lenient` can turn a 1 into a 0 and never a 2
into either. [Gate a pipeline with mathema
verify](gate-a-pipeline.md#7-tell-a-failing-gate-from-a-broken-job) shows
each code from a real run.
