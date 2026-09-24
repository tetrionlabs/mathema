# Changelog

All notable changes to mathema are recorded here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are
dated on the day they are tagged and published.

## Unreleased

### Added

- `mathema coverage --stamp` records the content hash of every source
  file an existing coverage report measured, in `coverage.sources.json`
  beside it. A stamped report's freshness is judged by content, so it
  stays trustworthy across a checkout, a CI artifact or a cache, where
  file times mean nothing. Unstamped reports fall back to file times, and
  `mathema coverage` prints which check it used. `--run-tests` stamps the
  report it produces.

### Fixed

- `mathema coverage --run-tests` keeps the report when a test fails. The
  suggested command no longer chains the JSON export on the test run's
  success, so one red test no longer discards every other test's lines.
- `--run-tests` combines per-process coverage data files (a parallel-mode
  run, or subprocess measurement) before exporting, so lines executed in a
  subprocess are no longer lost.

### Changed

- `mathema.lemmas` is now `mathema.partiality`. The module declares
  where a function raises so that claims about its callers can reason
  about it, which is an asserted fact rather than an established one,
  and "lemma" reads as established. It also collided with the claim
  sense of the word: a lemma is a named claim another claim rests on
  through an `assuming` premise. `register_raises_when` is unchanged.

## 0.6.0

First public release. Highlights:

- **Lock a function; only a person unlocks.** `mathema lock KEY` pins
  the form hash in `.mathema/meta/locks.yaml`: `verify` fails, and
  refuses to re-adjudicate, if the body changes, leaving the record
  byte-identical, so a CDD loop cannot drift the baseline onto code a
  human never sanctioned. Docstring edits never trip it. Agents may
  lock (an MCP `lock_target` tool exists; `pending_decisions` shows
  `locked-changed` rows); `mathema unlock` is prompted, has no
  `--yes`, is PIN-verified when one is set, and leaves an audit event.
  Hand-deleting the lock entry is detected against the record's own
  stamp.
- **Human-verified acceptance (optional).** `mathema pin set` stores a
  memorised PIN at user level (`~/.config/mathema/auth.yaml`, never in
  the project); every acceptance path and every unlock then prompts
  for it at the write boundary, covering the JSON, scripted and
  concepts paths too, and stamps `verified_by: {method, key}` into the
  record, so a sign-off provably came from a person at a terminal
  rather than an agent. RFC 6238 authenticator-app codes are built
  behind `--totp` (experimental). `.mathema/meta/policy.yaml` is the
  enterprise posture: require verification, restrict methods
  (disabling the static PIN), allowlist key ids, enforced at write
  time and by `verify` as the CI gate. The integrity checksum now
  covers acceptance blocks. A tripwire and an attestation, documented
  as exactly that, never a cryptographic barrier.
- **Records speak spec v0.2's normative core.** A claim's `authored`
  is an object: the checker stamps the surface it observed and carries
  the declared layer's origin facts (`ref`/`by`/`at`) forward, never
  overwriting an author's word; a v0.1.0 bare string reads as
  `{ref: ...}`. `identity` gains `source_available`, and `pure` is
  `null` for a function whose source could not be read, never a
  confident value. A same-name/different-statement collision across
  authoring surfaces warns instead of silently preferring the overlay.

- **A claim's canonical form is its plain text, and every store
  speaks it.** The statement a verified record carries is the
  canonical ascii rendering of the whole claim (premise, bindings,
  quantifier, chain, outcome) which re-parses on its own to the same
  claim; `domain`, `grammar`, `tolerance`, and `authored` (the
  authoring surface) ride beside it as the same claim for machines.
  `claims_fingerprint` hashes that canonical text, so where a
  quantifier was written, which glyphs spelled it, and which internal
  shape a bound landed in can never change a claim's identity, and a
  conformant tool in any language computes the same fingerprint by
  implementing the grammar. `condition` remains what it honestly is:
  the region the evidence covered, which a derive proof may
  legitimately narrow; display and provenance, never read back. The
  renderer is total (a subtree with no algebraic model, like `x[-1]`
  or a string literal, renders verbatim and re-parses to itself), a
  malformed outcome arrow errors at declaration instead of silently
  joining the right-hand side, and records pin one spelling
  regardless of the writer's display preferences. Stores written by
  earlier development builds re-adjudicate once on first contact.

