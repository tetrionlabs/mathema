# `mathema badges`

Three orthogonal measures of a codebase, each 0-100, and one picture.

```
mathema badges [targets]                # print the triangle + numbers
mathema badges [targets] --out .mathema/badges/   # also write artifacts
mathema badges [targets] --refresh       # score every function again
```

Omit targets for the rootwide analogue of `verify` (every function the
store knows under `--root`).

A run reads the stores, the claims files and the library claims once,
so its cost grows with the number of functions it scores. On a terminal
it reports progress to stderr every 50 functions, with the count and the
time elapsed, and prints nothing extra when stderr is not a terminal, so
a CI log or an `--out` directory stays as it was. Each function's three
steps stop at the badges step cap (60 seconds unless
`MATHEMA_BADGES_STEP_TIMEOUT` sets another), and a function whose step
stopped is named on stderr and in the snapshot's `capped` list: its
implementation then counts only the lines a fresh test report covers,
and its intent or clarity is left out of that score's roll-up.

The functions are scored in `--jobs N` worker processes (the CPU count,
up to 4, by default; `--jobs 1` scores them in the one process), and the
results are rolled up in the same order whatever N is, so the scores do
not depend on it. Each function's result is kept in
`.mathema/cache/badges/`, which carries its own `.gitignore` and is
never committed. A later run uses a kept result only when nothing that
function's result is computed from has changed:

- the function itself and everything it reaches: the functions and
  classes its source calls, theirs in turn, and any function a reached
  verified record lists among its dependencies, each by its source, its
  place in its file, its module docstring and the values of the
  module-level names it reads, with its verified record and its
  claims-file entry;
- for implementation, whether the test report is fresh for the
  function's file and which of its lines the tests ran;
- what every function shares: mathema's version and its own code, the
  sampling seeds, the Python version and platform, the `MATHEMA_*`
  environment, the installed packages and their versions, the library
  claims, `README.md`, `pyproject.toml`, `.mathema/index.yaml` and
  `.mathema/meta`.

So editing one function scores that function and its callers again, and
leaves every other function's result in place; a second run on an
unchanged project takes seconds and gives the same numbers as a run
without the cache. A result is never kept when any wall-clock cap fired
while scoring it, a capped step or a proof cap inside its check, since
that result depends on how loaded the machine was; such a function is
scored again on every run.

The reach is what the source names. A function reached only at run
time, through a name the source does not bind (a callable looked up in
a table, passed in, or built by `getattr`), is not part of it, so an
edit to that function leaves its callers' kept results in place.
`--refresh` is the full recomputation: it scores every function again
and rewrites the cache. Deleting the directory clears the cache too.
From Python, `repo_badges(cache="refresh")` does the same, and
`repo_badges(cache=False)` neither reads nor writes the cache.

## The three badges

- **implementation** (code layer): the raw line ratio from `mathema
  coverage`, how many statements a test, a probe, or a derive proof
  exercises (their union). A physical ratio, so it is neither averaged
  nor weighted.
- **intent** (spec layer): `docsync`, how much of what each function is
  meant to do is explicitly specified and up to date, so intent that lives
  only in someone's head shows up as a gap.
- **clarity** (behaviour layer): how much is KNOWN about a function's
  behaviour, scored from its VERIFIED claims. See below.

The two per-function-quality scores, intent and clarity, roll up to the
repo by a centrality-weighted mean: a function the rest of the codebase
depends on (by PageRank over the call graph) counts for more than a leaf
helper.

## The test report behind implementation

The test source of implementation comes from a coverage report that
already exists at the root, `coverage.json` first, then a native
`.coverage`. mathema reads it and never runs your tests, unless you ask:

```
mathema coverage [targets] --run-tests   # re-run the tests under coverage first
mathema coverage --stamp                 # stamp a report produced elsewhere
```

A report only counts while it still describes the code. Its lines are
keyed by line number, so once a source file changes they can point at
the wrong statements. Those lines are then left out of the score and
reported as reclaimable by a re-run. Freshness is judged per source file,
in one of two ways, and `mathema coverage` prints which one it used:

- **by content hash**, when the report is stamped. `coverage.sources.json`
  sits beside the report and holds the sha256 of every file it measured,
  plus the report's own hash. A file's lines count exactly while its
  content still matches. This holds anywhere the report travels: a fresh
  checkout, a CI artifact, a cache. A stamp written for a different report
  is ignored.
- **by file modification time**, when there is no stamp. A file is stale
  when it was modified after the report was written. That is only
  reliable on the machine that ran the tests, because a checkout resets
  file times.

`--run-tests` stamps the report it produces. A report made by another
tool, for example `pytest --cov` in CI, needs `mathema coverage --stamp`
run once afterwards, in the same tree. Stamping costs a hash of each
measured file, milliseconds even for a large package.

