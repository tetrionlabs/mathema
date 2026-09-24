# `mathema audit`

Population-level report: every function mathema can find under the
given targets, whether it's claimed at all (any of the four authoring
surfaces), whether it's liftable for a *derive-route* proof
specifically, and if not, why not, distinct from `verify`'s per-
function completeness view, which only ever reports on functions that
already have at least one claim. A function with zero claims is
invisible to `verify`/`status` by construction; `audit` is the tool
that answers "where do I even start" on a real, existing codebase.

```bash
mathema audit mypkg [mypkg.sub ...]
```

## Arguments

| Flag | Meaning |
|---|---|
| `target` | importable module or package name(s), must already be importable |
| `--root` | project root holding `claims/` and any `coverage.json`/`.coverage` (default `.`) |
| `--exclude ANALYSIS` | skip an analysis entirely, not just hide its column: `derivable`, `complexity`, `typing`, `scope`, `tested`, `docs`, `docsync` (comma-separated or repeatable) |
| `--index` | write the global index record (`.mathema/index.yaml`) instead of the analysis table, and print what it wrote as a per-module table (overwriting the previous index is by design; it is a generated view nothing reads back into the declared or verified layers) |
| `--docs` | skip the wide table and report per-function checkbox breakdowns of just the docs criteria, both the quality checklist and the docsync schema, see below |
| `--deriv-report` | the full per-function detail below the table (off by default): underivability reasons with reason-code hints, and each function's complete module-state view, the names the grid's `vars`/`mutates` cells condense, with the file lines they appear at |
| `--one-line` | one row per function with the full dotted key and no cell compression: the default tree layout (module line, class line, functions indented under their scope) plus its name ellipses and `+N` condensing all off |
| `--compact` | column-oriented JSON instead of the grid: `{"prefix", "cols", "rows"}` with column names once, the shared key prefix factored out of every row, and raw values (JSON null for missing, never `-`); the same shape the MCP `audit_targets` tool returns |
| `--filter TERM,...` | keep only matching rows (implies `--compact`): semantic terms, derive_unlock classes (`actionable`, `limitation`, `N/A`), `claimed`/`unclaimed`, `derivable`/`underivable` (what the derive route can do given the declared domain), `unconditional`/`needs-context` (whether the body lifts with nothing supplied), `underclaimed` (fewer claims than the function's own structural floor; the "what have I not evidenced" query), and columnar substring matches (`blocker~loop` scopes to one column, `~mutual` matches any column). Terms from the same dimension OR together (`actionable,limitation` keeps either, which is also how "everything except N/A" is spelled); dimensions and columnar terms AND across, and an empty match text (`~`, `col~`) is an error, never a keep-everything no-op. A filter's column references are computed even when not selected as output, so an empty result always means "nothing matched", never "never looked". Explicit by design, never a default, right for a lifting pass, wrong for a claims pass, since probe claims stay viable on every `limitation` row |
| `--cols COL,...` | columns for `--compact` (implies it), e.g. `key,span,claims,derivable,unconditional,blocker,typed,tested` (the default set); also `min_expected_claims`, `claims_vs_floor` (the `[actual, floor]` pair, side by side), `blocker_params`, `blocker_more`, `blocker_hint` and `blocker_unlock` (the remedy and its derive_unlock class, carried in the row rather than needing a second `reason_code` lookup), `constructs`, `cx`, `quality` (alias `doc_quality`), `docsync` (the 0-100 percent), `intent`, `domain_declared`, `raises_declared`, `callees_doc_quality`, `callees_docsync`, `concepts`, `global_vars`, `mutates`, `unresolved`. The resolved selection is echoed back in the output's `cols` field; an unknown name exits 2 listing the vocabulary |

## What each column reports

| Column | Meaning |
|---|---|
| `key` | the canonical dotted key, `module.qualname` |
| `span` | the function's source span, sed-address style (`142:187p`), a ready-made `sed -n` range, so reading exactly one function needs no search |
| `claimed` | any of the four authoring surfaces has a claim for this function |
| `cx` | cyclomatic complexity (branches + loops + 1), shown for every row |
| `derives` (derive route group) | whether the derive route can work on this function **given the domain its signature, docstring and claims declare**. This is the provability question |
| `reason` (derive route group) | the structural shape blocking an **unconditional** lift, the body with nothing supplied ("2 branches, 1 loop", "recursive (2 call sites)"); a dash means nothing blocks it even bare |
| `code` (derive route group) | the compact underivability code, see [Reason codes](../reason-codes.md) |
| `typed` | signature typing coverage |
| `finite_domain` (typing group) | a `Literal[...]`/`Enum`/`bool` parameter annotation, surfaced as a finite domain (a bool's stated values are the real `False`/`True` objects, so identity guards behave) |
| `vars` (globals group) | genuine global *variable* dependencies, real, hidden state; a claim about this function is only as reliable as that value |
| `mutates` (globals group) | module state this function writes, the stronger relationship |
| `funcs` (globals group) | references to a sibling function/class/module by name, ordinary code structure, not a state dependency |
| `unresolved` (globals group) | free names with no binding mathema can find at all, almost always a real bug |
| `tested` | whether an existing `coverage.json`/`.coverage` covers this function (never runs tests itself): `yes`, `no`, `no-report`, or `outdated` when the function's source file changed after the report was produced; a stale yes is not evidence |
| `locked` | whether the function's form hash is [locked](lock.md): `yes` (with who pinned it) means the body cannot change until a human runs `mathema unlock`. Hidden when nothing in the population is locked; `--compact` carries the pinned form hash in a `locked` column on request |
| `quality` (docs group) | the docstring quality-checklist score, see below |

The grid prints a group-title row above the columns (`derive route`,
`typing`, `globals`, `docs`), so the short names above always sit
under their group's own heading, and the key column is a tree by
default: one line for the module, one per enclosing class, each
function indented under its scope (`--one-line` for the flat,
fully-expanded table). Long name lists in the `vars`/`mutates`/
`funcs` cells condense (each long name ellipsized, at most three
shown, then a bare `+N`), an overlong `reason` ellipsizes too, and
the `unresolved` column drops entirely when nothing is unresolved
across the whole population, `--deriv-report` and `--one-line`
carry the full view. A concept-tag count rides the `--docs` report,
not the wide grid. A mistyped function key suggests close matches
("did you mean: ..."). The compact/MCP column vocabulary
is unchanged and additive-only (`global_vars`, `blocker`, ... stay
the selection names there).

Discovers module-level functions and a class's own methods (static and
instance, `self`/`cls` intact; a read-only method derives like a
plain function, and one that modifies instance state (or lets self
escape) is reported `derivable: no <- stateful`). Only dunder names (`__init__`,
...) are excluded; a single-leading-underscore helper is included like
any other function, since it's often the more claimable one (a public
function frequently just dispatches to a private numeric core).

