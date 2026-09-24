# `mathema accept`

The human decision verb: annotate one adjudicated claim with an
explicit acceptance. Prompted; the exact write is printed first and
nothing happens without a yes. Deliberately CLI-only: acceptance is a
human act, never exposed to agent tooling or any MCP surface.

```bash
mathema accept KEY CLAIM --as evidence|risk|discovery [--by NAME] [--note TEXT]
mathema accept KEY --as reconciled [--from OLD_KEY]
```

Three acceptances cover the everyday loop (`evidence`, `risk`,
`discovery`). Four more handle record housekeeping, each with its own
section below: `historical` and `superseded` retire a claim with its
history intact, `reconciled` restamps a record after a merge or rebase,
and `trusted` records testimony from a source you vouch for. `--intent`
and `--concepts` accept the function's stated intent and concept tags.

## Arguments

| Flag | Meaning |
|---|---|
| `key` | function key (the record under `.mathema/verified/`) |
| `claim` | claim name inside that record (omit for `--as reconciled`, which acts on the whole record) |
| `--as` | `evidence`, `risk`, `discovery`, `historical`, `superseded`, `trusted`, or `reconciled` (see below). In text mode you can omit it and mathema reads the claim's verdict and proposes the natural kind; `--format json` never guesses, and without `--as` it exits 2 |
| `--all` | with `--as reconciled` and no key: reconcile every record whose checksum no longer matches, in one act |
| `--from OLD_KEY` | with `--as reconciled`: rename `OLD_KEY`'s record to `KEY`, for a function that moved (see [moved functions](#moved-functions-as-reconciled-from)) |
| `--accept-form-change` | with `--from`: rename even though the record's form hash differs from the live function's |
| `--by` | who decided (default: `git config user.name`) |
| `--note` | free-text rationale, kept in the record |
| `--yes` | skip the confirmation prompt (for scripted use by a human; never wire this into agent tooling) |
| `--root` | project root (default `.`) |
| `--format` | `text` (default) or `json`: emit the acceptance as data. Without `--yes` this is a preview that writes nothing; JSON mode never prompts |
| `--output FILE` | write the report to a file instead of stdout |

## The three everyday acceptances

- **`--as evidence`**: a `holds` verdict has enough empirical support
  for your purposes. The record keeps the acceptance alongside the
  verdict; a later run with weaker evidence warns.
