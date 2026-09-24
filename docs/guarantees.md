# Guarantees and limits

A verification result is only as useful as the reader's certainty about
what it means, so this page states, in one place, what each verdict
establishes, what it deliberately does not, and what the record keeps
as evidence. Every statement here describes the engine as it runs today.
Where a limit exists it is stated precisely rather than hedged, because
a verifier that is vague about its own edges is asking to be trusted
rather than checked.

## What each verdict guarantees

| Verdict | What it establishes | What it does not | What the record keeps |
|---|---|---|---|
| `proven` | The claim holds for every input in the declared domain, established by algebra in exact real arithmetic. On a finite integer domain, `derive:brute_force` has instead evaluated every point. | That floating point reproduces what the reals prove. Where the code raises inside the domain the claim itself is falsified, see [the sigmoid case study](case-studies.md); where it returns but loses the mathematics (a NaN, a precision collapse) the `[float]` companion claim, which runs the real function at the domain's corners and across its interior, is falsified while the proof stands. | The route (`derive`, `derive:extensive`, `derive:brute_force`) and a sketch naming the mechanism behind the proof. A `proven` never rests on an unnamed step. |
| `holds (n=...)` | The real function survived exactly `n` executed trials without a counterexample, on seeded inputs biased toward domain edges, corners, poles and special values. | A probability of failure. No statistical bound is computed or implied. The confidence stars beside a `holds` measure sampling density against the function's structure, and top out at four of five, since five is reserved for proof. | `n`, the sampling plan including its seed, and the confidence breakdown. |
| `falsified` | The real function, called at an in-domain point, violates the claim. That point is the **witness**, and a `falsified` always has one. | Anything about why. A falsification may mean the code is wrong or the claim is, and the loop exists to tell those apart, see [the CDD loop](tutorial.md). | The counterexample, kept permanently and replayed on every later run, so a bug cannot be fixed by accident and quietly unfixed. |
| `invalidated` | The claim was `proven` or `holds` in the previous record and the current code no longer supports it. | That it may simply be re-adjudicated away. It stays `invalidated` until the claim is supported again, or a person accepts it as a discovery or as history. | The previous verdict, what it regressed to, and the last commit where it was supported. |
| `unknown` | Nothing was decided, and the reason is kept. This includes a symbolic disproof that no executed point reproduces, which is flagged as a probable engine fault rather than reported as a bug in your code. | A pass. `verify` fails on an `unknown` unless a person accepts it as risk. | Why each route stopped (unliftable, undecided, timed out). |
| `skipped` | The claim could not be adjudicated as stated: misspecified, or a form the chosen route cannot evaluate. | A pass. `verify` fails on a `skipped` in its default strict mode. | The reason, with a [reason code](reason-codes.md). |

**Accepted risk** is not a verdict. It is a person's recorded decision
to own an `unknown` or `skipped` gap, with their name, the date and
their note. It stays visible in every report, and strict `verify` still
refuses it. See [`mathema accept`](modes/accept.md).

## Corroboration: why every falsification has a witness

The derive route can report that a claim is false by algebra alone. Such
a disproof stands only if running the real function reproduces it: the
engine tries the symbolic witness, small perturbations of it, and a
seeded blind search, and calls the function at each point. If one of
them fails the claim, the result is `falsified` with that executed
witness, recorded as `mathema.corroboration: "reproduced"`. If none do,
the result is `unknown` with `mathema.corroboration: "uncorroborated"`,
since an algebraic disproof that the code never exhibits more likely
points at a fault in the engine than in the code. A safety predicate's
structural disproof follows the same rule. A pole inside the declared
domain (`is_pole_safe`, `is_numerically_stable`), or a raising guard on
a missing value the domain admits (`is_missing_safe`), is checked by
calling the function at the point the structure names. A raise there,
or a non-finite result at a pole, is the witness; a call that behaves
leaves the disproof uncorroborated. A falsification is
therefore equally strong whichever route found it, because it always
rests on the same thing, the real function failing at a real input.

## How the routes combine