When the tests run in parallel mode, or measure subprocesses, coverage
writes one data file per process (`.coverage.<suffix>`). `--run-tests`
combines them before exporting, so lines executed in a subprocess, such as
a test that invokes the CLI, count. A test run that fails still produces
the report: the lines every other test executed are kept.

mathema's own functions get no probe source when mathema measures
itself. Checking one of them runs mathema's machinery, which may call
that same function, so a probe's lines cannot be told apart from the
machinery's. Test and derive lines still count.

## How clarity is scored

Clarity is an entropy measure. Before any evidence, a function carries an
a-priori uncertainty about its behaviour: which map it computes, which
inputs it takes, what its output looks like, how safely it runs and where
it can fail. mathema splits that uncertainty into sources, gives each
source an entropy in bits, and asks how much of the total your verified
claims have removed:

```
H0     = sum over sources s of  h(s)
H_rem  = sum over sources s of  h(s) * (1 - r(s))

clarity = 1 - H_rem / H0
```

Here `h(s)` is the a-priori entropy of source `s` and `r(s)`, between 0
and 1, is the fraction of it the strongest evidence bearing on that
source has eliminated. Clarity is 0 when nothing is known and 100 when
every source is settled by proof. It is a measure of how sharply the
function is characterised, not a pass rate: whether the claims hold is
reported separately.

### Sources and their entropy

The sources fall into five dimensions, each a different kind of thing you
can know:

| dimension | the question it answers | sources and their entropy | a claim that removes it |
|-----------|-------------------------|---------------------------|--------------------------|
| **what it computes** | which function is this, exactly? | the map, 1 bit, plus 0.4 bits per branch region | `f(x) == 2*x`, an equivalence, a closed form |
| **its bounds & shape** | what is the output's range and form? | the output envelope by return kind (a bool 0.5, a scalar 1, a sequence or mapping 1.5, a matrix 2) and its relational form (0.4 flat, 1 branched) | a bound, monotonicity, symmetry; a proof of *what it computes* settles these too |
| **what it accepts** | which inputs are in and out of bounds? | each parameter's domain (below), and 0.5 bits for the absence an `Optional` admits | a domain stated on the function, a proof of what it computes, a `raises` or `is_defined` row; an `absent` row or policy for the absence |
| **how safely it runs** | does it run cleanly and deterministically? | one source per safety family that can apply: state and determinism (0.15 bits each on a visibly pure function, 0.8 otherwise), numerical stability and representation (0.2 bits, plus 0.4 per loop), missing values for a sequence input (0.4), text for each string input whose domain is not a finite set (1) | the safety families (`is_state_safe`, `is_numerically_stable`, ...); a `missing` policy row for missing values |
| **where it can go wrong** | how and where does it fail? | 0.5 bits per raise site, 2 bits per call into another function | a `raises` contract; for a call, the callee's own record |

A dimension that cannot apply has no sources, so it carries no entropy: a
pure, total function with nothing that can fail has nothing in *where it
can go wrong* to count against it. A decorator is not a call the function
makes, and a guard that states a parameter's domain (below) is charged as
that domain, not also as a branch and a raise site, so
`@enforce_domain({"side": {"buy", "sell"}})` and
`if side not in {"buy", "sell"}: raise ValueError(side)` score the same.

### What a parameter accepts

Each parameter's entropy is what its completed domain leaves unknown, read
from the same domain every check uses. That domain is what the function
itself states: its annotation, a guard in the body refusing every value
outside a set (`if side not in {"buy", "sell"}: raise ValueError`), or an
`@enforce_domain(...)` decorator, which takes the place of the annotation
(two numbers there are the closed interval between them, a string is read
in the domain grammar, and any other set, list or tuple is the finite set
of its members):

| what is known about the parameter | bits |
|-----------------------------------|------|
| nothing (no annotation, no binding) | 1.5 |
| a type alone (`float`, `str`, a language admitting every string) | 1.0 |
| a language narrowed to an alphabet | 0.8 |
| a language narrowed by a predicate | 0.6 |
| a refined language (`L[ascii, len <= 80]`) or a bounded range (`@enforce_domain({"x": (0.0, 1.0)})`) | 0.4 |
| a finite set of `k` values (a `Literal`, a str `Enum`, a guard to a set, `@enforce_domain` to a set) | `min(0.3, log2(k) / 10)` |
| any other guard in the body (its boundary is the unknown) | 1.0 |

