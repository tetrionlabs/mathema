# Changelog

Notable changes to mathema are recorded here from its first public release onward.

## Unreleased

- The wheel now ships the bundled compendium. The 0.6.0 wheel carried
  none of its compendium files (the package-data pattern missed the
  per-library directories), so `is_compendium_safe(numpy)` was `unknown`
  for every installed copy and numpy calls counted as uncovered in the
  clarity score.
- A compendium is now an ordinary claims file whose keys are a library's
  functions, with two file-level fields: `compendium:` naming the
  library and `versions:` the installed versions its claims apply to
  (`"*"`, `">=X"` or `">=X,<Y"`). A project states its own in any claims
  file, such as `claims/numpy.claims.yaml`, shadowing the bundled entry
  per function. `mathema verify` adjudicates the rows of the library
  functions a project calls or rests a premise on against the installed
  library, and a premise resolves at the verdict recorded there.
- The 0.6.0 compendium shape (`package:`, `functions:`, `params`,
  `raises_when`, `nan_when`, `limitations`) and the
  `.mathema/compendium/` directory are gone; a definedness region is an
  `is_defined` row and a limitation is the entry's `intent:`.
- `mathema compendium export <library>` writes the library's proven and
  held rows as such a claims file, by default to
  `claims/<library>.claims.yaml`.
- `mathema --version` prints the installed version.

## 0.6.0

First public release.