- **The MCP surface, reshaped around how agents actually use it.**
  `adjudicate_target` returns the DECLARED claims by default (`include=`
  selects `declared`/`suggested`/`all`), which is 72-86% smaller and
  5x-26x faster because the suggestion battery is fully adjudicated,
  not merely serialized; statements are linted before anything is
  adjudicated, so a malformed or wrong-arity claim costs milliseconds
  instead of a full run. `adjudicate_targets` adjudicates a whole module
  in one call, reading the stores once. `parse_claim` takes an
  optional `target` and checks arity and parameter names against the
  real signature. The audit rows can carry the remedy itself
  (`blocker_hint`, `blocker_unlock`) and the claim gap
  (`claims_vs_floor`, and an `underclaimed` filter). The `lines`
  column is now `span`, a ready-made `sed -n` range, and
  `verify_project` returns `report` for its prose, ending a collision
  where one name meant two unrelated things. Payloads go over the
  wire compact rather than pretty-printed (`audit_targets` 1468 ->
  738 bytes). The server also serves reference material and
  procedures as MCP resources and prompts, generated from the lexicon
  and reason-code table so they cannot drift.
- **A suggested claim can no longer outrank a declared one.** The
  suggestion battery merged as an overlay, so a suggestion sharing a
  name with a human's declared claim won; the declared claim was
  reported as `suggested`, `gates` false, and its verdict silently
  stopped counting toward the gate.
