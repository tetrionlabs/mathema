# Changelog

Notable changes to mathema are recorded here from its first public release onward.

## 0.6.1

- The wheel now ships the bundled compendium. The 0.6.0 wheel carried
  none of its compendium files (the package-data pattern missed the
  per-library directories), so `is_compendium_safe(numpy)` was `unknown`
  for every installed copy and numpy calls counted as uncovered in the
  clarity score.
- A compendium is now an ordinary claims file whose keys are a library's
  functions, with file-level fields beside `grammar`: `compendium:`
  naming the library, `versions:` the installed versions its claims
  apply to (`"*"`, `">=X"` or `">=X,<Y"`), and optionally `aliases:`,
  other names for the library (a distribution name such as `PyYAML`, a
  key prefix such as `np`). A row may carry its own `versions:`. A
  project states its own compendium in any claims file, such as
  `claims/numpy.claims.yaml`, shadowing the bundled entry per function.
  The bundled compendium covers `math` and 28 numpy functions, now
  including `divide`, `true_divide` and `reciprocal`.
- The 0.6.0 compendium shape (`package:`, `functions:`, `params`,
  `raises_when`, `nan_when`, `limitations`) and the
  `.mathema/compendium/` directory are gone; a definedness region is an
  `is_defined` row, and what the library does outside it is the row's
  `note:`.
- `mathema verify` adjudicates the rows of the library functions a
  project calls or rests a premise on against the installed library,
  and those rows gate the run until verified locally or accepted with
  `mathema accept <key> <row> --as trusted`. `mathema verify <claims
  file>` adjudicates every row of that file up front.
- Mathematics and computation are separate. The derive route proves a
  claim over the reals, with infinity as infinity, and reads nothing
  about float64; what the code does in float64 is the computation's
  question, answered by execution: the `[float]` companion every proof
  spawns and the probe route. A raise, a NaN from non-missing inputs or
  an infinity from a finite input is no value, and fails every relation.
- The operational infinity resolves at three levels, the claim (`let
  |inf| be`), the function (a claims-file entry's `pseudo_infinity:`,
  or `check(fn, pseudo_infinity=)`) and the project
  (`MATHEMA_PSEUDO_INFINITY`), else the number representation's maximum. It bounds
  only the computation, never a claim's identity, and is shown as a
  plain `let |inf| be ...` in front of a computation row's condition
  only where it bounds an unbounded direction. Along an unbounded
  direction, nine draws in ten stay at everyday magnitudes and one in
  ten goes toward the reach.
- The computation-safety families are organised by the three questions
  they answer: does it run on my domain, is the answer right in
  float64, is it repeatable. New: `is_overflow_safe` (with a
  restriction form stating where the computation stays in float range),
  `is_recursion_safe`, and two roll-ups, `is_computation_safe(f)` for
  the first two questions and `is_repeatable(f)` for the third, where a
  function taking a seed or generator is held to `is_reproducible`.
  `is_memory_safe`, `is_precision_safe`, `is_order_invariant`,
  `is_concurrency_safe` and `is_representation_consistent` are reserved:
  `skipped` in this release.
- The clarity score reads each call's hazard from the callee's own
  record (`CLARITY_ALGO` entropy-dimensions@1.2), so clarity scores move
  once with this release.
- `mathema compendium status` reports, for each third-party library the
  project calls, its claims files, the called functions with no claims,
  and how many rows are verified locally, trusted or unsettled.
  `mathema compendium update` pins the non-default literal arguments
  the project's calls pass into rows of its own compendium files, and
  widens a used row's own `versions:` once it holds on the installed
  version. `mathema compendium export <library>` writes a library's
  proven and held rows as a claims file for downstream projects.
- `mathema describe` lists the edges just outside a passing domain that
  the computation rows know about, as information, never a verdict.
- `mathema --version` prints the installed version.

## 0.6.0

First public release.
