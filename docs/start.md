# Start here

mathema checks Python functions against short mathematical statements
about them, called claims. Where a function can be read as mathematics,
mathema proves the claim for every input in the range you name; where it
cannot, it runs the real function on inputs chosen to break the claim and
reports the input that did. Each result is kept as a record bound to the
exact code it was checked against, so the check is repeated when that code
changes.

Below are four reading orders through this site, one per job. Each names
what you get from each page and ends with the first command to run.

## Checking a numerical library function

For a quant or data scientist whose function calls numpy, pandas or
polars, and who wants to know what a proof adds to the tests they already
have.

1. [Quick start](quickstart.md): one scalar function, a claim that is
   falsified, the counterexample that says why, and the same claim proven
   once its domain is stated.
2. [Claims about a pandas function](pandas-function.md): a function that
   takes a `Series`, the real `Series` it receives, a wrong claim and its
   witness, and a proof for every length through what mathema knows
   about pandas.
3. [The evidence ladder](evidence-ladder.md): what `proven` establishes,
   what `holds` establishes, and why the two are never reported as one.
4. [See what mathema knows about a library you call](library-claims.md):
   which of the numpy calls your code makes have claims, the sweep that
   checks them on your machine, and how to state one for a call nothing
   covers.
5. [Runtime types: numpy, pandas, polars](runtime-types.md): the reference
   behind it, from how a parameter's runtime type is read off the
   signature to claims over `DataFrame` columns.

First command:

<!-- checked by hand -->
```bash
pip install "mathema[numpy,pandas]"
```

## Adding claims to an existing codebase

For a maintainer with a pytest suite who wants to know how claims relate
to the tests they have, where a claim goes, and how to reach a passing
`mathema verify` without rewriting anything.

1. [Quick start](quickstart.md): the shape of a claim, the record it
   produces, and the docstring `Claims:` block, which is where a claim goes
   when it lives beside its function.
2. [From a pytest test to a claim](from-a-pytest-test.md): one real test
   read as a sentence, that sentence stated as a claim and run, and what
   each of the two still does that the other cannot.
3. [Add claims to an existing codebase](existing-codebase.md): where to
   start in a package with none, the stubs and suggestions that get the
   first claims written, one claim tried before the sweep writes anything,
   and the first green sweep.
4. [Authoring claims](authoring.md): the four places a claim can live, and
   which one wins when two disagree.
5. [`mathema coverage`](modes/coverage.md): which lines of each function
   your tests, mathema's probes and its proofs have exercised, and the one
   action that would raise the figure.
6. [Gate a pipeline with mathema verify](gate-a-pipeline.md): the sweep
   in CI, from the first red run to a green one.

First command:

<!-- checked by hand -->
```bash
mathema audit mypkg
```

## Gating a pipeline with mathema verify

For a platform engineer who wants the workflow file, the exit codes, and
what to do when the gate fails on a claim nobody on the team wrote.

1. [Gate a pipeline with mathema verify](gate-a-pipeline.md): the
   workflow `init --ci` writes, the first red run read line by line, the
   decision a library row nobody wrote asks of the team, strict against
   lenient, and each exit code from a real run.
2. [Verdicts and exit codes](verdicts.md): what each verdict establishes
   and does not, and the four exit codes every verb shares.
3. [`mathema verify`](modes/verify.md): the full table of what fails the
   run in strict and in lenient mode.
4. [Governance and audit](governance.md): who can decide what, what each
   decision records, and the integrity checksum that catches an edit made
   outside mathema.
5. [Security and execution](security.md): what runs when a claim is
   checked, and where to put the boundary in CI.
6. [`mathema review`](modes/review.md): the claim-level difference between
   a git ref and the working tree, for the pull request.

First command:

<!-- checked by hand -->
```bash
mathema init --ci
```

## Building with a coding agent

For a developer whose agent should write claims and run checks without
deciding what counts as correct.

1. [Set up mathema for a coding agent](agent-setup.md): the server block
   for Claude Code, Cursor and Claude Desktop, the skills `init --agents`
   vendors, the PIN and the policy, in the order to do them.
2. [Working with coding agents](agents.md): what an agent can do, what only
   a person can do, and why the PIN keeps the two apart.
3. [`mathema mcp`](modes/mcp.md): each tool, resource and prompt the server
   exposes, and the shape of what they return.
4. [`mathema pin`](modes/pin.md): what the PIN stamps into a record, and
   the policy file that makes a missing stamp fail the sweep.
5. [`mathema lock`](modes/lock.md): settling a finished function, so that
   the sweep fails and refuses to re-adjudicate if the agent's next pass
   changes its body.

First command:

<!-- checked by hand -->
```bash
pip install "mathema[mcp]"
```
