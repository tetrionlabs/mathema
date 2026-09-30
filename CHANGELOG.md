# Changelog

Notable changes to mathema are recorded here from its first public release onward.

## 0.6.1

- A policy claim states what a function does with a value that is not
  there: `missing(f, x) propagates`, `absent(f, x) raises(TypeError)`,
  `missing(f, xs, null) drops`, with an optional premise (`assuming
  count(xs) >= 1, ...`). mathema writes one for every parameter that
  admits a kind, from a library's row, from a guard in the code, from
  what the code did, or as the default for the type (propagates for a
  hole, raises for absence), and checks each; `mathema claims KEY` lists
  them and `--write` puts the confirmed ones in
  claims/policies.claims.yaml, where changing a policy is editing one
  word. The bundled math, numpy, pandas and polars compendiums carry
  their policy rows.
- Fingerprints move once in 0.6.1: the rendered domain now states what
  it admits. A value can be not there in two ways: absent (`absent`;
  Python spells it `None`), the object itself not there, and missing
  (`missing`, `∅` in unicode), one slot holding no computable value,
  with the members `nan`, `NA`, `null` and `NaT`. A domain renders only
  what it admits: `[0.0, 1.0] : float|missing` in ASCII, `[0.0, 1.0] ⊂ ℝ
  ∪ {∅}` in unicode, a space's slot holes in brackets before the power
  (`([0.0, 1.0] | {missing})^n : float`). A type clause states exactly
  what the domain admits (`[0, 100] ⊂ Z` now admits no missing value), a binding without
  one is completed from the annotation (a `float` holds `nan`, an `int`
  or `str` nothing, `Optional[...]` may be absent), the record's
  `meta["mathema.missing"]` states the members the class resolved to,
  and a finite set is exactly its members (`{0.25, absent}` is 0.25 and
  absence). Every
  earlier spelling still reads and comes back in the new form. `mathema
  verify` re-records a claim whose record differs only by this change
  and says so once for the run, not claim by claim.
- A record writes a sentinel as its word, `{"sentinel": "missing"}`,
  and reads the older `__mathema_missing__` as `missing`.
- A function is called with the real value a listed word stands for
  (`None`, `nan`, `pd.NA`), never with a placeholder of mathema's own;
  each is tried at least once per claim, and the record lists what was
  tried (`meta["mathema.missing"]`).
- A runtime's missing values are stated as definition rows under a
  key's `defines:` (`missing := {null, nan}`), taken at face value
  (`verdict: trusted`, `route: axiom`); `mathema verify` lists a
  project's own under `definitions (trusted)`. `:=` is refused in a claim and in a
  binding. mathema ships `polars.Series` and `pandas.Series` definitions,
  and the bundled definition rows state `R^n` without `\ {∅}`.
- A `raises(...)` claim over a finite domain is proven by calling the
  function at every point.
- A value claim is judged wherever the function returns a value, a
  missing input it replaces included, and never where it returns a
  missing value: that point is recorded in the record's missing
  behaviour, not compared. A raise at a missing input is recorded the
  same way and, where no claim accounts for it, reported in the row's
  note and on `mathema verify`'s line for the function. A value claim
  with no point left to compare is `unknown`, and its note says what to
  write instead. `meta["mathema.missing"]` records what the function did at
  each missing input it was called with (`executed`) and the behaviour
  per parameter and member (`behaviour`: `raises`, `drops`,
  `propagates`, `converts` or `introduces`, or `mixed` with a witness
  for each).
- A claim over a vector, a matrix or a table meets the degenerate
  containers first (the zero and a constant vector, a vector of length
  1, all-missing vectors, a missing value at the first and at the last
  position, the zero, constant and rank-deficient matrices, a missing
  entry and an all-missing row, a missing value in every column and an
  all-missing column); a random vector then has each slot missing with
  probability 0.15, at least one and at most three slots per vector,
  each admitted member in turn. A float companion runs these too.
- `sum`, `mean`, `std`, `var`, `min`, `max`, `prod`, `median`,
  `quantile`, `dot`, `cumsum`, `cumprod` and `count` in a claim read the
  values of a vector, a missing value left out. Over no value `sum` is
  0, `prod` 1, `count` 0, `dot` and `norm` 0, and `mean`, `std`, `var`,
  `min`, `max`, `median` and `quantile` are missing; `len` counts every
  position. The bundled `polars.Series.count` row counts `null` slots
  as missing and `nan` slots as values.
- A definition row may define `absent` (`absent := {Option::None}`); one
  value may be both the absence and a hole member, and two hole members
  that are one value are refused at load.
- A record says in one sentence what the function did at each missing
  input it was called with (`at x = nan f gave nan back`, `at x = None
  f raised TypeError`); what to do about it is said once, on the policy
  row. A declared `Optional` return's `None` is recorded, not judged; a
  row's count reads `(43 draws)`, or for a container `(257 entries
  across 57 draws, sizes (1, 1) to (8, 1))`.
- A policy row mathema writes that the code contradicts, and a raise no
  claim accounts for, are falsified and fail `verify` and `check` like
  any falsified claim; the row's second line names the word to write,
  and `mathema accept KEY missing[x] --as discovery --corrected "..."`
  retires it with its witness.
- `is_memory_safe` is not part of this release: it is named nowhere,
  and a claim naming it fails as an unknown predicate does, with one
  sentence saying the family is planned.
- A dimension written as a number (`for A in R^(30,15)`, `for xs in
  [0, 1]^30`, `Mat(30, 15)`, `Vec(30)`) is drawn at that size on every
  route and every runtime type. A fixed axis and a name mix in one
  binding (`R^(n,15)`), and a name a binding fixes is that size wherever
  a marker shares it.
- A value of another shape or rank is outside the domain: `f(A) in
  R^(4,3)` is judged by the output's shape (a named axis by the size the
  trial bound, a missing entry as no member), and
  `excluded_outside_domain(A)` tries every shape just outside the
  space.
- The sketch adds one clause for a fixed size (`the binding fixes xs at
  length 30`), the sampling note prints a matrix's size, a premise
  contradicting a fixed dimension is reported as vacuous, and one name
  fixed to two sizes is a conflict.
- `@enforce_dimensions()` checks rank, fixed sizes and shared names at
  entry and the return marker at exit, each failure a `ValueError`
  naming the parameter (or the result), the shape found and the shape
  expected. It stacks with `@enforce_domain()`, declares
  `excluded_outside_domain(p)` for each parameter it guards, and the
  engine draws what the guard admits.
- Rows renamed: `shape` is `result_dimensions` (it now reads a claim's
  binding, and a raise at a consistent input is its counterexample),
  `shape_enforced` is `dimensions_enforced`. New row `size_enforced`:
  does the function reject a wrong fixed size a marker states. A size
  fixed only by a binding adds no row; that question is the declared
  `excluded_outside_domain(p)` claim's. Both rejection rows need one
  in-shape call to return before they say anything.
- A vector or matrix witness above sixteen entries prints its shape, a
  first row and a count; the full value stays in the record's
  counterexample arguments.
- The lexicon gains twelve rows on fixed sizes, output spaces and the
  exclusion over a space, each with a function, and every row with a
  function now carries a pinned verdict.
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
  `is_precision_safe`, `is_order_invariant`, `is_concurrency_safe` and
  `is_representation_consistent` are reserved: `skipped` in this
  release.
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

## 0.6.0

First public release.
