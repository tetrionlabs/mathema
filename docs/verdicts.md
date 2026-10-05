# Verdicts and exit codes

Every claim mathema adjudicates ends in one verdict, and every command
ends in one of four exit codes. This page is the reference for both.
[Guarantees and limits](guarantees.md) gives the reasoning behind each
verdict, [the evidence ladder](evidence-ladder.md) ranks them, and
[`mathema verify`](modes/verify.md) lists everything that fails the gate.

## Verdicts

| Verdict | Route | What it establishes | What it does not |
|---|---|---|---|
| `proven` | derive | The claim holds for every input in the declared domain, established by algebra in exact real arithmetic. On a finite integer domain, `derive:brute_force` has instead evaluated every point. The record keeps the route and a sketch naming the mechanism. | That floating point reproduces what the reals prove. A proof of a relation between values spawns a `<name>[float]` companion, the same relation run through the real code, whose verdict is its own. A claim proven as a fact about the function rather than at points (a derivative sign, a shape) spawns none, and the record's `mathema.float_companion` field says so: `none (the claim has no point evaluation against the code)`. A point inside the domain where the mathematics is undefined, or where the source raises, falsifies the claim itself. |
| `holds (n=...)` | probe | The real function survived exactly `n` executed trials without a counterexample, on seeded inputs biased toward domain edges, corners, poles and special values. The record keeps `n`, the sampling plan with its seed, and the confidence breakdown. | A probability of failure. No statistical bound is computed or implied. |
| `falsified` | either | The real function, called at an in-domain point, violates the claim. That point is the **witness**, and a `falsified` always has one; it is kept permanently and replayed on every later run. A raise, a NaN computed from inputs that are not missing, or an infinity returned for a finite input is no value, so it falsifies every relation, `!=` included. | Why. A falsification may mean the code is wrong or the claim is, and [the CDD loop](tutorial.md) exists to tell those apart. |
| `invalidated` | either | The claim was `proven` or `holds` in the previous record and the current code no longer supports it. The record keeps the previous verdict, what it regressed to, and the last commit where it was supported. | That it can be re-adjudicated away. It stays `invalidated` until the claim is supported again, or a person accepts it as a discovery or as history. |
| `unknown` | either | Adjudication ran and decided nothing; the record keeps why each route stopped (unliftable, undecided, timed out). A symbolic disproof that no executed point reproduces lands here, flagged as a probable engine fault rather than reported as a bug in your code. | A pass. `verify` fails on an `unknown` in every mode. Accepted as risk, it still fails strict and is reported, not failed, under `--lenient`. |
| `skipped` | either | The claim could not be adjudicated as stated: misspecified, or a form the chosen route cannot evaluate. The record keeps the reason, with a [reason code](reason-codes.md). | A pass in strict mode. `--lenient` reports it and proceeds. |
| `documented` | none | Of intent, not of a claim: stated intent a person has accepted with `mathema accept --intent`. | Anything about behaviour; it is the human rung of the evidence ladder. |
| `declared` | none | Of a claim: authored and stored, awaiting adjudication. Of intent: stated, not yet accepted by a person. | Anything at all yet; it is the lowest rung. |

A verdict may carry a colon subroute refining its base family,
`skipped:misspecified` when the claim itself is malformed rather than
the function unadjudicable. Everything before the colon is the base
family, and the fold into supported, refuted, blocked and undecided uses
only the base, so a subroute never changes what a verdict counts as, only
says more precisely why. The `route` field follows the same convention:
`derive:extensive`, `probe:semi_analytical` and `derive:brute_force` name
the mechanism that decided.

**Accepted risk** is not a verdict. It is a person's recorded decision to
own an `unknown` or `skipped` gap, with their name, the date and their
note. It stays visible in every report, and strict `verify` still refuses
it. See [`mathema accept`](modes/accept.md).

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
mathema.Record(clamp_discount) · source, no side effects · form bc9fa73b5bd1
  in_unit  for rate in R|missing, 0 <= f(rate) <= 1   falsified at rate = nan
    proven     mathematics  for rate in R, 0 <= f(rate) <= 1
    holds      computation  for rate in R, 0 <= f(rate) <= 1   43 draws
    falsified  policy       f(nan)   no missing policy stated; returns 1.0
                            possible fixes: (i) mathema claims pricing.clamp_discount --adopt 'missing[rate]'  (ii) exclude nan  (iii) handle nan at entry
```

<!-- illustration -->
```text
in_unit  <claim as resolved>               falsified at rate = nan    headline: name, claim, verdict, witness
  proven     mathematics  <claim over R>                              the claim over the real numbers
  holds      computation  <claim : float>  43 draws                   the same claim run in float64
  falsified  policy       f(nan)           returns 1.0                an input that is not an ordinary value
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

## What fails the gate

`falsified`, `invalidated` and an unaccepted `unknown` fail `mathema
verify` in every mode. `skipped` and accepted risk fail in the default
strict mode and are reported, not failed, under `--lenient`. The full
table, including tripped locks, unresolved names and acceptances the
policy rejects, is on [`mathema verify`](modes/verify.md#what-fails-the-run).

## Exit codes

Every verb uses the same four, so a CI step can tell a failing gate
apart from a broken invocation without parsing output:

| Code | Meaning |
|---|---|
| 0 | ran, and nothing gated: claims adjudicated as stated, or the verb only reports |
| 1 | ran, and the gate failed: a claim is falsified, invalidated or unknown, a claim is skipped or accepted as risk in strict mode, a lock is tripped, or an acceptance fails the policy |
| 2 | could not run: a target that does not resolve, an unreadable or malformed file, a bad argument, a missing optional dependency |
| 130 | interrupted (Ctrl-C or EOF) |

The distinction that matters in CI is 1 against 2: a 1 is a finding about
your code and the report names the claim; a 2 means mathema never got far
enough to have an opinion. `--lenient` can turn a 1 into a 0 and never a 2
into either. [Gate a pipeline with mathema
verify](gate-a-pipeline.md#7-tell-a-failing-gate-from-a-broken-job) shows
each code from a real run.
