# `mathema badges`

Three orthogonal measures of a codebase, each 0-100, and one picture.

```
mathema badges [targets]                # print the triangle + numbers
mathema badges [targets] --out .mathema/badges/   # also write artifacts
```

Omit targets for the rootwide analogue of `verify` (every function the
store knows under `--root`).

## The three badges

- **implementation** (code layer): the raw line ratio from `mathema
  coverage`, how many statements a test, a probe, or a derive proof
  exercises (their union). A physical ratio, so it is neither averaged
  nor weighted.
- **intent** (spec layer): `docsync`, how much of what each function's
  docstring states is actually claimed and verified.
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

Clarity asks a single question: **of everything knowable about this
function's behaviour, how much have your verified claims actually pinned
down?** It is an information measure, not a pass-rate. Formally it is the
fraction of the function's behavioural uncertainty that the evidence has
removed (`1 - remaining / total`); informally, how sharply the function
is characterised.

The uncertainty is split into five dimensions, each a different kind of
thing you can know:

| dimension | the question it answers | a claim that settles it |
|-----------|-------------------------|--------------------------|
| **what it computes** | which function is this, exactly? | `f(x) == 2*x`, an equivalence, a closed form |
| **what it accepts** | which inputs are in and out of bounds? | a domain, a marker, a `raises` on bad input |
| **its bounds & shape** | what is the output's range and form? | a bound, monotonicity, symmetry (a proof of *what it computes* settles these too) |
| **how safely it runs** | does it run cleanly and deterministically? | the safety families (state, determinism, numerical stability, ...) |
| **where it can go wrong** | how and where does it fail? | a `raises` contract, `is_compendium_safe` |

A few consequences worth knowing:

- **A dimension that cannot apply is already fully known.** A pure,
  total function with nothing that can fail has no *where it can go
  wrong* to characterise, so that dimension is satisfied for free rather
  than counted against it.
- **Stronger evidence counts for more.** A proof settles a dimension in
  full; a `holds` counts for less, and a `holds` from a structured probe
  (critical-point or exhaustive sampling) counts for more than one from
  plain random sampling, because it leaves less of the input surface
  unexplored. A witnessed falsification still counts as knowledge (you
  now know where it fails); correctness is reported separately.
- **A `[float]` companion that holds counts as numerical stability.** A
  claim the derive route proves spawns a
  [`<name>[float]` companion](../evidence-ladder.md#a-proof-is-the-mathematics-float-is-the-code),
  the relation executed against the code in float, in the
  `is_numerically_stable` family. A companion that holds or is proven
  credits that family for its function, as a verified
  `is_numerically_stable` claim with the same verdict and route would. A
  falsified companion credits nothing: it records one relation the float
  code breaks, not the function's stability.
- **A black-box dependency lowers clarity, and caps it.** When a function
  calls a library that has a [compendium](../claims-transfer.md), mathema
  has a model of where that call can fail, and `is_compendium_safe` can
  clear it. When it calls a library with NO compendium, there is no model
  of where it fails, and no claim you can write will settle it. That
  uncertainty is irreducible, so such a function cannot reach 100 until a
  compendium covers the library. Writing a compendium stub is the way to
  lift the ceiling.
- **No claims is a low floor, not always zero.** A function nobody has
  verified is scored only on what its code visibly shows: a plainly pure,
  total, hazard-free helper reads low but not zero (it is nearly
  transparent), while a branchy, impure, or black-box-calling function
  floors much closer to zero. Declaring and verifying claims is what
  raises the score.

The scoring algorithm is versioned (`entropy-dimensions@1.1`) and recorded
beside the scores, so a number is only ever compared against one computed
the same way; a change to the algorithm reads as an algorithm change, not
a regression. `@1.1` made two changes, and both raise clarity and overall
against `@1`. It added the `[float]` companion credit above. It also reads
the relation of a verified claim the way the claim grammar does, so a
stored identity (the store writes `f(x) = 2*x`, with a single `=`), or an
approximate one (`~=`), now counts toward *what it computes*. Under `@1`
it counted only toward *bounds & shape*.

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
  comment the area delta between commits.
