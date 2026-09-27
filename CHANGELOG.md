# Changelog

Notable changes to mathema are recorded here from its first public release onward.

## Unreleased

- A value claim over a string parameter with no stated domain is skipped
  with the `string-domain-missing` gap, naming the parameter and the
  spelling that fixes it, as the automatic probes already were; it used
  to draw real numbers for the string and falsify on them.
- A function whose parameters are all strings and which returns no
  number is no longer offered `is_numerically_stable` among its
  suggested claims; it keeps the arbitrary-input family and the purity
  claims.
- A parameter's kind is read through a quoted annotation (every one under
  `from __future__ import annotations`), `typing.`, `Optional[...]` and a
  union with `None`, so `Optional[str]` is a string parameter and
  `Optional[float]` a scalar one.
- A finite set listing a missing value beside numbers
  (`for x in {0.25, None}`) no longer crashes the record's sampling
  summary.
- A claim whose domain bound turns complex under interval evaluation
  (`sqrt(1 - r**2)` over an unbounded `r`) returns a verdict instead of
  raising out of `check_conjectures`.


## 0.6.0

First public release.
