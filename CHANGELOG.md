# Changelog

Notable changes to mathema are recorded here from its first public release onward.

## Unreleased

- Language domains: `for text in L[unicode], ...` quantifies a string
  parameter over a named language. mathema parses, renders and records
  `L[...]`; the names come from the `mathema-language` package
  (`pip install "mathema[language]"`), or from a language registered in
  the process, a `mathema.languages` entry point, or a
  `mathema.language_adaptors` adaptor. The probe samples the language's
  own hazards and members, the record states what a language resolved
  to, and the derive route declines a string with the reason, except
  over a finite language, which it sweeps.
- The extension surface gains three seams, `languages`, `families` and
  `sampling`, and two entry-point groups, `mathema.languages` and
  `mathema.language_adaptors`; a claim family registered under a name
  shaped `output_<slug>` contributes an output-contract predicate the
  way `is_<slug>_safe` contributes a safety predicate. The extension
  API version is unchanged.
- A claim over a language domain is stamped `grammar: mathema/language`;
  `𝕃[...]` is accepted on input.
- Two new relations, `in` and `not in` (`∈`, `∉`): `f(s) in L[slug]`
  holds every output to a language or a set, `"<" not in f(s)` says a
  value is never found in another, and `f(x) in [0, 1]` is read as the
  chain `0 <= f(x) <= 1`. Both are decided by execution; a missing value
  is a member of nothing unless the right-hand side says so.
- The lexicon's language rows spell the string parameter `s`, and gain
  `language_closure`, `containment_absent` and
  `membership_interval_reduces_to_chain`.
- `excluded_outside_domain(s)` and `is_arbitrary_input_safe(s)` read a
  declared language: the near non-members come from the language, a
  witness says whether it lies inside or outside it, and shrinking never
  crosses the boundary. The derive route lifts a schema language's
  numeric fields, so a claim over rows can reach `proven`. A field
  binding deeper than one level is refused by name.
- Two results compare by their values whatever their leaves are: a
  parser's nested result holding `None` or strings is equal to itself,
  a ragged value is compared leaf by leaf, records that do not subtract
  compare by their own equality, and two sequences of different length
  (or arrays of shapes that do not broadcast) are unequal outright, so
  a filter that drops a row falsifies `f(xs) == xs` with a witness. An
  ordering over such values is unanswerable, as before.
- A string concatenation in a claim keeps its order when rendered
  (`s + "0"` never becomes `"0" + s`).

## 0.6.0

First public release.