A claim takes the `best` route unless you pin one. The engine first
attempts a proof (a fast attempt, then the
[extensive strategy ladder](index.md#no-model-in-the-loop)), and a claim the proof
cannot decide falls through to probing, with the reason the proof
stopped kept in the record. The result names the mechanism that settled
it, and a claim's name never implies a route.

- A claim pinned to `route: derive` makes the fast proof attempt only;
  if that cannot decide, it still falls through to probing, with the
  derive status recorded.
- A claim pinned to `route: probe` never attempts a proof.
- Calculus forms (`d`, `lim`, `integrate`, `Sum`, `Prod`) are decided by
  the derive route. When the proof cannot close, numeric evidence on
  the lifted expression is reported as such, as mathema's reconstruction
  of the code rather than the code itself.
- A matrix identity the algebra cannot close is sampled over matrices
  of its declared shape, and stays `unknown` only where it cannot be
  sampled.

## What composes, and what does not

Evidence never gets stronger as it propagates. A claim that rests on
another through an `assuming` premise is capped at the evidence of the
weakest premise, and the record names the cap
(`meta["mathema.capped_by"]`); a premise that demands `is proven` and
finds only `holds` leaves the conclusion `unknown`. See
[Conditional claims and lemmas](lemmas.md).

An equivalence between two implementations lets one's mathematical
claims stand for the other at the equivalence's own evidence level and
never higher, so a `holds` equivalence can never make a claim about the
other implementation `proven`. Safety properties (state,
representation, overflow) never transfer, since they belong to an
implementation and its language rather than to the mathematics.
Recording transferred claims in the other implementation's own record,
with the equivalence named as provenance, is designed and not yet
built. See [Claims transfer](claims-transfer.md).

## Boundaries worth knowing

- **Reals and floats.** Proof is over the reals. Floating-point
  behaviour is covered by running the code: probing, witnesses, the
  overflow rule, the `[float]` companion claim every proof spawns, and
  [operational infinity](grammar.md#operational-infinity-let-inf-be) for
  unbounded domains.
- **Time caps.** Proof attempts are capped on the wall clock: 3 seconds
  for the ordinary attempt, 15 when `extensive=True` asks for more, with
  a 45 second failsafe over the whole extensive ladder. A proof that runs
  out of time falls through to probing and the record says so
  (`mathema.timeout`), so a slow machine can turn a `proven` into a
  `holds`, and never the reverse.
- **What the derive route lifts.** Straight-line and branching scalar
  code, accumulating loops, linear self-recursion, and more, catalogued
  in [The derive route](derive-route.md). Beyond scalars and sequences,
  matrices are partial: structure and identities prove, and probing
  samples matrices by shape and structure. Complex-valued code supports
  identities, not analysis. Everything outside the lift is still checked
  by running it.
- **Reproducibility.** Sampling is seeded (seed `20260718`) and the seed
  travels in the record's sampling plan, so a re-run on the same code and
  the same mathema version reproduces the same draws. Each record states
  the mathema version, the CDD spec version, the date and the commit it
  was adjudicated at.

## Glossary

**System 0 engine.** A verification engine with zero models between the
code and its verdict. Every result comes from mathematics and from
running the real code, never from a model's judgement.

**Claim.** A statement about what a function computes, written in the
[claim grammar](grammar.md), with a name and a declared domain.

**Domain.** The set of inputs a claim quantifies over. A claim without
its domain is a different claim.

**Route.** The mechanism that decided a claim: `derive` (algebra),
`probe` (running the code on sampled inputs) or `examine` (structural
facts about the code). Colon subroutes such as `derive:extensive` or
`probe:minimal_example` name a stronger or more specific mechanism.

**Lift.** The derive route's translation of a function body into a
mathematical expression. A function that lifts can be proven about; one
that does not is still probed.

**Witness.** The executed input at which the real function fails a
claim. Every `falsified` has one.

**Corroboration.** Reproducing a symbolic disproof by running the real
function, which is what turns an algebraic disproof into a `falsified`.

**Form hash.** A hash of the function's structure with names
normalised, so a rename or reformat leaves it unchanged and a change in
what the code does moves it. A record binds to it, which is how a
verdict notices that its code has changed.

**Evidence ladder.** The ordering of verdicts by strength, from `proven`
through `holds` to the unsettled states, set out in
[The evidence ladder](evidence-ladder.md).

**Record.** The durable result of adjudication, stored under
`.mathema/verified/`, bound to the form hash and committed with the code.
