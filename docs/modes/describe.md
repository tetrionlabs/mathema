# `mathema describe`

The read-only look at what mathema sees in your code. Nothing is
adjudicated, nothing is written, and no claim is checked: `describe`
answers "what is here, and what does mathema make of it" before you
commit to the cost of `check` or `verify`.

```bash
mathema describe TARGET... [--root .] [--tier NAME|1-5] [--depth 3]
mathema describe TARGET --issue [--include-source] [--include-falsified]
```

## Two modes, chosen by the target

A target that resolves to **exactly one function** (a full dotted key
like `funcs.midpoint`, or the `module:name` shorthand) prints that
function's detail view. Anything else, a package, a module, several
targets, lists every function found, one per line, with its rendered
signature. With the [tutorial](../tutorial.md) project's `funcs.py`:

<!-- example: tutorial file=funcs.py -->
```python
def settle(x: float) -> float:
    """Settlement amount for a signed exposure x."""
    return x


def midpoint(a: float, b: float) -> float:
    """The midpoint of two values."""
    return (a + b) / 2.0
```

<!-- example: tutorial run -->
```bash
mathema describe funcs
```

<!-- example: tutorial output -->
```text
funcs.midpoint(a: float, b: float) -> float
funcs.settle(x: float) -> float

2 functions found
```

That list is deliberately lighter than [`mathema audit`](audit.md): no
declared-claims lookup, no coverage report, no docstring scoring, no
derivability analysis. It is discovery plus a signature, which makes it
the cheap way to check that a target string resolves to the functions
you meant before pointing an expensive verb at it.

## The detail view

Here the tutorial's claims file also gives `midpoint` a
`mean_bound` claim:

<!-- example: tutorial file=demo.claims.yaml -->
```yaml
funcs.settle:
  claims:
    - name: nonneg
      statement: "for x in [-5, 5], f(x) >= 0"
      route: probe
    - name: symmetric_in_sign
      statement: "for x in [-5, 5], f(x) == f(-x)"
      route: probe
    - name: negative_exposure_negative
      statement: "for x in [-5, -1], f(x) <= 0"
      route: probe
funcs.midpoint:
  claims:
    - name: commutative
      statement: "f(a, b) == f(b, a)"
      route: derive
    - name: mean_bound
      statement: "for a in [0, 1], b in [0, 1], f(a, b) <= 1"
```

and after one sweep:

<!-- example: tutorial run -->
```bash
mathema verify --root .
```

<!-- example: tutorial session match=subset -->
```
$ mathema describe funcs:midpoint
funcs.midpoint(a: float, b: float) -> float
  sig_hash:  6e64b8a7a1f0
  form_hash: 54265556347f

Domains:
  (none inferred)

Claims:
  commutative: f(a, b) == f(b, a)  [proven]
    latex: f{\left(a,b \right)} = f{\left(b,a \right)}
  mean_bound: for a in [0, 1], b in [0, 1], f(a, b) <= 1  [proven]
    latex: \forall a \in \left[0, 1\right],\ b \in \left[0, 1\right]:\ f{\left(a,b \right)} \leq 1

Concepts: symmetry
```

The two hashes are the identity a record binds to: `form_hash` over the
function's structure (a rename or a reformat leaves it alone, a
behavior change does not) and `sig_hash` over its parameter shape.
Domains are listed with the source each was inferred from, so a domain
that came from a claim is distinguishable from one read off a guard in
the code. Claims come from the declared and verified layers together,
each showing its verified verdict when a record exists for it.

## The tier ladder

The detail view then prints the same function at each of five tiers,
which is the derive route's own pipeline made visible:

| Tier | Name | What it shows |
|---|---|---|
| 1 | `source` | the function body as written |
| 2 | `normalized` | parameters renamed to positional `v0`, `v1`, ... |
| 3 | `structural` | the statement skeleton with expressions dropped |
| 4 | `lifted` | the sympy expression tree the body lifted to |
| 5 | `canonical` | that tree simplified |

With `--tier`, the header above is followed by that one tier alone
(shown here without the header):

<!-- example: tutorial session match=subset -->
```
$ mathema describe funcs:midpoint --tier lifted
--- lifted ---
Add
    Mul
        Half(1/2)
        Symbol(a)
    Mul
        Half(1/2)
        Symbol(b)
```

`--tier` takes either the name or the ladder position (`--tier 4` is
`--tier lifted`), and without it all five print in order. A tier that
is unavailable prints its own real reason rather than a silent gap,
which is usually the fastest way to see *where* in the pipeline a
function stops being derivable, if `lifted` reports a blocker, the
matching [reason code](../reason-codes.md) explains it and says whether
it is actionable. `--depth` controls how far callees are inlined while
building the ladder (default 3).

## `--issue`

A structured failure report for exactly one function, printed and then
offered for writing under `.mathema/issues/`:

```bash
mathema describe funcs:settle --issue
```

It collects the reason codes, the blocked constructs, and the claim
state into one payload you can paste into a bug report. `--include-source`
adds the function's source to that one payload and is never remembered
between runs; `--include-falsified` widens the report to an undiagnosed
falsified claim, where the default covers only skipped ones. Declining
the write, or running it on a function that turns out to be perfectly
derivable, is a normal outcome and exits 0. It never makes a network
request: the payload is yours to send, or not.

## Arguments

| Flag | Meaning |
|---|---|
| `target` | importable module, package, or `module:function` name(s), the same convention as `audit` |
| `--root` | project root to import targets relative to (default: the nearest ancestor holding `.mathema/` within the enclosing git repository, else that repository, else `.`; never the home directory) |
| `--tier` | narrow the ladder to one tier, by name or by position 1-5 (single-function mode only) |
| `--depth` | callee-inlining depth for the ladder (default 3, single-function mode only) |
| `--issue` | build the structured failure report for one function |
| `--include-source` | with `--issue`: include the source in this one payload |
| `--include-falsified` | with `--issue`: also report an undiagnosed falsified claim |

## Exit codes

`describe` reports rather than gates, so a successful run is always 0,
including the run that finds no functions at all. A target that does
not resolve exits 2, like every other verb (see
[exit codes](../cdd.md#exit-codes)).
