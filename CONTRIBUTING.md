# Contributing

## Before your first contribution

You'll need to agree to the [Contributor License Agreement](CLA.md) before a contribution from you can be merged. There is no separate signing step to do in advance: by submitting a Contribution, you accept the terms of CLA.md.

For your first pull request, please confirm in a comment that you have read and agree to the terms of CLA.md. This confirmation is recorded with the pull request.


## Process

1. Open an issue first for anything beyond a small, obvious fix, so
   the approach can be discussed before you put time into an
   implementation.
2. Fork the repository and work on a branch. In a virtual environment,
   `pip install -e '.[test]'` installs mathema plus everything needed
   to run the test suite.
3. Make sure `python -m pytest`, `ruff check .`, and `mypy mathema`
   all pass locally before opening a pull request. Use `python -m
   pytest`, not bare `pytest`: `tests/` has no `__init__.py` and some
   test modules import from a sibling as `from tests.test_x import y`,
   which only resolves when the repository root is on `sys.path`, and
   the `-m` form puts it there. For a faster loop, `python -m pytest
   -n 4` runs the suite in parallel. The `dev` extra (build, twine, pre-commit, ruff, mypy) needs Python 3.11 or later; mathema itself supports and is tested on 3.10.

   One thing worth knowing before you trust a red result: proof
   attempts are capped on the wall clock, so anything that slows the
   machine (heavy load, a second test run, coverage tracing) can turn
   a `proven` into a `holds` and fail an assertion about the verdict
   rather than about the code. Re-run a failing verdict assertion on
   its own before believing it, and check
   `Probe.meta["mathema.timeout"]`, which records when a cap fired.
4. Every new claim family, probe, or derive-route capability needs
   test coverage exercising both the case where it applies and the
   case where it correctly declines to.
5. A change that can move a verdict runs the verdict family of its
   rule area before review. A family (`tests/families/`) is a set of
   small functions and claims about them; the runner calls each
   function at points of the claim's domain and checks that no
   `proven` verdict is contradicted by a call and that every
   `falsified` witness really fails when called. The areas are
   `raises`, `missing`, `safety`, `enforced` and `assumptions`.

       python -m mathema._devtools.verdict_families raises

   To see which rows your change moves, export the base branch's
   `mathema/` package and run against it:

       mkdir -p /tmp/base && git archive origin/develop mathema | tar -x -C /tmp/base
       python -m mathema._devtools.verdict_families raises --base /tmp/base/mathema

   Each row is then unchanged, fixed (wrong on the base, right now),
   lost (a true proof the base gave and your branch does not) or
   newly wrong. Paste the summary into the pull request. The tests in
   `tests/test_no_family_verdict_is_contradicted_by_a_call.py` run
   every family on the current tree; a case that needs a reading this
   tree does not have yet is skipped with that reading named. A case
   that shows something new about the code goes into its family, with
   a line saying what it shows, and its verdict on the base branch is
   recorded in `tests/families/expected.json` (`--all-rules --record`).
6. Open the pull request against `main`, describing what changed and
   why. Reference the issue it addresses, if any.

## What's most useful to contribute

- **New claim families**: a built-in algebraic law (like the existing
  commutativity/idempotence/monotonicity checks) that applies broadly
  enough to be worth probing for automatically, not just something
  specific to one function.
- **Reduced counterexamples**: when a probe falsifies a claim, a
  smaller or simpler counterexample than the one first found is a real
  improvement to the record, not a cosmetic one.
- **Specification clarifications**: mathema implements
  [claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development),
  a separate, independently maintained spec. If you find a place where
  mathema's own output doesn't match what the spec actually says (or
  where the spec itself is ambiguous), an issue describing the
  mismatch precisely, quoting both sides, is genuinely useful, whether
  the fix belongs in mathema or upstream in the spec.

## Reporting a bug

See [SECURITY.md](SECURITY.md) for a security vulnerability. For
anything else, `mathema describe --issue` generates a structured failure report
you can attach to a new GitHub issue; see its `--help` output for
usage.
