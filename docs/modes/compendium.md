# `mathema compendium`

A compendium is a claims file about a library's functions rather than
your own (see [Claims transfer](../claims-transfer.md#in-the-compendium)).
This verb has two actions: `status`, for a project that calls
libraries, and `export`, for a library author publishing their own
verified claims.

```bash
mathema compendium status [<library>] [--root .] [--json]
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