- **A timed-out critical-point search is recorded.** The alarm raises
  a `BaseException` (so sympy's own handlers cannot absorb it) that
  only becomes `TimeoutError` at the timeout boundary, above the
  cache, so the cache's handler never fired and every later call
  redid the same doomed search.
- **Machine-readable verbs.** `verify`, `accept`, and
  `claims --suggest` gained `--format json` and `--output FILE`.
  `verify` emits per-key entries carrying why each key was looked at,
  its gate counts, and its claim rows in the same vocabulary
  `check --format compact` and the MCP tools already speak;
  `VerifyResult` gained a structured `keys` list to back it, and the
  MCP `verify_project` tool carries it too. `accept --format json`
  prints the acceptance PLAN and writes nothing unless `--yes` is also
  given, so a client can preview a decision without ever prompting on
  stdin; acceptance stays a human act. `claims --suggest` and the
  MCP `suggest_claims` tool now return identical columns
  (`name, statement, route, declared, exclusive_group`).
- **One diagnostic bundle, `diagnostics.diagnostic_report()`.**
  Renamed from `richer_diagnostics` (and its record meta key to
  `mathema.diagnostic_report`), it returns one stable key set whether
  or not the function lifts, so a consumer reads any field without
  branching first and an empty list means "found nothing" rather than
  "never looked". Structural motifs are reported for functions that
  fail to lift too, which is the case failure telemetry most needs.
  Core ships no similarity fingerprinting: comparing functions against
  each other is deliberately not core's concern.

- **The claim floor.** `mathema audit` now reports claims as
  `{floor | actual | expected}`: the least a function's shape gives
  you to state, what it states, and; once a corpus can predict it,
  how many a function of this shape typically carries. The floor is
  one claim per relevant claim family per target
  (`inventory.claim_floor()`), so alternatives about the same question
  count once and every member of a keyword group counts separately. It
  is a floor, never a ceiling, and stays out of every score. Replaces
  the boolean `claimed` column, and supersedes the old
  `branch_count + domain_declared` heuristic. `n_claims` now excludes
  claims whose recorded verdict is blocked (skipped, unliftable):
  adjudication never engaged with them. Unknown and falsified claims
  still count; a falsification is evidence.

- **Guard verdicts you can trust, budgets that hold.** A guard
  disproof now requires an executed witness (the real call, run at
  the candidate point, must actually raise), uncorroborated
  symbolic witnesses downgrade to undecided, ending a family of
  false `falsified` verdicts on composed calls. Nested wall-clock
  caps no longer cancel their enclosing deadline, the extensive
  ladder has an aggregate budget, and symbolic Sum/Prod lowering is
  capped, retiring two known hang shapes.
- **Loops and branches compose.** Value branches around loops,
  loop-then-branch, and in-loop conditional updates under an outer
  branch all lift as one ordered piecewise; computed guard
  quantities (`re = rho*v*d/mu`) resolve past lead guards and decide
  by interval arithmetic; a `funcs=`-bound function may carry
  guards, branches, or a scalar loop and still compose (nested
  `h(g(...))`, `d(...)` through the composition, `Sum(...)` over a
  loop-lifted binding). An undirected finite limit whose far side
  leaves the reals resolves one-sided, with the direction stated in
  the record.
- **A pure `check` behind one IO boundary.** `mathema.retrieve(fn,
  root)` is the declared layer's one read entry point: it joins the
  hand-written claims-file store (the highest-precedence authoring
  surface) with the function's own decorator/docstring claims and
  hands the result to `check(declared=...)`, `check` itself never
  touches the filesystem. `note()` is renamed `write_spec()` (the IO
  composition: retrieve + check + record), and the CLI check verb and
  MCP `adjudicate_target` do the join automatically. This fixes a real
  hole: the function-object entry points previously never saw
  file-declared claims at all, so their gate counts were vacuous
  (`passed: true` beside falsified rows).
- **A tightened compact contract.** One null policy (null strictly
  means not-computed; computed-empty is the typed empty value), a
  real enum `blocker` column (bare reason-code key, decorations split
  into `blocker_params`/`blocker_more`), `[n, m]` pairs for
  `typed`/`doc_quality`/`docsync`, and a closed
  `"yes"`/`"no"`/`"no-report"` `tested` enum. Reason codes carry
  stable `major.minor` ids with group-level selective lookup, and
  audit's explicit `filter` takes semantic terms and columnar
  substring matches.
- **Agent-shaped output.** Adjudication rows (`check --format
  compact`, MCP `adjudicate_target`) carry a closed `stance`
  (supported/refuted/undecided/blocked) beside the open verdict, the
  authoring-surface `source`, and a `gates` flag, with
  `counterexample` present iff refuted and `blocked_by` iff blocked.
  Population output (`audit --compact`/`--cols`, MCP `audit_targets`)
  is column-oriented, `{prefix, cols, rows}`, caller-selected
  columns, shared key prefix factored out, sed-ready line spans.

- **The CLI runs on real packages, with one target grammar.** Every
  command resolves through one resolver: dotted names,
  `module:function` forms, and file paths all work everywhere, and a
  file target imports with real package context, so relative imports
  inside it no longer break `check`/`docsync`. Report and store keys
  are the canonical dotted `module.qualname` everywhere (`verify`'s
  `--target` file preload and its bare-name key fallback are gone).
  Authoring errors, a malformed claim, a bad target, broken YAML,
  exit 2 with a one-line message instead of a traceback. Exit codes:
  0 clean, 1 gate failure, 2 usage/target/authoring error, 130
  interrupted.
- **Eight verbs.** `status` folded into `verify --status`, `index`
  into `audit --index`, `issue` into `describe --issue`; `check` and
  `verify` share one `--strict`/`--lenient` pair (check defaults
  lenient, verify strict). `verify` is also a library call now
  (`mathema.verify_project`), and the gate is one shared policy
  (`mathema.gate`), provenance-based, so built-in structural probes
  gate in `verify` too, and accepted risk is honored in `check`.
- **Underivability is coded.** `audit --deep-dive` is gone: the audit
  grid says `structure` (the shape) plus a `blocked` column with a
  stable compact code (`loop:non-affine-update`,
  `branch:needs-domain(scale)`), a per-construct coded detail block
  always prints, and the full meaning/fixability/hint table is a docs
  page (Reason codes) plus `mathema.reason_codes.describe_code()`.
  The grid gains a sed-style `lines` column; `wraps` moved into
  `diagnostic_report`, which now carries the per-construct human
  hints.
- **String parameters stop producing fake gaps.** A `str`-annotated
  parameter is never sampled as a float again: a `Literal[...]`/Enum
  annotation is treated as the parameter's declared value set
  (sampled, inferred at claim time, rendered explicitly), and a bare
  `str` with no finite domain declines honestly, naming the parameter
  and the domain spelling that fixes it.
- **Concepts and links.** `Concepts:` (or `Tags:`) docstring markers,
  module-README concepts, and declared-file `meta.concepts` (entry
  and per-claim) all land in the record, the spec's own
  `meta.concepts` shape, flat union at the interop surface with full
  provenance beside it, and mathema additionally derives concepts
  from the proof machinery itself (a fold lift tags summation, an
  nlsat proof tags polynomial-arithmetic, a pole tags singularity).
  References gain roles: `Analysis:`/`Evidence:`/`Policy:` sections
  carry links (a notebook documenting a model assumption) into the
  record's references with `via` labeling each. Audit counts
  concepts; the index and describe carry them.
- **The nlsat rung (`mathema[smt]`).** With the optional z3 extra
  installed, the extensive ladder gains a nonlinear-real-arithmetic
  decision rung: polynomial and rational sign claims (radicals and
  Abs/Min/Max included) are decided completely, Schur's inequality
  and the Motzkin polynomial prove in fractions of a second. Proofs
  name the oracle; a counterexample is re-confirmed by exact
  arithmetic before any disproof is reported. Without the extra,
  nothing changes.
- **MCP interface.** `pip install mathema[mcp]` and `mathema mcp
  serve` expose the library surface as MCP tools (resolve, check,
  verify, describe, audit, the reason-code lookup, the claim
  grammar). No tool accepts a caller-supplied verdict; `accept` is
  never exposed.

- **Pedantic verdicts.** A value claim whose calls raise anywhere
  inside its declared domain is falsified, on both routes, a raise
  is not a value, with the witness point and the remedy in the
  message (narrow the domain, or state the raising region as its own
  `raises(...)` claim). Vacuous truth is refused the same way.
- **The gate got honest.** A falsified claim fails `mathema verify`
  and `mathema check` in every mode (it previously did not fail the
  exit code at all); an unknown claim fails until a human accepts the
  risk. Freshness no longer bypasses the gate: a record's stored
  verdicts are checked even when nothing is re-adjudicated.
- **`mathema accept`**: the human decision verb; accept a `holds`
  verdict's evidence, own an unknown/skipped gap as risk (what lets
  `verify --lenient` proceed; strict still refuses it), or diagnose a
  falsification as a discovery, declaring the corrected claim while
  the superseded one stays retained. Acceptances bind to the
  function's `form` hash and go stale when the code changes. There is
  no accepting a bug: the recorded counterexample replays until the
  claim proves.
