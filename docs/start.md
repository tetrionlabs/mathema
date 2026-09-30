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
2. [Runtime types: numpy, pandas, polars](runtime-types.md): how a
   `pd.Series` or `np.ndarray` parameter is sampled as the object your
   code expects, and how a Sharpe ratio over a Series is proven for every
   length by reading its pandas and numpy calls through the definition
   rows mathema ships for those libraries.
3. [The evidence ladder](evidence-ladder.md): what `proven` establishes,
   what `holds` establishes, and why the two are never reported as one.
4. [`mathema compendium`](modes/compendium.md): `status` lists the library
   functions your code calls, the claims mathema ships about each, and
   which of them have been verified in your own project.

First command:

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
2. [A first look](first-look.md): what mathema reports about a function
   with no claims written, how declaring a domain changes that, and how to
   read the stored record.
3. [`mathema audit`](modes/audit.md): one line per function under a
   package: whether it has claims, whether it could be proven, what state
   outside its parameters it touches, and whether a test report covers it.
4. [`mathema claims`](modes/claims.md): the standard claims mathema
   suggests for one function, and the step that adopts one into the
   declared layer.
5. [Authoring claims](authoring.md): the four places a claim can live, and
   which one wins when two disagree.
6. [`mathema verify`](modes/verify.md): the sweep that re-checks what
   changed, and the table of what fails it.

First command:

```bash
mathema audit mypkg
```

## Gating a pipeline with mathema verify

For a platform engineer who wants the workflow file, the exit codes, and
what to do when the gate fails on a claim nobody on the team wrote.

1. [`mathema init`, the CI gate](modes/init.md#the-ci-gate-ci): `init
   --ci` writes the GitHub Actions workflow, or the GitLab fragment, that
   runs `mathema verify` on pushes to main and on pull requests, with the
   install step marked for you to edit.
2. [`mathema verify`](modes/verify.md): what fails the run in strict and in
   lenient mode, and what an `unknown` claim on a library row means for the
   gate.
3. [Exit codes](cdd.md#exit-codes): the four codes every verb shares, and
   why 1 and 2 are kept apart.
4. [Governance and audit](governance.md): who can decide what, what each
   decision records, and the integrity checksum that catches an edit made
   outside mathema.
5. [Security and execution](security.md): what runs when a claim is
   checked, and where to put the boundary in CI.
6. [`mathema review`](modes/review.md): the claim-level difference between
   a git ref and the working tree, for the pull request.

First command:

```bash
mathema init --ci
```

## Building with a coding agent

For a developer whose agent should write claims and run checks without
deciding what counts as correct.

1. [Working with coding agents](agents.md): what an agent can do, what only
   a person can do, and the PIN that keeps the two apart.
2. [`mathema mcp`](modes/mcp.md): the server your agent connects to over
   stdio, and each tool it exposes.
3. [`mathema init`, the agent skills](modes/init.md#the-agent-skills-agents):
   `init --agents` vendors the skills that teach your agent the claim loop,
   placed where your tool reads them.
4. [`mathema pin`](modes/pin.md): a PIN only a person knows, so an
   acceptance in the record was made at a keyboard.
5. [`mathema lock`](modes/lock.md): settling a finished function so the
   agent's next pass cannot change its body.

First command:

```bash
pip install "mathema[mcp]"
```
