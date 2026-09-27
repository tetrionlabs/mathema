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
- A length bound inside a language piece, `L[ascii, len <= 80]`,
  `L[unicode, len > 20]`, `L[unicode, len in [1, 80]]`, refines the
  language to members of that many code points; its outside draw is the
  member one past the bound. An `Annotated[str, MaxLen(80)]` parameter
  infers the refined language through the text adaptor.
- The derive route over a row language lifts the fields the body reads,
  through an attribute (`o.qty`) or a subscript (`o["qty"]`), for a row
  of any class an adaptor reads: a numeric field is one symbol bounded
  by its constraints (one side is enough), a text field read only as
  `len(o.sku)` is a whole number bounded by its length, and a field read
  any other way, or a row the body reads no field of, declines the lift
  with the reason, leaving the claim to the probe.
- A binding names a path into a member at any depth, `o.address.zip`,
  `o.lines[0].sku`, `o.lines[*].qty`, narrowing the probe's draws and
  bounding the leaf in the lift; the one-level limit is gone.
- Refinements inside `L[...]` are a seam: any `key op n` parses, a
  refinement registered under the key (in the process, or under the
  `mathema.language_refinements` entry-point group) serves it, and a key
  nothing serves is refused when the claim is checked. mathema owns no
  key; `len` comes from the `mathema-language` package.
- A value claim's witness over a language is shrunk inside the language,
  and a language's hazard lap visits the members at a refinement's
  bounds first.
- Over a language, a value's length renders as `len(s)`; the canonical
  form keeps `dim(s, 0)`.
- A claim over a language visits every hazard of the language once
  before any random member. The hazards are a risk factor like a wide
  interval: they raise the trial budget up front and mark down the
  confidence score, and a language with more hazards than the budget
  raises the trial count to them, which the sampling line states.
- A registered family's probe may end its result with a mapping merged
  into the record's `meta`, which reaches the record whichever route's
  report stands; `mathema.language` merges per key.
- The language adaptors are asked in an explicit order,
  `__mathema_adaptor_priority__` then name, and `language_adaptors()`
  is on the extension surface.
- A new entry-point group, `mathema.lexicon`: a package's worked claims
  join `mathema.lexicon`'s `entries()`, `search()` and `find()`, marked
  with where each came from, and are held to the checks mathema's own
  lexicon is, through `lexicon_problems` on the extension surface.
- A language domain renders the missing value as `missing` in both
  modes (`L[unicode]|missing`), never as `∅`, which reads as the empty
  language.
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
