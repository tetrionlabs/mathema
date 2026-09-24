# `mathema pin`: human-verified decisions

The claim record answers what was verified and how hard. This answers
the other question a reviewer, an auditor, or a regulator asks about a
codebase agents help build: **was the sign-off actually made by a
person?**

`by:` alone cannot answer it; a free string is typed by an agent as
easily as by a person. A PIN can: a person knows it, an agent does
not, so an acceptance (or an [unlock](lock.md)) that carries the stamp
was authorised by someone at a keyboard, and the record proves it
rather than asserts it. The verification is written into the record
twice, permanently: the `accepted` block carries
`verified_by: {method, key}`, and so does every event in the claim's
`acceptance_history`, so the audit trail survives later re-decisions.

```bash
mathema pin set          # choose a PIN (4-12 digits), prompted twice
mathema pin status       # method and key id, never the secret
mathema pin rotate       # replace it (verifies the current one first)
mathema pin remove       # delete it (also verifies first)
```

Entirely **optional**: with no PIN set, nothing prompts and nothing
changes. Set one and every acceptance path (claim, intent, scope
intent, concepts) and every unlock asks for it before writing.

## What it looks like

```text
$ mathema accept funcs.settle nonneg --as evidence
accepting funcs.settle :: nonneg (verdict holds) as evidence, by Alonzo Church
  - annotate nonneg as accepted evidence at n=130 (bound to form 206704b327da...)
write this acceptance? [y/N] y
PIN:
written: annotate nonneg as accepted evidence at n=130 (bound to form 206704b327da...)
```

and in the record (trimmed):

```yaml
      accepted:
        as: "evidence"
        at: "2026-09-24"
        n: 130
        form: "206704b327da"
        by: "Alonzo Church"
        verified_by:
          method: "pin"
          key: "a3f2c1"
```

`verified_by` names the method and the credential's **key id**. The
key id is why a PIN reset is auditable: rotating or replacing the
credential produces a new id, so an acceptance signed by a key that is
not the currently configured one is visible to any reviewer.

## The rules that make it mean something

- **The code is read from the controlling terminal only.** A pipe, a
  captured subprocess, a caller with no `/dev/tty`: refused outright,
  never silently read from stdin. `--yes` still skips the y/N prompt;
  it never skips the PIN. `--format json` without a terminal refuses
  to apply and says why (the plan-only preview still works).
- **The gate sits at the write boundary, not at the prompts.** Every
  acceptance path funnels through one library chokepoint, so the JSON
  path, scripted use, and the concepts curation path (which previously
  wrote without any prompt) are all covered.
- **Rotate and remove verify the current PIN first.** Otherwise an
  agent could reset the credential to one it knows.
- **The secret never enters the project.** It lives in
  `~/.config/mathema/auth.yaml` (mode 0600, respecting
  `XDG_CONFIG_HOME`), outside any repository an agent works in.
  Records and policy files carry only the key id. Lost PIN: delete
  that file and set a new one; the old key id stops matching, which is
  itself the audit trail working.

## The honest threat model

This is a tripwire and an attestation, not a cryptographic barrier. An
agent with unrestricted shell could delete the credential file or edit
mathema itself; what it cannot do is produce a valid `verified_by`
stamp in the normal course of work, and every subversion leaves a
visible trace: a missing credential, a key id mismatch, an integrity
checksum failure (the checksum covers the acceptance block and every
retirement row). Calibrate
trust accordingly, the same way the evidence ladder asks you to.

## Project policy

`.mathema/meta/policy.yaml`, committed and human-owned, holds the
public constraints:

```yaml
acceptance:
  require_verification: true   # every acceptance must carry verified_by
  methods: [totp]              # allowed methods; omitting pin disables the static PIN
  keys: [a3f2c1]               # optional allowlist of key ids
```

Enforced twice. At **write time**, an acceptance the policy forbids is
refused: no credential when one is required, a static PIN where only
stronger methods are allowed, a key outside the allowlist. At
**verify time**, every *standing* acceptance in the record is checked
too, so an unverified sign-off cannot ride in through a hand-edited
YAML file: `mathema verify` fails the run, which is the CI gate. That
includes the rows of the `discoveries`, `historical` and `superseded`
sections, since each one takes a claim out of the gate. Under
`require_verification` a record whose integrity checksum no longer
matches its contents also fails the run, where without a policy it
only warns.

### CI, GitHub, GitLab

Acceptances happen locally, at a terminal, and travel as commits; CI
never holds the PIN. The pipeline runs `mathema verify`, and with a
policy present that alone enforces that every acceptance was
human-verified by an allowed credential.

Platform protections compose on top: branch protection plus a
CODEOWNERS rule on `.mathema/verified/` makes any change to acceptance
blocks require a human PR approval, with the forge's own login 2FA as
the second factor. `verified_by` is the record-level half that
survives outside any forge.

## Planned enhancement: authenticator-app codes

`mathema pin set --totp` (experimental) enrols a standard RFC 6238
TOTP secret into any authenticator app, the same 6-digit
rotate-every-30-seconds codes used for GitHub or Google 2FA. One QR
scan at setup; afterwards the prompt accepts the app's current code,
and a code an agent observes in a transcript is dead half a minute
later. The mechanism is built and tested; the static PIN is the
promoted path for now. The `verified_by: {method, key}` stamp is an
open seam: a stronger backend verifies its own way and records its own
method and key.