- **`--as risk`**: you own an `unknown` or `skipped` gap. The claim
  reclassifies to an accepted state that `verify --lenient` proceeds
  past (named in the row as accepted risk) while strict mode still
  refuses it. This is the only way an unknown claim stops failing the
  gate, see [what fails the run](verify.md#what-fails-the-run).
- **`--as discovery`**: a falsification that was right about the code
  and wrong about the claim: the function's actual behavior is the
  interesting fact. Accepting it retires the claim into the record's
  discoveries section, permanently, with the counterexample kept as
  the witness; every falsified claim can be accepted this way,
  whatever its shape. A corrected claim is declared alongside only
  when it is verified first. State it yourself with
  `--corrected "<law>"` and mathema adjudicates it against the live
  function before anything is written (a correction that itself
  falsifies is refused, with the counterexample named). Without
  `--corrected`, a mechanically sound inverse (a bare single relation
  flipped, or a predicate through the grammar's `not` form) may be
  offered, but only after it has been adjudicated and holds; a
  chained comparison, an `assuming` premise, a `let` section, or an
  inverse that fails adjudication is never guessed at, and the
  discovery is simply recorded with no replacement. When a correction
  is written, it carries its real adjudicated verdict. The acceptance
  also keeps the declared layer honest: any claims file stating the
  retired law is rewritten as part of the act (the stanza replaced by
  the correction, or removed when there is none), because a leftover
  declaration would regenerate the falsification on the next real
  sweep. A docstring or decorator surface cannot be rewritten by an
  acceptance, so `verify` skips the retired law there with a non-fatal
  note naming the remedy until the source changes; a DIFFERENT law
  under the same name is new authorship and adjudicates normally.

**What is acceptance?** Verification says what the machine established;
acceptance is where a *person* takes accountability for what to do about
it. It is integral to the CDD loop, not an add-on: evidence is adjudicated
by the tool, but the decision to rely on a `holds`, to own a gap, or to
adopt a corrected claim is a human's, and the record carries whose. You do
not have to learn the vocabulary first. Run `mathema verify` to see which
records fail on an unknown or falsified claim, then type `mathema accept KEY
CLAIM` with no `--as` (at a terminal; `--format json` always needs `--as`),
and mathema reads the claim's verdict and proposes
the natural kind (a `holds` is *evidence*, an `unknown` is a *risk*, a
falsification is a *discovery*), then asks you to confirm. You take the
decision by saying yes, not by memorising a vocabulary.

A configured [PIN](pin.md) is prompted for before any acceptance
writes, and the record's `accepted` block gains a
`verified_by: {method, key}` stamp, evidence the decision was made by
a person rather than an agent. Optional, and off until
`mathema pin set`; a record with no human sign-off states `pin: none`
in its identity block, so the absence is explicit, never inferred.

There is deliberately **no accepting a bug**: if the code is wrong,
fix the code, the recorded counterexample replays on every
re-adjudication until the claim proves, so a falsified claim can't be
waved through.

## Machine-readable acceptance

`--format json` emits the acceptance as data, and **writes nothing
unless `--yes` is also given**: without it you get the plan
(`applied: false`, plus the `actions` that would run), so a client can
render the decision for a human and only then commit it. JSON mode
never prompts, so a non-interactive caller can't hang waiting on
stdin, and the human gate stays exactly where it always was. A refusal
comes back as `{"ok": false, "error": ...}` with the same exit code
the prose path uses; `--output FILE` writes the payload to a file.

The same envelope covers every acceptance path, claim, function
intent, scope intent (module or `__project__`), and concepts, with
`kind` naming which one.

## Form-bound

Every acceptance binds to the function's `form` hash at the moment of
the decision. Change the function and the acceptance goes stale
outright; the gap or evidence you accepted was about different code,
so the claim fails the gate again until someone re-decides.

## Worked example

A running balance in `balances.py`, with three claims in
`claims/running_total.claims.yaml`:

<!-- example: balance file=balances.py -->
```python
def running_total(xs: list, y0: float) -> float:
    """Add every value in xs to a starting balance y0."""
    total = y0
    for v in xs:
        total = v + total
    return total
```

<!-- example: balance file=claims/running_total.claims.yaml -->
```yaml
balances.running_total:
  claims:
    - name: shifts_with_start
      statement: "f(xs, y0) == f(xs, 0) + y0"
    - name: nonneg_for_nonneg_steps
      statement: "for xs in [0, 1]^n, f(xs, 0) >= 0"
    - name: never_overshoots_much
      statement: "assuming nonneg_for_nonneg_steps is proven, for xs in [0, 1]^n, f(xs, 0) <= len(xs)"
```

`shifts_with_start` is proven (and its `shifts_with_start[float]`
companion holds). `nonneg_for_nonneg_steps` only holds: the probe
agrees, but derive cannot settle the sign of the lifted sum.
`never_overshoots_much` rests on it being proven, so it comes back
`unknown` with the note `prerequisite nonneg_for_nonneg_steps is holds,
not proven, nothing to rest this claim on`, and `verify` fails on it
(see [`mathema verify`](verify.md#unknown-claims-and-accepted-risk)):

<!-- example: balance session -->
```
$ mathema verify --root .
FAIL balances.running_total: no baseline record; 2 proven, 2 holds, 0 falsified, 1 unknown  <- 1 unknown claim(s)
0 fresh (form unchanged, skipped), 1 adjudicated, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
```

Owning that gap is a decision. At a terminal, mathema prints the exact
write and asks `write this acceptance? [y/N]`; `--yes` answers it here:

<!-- example: balance session -->
```
$ mathema accept balances.running_total never_overshoots_much --as risk --note "the premise only holds empirically; monitored" --by "Charles Babbage" --yes
accepting balances.running_total :: never_overshoots_much (verdict unknown) as risk, by Charles Babbage
  - reclassify never_overshoots_much: unknown -> skipped:unknown_but_accepted (strict mode still refuses it; lenient proceeds)
written: reclassify never_overshoots_much: unknown -> skipped:unknown_but_accepted (strict mode still refuses it; lenient proceeds)
```

## `--as historical`

A claim the code has moved past, a parameter renamed or removed, so
its variables no longer match the signature, is flagged by verify
and accepted as history: the row leaves the live claims for the
append-only `historical:` section, carrying the git commit its last
supported adjudication was stamped with. It stops gating and never
resurrects.

## `--as superseded`

Re-authoring a claim that is already in the verified layer (the
same name with a different statement, region, tolerance or route on
any authoring surface) is a conflict verify flags, and the verified version keeps
adjudicating until a human adopts the change:

```
mathema accept mypkg.mod.fn claim_name --as superseded
```

Any verdict can be superseded. The old row moves to the record's
`superseded:` section (carrying the commit of its last supported
adjudication), and the next sweep adjudicates the authored version
as the live claim under the same name. This is how a claim's meaning
changes without its history being silently rewritten.

## `--as reconciled`: after a merge, rebase, or a declared-claim edit

Every verified record carries an
[integrity checksum](../governance.md#the-integrity-checksum) over its
claims, verdicts, and sign-offs, and an anchor (the commit it was stamped at).
When the record's contents no longer match the checksum, `verify` says
so, and now that `.mathema/` is tracked, ordinary git makes this happen
without anyone hand-editing anything: a merge or rebase brings in a
different version of a record, a stash pop restores an in-progress one,
or you append a declared claim to a function that already has a verified
row. The warning names the likely cause (a moved anchor reads as a
history rewrite; an intact one as a content change) and never accuses
you of tampering. Under a [policy](pin.md#project-policy) with
`require_verification`, the mismatch fails the run instead of warning.
Two ways to clear it:

- **Re-verify** (`mathema verify <key>`, or the whole sweep): re-adjudicates
  against the live code and re-stamps. This is the default and the right
  move after a merge, it re-checks as well as re-stamps.
- **Reconcile** when the contents are already correct and you just want to
  bless them as they stand (a large suite, a record you have reviewed):

  ```
  mathema accept mypkg.mod.fn --as reconciled
  ```

  The `key` is the function record (its `module.qualname`), and reconcile
  covers ALL of that record's claims at once, never one claim at a time. A
  human vouches for the current contents, re-stamps the integrity, and
  re-anchors to `HEAD`, records who reconciled it and when, and carries the
  [PIN](pin.md) stamp when one is configured, so an agent cannot pass it
  off as a human decision. With no PIN set it still works and records
  `pin: none`, so an unpinned reconcile stays visible as exactly that.

  A merge usually touches more than one record, so clear the whole set in
  one act with `--all` (no key):

  ```
  mathema accept --as reconciled --all
  ```

  It lists every record whose checksum no longer matches, asks once, and
  re-stamps them all under a single sign-off.

### Moved functions: `--as reconciled --from`

A record is keyed by the function's dotted `module.qualname`, so moving
a function to another module (or renaming it) leaves its record behind
under a key that no longer resolves. `verify` notices when that orphan's
form hash matches a function that has no record, and prints the rename
as the remedy. Moving `running_total` from `balances.py` to
`ledger.py`, with its claims file stanza renamed to match:

<!-- example: balance run -->
```bash
mv balances.py ledger.py
```

<!-- example: balance file=claims/running_total.claims.yaml -->
```yaml
ledger.running_total:
  claims:
    - name: shifts_with_start
      statement: "f(xs, y0) == f(xs, 0) + y0"
    - name: nonneg_for_nonneg_steps
      statement: "for xs in [0, 1]^n, f(xs, 0) >= 0"
    - name: never_overshoots_much
      statement: "assuming nonneg_for_nonneg_steps is proven, for xs in [0, 1]^n, f(xs, 0) <= len(xs)"
```

<!-- example: balance session -->
```
$ mathema verify --root .
FAIL balances.running_total: cannot resolve to a live function (declared in .mathema/verified/balances.running_total.yaml); its form hash matches ledger.running_total, which has no record. If it moved, a human keeps its history with: mathema accept ledger.running_total --as reconciled --from balances.running_total
FAIL ledger.running_total: no record yet, and its form hash matches the orphan record balances.running_total; nothing was adjudicated or written for this key. If it moved, a human keeps its history with: mathema accept ledger.running_total --as reconciled --from balances.running_total; if it is a different function, remove the orphan record instead
0 fresh (form unchanged, skipped), 0 adjudicated, 2 problem(s)
grammars detected: (none); verified by this run: mathema
```

The new key gets no fresh record in the meantime, because a fresh
record would start its history over. The rename is a human act, since
only a person can say the two are the same function (again with
`--yes` standing in for the prompt, `write this rename? [y/N]`):

<!-- example: balance session -->
```
$ mathema accept ledger.running_total --as reconciled --from balances.running_total --by "Charles Babbage" --yes
reconciling ledger.running_total from balances.running_total: a record rename, by Charles Babbage
  - rename the record balances.running_total to ledger.running_total, carrying its claims, acceptance history, lineage and sign-offs
  - remove .mathema/verified/balances.running_total.yaml
  - re-stamp the integrity and re-anchor it to HEAD
written: reconciled: balances.running_total renamed to ledger.running_total (by Charles Babbage)
next: `mathema verify ledger.running_total` re-adjudicates it at its new location
```

The record moves whole: every claim row with its acceptance and
acceptance history, the discoveries, historical and superseded
sections, the lineage, and a lock if there is one. Like any reconcile
it re-stamps the integrity, re-anchors to `HEAD`, and records who did
it, when, and where the record came from (`identity.reconciled.from`),
with the [PIN](pin.md) stamp when one is configured. The old record
file is removed, so no orphan is left behind.

The rename is refused (exit 1, nothing written) when the old key still
resolves (that is a copy, not a move) or the new key already has a
record. An old key with no record, or a new key that does not resolve
to a live function, is exit 2. When the record's form hash differs
from the live function's, the rename asks a second question at the
prompt, since the record was made for different code; `--yes` does not
answer it, and `--accept-form-change` does. The record then keeps its
recorded form, so the next `verify` re-adjudicates it against the code
it now names, and `identity.reconciled.form_changed` states both hashes.

**Working with git.** The advice is one line: after a merge, rebase, or
conflict resolution that touched `.mathema/`, run `mathema verify` to
re-adjudicate and re-anchor. The integrity warning in that window is
expected, not evidence of tampering, and either fix above clears it.

[`mathema init`](init.md) scaffolds the git ergonomics for a tracked
store: a `.gitattributes` marking `.mathema/verified/**/*.yaml`
`linguist-generated` (a records diff collapses by default and the store
drops out of the repository's language stats, while staying expandable
when you do want to read it), and a `.mathema/.gitignore` that tracks the
durable evidence and required artifacts (`verified/`, `meta/`,
`compendium/`, `badges/`) while ignoring regenerated state (`declared/`,
`issues/`). It is additive and idempotent, so running it on an existing
project only fills in what is missing.

To review what actually changed in the store between two states, read it
by CLAIM rather than by raw YAML: [`mathema review [<ref>]`](review.md)
reports which verdicts flipped, which claims were added or removed, which
are newly falsified, and which records were reconciled, since a base ref
(default `HEAD`). `--format json` emits the same delta for a CI job to
post as a PR comment. It is the counterpart to a `git diff` over
`.mathema/verified/`, whose re-anchored lineage and reordered rows bury
the handful of facts a reviewer needs.

## `--intent` and `--concepts`

`mathema accept <key> --intent` is the human rung: it moves the
function's stated intent from `declared` to `documented`, binding to
the signature, the raised-exception surface, and the intent text
(a body-only refactor keeps it; any of those changing re-opens it).
The key can also be a module (`mypkg.mod`) or the literal
`__project__`: scope-level intents (module docstring or README
sections) accept the same way, bound to the intent text alone, and
land in `.mathema/meta/intent.yaml`; the index reports each scope's
rung and flags a stale acceptance when the text has moved on.
`--concepts a,b` accepts tags as documented; `--dismiss-concepts c`
records a dismissal in `.mathema/meta/concepts.yaml` so the
suggestion never repeats. All prompted, all CLI-only, like every
acceptance.

## `--as trusted`

A compendium row (curated knowledge about a library, materialised
into the store at `declared` status when a premise first references
it) accepted at the level its curator claims. The row's verdict
becomes that level, the acceptance records the source
(`compendium:numpy-2.5`), and every conclusion resting on the row
caps there. The alternative needs no verb at all: `mathema verify`
re-adjudicates the row against the installed library, and the local
verdict replaces the testimony. See
[Claims transfer](../claims-transfer.md).