## `derivable` and `unconditional` are different questions

`unconditional` asks whether the body lifts with **nothing supplied**:
no declared domain, no claim context. It is a property of the code
alone, and it is *not* a ceiling on what can be proven.

`derivable` asks what the derive route can do **here**, given the domain
the signature, docstring and claims declare.

They differ constantly, and the difference is not an edge case. A
function guarded by a branch reports:

    reason  1 branch
    code    branch:needs-domain(theta)
    derives yes

The blocker is real; the body does not lift bare, and the claim's
own `for theta in [...]` quantifier prunes the branch, so the derive
route proves it anyway. A repository read `2/75` on the unconditional
number while carrying derive-route proofs on functions the column
called underivable.

Read `derivable` for "can this be proven", `unconditional` for "does
this need help". Neither rules out a probe claim.

## The `code` column and the underivable detail

The `reason` column reports the shape; `code` names the exact
blocker as a compact, stable code, `loop:non-affine-update`,
`branch:needs-domain(scale)`, `unsupported:unbound-name`, and
`--deriv-report` adds a detail block below the table for every
underivable function, one source line and code per blocking
construct, plus each function's full module-state view. The full meaning, the
`derive_unlock` tag, and the fix hint for every code live in
[Reason codes](../reason-codes.md); `mathema describe --issue <key>`
carries the same detail (plus the interpolated hints) as a structured
payload. For a branch, each condition is classified independently, a
function can have one resolvable branch and one structurally blocked
one, and both get their own line.

Against `strength_to_distance` (a real fixture in
`tests/test_branch_pruning.py`):

```python
def strength_to_distance(r: float, scale: str = "info") -> float:
    if scale == "info":
        return math.sqrt(1.0 - r ** 2)
    if scale == "linear":
        return 1.0 - r
    raise ValueError(f"unknown scale {scale!r}, use 'info' or 'linear'")
```

