# The method: claim-driven development

mathema is the tool; claim-driven development is the method it
implements. This page sets out that method and the vocabulary every
part of mathema shares, and is the one to come back to when a term
shows up somewhere else in these docs.

This page restates **claim-driven development v0.2**, the
specification mathema implements. The specification itself lives in a
separate repository,
[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development),
and is published under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). mathema
targets exactly one spec version at a time, readable at runtime as
`mathema.SPEC_VERSION`, and every verified record stamps the version
it was written against in its `lineage.CDD_spec_version` field.

## The problem it addresses

A test tells you a function behaved correctly on the specific inputs
the test author thought to write down. A type hint tells you the
*shapes* of the inputs and outputs line up. Neither tells you *why*
the function is trusted, in a form that survives the function being
rewritten, or that a reviewer (human or model) can check against the
real code in seconds rather than by re-reading the implementation.

Claim-driven development is a small, deliberately spec-first answer
to that gap: a **claim** is a specific, checkable statement about what
a function does (`f(-x) == -f(x)`, `min(x) <= f(x) <= max(x)`, `f`
raises on a shape mismatch), adjudicated against the *real* function,
not assumed from its signature. The claim, its verdict, and the
evidence behind that verdict are the durable artifact, not a
disposable test file that only proves something the day it was
written. The full specification, including the exact vocabulary and
the YAML record schema, lives in a sibling repository:
[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development)
on GitHub. mathema is one implementation of it, in Python.

The name mathema is Greek: μάθημα, a thing learned. A function is
trusted exactly to the extent of its verified claims.

## What Claim-Driven Development is

State a mathematical claim about a function, mathema adjudicates it
against the real function, and keeps the record. A claim is a
statement like `f(-x) == -f(x)` (an odd function) or
`for x in [0, 1], f(x) <= 1` (bounded on a declared domain), written
over the generic function name `f` and the function's own parameter
names.

## The two evidence routes

- **`probe`**: call the real function on seeded, synthesized inputs
  and check the claim numerically. Verdict: `holds (n=...)` or
  `falsified` with a counterexample. Evidence, not proof.
- **`derive`**: lift the function's body to a symbolic expression and
  decide the claim algebraically. Verdict: `proven`, or `falsified`
  with a witness the real function reproduced, and never a false
  `proven`. A symbolic disproof with no point to execute (a derivative
  or limit claim, say) stays `unknown`. When the body will not lift, or the proof
  cannot close, the claim falls through to the probe route with the
  reason the derive attempt stopped kept in the record; a matrix
  identity is sampled over matrices of its declared shape, and stays
  `unknown` only where it cannot be sampled or was declared
  `route: derive`. Only available
  for a real subset of functions; see
  [The derive route](derive-route.md).

## Verdict vocabulary

