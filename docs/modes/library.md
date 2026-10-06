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

## `check(fn, claims=None, domain=None, trials=None, trials_downscale=None, extensive=False, declared=None, known_premises=None, pseudo_infinity=None, runtime_types=None, trials_scale=None)`

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

`trials` sets the probe's trial budget for this call (left out, mathema
decides it from the function's structure and domain, see
[the trial budget](check.md#the-trial-budget)). `trials_downscale`, a
factor no greater than 1, shrinks the budget for a fast development
loop; it never raises it. `trials_scale` is the old spelling of
`trials_downscale`, still accepted with a deprecation warning until 0.7.

`pseudo_infinity` is the function level of the operational infinity:
how far the computation of each claim (the probe route and the
computation line) is exercised along an unbounded direction, unless the claim
binds its own `let |inf| be`. Left out, a `declared=` entry's
`pseudo_infinity:` field applies, then the project's
`MATHEMA_PSEUDO_INFINITY`, then float64's own maximum. A proof never
reads it; see [operational
infinity](../grammar.md#operational-infinity-let-inf-be).

`runtime_types` names the [runtime type](../runtime-types.md) of a
parameter whose signature names none, for code that cannot be
annotated: `runtime_types={"returns": "pandas.Series"}`. Left out, a
`declared=` entry's `runtime_types:` field applies.

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

def ema(x: list[float], alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y
```

<!-- example: ema repl -->
```python
>>> mathema.check(ema, domain={"x": (-1e6, 1e6), "alpha": (-10, 10)})
mathema.Record(ema) · source, no side effects · form 0f61bbd9aa20
  monotonic_increasing[alpha]  d(f(x, alpha), alpha) >= 0   falsified at alpha = 8.459992498903986 -> -4.930559650170467e+304, alpha = 8.70201321389522 -> -5.772547268351122e+304 at x = [1e+300, -1e+300, -2.7255878198803085, 1.4703849054783387, 4.922577492583454, -8.999703650149867] (not increasing)
    falsified  computation  d(f(x, alpha), alpha) >= 0   counterexample alpha = 8.459992498903986 -> -4.930559650170467e+304, alpha = 8.70201321389522 -> -5.772547268351122e+304 at x = [1e+300, -1e+300, -2.7255878198803085, 1.4703849054783387, 4.922577492583454, -8.999703650149867] (not increasing)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  monotonic_decreasing[alpha]  d(f(x, alpha), alpha) <= 0   falsified at alpha = -9.83680626493992 -> -1796.0154991652923, alpha = 0 -> -9.630119309794798 at x = [-9.630119309794798, 6.4611233807873525, -2.4056272554860447] (not decreasing)
    falsified  computation  d(f(x, alpha), alpha) <= 0   counterexample alpha = -9.83680626493992 -> -1796.0154991652923, alpha = 0 -> -9.630119309794798 at x = [-9.630119309794798, 6.4611233807873525, -2.4056272554860447] (not decreasing)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  affine[alpha]  d(f(x, alpha), alpha, alpha) = 0   falsified at alpha = 0.5942120819077363, h = 0.000594
    falsified  computation  d(f(x, alpha), alpha, alpha) = 0   counterexample alpha = 0.5942120819077363, h = 0.000594: curvature estimate -4.01335 does not settle affine
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  convex[alpha]  d(f(x, alpha), alpha, alpha) >= 0   falsified at alpha = 4.553442718560774, h = 0.00455
    falsified  computation  d(f(x, alpha), alpha, alpha) >= 0   counterexample alpha = 4.553442718560774, h = 0.00455: curvature estimate -849.761 does not settle convex
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  concave[alpha]  d(f(x, alpha), alpha, alpha) <= 0   falsified at alpha = 4.709760826489109, h = 0.00471
    falsified  computation  d(f(x, alpha), alpha, alpha) <= 0   counterexample alpha = 4.709760826489109, h = 0.00471: curvature estimate 10716.6 does not settle concave
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  proven    is_deterministic: f(x, alpha) = f(x, alpha)
  proven    is_state_safe: f(x, alpha) = f(x, alpha)
  unknown   is_numerically_stable: let g = mathema.f.accurate, g(f, x, alpha) = 1
           derive could not decide it; the probe could not decide it either (accuracy against the exact value is read for scalar parameters only)
  holds     is_representation_safe[alpha]: is_representation_safe(alpha) (20 draws)
  holds     is_dimension_safe[f]: is_dimension_safe(f) (192 draws)
  bounded_lower  min(x) <= f(x, alpha)   falsified at x = [222791.29884554766, -852156.6094995309, -647122.5636467072, -772598.9379420548, 854595.3224724911, 999998], alpha = 4.542301584683122
    falsified  computation  min(x) <= f(x, alpha)   counterexample x = [222791.29884554766, -852156.6094995309, -647122.5636467072, -772598.9379420548, 854595.3224724911, 999998], alpha = 4.542301584683122: -852156.6094995309 vs -656298366.2095869
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  bounded_upper  f(x, alpha) <= max(x)   falsified at x = [216941.53207844822, -368274.1184160299, 682330.1826507892], alpha = 1.7838785067417557
    falsified  computation  f(x, alpha) <= max(x)   counterexample x = [216941.53207844822, -368274.1184160299, 682330.1826507892], alpha = 1.7838785067417557: 1865471.1484383387 vs 682330.1826507892
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  permutation_invariant  let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)   falsified at x = [850043.9278135903, 905210.656449008, 782687.5954072354], alpha = 6.752137638609439
    falsified  computation  let g = mathema.f.reverse_seq, f(x, alpha) = f(g(x), alpha)   counterexample x = [850043.9278135903, 905210.656449008, 782687.5954072354], alpha = 6.752137638609439: -1747388.2882860936 vs -3521213.9192287754
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  scale_equivariant  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)   falsified at x = [], alpha = 5.159088058806049
    proven     mathematics  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)
    holds      computation  let g = mathema.f.scale_seq, let c be [-5.0, 5.0], c*f(x, alpha) = f(g(x, c), alpha)   285 entries across 67 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
  translation_equivariant  let g = mathema.f.shift_seq, let c be [-5.0, 5.0], c + f(x, alpha) = f(g(x, c), alpha)   falsified at x = [], alpha = 5.159088058806049
    proven     mathematics  let g = mathema.f.shift_seq, let c be [-5.0, 5.0], c + f(x, alpha) = f(g(x, c), alpha)
    holds      computation  let g = mathema.f.shift_seq, let c be [-5.0, 5.0], c + f(x, alpha) = f(g(x, c), alpha)   285 entries across 67 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 5.159088058806049 with no emptiness guard in the body: the empty input is stumbled into, not handled
                            possible fixes:
                              (i) if the IndexError is the intended refusal, state: raises(ema([], alpha), IndexError)
                              (ii) guard the empty input at entry
