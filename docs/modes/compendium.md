# `mathema compendium`

A compendium is a claims file about a library's functions rather than
your own (see [Claims transfer](../claims-transfer.md#in-the-compendium)).
This verb has three actions: `status` and `update`, for a project
that calls libraries, and `export`, for a library author publishing
their own verified claims.

```bash
mathema compendium status [<library>] [--root .] [--json]
mathema compendium update [--root .] [--dry-run]
mathema compendium export <library> [--out PATH] [--root .]
```

## `status`: where the project stands with each library

`status` reads every function the project's stores know, resolves each
call it makes through its import aliases (`np.sqrt` is `numpy.sqrt`),
and reports on every third-party library called. Standard-library
calls are left out: `math`'s claims ship with mathema and are
adjudicated like any others, but a standard library is not something
you install or pin. For each library it prints one block, the most
called first, headed by the library, its installed version and the
number of calls (`numpy 2.5.3: 4 calls`, a call counted once per
function that makes it):

- the claims files about it, bundled with mathema or in your project,
  each with its `versions` range and whether the installed version is
  in range;
- each called function that has rows, with how many are **verified
  locally** (proven or holds in this project's store), **trusted**
  (accepted with `mathema accept ... --as trusted`, at the level
  accepted), **falsified**, and **unsettled** (not yet adjudicated
  here, or adjudicated without a verdict);
- the called functions no claims file states anything about.

Two functions calling numpy, verified:

<!-- example: status file=quant.py requires=numpy -->
```python
import numpy as np


def to_angle(x: float) -> float:
    """The angle whose sine is x."""
    return float(np.arcsin(x))


def spread(x: float) -> float:
    """The square root of x, plus the mean of a unit grid."""
    grid = np.linspace(0.0, 1.0, 5)
    return float(np.sqrt(x)) + float(np.mean(grid))
```

<!-- example: status file=claims/quant.claims.yaml -->
```yaml
quant.to_angle:
  claims:
    - name: bounded
      statement: "for x in [-1, 1], -2 <= f(x) <= 2"
quant.spread:
  claims:
    - name: nonneg
      statement: "for x in [0, 4], f(x) >= 0"
```

<!-- example: status run -->
```bash
mathema verify --root . > /dev/null
mathema compendium status --root .
```

<!-- example: status output match=subset -->
```
  claims files:
    mathema/compendium/numpy/bounds.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/reductions.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/scalars.claims.yaml (bundled, >=1.24,<3, in range)
  numpy.arcsin  1 call, 1 row: 1 verified locally, 0 trusted, 0 falsified, 0 unsettled
  numpy.mean    1 call, 1 row: 1 verified locally, 0 trusted, 0 falsified, 0 unsettled
  numpy.sqrt    1 call, 1 row: 1 verified locally, 0 trusted, 0 falsified, 0 unsettled
  no claims: numpy.linspace
```

`numpy.linspace` is called and nothing states a claim about it, so
its failures are a black box to mathema. Writing the rows you rely on
into `claims/numpy.claims.yaml` (a file with `compendium: numpy`)
closes that gap, and `mathema verify` adjudicates them against the
numpy you have installed. `status` reads the stores and claims files
and writes nothing. `--json` prints the same report as data, and a
library name confines it to that library.

## `update`: rows for the calls the project makes

A library row states what a function does at its defaults. A call
that passes something else, `np.mean(a, axis=1)` rather than
`np.mean(a)`, is a different computation, and no row speaks for it
until one pins the argument. `update` reads every call the project's
functions make to a library function that has rows, the positional
and keyword arguments as written, and for each call that passes a
non-default literal no row pins yet it copies each of the function's
rows with the arguments bound first:

```yaml
numpy.mean:
  claims:
    - name: "is_defined"
      statement: "dim(a) >= 1"
    - name: "is_defined@axis=1"
      statement: "let axis be 1, dim(a) >= 1"
      note: "pinned for the call in quant.rows_mean (line 14), which passes axis=1"
```

A pinned row is named after the row it copies and the arguments it
pins, `<row>@<parameter>=<value>`, with a comma between pins
(`is_defined@axis=1,ddof=1`). A bracket after a claim name means
something else: it names the computation a companion claim runs in
(`[float]`).

The rows go into the project's compendium file for the library,
`claims/numpy.claims.yaml`, created with `compendium:` and a
`versions:` range from the installed version when the project has
none. Adding a function to that file shadows the bundled entry for it,
so the bundled rows are copied in beside the pinned ones. New rows are
unverified until `mathema verify` adjudicates them. An argument that is
not a literal (`axis=k`) cannot be pinned, and `update` says so rather
than guessing a value.

A row can carry its own `versions:` range, which overrides the file's
for that row. A row whose range excludes the installed version is
still adjudicated by `mathema verify` when the project calls its
function, and is never used as a fact (a guard, a sampling hint)
meanwhile. Once verify has recorded such a row holding or proven on
the installed version, `update` widens the row's range just enough to
include it (`<2` becomes `<2.6` on numpy 2.5). A row of a function the
project does not call keeps its range.

`update` prints every change it makes, and writes nothing with
`--dry-run`. Run it again and a call its rows already cover changes
nothing. A rewritten file keeps the comment block at its top; any
other YAML comment is lost, and `update` warns, naming the file, when
a file it rewrites (or would, under `--dry-run`) has one. Keep a row's
annotation in its `note:` field, which survives every rewrite.

## `export`: publishing a library's verified claims

`export` is for the author of a library. Once `mathema verify` has
run on your own package, its verified store holds your functions'
proven and held claims. `mathema compendium export mylib` writes them
as a compendium claims file (`compendium: mylib`, `versions:
">=<installed major.minor>"`), by default to `claims/mylib.claims.yaml`
under `--root`, each row carrying the verdict it reached as its
claimed level and the note your claims file gives it. Ship that file
and a downstream project that calls your library drops it into its own
`claims/` directory, where it reads exactly like a bundled one: its
rows are testimony until the downstream `mathema verify` adjudicates
them against the version installed there, or someone accepts them as
trusted. The details are in
[Claims transfer](../claims-transfer.md#out-exporting-your-own-verified-claims).

An export transfers claims with a package to the projects downstream
that consume it. It changes nothing for the package itself: in the
package's own repository, a compendium file naming the package
(`compendium: mylib` inside `mylib`'s project) is ignored, because
there the claims are first-party, stated in the ordinary claims files
and recorded in the verified store. `mathema verify` prints a note
naming the ignored file.

## Installing third-party claims files

mathema bundles claims files for the most used libraries (`math` and
`numpy` today). Installing claims files for other libraries, published
by their authors or by anyone else, through this verb is planned.
Until then, a library's claims file goes into your project's own
`claims/` directory by hand.
