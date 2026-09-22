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
   -n 4` runs the suite in parallel.

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
5. Open the pull request against `main`, describing what changed and
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