A finite set of `k` values is a choice carrying `log2(k)` bits, scaled by
a tenth because a closed set is already most of the way to known. Every
parameter starts at the 1.5 bits of nothing known, and whatever the
function states about it (its annotation, a guard, `@enforce_domain`)
counts as known, so annotating a parameter or stating its domain never
lowers a score: only what the stated domain leaves is charged, and the
claims clear part of that.

Who states the domain matters. When a finite set is the function's own
domain, a proof that visits every member covers every input the function
accepts and clears the parameter entirely. When the set, or a range,
comes only from a claim's binding, the function still accepts every other
value of its type, so the claim speaks about its share of the inputs
(below) and leaves the parameter charged for the rest. For example,
`for name in {"Alice", " alice ", "ALICE"}, f(name) == "alice"` on
`username_key(name: str)` settles three strings out of unboundedly many,
which is a vanishing share, while the same proof on
`username_key(name: Literal["Alice", " alice ", "ALICE"])` settles every
input. A parameter guarded in the body by anything other than a set is
charged as a guard, for its boundary, which a verified claim about what
the guard refuses clears.

### How far a claim reaches

A claim credits what it says about a function in proportion to the share
of the function's inputs it ranges over. The share is counted in the
values each parameter's type can actually hold:

- a `float` holds float64 doubles, which crowd towards zero, so `[0, 1]`
  holds about 25% of them, `[0, 100]` about 25.2%, `[0, inf)` half, and
  `[0.5, 0.6]` about 0.005% (these shares are exact counts of doubles);
- an `int` is unbounded, so a bounded stretch of integers is a vanishing
  share and a half-line half, unless the function itself bounds the
  parameter, when the integers in its range are counted;
- a finite domain counts its members, so two of three `Literal` values
  are two thirds of it;
- a string or any other type has unboundedly many values, so a few named
  values or a narrower language are a vanishing share.

A claim binding several parameters covers the product of their shares.
The share scales every dimension the claim credits: what it computes, the
envelope and shape a proof of that entails, and what the parameters
accept. Every claim also earns a tenth of what it would earn over the part
of the domain it does not cover, so a claim covering a share `s` is
credited `s + 0.1 * (1 - s)` of its whole-domain credit: a proof at three
names of a bare `str` earns a tenth, a claim over most of a stated domain
nearly all of it, and a claim over everything exactly all of it. That
tenth is counted once per source, so a pile of claims at single points
earns no more than one does. Claims over different parts of one
parameter's domain add up, so `{"buy", "sell"}` and `{"hold", "skip"}`
together settle a four-value `Literal`. The easy way to earn the full share is to state the domain on
the function, with `@enforce_domain`, an annotation or a guard, and then
claim over all of it.

### How much a verdict removes

`r(s)` is set by the strongest verdict bearing on the source, and for a
`holds` by the mechanism that produced it, since a structured search leaves
less of the input space unexplored than random sampling:

| verdict | fraction removed |
|---------|------------------|
| `proven` | 1.0 |
| `holds` from derive or examination | 0.90 |
| `holds` from a semi-analytical probe (critical points, poles) | 0.85 |
| a witnessed `falsified` | 0.85 |
| `holds` from an algorithmic probe | 0.80 |
| `holds` from a minimal-example probe | 0.78 |
| `holds` from random sampling over `n` draws | `0.60 * (1 - 3/n)` |
| `unknown` | 0 |

A subroute with no grade of its own (`derive:extensive`,
`probe:counterfactual`) is graded as the route it refines. The random
sampling grade shrinks with few draws because `n` failure-free draws
leave, at 95% confidence, up to `3/n` of what they sample possibly
failing; a row that records no count is graded 0.60.

A witnessed falsification removes entropy because it is knowledge: you now
know an input where the function fails. It credits only the source the
claim speaks about, since a map shown wrong at one input says nothing about
the output's envelope, its shape or what the function accepts. A `[float]`
companion that holds or is proven credits numerical stability for its
function, as a verified `is_numerically_stable` claim would; a falsified
companion credits nothing, since it records one relation the float code
breaks, not the function's stability. A safety family that only rolls
others up (`is_computation_safe`, `is_repeatable`) credits nothing itself,
since its children do, and an `absent` or `missing` policy row speaks only
about absence or missing values.

### Calls

Every call into another function, one of your own or a library's, is a
two-bit source in *where it can go wrong*, and only the callee's own
record reduces it. mathema looks one level down, at the callee's settled
definedness rows (`is_defined`, bare or with a region, or a `raises`
row) and at any identity it holds over its whole domain, which gives a
value at every input: proven, the call's entropy is gone; holds removes
the fraction the table gives; a row accepted with `--as trusted` counts
as a holds. A callee with no such record keeps its two bits, which caps
the caller below 100. For a library function the record is the one
`mathema verify` writes when it adjudicates the function's
[compendium](../claims-transfer.md) rows against the installed library;
a claims file nobody has verified is testimony and moves nothing. What
the callee itself calls is the callee's own clarity, not the caller's.
Built-in and standard-library calls with no claims file are not sources.