- **`mathema claims`**: the authoring surface for standard claims,
  list a function's declared claims, render mathema's suggestions
  (determinism, domain safety, missing-value policy, with mutually
  exclusive alternatives grouped), and `--adopt` one into the declared
  layer. Suggestions never live in a verified record and never gate;
  adoption is the explicit human step.
- **The complex plane.** Definite-integral claims can now prove via
  the residue theorem (semicircle, unit-circle, Jordan, half-line,
  principal-value `P.V.(...)`, and keyhole contours), with every
  precondition discharged exactly and disagreements with sympy's own
  integrator adjudicated numerically and named in the sketch. Domains
  gained the `C` base type: complex parameters parse (`1+2i` or
  `1+2j`), prove, probe, and render.
- **Multi-function claims derive.** A claim relating several functions
  (`f(x) == g(x)`, a two-function tangency condition) now proves on the
  derive route: each bound function lifts to its own closed form and
  substitutes like `f` does, nested calls included. A bare call name in
  claim text binds automatically from `f`'s module or the calling
  scope's local variables, with every binding named in the note;
  `funcs=` stays the explicit form and always wins. Counterexamples now
  also respect `let`-declared free-variable domains.
- **`assuming` clauses.** A claim can state its own precondition:
  `assuming b^2 - 4*a*c >= 0.01, d(f(a,b,c), c) <= 0` proves where the
  unconditional claim honestly falsifies (the sqrt raises below the
  discriminant). Relations `==`/`!=`/`>=`/`<=`/`>`/`<` are accepted;
  `assuming <name>` references a sibling claim by name and renders its
  relation inline; `assuming <name> is proven` / `holds` makes the
  named claim a prerequisite, and a claim resting on empirical (holds)
  evidence caps its own proof at holds. The probe route
  rejection-samples the assumed region.
