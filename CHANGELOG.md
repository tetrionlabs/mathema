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
  numeric fields, so a claim over rows can reach `proven`.
- Two results compare by their values whatever their leaves are: a
  parser's nested result holding `None` or strings is equal to itself,
  a ragged value is compared leaf by leaf, records that do not subtract
  compare by their own equality, and two sequences of different length
  (or arrays of shapes that do not broadcast) are unequal outright, so
  a filter that drops a row falsifies `f(xs) == xs` with a witness. An
  ordering over such values is unanswerable, as before.
- A string concatenation in a claim keeps its order when rendered
  (`s + "0"` never becomes `"0" + s`).
- A language may supply its own derive strategy, a `derive` method
  found through any refinements around it and called for a claim
  quantified over it; a proof it returns is the claim's derive verdict
  on the route `derive:<mechanism>` it names, and anything else leaves
  the claim to the probe.
- A witness too deep for Python to print is summarised by its type and
  depth, `<Node nested 2100 levels deep (1050 Node records)>`, instead
  of the adjudication raising.
- A claim resolves each language once for all its draws; where no
  member sits exactly on a refinement's bound, the nearest ones inside
  and past it are visited.
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
- A witness that is a record with only a default repr (a SQLAlchemy or
  Django row) is shown by its public fields, `Order(id=1, sku='ABC',
  quantity=0)`, instead of its class and address.
- A claim over a language that cannot produce a member to sample (a
  schema whose checks reject every record drawn) is skipped with the
  `input-synthesis` gap and the language's reason, instead of raising
  out of `check_conjectures`.
- A language's shrink candidates come one at a time, largest deletions
  first, and the witness shrinker takes them as they come, so a long
  failing string shrinks in a few hundred membership checks instead of
  tens of thousands (a 20,000-character witness took 42 seconds).
- An `excluded_outside_domain` witness over a language says why the value
  is outside it, in the language's own words: `form = SignupForm(...)
  (outside L[SignupForm] at .age: Input should be greater than or equal to
  13)`.
- An `is_arbitrary_input_safe` witness over a language says whether it lies
  inside the claim's domain, exclusions included: over `L[unicode] \ {""}`
  a crash on `''` is labelled outside `L[unicode] \ {""}`, not inside
  `L[unicode]`.
- A norm can be written with double bars, the order a subscript on the
  closing bars: `||x||` is `norm(x)` (Euclidean for a vector, Frobenius
  for a matrix), `||x||_1`, `||x||_2`, `||x||_inf` (also `_oo`, `_∞`)
  and `||x||_p` for an integer `p >= 1` are `norm(x, 1)` and so on, and
  `||x||^2` is the square of the norm. Unicode reads and writes `‖x‖`,
  `‖x‖₂`, `‖x‖∞`. A claim renders in the spelling it was written in, a
  bare `||x||` names the norm it resolved to in the record's note, and
  any other order is refused naming the accepted ones. In the call
  form every infinite order (`norm(x, oo)`, `norm(x, infinity)`,
  `norm(x, ∞)`) is `norm(x, inf)`, which the probe evaluates as the
  largest magnitude; before, `oo` there was sampled as a free variable
  and the claim falsified. A claim written with the bars before 0.6.1
  stored `norm(x)` as its statement and re-fingerprints once.
- The derive route reads a norm over a vector: `||x||` and `||x||_2`
  as the root of the sum of squares, `||x||_1` as the sum of
  magnitudes, `||x||_inf` as the largest magnitude, and `||A||` on a
  matrix as the root of the trace of `A @ A.T`. A length, a distance,
  a normalisation, a weight vector's `||w||_1` and a Gram trace are
  proven for every length through the numpy definition rows; a matrix
  `_1`, `_2` or `_inf` norm, a chain of norm orders and the triangle
  inequality stay with the probe.

## 0.6.0

First public release.
