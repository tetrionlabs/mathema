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

Domains are per claim. `domain=` and the signature's `Annotated`
markers form the function-level parent domain, which every claim
inherits; a claim's own `for` binding overrides the parent for that
parameter. One claim's quantifier never reaches another claim, so
`f(x) >= 0` checked beside `for x in [0, 1e6], f(x) >= 0` still means
every x. Each record states what it was adjudicated over: the claim's
own bindings in its `domain` and `condition`, the parent's share in
`meta["mathema.parent_domain"]`. The `excluding` keyword reads the
parent domain only: a parameter bounded only inside one claim has no
function-level outside to exclude.

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
per claim adjudicated. For the exponential moving average of the
[first look](../first-look.md):

<!-- example: ema run slow -->
```python
import mathema

def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y
```

<!-- example: ema repl -->
```python
>>> mathema.check(ema, domain={"x": (-1e6, 1e6), "alpha": (-10, 10)})
mathema.Record(ema) · source, no side effects · form 5108dc8b5d5c
  FALSIFY monotonic_increasing[alpha]: d(f(x, alpha), alpha) >= 0
           counterexample alpha=-5.44324 -> -504886.9526187774, alpha=9.99998 -> -2491045.924006212 (not increasing)
  FALSIFY monotonic_decreasing[alpha]: d(f(x, alpha), alpha) <= 0
           counterexample alpha=3.09918 -> 43.62072599569275, alpha=10 -> 21771.614551164577 (not decreasing)
  FALSIFY affine[alpha]: d(f(x, alpha), alpha, alpha) = 0
           counterexample alpha=3.53765, h=0.02: curvature estimate 3.12726 does not settle affine
  FALSIFY convex[alpha]: d(f(x, alpha), alpha, alpha) >= 0
           counterexample alpha=8.52571, h=0.02: curvature estimate -221.981 does not settle convex
  FALSIFY concave[alpha]: d(f(x, alpha), alpha, alpha) <= 0
           counterexample alpha=-0.594668, h=0.02: curvature estimate 1222.99 does not settle concave
  proven  is_deterministic: f(x, alpha) = f(x, alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [-10, 10] ⊂ ℝ ∪ {∅}
  proven  is_state_safe: f(x, alpha) = f(x, alpha)
  holds   is_numerically_stable: let g = mathema.f.finite_no_error, g(f, x, alpha) = 1 (n=192)
  holds   is_representation_safe[alpha]: is_representation_safe(alpha) (n=20)
  FALSIFY bounded_lower: min(x) <= f(x, alpha)
           counterexample ([0, 902023, 21859.3, 865038, -999998, 740637, -77557.7, 946318], -8.89934): -999998.0 vs -7639061686900.594
  FALSIFY bounded_upper: f(x, alpha) <= max(x)
           counterexample ([103173, 1e+06, -993405, -514945, 606668, -999998], 6.56264): 6722876822.250346 vs 1000000.0
  FALSIFY permutation_invariant: let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)
           counterexample ([519138, 999998, 1e+06, 0, 917863, 745687, -818085], 10): -248319487748.5595 vs -814138493405.3986
  proven  scale_equivariant: let g = mathema.f.scale_seq, let c be [-5.0, 5.0]:float|missing, c*f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [-10, 10] ⊂ ℝ ∪ {∅}
  holds   scale_equivariant[float]: let g = mathema.f.scale_seq, let c be [-5.0, 5.0]:float|missing, c*f(x, alpha) = f(g(x, c), alpha) (n=48)
  proven  translation_equivariant: let g = mathema.f.shift_seq, let c be [-5.0, 5.0]:float|missing, c + f(x, alpha) = f(g(x, c), alpha)
           where y=alpha: ∀ x ∈ Seq(ℝ), y ∈ [-10, 10] ⊂ ℝ ∪ {∅}
  holds   translation_equivariant[float]: let g = mathema.f.shift_seq, let c be [-5.0, 5.0]:float|missing, c + f(x, alpha) = f(g(x, c), alpha) (n=48)
```

Read the `FALSIFY` rows as facts about `ema`, not as bugs in it. The
suggestions ask standard questions of any function, and a falsified
suggestion is an answer, with the witness to prove it: an exponential
average really is neither monotone nor order-independent in its inputs.
Each `[float]` row is the float companion of the proof above it, the
same law run through the real code in floating point inside the stated
domain; both hold. Two of the answers change once the smoothing factor's
real domain is stated. Checked with `alpha` in `(0, 1)`, the bounds that
failed for an `alpha` outside it are proven outright, and their float
companions hold (an excerpt):

<!-- example: ema repl match=subset -->
```python
>>> mathema.check(ema, domain={"x": (-1e6, 1e6), "alpha": (0, 1)})
  proven  bounded_lower: min(x) ≤ f(x, alpha)
  holds   bounded_lower[float]: min(x) <= f(x, alpha) (n=44)
  proven  bounded_upper: f(x, alpha) ≤ max(x)
  holds   bounded_upper[float]: f(x, alpha) <= max(x) (n=44)
```

That is the loop in miniature: the suggestion found the assumption the
code relies on, and stating it turned a counterexample into a proof.

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