- **Partiality lemmas.** Where a function raises is a consumable fact:
  `math.sqrt`'s negative axis, `log`'s nonpositive region, and
  division by zero ship built in, and
  `mathema.partiality.register_raises_when` states the raising region of
  any function, callers' claims then falsify over it exactly as over
  an explicit `raise` guard, or prove once their domain (or `assuming`
  clause) provably avoids it.
- **Unknowns are superseded by evidence.** A route="derive" claim
  whose proof attempt can't decide now falls back to probing:
  empirical holds/falsified beats an unknown, from either direction,
  with the route field naming the mechanism that actually decided and
  the derive diagnosis kept on the record. Only a claim neither route
  can touch stays unknown.
- **Recurrences.** A self-recursive linear recurrence (fibonacci,
  doubling, factorial's `n*f(n-1)`) lifts to its exact closed form via
  `rsolve` and proves its own recurrence claim, gated to integer
  domains, and refusing to prove a domain whose recursion depth would
  overflow the interpreter's stack, since the implementation raises
  `RecursionError` there however true the formula is.
- Licensed under the [Business Source License 1.1](LICENSE.md)
  (Additional Use Grant with a USD 10M revenue floor, a
  three-repository floor, non-commercial and 90-day evaluation use;
  each released version converts to AGPL-3.0-or-later four years after its
  release); see [LICENSING.md](LICENSING.md) and
  [docs/licensing-policy.md](docs/licensing-policy.md) for what that
  means in practice.
- `mathema issue`: a structured, offline failure report for a function
  that didn't lift to a closed form, built on a new versioned
  `reason_codes` registry (`ReasonCode`, `Category`, `FailureRecord`).
  Never makes a network call; source is included only when
  `--include-source` is passed on that one invocation.
- Fixed a real hang: a claim's plain equality proof (`_prove_relation`)
  had no wall-clock cap at all, and a separate, already-existing cap
  elsewhere (the derive route's critical-point search) was being
  silently defeated by a broad exception handler swallowing the
  timeout's own signal. Both fixed; the `extensive` flag now reliably
  bounds every derive-route proof attempt.
- Two dead-code `NameError`s fixed: a math-function call (`sqrt`,
  `sin`, ...) inside a dot-product- or fold-route claim's law text
  crashed on first use, in both cases from a missing import that
  nothing had exercised before.
- A critical packaging bug fixed before it ever shipped: the
  `mathema.symbolic` subpackage was never listed in the package's own
  `packages` setting, so it silently never made it into a built wheel.
  Packaging now uses automatic package discovery instead of a
  hand-maintained list.
- Extensive derive-route work: `extensive` mode (opt-in, wider search
  with real cost) for critical-point-informed sampling and case-split
  proofs; `domain_safe[param]` probes; `mathema.suggest_claims()` for
  structurally-routed candidate claims.