| Verdict | Route | Means |
|---|---|---|
| `proven` | derive | Established by algebra over the whole declared domain, in exact real arithmetic. That is all it says: the float implementation is its own claim, the `<name>[float]` companion every proof spawns (see [the evidence ladder](evidence-ladder.md#a-proof-is-the-mathematics-float-is-the-code)). A raise inside the domain still falsifies the claim itself; see [the sigmoid case study](case-studies.md#where-it-gets-interesting-a-true-claim-that-falsifies). |
| `holds (n=...)` | probe | Held on every one of `n` seeded trials. Evidence, not proof. |
| `falsified` | either | A counterexample exists and is kept, permanently. |
| `unknown` | either | Adjudication ran but couldn't decide (an undecided proof, inconclusive sampling). |
| `skipped` | either | Couldn't be adjudicated at all (unliftable body, foreign grammar, an unresolvable key). |
| `invalidated` | either | A previously supported claim regressed: re-adjudication no longer supports it, and the record says what it was before. |
| `documented` | none | Of intent, not a claim: stated intent a person has accepted with `mathema accept --intent`. |
| `declared` | none | Of a claim: authored and stored, awaiting adjudication. Of intent: stated, not yet accepted by a person (the lowest rung of [the evidence ladder](evidence-ladder.md)). |

A verdict may carry a colon subroute refining its base family, e.g.
`skipped:misspecified` when the claim itself is malformed rather than
the function unadjudicable. Everything before the colon is the base
family; the fold into supported/refuted/blocked/undecided uses only the
base, so a subroute never changes what a verdict counts as, it only
says more precisely why. The `route` field follows the same convention
(`derive:extensive`, `probe:semi_analytical`, `derive:brute_force`
name the mechanism that actually decided).

Verdicts are pedantic and exact: nothing is called proven that isn't,
and a value claim whose calls raise anywhere inside its declared
domain is falsified (a raise is not a value); the remedy is always
claims-side, narrowing the domain or stating the raising region as its
own `raises(...)` claim, never a softer adjudication.

The counterexample behind a `falsified` verdict is knowledge, kept
permanently in the record, and a falsified claim fails
`mathema verify`'s exit code in every mode, because a gate that waves
through a known-broken claim isn't a gate. A human decides what the
falsification *means*: fix the code (the recorded counterexample
replays until the claim proves), or, when the code was right and the
claim was wrong, record the discovery with
[`mathema accept --as discovery`](modes/accept.md), stating the
corrected claim (or adopting a verified mechanical inverse), each
adjudicated before it is written. An `unknown` claim
also fails until it is resolved or a human owns the gap with
`accept --as risk`. Only `skipped` and accepted risk are mode-dependent
(strict refuses them, lenient reports them). See
[mathema verify](modes/verify.md).

## Identity hashes

Every record binds to the function's `form` hash (a rename/reformat-
invariant AST fingerprint) and `sig` hash (parameter shape), so a
claim can't silently outlive the code it describes. If the function's
`form` changes, the claim is re-adjudicated, not assumed still true.

## The spec record

`mathema.write_spec(fn, ...)` writes a standalone YAML record
(`.mathema/verified/<key>.yaml`) conforming to the
`claim-driven-development` repo's `record-schema.md`: intent, identity,
claims with verdicts, references, and the reasoning chain that
connects them. The record is deliberately independent of the Python
implementation; it carries the identity hashes, so it can outlive the
code and be re-verified against a regeneration.

## Four ways to author a claim, one precedence order

Lowest to highest precedence, a same-named claim from a higher
surface overrides a lower one. See [Authoring claims](authoring.md)
for the full reference.

1. **Inferred from types**, a `typing.Annotated` marker on the
   signature, automatic, no claim actually typed.
2. **Docstring** `Claims:` block.
3. **Decorator**: `@mathema.claims_decorator(...)`.
4. **A claims file** on disk (`*.claims.yaml`, `claims/*.yaml`,
   anywhere in the tree).

All four funnel into the same declared shape, nothing downstream
cares which surface a claim came from.


## Which specification version

`mathema.SPEC_VERSION` is the one authority for which version a given
release targets, and that exact string is written into every record's
`lineage.CDD_spec_version`. A record therefore says which vocabulary it
was adjudicated under, so a store written today stays readable when the
specification moves on. Read it rather than assuming:

```python
import mathema
mathema.SPEC_VERSION
```

The specification is versioned separately from mathema: a mathema
release names the one spec version it targets, and a spec revision
lands in mathema as a deliberate, documented upgrade rather than
silently.

## What mathema does with a claim

- **Structural analysis** (pure `ast`, no dependencies): loop shape,
  purity and effects, parameter kinds, per-parameter domain guards.
- **Probing**: runs the real function on seeded random inputs and
  checks built-in algebraic laws (commutativity, idempotence,
  boundedness, parity, monotonicity, equivariances) plus any claim you
  state yourself. `holds (n=...)` is evidence, not proof. `n` is a
  trial budget decided once per call from the function's own
  structure, never a flat constant, and `falsified` comes with the
  counterexample, permanently.
- **Symbolic proof (the derive route)**: lifts a function's body to a
  symbolic expression and decides a claim algebraically, over several
  mathematics engines (principally sympy) and mathema's own solving. `proven` is
  strictly stronger than `holds`: not "n samples agreed," but "the
  relation holds for every input in the domain", an equality or an
  inequality alike. See [The derive route](derive-route.md)
  for exactly what is liftable.
- **The conjecture pipeline**: state a claim as one string
  (`"f(-x) == -f(x)"`) or a `Conjecture`. Laws are validated against a
  strict AST whitelist before they run, so a proposal from an untrusted
  source (a human in review, or a model) can do no more than evaluate
  mathematics over the function, which itself runs as it would in its
  own tests, see [Security and execution](security.md). The proposer
  never adjudicates its own claims.
- **Identity hashes**: `form` (rename/format-invariant AST structure)
  and `sig` (parameter shape). Every claim binds to them, so a record
  cannot silently outlive the code it describes.
- **The spec store**: `mathema.write_spec(fn, ...)` writes a standalone YAML
  record to `.mathema/verified/`, and `mathema verify` re-checks every
  record whose function or dependencies changed.

## Exit codes

Every verb uses the same four, so a CI step can tell a failing gate
apart from a broken invocation without parsing output:

| Code | Meaning |
|---|---|
| 0 | ran, and nothing gated: claims adjudicated as stated, or the verb only reports |
| 1 | ran, and the gate failed: a claim is falsified, invalidated or unknown, a claim is skipped or accepted as risk in strict mode, or a conflict is unresolved |
| 2 | could not run: a target that does not resolve, an unreadable or malformed file, a bad argument, a missing optional extra |
| 130 | interrupted (Ctrl-C or EOF) |

The distinction that matters in CI is 1 against 2. A 1 is a real
finding about your code and the record will say which claim; a 2 means
mathema never got far enough to have an opinion, so treating the two
alike hides a broken invocation as a failing test. `--lenient` moves
accepted risks out of the gate and so can turn a 1 into a 0, but it
never turns a 2 into either (see [what fails the
run](modes/verify.md#what-fails-the-run)).

## The specification documents

The full vocabulary and schema this package is checked against:

- [claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development):
  the repository itself, starting with its own README. Each published
  version has its own directory, holding the three documents mathema is
  checked against:
  - `cdd.md`, the core vocabulary (claim, verdict, evidence route).
  - `claim-anatomy.md`, what a claim is made of.
  - `record-schema.md`, the exact shape of the YAML record shown in
    step 4 of [A first look](first-look.md).
