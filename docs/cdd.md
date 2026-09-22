# CDD in one page

The vocabulary every mode of running mathema shares. Short and
reference-shaped; come back to this page when a term below shows up
somewhere else in these docs.

This page restates **claim-driven development v0.2**, the
specification mathema implements. The specification itself lives in a
separate repository,
[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development),
and is published under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). mathema
targets exactly one spec version at a time, readable at runtime as
`mathema.SPEC_VERSION`, and every verified record stamps the version
it was written against in its `lineage.CDD_spec_version` field.

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
- **`derive`**: lift the function's body to a `sympy` expression and
  prove the claim algebraically. Verdict: `proven`, `falsified`, or
  honestly `skipped` when it can't be settled (never a false `proven`).
  Only available for a real subset of functions; see
  [The derive route](derive-route.md).

## Verdict vocabulary

| Verdict | Route | Means |
|---|---|---|
| `proven` | derive | The two sides are the same expression, exactly. |
| `holds (n=...)` | probe | Held on every one of `n` seeded trials. Evidence, not proof. |
| `falsified` | either | A counterexample exists and is kept, permanently. |
| `unknown` | either | Adjudication ran but couldn't decide (an undecided proof, inconclusive sampling). |
| `skipped` | either | Couldn't be adjudicated at all (unliftable body, foreign grammar, an unresolvable key). |
| `invalidated` | either | A previously supported claim regressed: re-adjudication no longer supports it, and the record says what it was before. |
| `documented` | none | Stated in documentation only; nothing was adjudicated. |
| `declared` | none | Authored and stored, awaiting adjudication. |

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
