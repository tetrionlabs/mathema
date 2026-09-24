# Library usage

`import mathema` and call it directly, for interactive or
programmatic use (a notebook, a script, an agent's own tool calls), as
opposed to the [CLI](check.md).

## The core calls

```python
mathema.claim("f(-x) == -f(x)")              # state a claim
mathema.check(fn, claims=[...])               # verify it, return a Record
mathema.write_spec(fn, claims=[...])                # verify + write the record
mathema.status()                              # fresh/stale sweep
mathema.track_claims                          # optional bare tag, zero overhead

mathema.claims.check(fn, [...])               # the conjecture pipeline directly
mathema.registry.load_specs(root)             # read the whole spec store
mathema.registry.load_claims(path)            # parse an authoring-shape claims file
```

## `check(fn, claims=None, domain=None, trials=None, trials_scale=1.0, extensive=False, declared=None, known_premises=None)`

Verify a function's claims, each adjudicated against the real
function: mathema's suggested standard claims when `claims` is
omitted, otherwise the claims you pass in.

```python
mathema.check(ema)                                    # suggested claims
mathema.check(ema, claims=["f(x, 1.0) == x[-1]"])      # add a claim
mathema.check(ema, domain={"alpha": (0, 1)})           # sample inside a declared domain
mathema.check(ema, claims=["excluding"], domain={"alpha": (0, 1)})
```

`domain` declares parameter limits, and the algebraic probes sample
inside the declared domain rather than across the whole real line.
Whether the code itself *rejects* an out-of-domain input is a separate
question: opt into it with the `excluding` keyword, which adds an
`excluded_outside_domain[param]` claim per declared parameter.

A parameter or return type hinted with a mathema type marker
(`Annotated[float, Probability]`, `Annotated[list, Shape("m", "n")]`)
contributes its own claims automatically; see
[Authoring claims](../authoring.md). A `@claims_decorator(...)`-tagged
function, or a docstring `Claims:` block, also contributes its claims
automatically. `claims=` passed here is unioned with those, winning per
claim name on a collision.

With `claims=None` (the default), mathema also adjudicates and
displays its own *suggested* standard claims (every row in the
transcript below is one of these), candidates
for adoption that never gate an exit code and are never written into a
spec record (see [`mathema claims`](claims.md)). `claims=[]` means
declared surfaces only: type markers, decorator, and docstring claims
still run, but no suggestions are added.

Returns a `Record`: the facts read off the function, and one `Probe`
per claim adjudicated.

```python
>>> mathema.check(ema)
mathema.Record(ema) · source, no side effects · form 1dda3a0d5a72
  FALSIFY monotonic_increasing[alpha]: d(f(x, alpha), alpha) >= 0
           counterexample alpha=1 -> 0.45118195841070374, alpha=3.09918 -> -349.0594689144083 (not increasing)
  FALSIFY monotonic_decreasing[alpha]: d(f(x, alpha), alpha) <= 0
           counterexample alpha=1e-09 -> 999999.9980000095, alpha=9.71405 -> 75934653.1750601 (not decreasing)
  FALSIFY affine[alpha]: d(f(x, alpha), alpha, alpha) = 0
           counterexample alpha=-2.00525, h=0.00401: curvature estimate 18.3289 does not settle affine
  FALSIFY convex[alpha]: d(f(x, alpha), alpha, alpha) >= 0
           counterexample alpha=-0.220263, h=0.002: curvature estimate -208.106 does not settle convex
  FALSIFY concave[alpha]: d(f(x, alpha), alpha, alpha) <= 0
           counterexample alpha=8.52571, h=0.0171: curvature estimate 3.64705e+06 does not settle concave
  proven  is_deterministic: f(x, alpha) = f(x, alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
  proven  is_state_safe: f(x, alpha) = f(x, alpha)
  holds   is_numerically_stable: let g = mathema.f.finite_no_error, g(f, x, alpha) = 1 (n=160)
  holds   is_representation_safe[alpha]: is_representation_safe(alpha) (n=12)
  FALSIFY bounded_lower: min(x) <= f(x, alpha)
           counterexample ([2.01488, 3.30692, -6.39418, 3.78355, 6.96564, 7.97935], -9.1034): -6.39418363288563 vs -45761.14174665739
  FALSIFY bounded_upper: f(x, alpha) <= max(x)
           counterexample ([2.59648, 2.09269], -7.84153): 6.5469484767516235 vs 2.596479621674405
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([6.22429, 5.95714, 3.98826, -6.56235, 7.20359, 1.66103, -8.45295], -5.87836): 78066.38231536481 vs -1129152.7241483687
  proven  scale_equivariant: let g = mathema.f.scale_seq, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
  proven  translation_equivariant: let g = mathema.f.shift_seq, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ ℝ
```

## `write_spec(fn, claims=None, root=".", key=None, **kwargs)`

The one-call IO workflow: retrieve the declared layer from the project
store under `root`, check the function's claims against it, write the
record into the store (`.mathema/verified/`), and return the `Record`.
Everything `check()` accepts, `write_spec()` also accepts.

```python
mathema.write_spec(ema, claims=[...])
mathema.write_spec(ema, domain={"a": (0, 1)})
```

The written key defaults to `module.qualname` (or bare `qualname` for
a `__main__`-defined function), pass `key=` to override.

## `retrieve(fn_or_key, root=".", *, store=None)`

The declared layer's one read entry point: the full declared entry for
a function, with the hand-written claims-file store under `root`
joined in at the documented precedence (file wins per claim name over
decorator/docstring claims). Takes the live function or its dotted
key. `check()` itself never reads the filesystem, pass the retrieved
entry in explicitly:

```python
rec = mathema.check(ema, declared=mathema.retrieve(ema, root="."))
```

`write_spec()`, the CLI, and the MCP tools do this join for you.

A sweep over many functions that has already loaded the whole declared
store once passes it as `store` (the mapping `spec.load_declared()`
returns) to skip the per-function re-read, which is the difference
between one tree walk and one per target.

## `analyze(fn)`

Machine-derived facts about a function: parameters, purity, guards,
structural shape. Pure `ast`, no probing, no claim verification. Falls
back to a documentation-only record for a callable with no retrievable
Python source (builtins, C extensions), the docstring states the
intent, and probing still runs against the live callable.

## `track_claims`

An optional bare decorator tag: `@mathema.track_claims`. Runs once, at
decoration time; the function object is returned unchanged (no
wrapper, zero call overhead). Entirely optional, everything still
works without it. What an untracked function loses is visibility in
`mathema.status()`, since status can only report on functions it knows
exist. See `mathema verify --status` in [mathema verify](verify.md).

## `%%mathema` in IPython/Jupyter

```python
%load_ext mathema
```

```python
%%mathema
def my_fn(x: list, alpha: float) -> float:
    ...
```

Runs the cell, then for every function it defines: checks it, writes
its record to `.mathema/verified/`, and displays the result inline.