```

Read the falsified claims as facts about `ema`, not as bugs in it. The
suggestions ask standard questions of any function, and a falsified
suggestion is an answer, with the witness to prove it: an exponential
average really is neither monotone nor order-independent in its inputs,
and it really does fail on an empty list, which every claim over `x`
reports on its `policy` line. Under each claim, the `mathematics` line
is the claim over the real numbers and the `computation` line is the
same claim run through the real code in floating point inside the stated
domain. Two of the answers change once the smoothing factor's real
domain is stated. Checked with `alpha` in `(0, 1)`, the bounds that
failed for an `alpha` outside it are proven outright, and their
computation lines hold (an excerpt; the headline stays falsified by the
empty list):

<!-- example: ema repl match=subset -->
```python
>>> mathema.check(ema, domain={"x": (-1e6, 1e6), "alpha": (0, 1)})
  bounded_lower  min(x) <= f(x, alpha)   falsified at x = [], alpha = 0.7579544029403025
    proven     mathematics  min(x) <= f(x, alpha)
    holds      computation  min(x) <= f(x, alpha)   227 entries across 49 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f(x=[])   f(x, alpha) raises IndexError at x = [], alpha = 0.7579544029403025 with no emptiness guard in the body: the empty input is stumbled into, not handled
  bounded_upper  f(x, alpha) <= max(x)   falsified at x = [], alpha = 0.7579544029403025
    proven     mathematics  f(x, alpha) <= max(x)
    holds      computation  f(x, alpha) <= max(x)   227 entries across 49 draws, sizes (1, 1) to (8, 1)
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
