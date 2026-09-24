# `mathema lock` / `mathema unlock`

Permissions for the agentic age: control what an agent may change at
the granularity that actually matters, the **function**.

File permissions cannot do this. A file is the wrong unit: one module
holds twenty functions, and making the file read-only to protect one
settled implementation blocks the other nineteen, every docstring fix,
and every new function anyone wants to add beside them. Git can tell
you a file changed; it cannot say *which function was off-limits*, and
it only speaks after the damage is committed. A lock is the granular
version: this function's implementation is settled, everything around
it stays editable, and the CDD loop itself enforces it.

A lock records the function's form hash; from then on `mathema verify`
fails if the body moves, and refuses to re-adjudicate until either the
body is restored or a human unlocks. The agent iterating in the loop
gets a clean, named stop instead of silently rewriting something a
person had signed off.

```bash
mathema lock KEY [--note WHY] [--root .]
mathema unlock KEY [--root .]
```

## What a lock pins, exactly

The **body**, nothing else. The form hash is computed over the
function's alpha-normalised AST with the docstring stripped, so:

- **Docstring edits never trip a lock.** Rewriting the prose, the
  `Intent:`, the `Notes:`, even the `Claims:` block leaves the form
  hash where it was. Claims re-authored on a locked function
  adjudicate normally.
- A rename or a reformat never trips it either, for the same reason a
  record's form binding survives them.
- Any change to what the function *computes* trips it.

## What verify does with a tripped lock

```text
$ mathema verify
ok   funcs.midpoint: fresh
FAIL funcs.settle: locked at form 3eb01e1d9919 but the code is now d70deb99df0e; the record is unchanged. Restore the function, or a human runs: mathema unlock funcs.settle
1 fresh (form unchanged, skipped), 0 adjudicated, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
$ echo $?
1
```

Three things, deliberately together: the run fails (exit 1, so a CI
gate or an agent loop stops), the message names both hashes and the two
ways forward, and **the record is byte-identical to before the edit**.
The verified baseline never moves onto code a human did not sanction,
so a failing loop cannot accumulate `invalidated` noise against an
implementation that was never supposed to change.

A function can be locked before it has any record or declared claim.
The sweep checks that lock too, and a changed body fails the same way,
with the line saying `there is no record to compare` in place of
`the record is unchanged`.

## Who locks, who unlocks

**An agent may lock.** Locking is the safe direction: a settled
implementation is worth protecting from later loop iterations, and the
MCP surface exposes `lock_target` for exactly that. An agent that has
just proven a function's claims and locked it has done something
genuinely useful: it has narrowed its own future blast radius.
`pending_decisions` shows any `locked-changed` rows, so an agent always
sees why its sweep is failing and what the remedy is.

**Only a person unlocks.** `mathema unlock` is CLI-only, prompts
`[y/N]` with deliberately no `--yes`, and, when a
[PIN is configured](pin.md), requires it. The released lock leaves an
audit event in the record (`lock_history`, with the `verified_by`
stamp when a PIN verified it), so a reviewer can see who thawed what
and when.

## Seeing what is locked

`mathema audit` shows a `locked` column whenever anything in the
population is locked (`yes`, with who pinned it), and counts locks in
the summary line, so what is locked is visible at a glance rather than
buried in a YAML file. `--compact --cols ...,locked` carries the
pinned form hash for machines.

## Where the lock lives

`.mathema/meta/locks.yaml`, committed with the store:

```yaml
# locked functions: the form hash each is pinned at.
# `mathema lock KEY` adds one; only `mathema unlock KEY`
# (a human act) removes one.
funcs.settle:
  at: '2026-09-24'
  by: Alan Turing
  form: 3eb01e1d9919
  note: settled implementation
```

The verified record carries a `locked` reflection of the same entry,
covered by the integrity checksum, which is what makes hand-deletion
detectable: a record that says locked with no meta entry behind it
fails the sweep as a lock removed outside `mathema unlock`, and a meta
entry whose `form` no longer matches the record's stamp fails it as a
lock moved outside `mathema unlock`. Either way the record is left as
it was, stamp included, so the failure stands on every sweep until the
entry is restored or a human unlocks.

## The honest threat model

An agent with unrestricted shell can edit `locks.yaml`, the record, or
mathema itself, so a lock is a tripwire, not a wall. What it
guarantees is that a locked body cannot change *through the normal
CDD loop*: the sweep fails loudly, the record stands still, and every
legitimate exit leaves a trace (the unlock event, the PIN key id).
Subversion is possible and visible; that is the design.
