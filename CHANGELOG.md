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
- `excluded_outside_domain(s)` and `is_arbitrary_input_safe(s)` read a
  declared language: the near non-members come from the language, a
  witness says whether it lies inside or outside it, and shrinking never
  crosses the boundary. The derive route lifts a schema language's
  numeric fields, so a claim over rows can reach `proven`. A field
  binding deeper than one level is refused by name.
- Two results compare by their values whatever their leaves are: a
  parser's nested result holding `None` or strings is equal to itself,
  a ragged value is compared leaf by leaf, and records that do not
  subtract compare by their own equality; an ordering over such values
  is unanswerable.
- A string concatenation in a claim keeps its order when rendered
  (`s + "0"` never becomes `"0" + s`).

## 0.6.0

First public release.
