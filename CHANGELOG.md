# Changelog

Notable changes to mathema are recorded here from its first public release onward.

## Unreleased

- Language domains: `for text in L[ascii], ...` quantifies a string
  parameter over a named language. Built in: `ascii`, `latin-1`,
  `unicode`, `printable`, `digit`, `alpha`, `alnum`, `identifier`,
  `json`; a package registers more under the `mathema.languages` and
  `mathema.language_adaptors` entry-point groups. The probe samples the
  language's own hazards and members, the record states what a
  language resolved to, and the derive route declines a string with
  the reason, except over a finite language, which it sweeps.
- Two results compare by their values whatever their leaves are: a
  parser's nested result holding `None` or strings is equal to itself,
  and a ragged value is compared leaf by leaf.
- A string concatenation in a claim keeps its order when rendered
  (`s + "0"` never becomes `"0" + s`).

## 0.6.0

First public release.
