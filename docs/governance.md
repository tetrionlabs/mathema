# Governance and audit

A verification record is only worth keeping if a reviewer can tell who
decided what, on what evidence, and whether anything has changed since
without anyone saying so. mathema is built around that question, in the
manner of a ledger rather than a report: every verdict is bound to the
code that earned it, every human decision is recorded with its author
and its reason, nothing is deleted when a belief turns out to be wrong,
and the gate in CI fails on anything that has drifted. This page puts
the pieces together for the person who has to sign off on them, whether
an engineering lead, a model validator or an auditor.

## Who can do what

| Action | Who | Where it is recorded |
|---|---|---|
| State or propose a claim | anyone, including a coding agent | the declared layer, with where it was authored (`authored.surface`) and who proposed it |
| Adjudicate a claim | only mathema | the verified record: verdict, route, evidence, and the form hash of the code |
| Accept evidence as sufficient, own a gap as risk, or record a falsification as a discovery | only a person, at a terminal, with [`mathema accept`](modes/accept.md) | the claim's `accepted` block and the record's acceptance history |
| Lock a function against change | a person or an agent | the lock file and the record's lock history |
| Unlock a function | only a person, behind a prompt and optionally a PIN, with no `--yes` | the lock history |

No tool exposed to agents over MCP accepts a verdict from its caller or
performs an acceptance, and a weaker restatement of a claim never erases
the stronger one it replaces, see
[Working with coding agents](agents.md).

## What a decision records

An acceptance writes what was accepted (`evidence`, `risk`,
`discovery`, and the housekeeping kinds), the date, who decided, their
note, and the form hash of the code the decision was about, so an
acceptance never silently carries over to code that has since changed.
An evidence acceptance also keeps the trial count and confidence it was
granted on. Each decision is appended to the record's acceptance history
rather than overwriting the last one.

Who decided is, by default, your git `user.name`, which is a name rather
than a proof of identity. To make it an attestation, set a
[PIN](modes/pin.md): the decision is then stamped `verified_by` with the
method and a key id. The code is read from the controlling terminal
only, which an agent driving a shell normally does not have, and the
secret lives outside the repository. A committed
[project policy](modes/pin.md#project-policy) can require that stamp,
restrict it to stronger methods, and name the key ids allowed to sign,
and `mathema verify` then fails any acceptance that does not carry it,
including one written into the YAML by hand.

## Nothing is deleted

A claim that was believed and turns out wrong is not removed. It moves
to the record's `discoveries`, `historical` or `superseded` section with
the commit of its last supported run, and a claim that stops holding on
changed code becomes `invalidated` until it holds again or a person
records why it no longer should. A year later the record still says
someone believed the opposite, and why they stopped. See
[the CDD loop](tutorial.md) for the whole sequence on a real function.

## The integrity checksum

Every verified record carries a checksum over the parts of the record a
decision rests on:

- for every live claim and every row of the `discoveries`, `historical`
  and `superseded` sections: its name, statement, domain, route,
  tolerance and verdict, what supersedes it, and a summary of its
  acceptance (the kind, the attesting key, and whether it has gone
  stale);
- the function's form hash and claims fingerprint, the accepted intent,
  and the locked form.

Notes, proof sketches, trial counts and sampling details are outside it,
since they explain a verdict rather than constitute it.

The checksum detects a record that was changed outside mathema: a
hand-edit, a botched merge, a rebase that interleaved two histories.
`mathema verify` reports such a record by name and says what most likely
happened; under a policy with `require_verification` the mismatch fails
the run. After a legitimate merge, `mathema accept --as reconciled`
restamps the record and records that it did.

The checksum is unkeyed, so anyone who can run mathema can restamp a
record. It is a tripwire for changes that did not go through mathema,
not a signature. What makes a deliberate change visible is the
combination around it: records are committed YAML, reviewed like code,
[`mathema review`](modes/review.md) renders a pull request's changes as
flipped verdicts, added and removed claims and new acceptances rather
than as YAML noise, and a CODEOWNERS rule on `.mathema/verified/` puts a
named approver in front of every change to it.

## The gate

`mathema verify` in CI re-adjudicates everything whose code has changed
and fails the run on a falsified, invalidated or unknown claim, on a
changed body behind a lock, on a lock removed outside `mathema unlock`,
and on an acceptance the policy rejects. In its default strict mode it
also fails on skipped claims and on accepted risk, so relaxing the gate
is itself a visible flag rather than a quiet default. The full table is
in [`mathema verify`](modes/verify.md#what-fails-the-run).

A pipeline that holds this together:

```yaml
- run: mathema verify                       # the gate
- run: mathema review origin/main --format json > review.json   # the PR comment
```

## Reproducing a verdict

A record states the mathema version, the CDD spec version, the date and
the commit it was adjudicated at, and sampling is seeded, with the seed
kept in the record's sampling plan. Re-running `mathema verify --all` at
that commit, with that version, reproduces the same draws and the same
verdicts, with one stated exception: a proof close to its time cap can
finish on one machine and not on a slower one, and the record says so
whenever a cap was hit. See [Guarantees and limits](guarantees.md).
