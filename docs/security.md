# Security and execution

mathema verifies code by reading it and by running it, and the second of
those is the one a security review needs stated plainly: checking a claim
imports the module under test and calls the real function in the same
Python process. That is what makes a `falsified` trustworthy, since every
counterexample is an input at which the actual code was seen to fail, and
it is also why mathema belongs wherever that code is already allowed to
run. This page sets out what is constrained, what is not, and where to put
the boundary in CI.

## What runs when you check a claim

| Input | How mathema treats it |
|---|---|
| **The claim text** | Parsed, then validated against a strict AST whitelist before anything is evaluated. A claim can call only the function under test, functions bound to it explicitly, and a fixed set of mathematical helpers. It has no access to builtins, dunder attributes, attribute chains deeper than one field, lambdas or comprehensions, and it cannot import anything. Claim text from an untrusted source, a reviewer or a model, cannot make mathema do more than evaluate mathematics over the function. |
| **The function under test** | Imported with Python's ordinary import machinery, which runs the module's top-level code, and then called in-process on the inputs mathema chooses. Whatever the function does when called, it does here: mathema adds no sandbox around it. |
| **Record and claims files** | YAML read with the safe loader only, so a spec or record file cannot construct arbitrary objects. |
| **Functions bound to a claim** | Treated exactly like the function under test: imported and called, including a foreign implementation reached through a shim. |

The practical rule follows from the second row. Checking a claim about a
function is the same trust decision as running that function's tests:
if you would not run the code, do not check it, and if you would, mathema
adds no new way for it to reach anything.

## What mathema itself touches

- **The network.** Checking, verifying and auditing never make a network
  call. The one command that reaches the network is `mathema init
  --agents`, which fetches the agent skills through your own `git`, with
  your own credentials, and only when you ask.
- **The file system.** Checking and verifying write only under the
  project's `.mathema/` store. Beyond that, mathema writes where a
  command's own documentation says it does and nowhere else: files you
  name (`--output`, `--out`), the scaffold `mathema init` creates where
  absent (`.gitattributes`, `.mathema/.gitignore`, `claims/` stubs, and
  the agent skills or CI fragment when asked), and the coverage report
  files of `mathema coverage`. Source files are edited only by
  `mathema docsync --write-docstrings` and `--write`, and only with
  those flags.
- **Other programs.** `git` (for commit anchors, `review`, and the one
  fetch above) and, when you ask for it, your own test command under
  coverage (`mathema coverage --run-tests`).
- **Time.** Symbolic work is capped on the wall clock, so a proof that
  cannot close stops rather than hanging. Sampling calls your function
  directly and is bounded by the trial budget, not by a timer, so a
  function that never returns will hold up a check the same way it would
  hold up a test.

## Running it on code you did not write

When the code under test comes from somewhere you do not fully trust, an
agent's first draft, a contributor's pull request, a vendored dependency,
give mathema the same containment you would give its test suite:

- Run `mathema verify` in CI, in the job that already runs the tests,
  with the same restricted permissions (read-only repository token, no
  deployment secrets in the environment).
- Keep acceptance out of reach of the code being checked. Acceptance is
  a human act on the command line, never exposed over MCP, and a
  [policy with registered keys](modes/pin.md#project-policy) makes an
  unattested acceptance fail the gate, see
  [Working with coding agents](agents.md).
- Treat the `.mathema/` store as reviewable code. Its records are YAML
  diffs in the pull request, carry an integrity checksum, and
  `mathema review` renders what changed at the level of claims and
  verdicts, see [Governance and audit](governance.md).

## Reporting a vulnerability

Report a suspected vulnerability privately, as described in the
[security policy](https://github.com/tetrionlabs/mathema/blob/main/SECURITY.md),
rather than through a public issue. The most useful reports show a
concrete way one of the statements on this page does not hold.