```
$ mathema audit mypkg --deriv-report
...
underivable functions:
  mypkg.strength_to_distance:
    line 2  branch:needs-domain(scale)
    line 4  branch:needs-domain(scale)
codes explained: the reason-code reference in the docs, or `mathema describe --issue <key>` for the full details
```

Both branches are resolvable once `scale` has a declared domain, a
claim like
`for r in [0, 1], scale in {"info"}, f(r, scale) == sqrt(1.0 - r^2)`
proves. A function whose branch condition depends on a *local*
variable not traceable back to its own parameters (or one with an
unrecognized condition shape) gets a `branch:untraceable-local` /
`branch:unrecognized-shape` code instead.

See [The derive route](../derive-route.md) for what resolvable and
blocked mean in terms of derivability, and
[Reason codes](../reason-codes.md) for the complete code table.

## The `quality` score

`quality` is a quality checklist, not a style grade, every
criterion is a presence check, not a correctness check, and a criterion
that genuinely doesn't apply to a given function (no parameters, no
`raise` anywhere in the body, no return value) shrinks the denominator
instead of counting against the score. "documents its parameters" and
"documents raising" are scored *per parameter/exception*, not as one
all-or-nothing point each, a function with 3 parameters and 2
documented contributes 2 to the score and 3 to the denominator, not a
flat 0 or 1, so the overall "N/M" reflects how close a docstring is,
not just whether it's perfect.

| Criterion | Applicable when | Passes when |
|---|---|---|
| has a docstring | always | the docstring is non-empty |
| has a summary | the docstring is non-empty | there's real text before the first recognized section header (`Args`/`Parameters`/... or a numpydoc `Header\n----`) |
| documents its parameters | the function has at least one real parameter (`self`/`cls` excluded) | every parameter's name appears literally somewhere in the docstring |
| documents its return value | `analyze()` infers a non-`None`, non-unknown return kind | a `Returns:`/`Yields:` section exists |
| documents raising | the body contains at least one `raise <Exception>(...)` with a resolvable exception type name | a `Raises:`/`Exceptions:` section exists **and** every distinct raised exception type is individually named in it, a section that exists but never mentions one of the actually-raised types still fails |

Example: this function only partially satisfies "documents raising";
`ValueError` is named, `OverflowError` isn't, so `documents_raises` is
`False` even though a `Raises:` section is present:

```python
def half(x: float) -> float:
    """Halves x.

    Raises:
        ValueError: if x is negative.
    """
    if x < 0:
        raise ValueError("x must be nonnegative")
    if x > 1e6:
        raise OverflowError("x too large")
    return x / 2
```

Run this checklist against a single function without the `audit` CLI,
useful in a notebook or a quick interactive check:

```python
>>> import mathema
>>> mathema.docstring_report(half)
mathema.DocstringReport(half) · 4/6 criteria met
  ✓ has a docstring
  ✓ has a summary
  ✓ params documented (1/1)
  ✗ documents its return value
  ✗ exceptions documented (1/2)
```

This is the same checklist `audit`'s `docs` column runs, a separate,
much stricter, opinionated docstring convention also exists (claims,
domain, and type declarations live *in* the docstring itself); see
[The mathema docstring](../mathema-docstring.md).

## `--docs`: just the docs criteria, broken out

Two labeled tables: `quality:` (the checklist, plus a `concepts/tags`
count) and `docsync:` (the strict schema; its claims column header
reads `{min_expected|actual|est_applicable}`).

`mathema audit --docs` skips the wide table and every other
analysis (nothing else is even computed) in favor of a colored grid,
one row per function, with each checklist criterion as its own column
(`has_docstring`, `has_summary`, `params`, `returns`, `raises`,
`claims`, `docs_score`) instead of one summary "N/M", the same
per-parameter/per-exception counts described above, laid out so a
whole package's docstring gaps are scannable at a glance rather than
read one function-block at a time. The docsync sync grid is appended by default (see [docsync](docsync.md)); exclude it with `--exclude docsync`.

## Rollups

A `by module:` section prints automatically whenever a sweep touches
more than one module; a `by package:` section prints when more than
one target was given on the command line. Both share the same
aggregate counts (`claimed`, `derivable`, `typed`, `tested`, `docs`)
the grand-total line already computes.