### A function nobody has claimed

With no verified claims, a function is scored only on what its code
visibly shows. Visible purity, an unguarded signature, a domain stated on
the function and the absence of hazards are facts examination establishes
without a claim, and each removes part of its source, weaker than a
verified claim would. A plainly pure, total helper therefore reads low but
not zero, while a branchy, impure or call-heavy function floors much
closer to zero.

### What the score does not tell you

The bit values are nominal: they rank the kinds of knowledge against each
other sensibly, but nobody measured them, and calibrating them against
real repositories is still to come, so a clarity of 60 against one of 70
says more about order than about distance. The score is per function and
reads one level of calls, so it says nothing about how functions behave
together, and a repository's clarity is a weighted mean of those
per-function views rather than a measure of the system. It depends on
which claims are verified: a function whose behaviour is perfectly well
understood but unclaimed reads low, and the score rises when that
understanding is written down and checked, not when it exists. Proof
attempts run under a wall-clock cap, so on a busy machine a claim that
would be proven can be recorded as holds, and the score drops with it
until the claim is verified again. Some of what a function does is not
seen at all, for example a guard bounding a number to a range (only a
guard to a set of strings is read as the domain), or a module-level list
the function appends to (it reads as pure).

Every fraction removed, every share and every credit stays between 0 and
1, so the score stays between 0 and 100. A score of 100 means every source
is settled by proof over the whole domain: a single holds, a claim over
part of the domain or an unsettled callee leaves something, and the score
then reads 99 at most, even where rounding would say 100.

The scoring algorithm is versioned, and its version is recorded beside
every score, so a number is only ever compared with one computed the same
way.

## The triangle

The three scores are the corners of a triangle: **CLARITY** at the top,
**IMPL** and **INTENT** the two bottom nodes. The sharp dotted outline is
the full `100/100/100` frame; inside it, each score is a dot on its spoke
from the base (all-zero) out to its corner, and the triangle those three
dots span is filled, so the filled area is the current state and the gap
to the frame is the room to grow. The fraction of the frame that area
shades is the **overall** number, so half the triangle shaded reads 50:
with clarity the apex height and implementation and intent the base, it
is `clarity * (implementation + intent) / 2` on the fractions. It is 100
when all three are 100, and 0 whenever clarity is 0 (a flat shape) or
both base scores are, so comparing two commits' areas shows the change in
overall characterisation. A dimension under 5% is degenerate and the
shape is not drawn, only the numbers.

## The standard location, and embedding in a README

```
mathema badges --out            # writes to .mathema/badges/ under --root
mathema badges --out path/       # or an explicit directory
```

Bare `--out` writes to **`.mathema/badges/`**, the documented home under
the tracked `.mathema/`. Committing it means a README can embed the SVG by
its in-repo path, no external hosting:

```markdown
![mathema](.mathema/badges/triangle.svg)
```

The shields.io JSON files serve the same badges through shields' endpoint
renderer, referenced by their raw URL, when separate pills are
wanted instead of the one triangle.

## Artifacts (`--out [DIR]`)

mathema OWNS the badge directory. Every run rewrites its artifacts and
DELETES any badge-shaped file (`.json`, `.svg`, `.txt`, `.md`) it did
not write, naming each removal. That is what keeps a renamed or retired
badge from being served forever from a stale file: a diff-based CI
guard cannot notice a file nothing writes any more, but it does notice
the deletion. Other extensions, and anything in a subdirectory, are
left alone. `readme-snippet.md` is a paste-ready block for your own
README: the three shields, the triangle, and one line on what each
score means.


- `triangle.txt`, the ASCII triangle: the git-diffable canonical artifact.
- `implementation.json` / `intent.json` / `clarity.json`, shields.io
  endpoint badges in the Tetrion Labs colours (an ink label, a deep green
  value) a README references by raw URL.
- `triangle.svg`, a dark-card twin of the ASCII triangle with the same
  layout: the dashed `100/100/100` frame, each score a vertex on its
  spoke, the triangle they span filled in the accent green, and the
  overall number in the top right. It carries its own background and needs
  no external fonts, so it reads the same on a light or a dark README.
- `snapshot.json`, the numbers (implementation, intent, clarity, overall,
  plus `clarity_algo` and the per-function rows), for CI to compute and
  comment the area delta between commits. When a step stopped at the
  badges step cap it also holds `capped`, a `[key, steps]` pair for each
  such function; with nothing capped the key is absent, so a snapshot
  reads as it always has.
