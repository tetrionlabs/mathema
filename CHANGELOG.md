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
- A witness a reader cannot see is spelled out: a string holding
  combining marks, format characters or unusual spaces is followed by
  its escaped form (`s='プ' ('\u30d5\u309a')`), and two compared sides
  that differ yet read the same are both spelled out. Ordinary text is
  shown as it is.
- An integer result too large for a float (factorial over `N`) is
  compared exactly and no longer crashes adjudication with an
  OverflowError.
- A recorded counterexample replays as the value that broke the claim: a
  string witness that reads as a complex number (`"j"`, `"2J"`) stays a
  string, and a complex witness is now stored tagged
  (`{"complex": "1+2j"}`); an older record's complex spelling still
  replays where the parameter can hold one.
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
