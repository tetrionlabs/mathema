# Tutorial: the CDD loop

The [quick start](quickstart.md) showed one claim going from falsified
to proven. This walks the whole loop on a small project: a real bug, a
claim that was simply wrong, the human decisions in between, and what
the record remembers about all of it. Every output below is from a real
run you can reproduce.

## The project

Two functions, in `funcs.py`. `settle` is meant to return a settlement
amount for a signed exposure, and it has a bug: it should take the
magnitude and instead returns its argument unchanged.

```python
def settle(x: float) -> float:
    """Settlement amount for a signed exposure x."""
    return x


def midpoint(a: float, b: float) -> float:
    """The midpoint of two values."""
    return (a + b) / 2.0
```

And `claims/demo.claims.yaml`, stating what someone believed:

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
```

Two of those claims are falsified by the bug. The third is falsified by
being *wrong*, and keeping those two diagnoses apart is the thing this
loop is for.

## 1. The first sweep

```bash
mathema verify --root .
```

```text
ok   funcs.midpoint: no baseline record; 2 hold, 0 refuted
FAIL funcs.settle: no baseline record; 2 hold, 2 refuted  <- 2 falsified claim(s)
0 fresh (form unchanged, skipped), 2 adjudicated, 1 problem(s)
```

`midpoint` proves on the derive route. `settle` fails, and the record
under `.mathema/verified/funcs.settle.yaml` says precisely how:

```text
falsified  nonneg
           counterexample: (-4.38367): -4.383667491623871 vs 0
falsified  symmetric_in_sign
           counterexample: (-1.36279): -1.3627939099401543 vs 1.3627939099401543
holds      negative_exposure_negative
```

Look at the third one. `negative_exposure_negative` **holds**, and it
holds for a bad reason: `return x` really is negative for negative `x`.
A wrong belief and a buggy implementation agreed with each other, which
is exactly how a bug survives review. The counterexamples are stored
structurally, not just as display text, which matters in a moment.

## 2. Fix the code

```python
def settle(x: float) -> float:
    """Settlement amount for a signed exposure x."""
    return abs(x)
```

```bash
mathema verify --root .
```

```text
ok   funcs.midpoint: fresh
FAIL funcs.settle: form changed; 3 hold, 1 refuted  <- 1 falsified claim(s)
1 fresh (form unchanged, skipped), 1 adjudicated, 1 problem(s)
```

`midpoint` is skipped as `fresh`: its form hash has not moved, so there
is nothing to re-adjudicate. `settle` changed, so it is swept again,
and the record now keeps the arc:

```text
holds        nonneg   (was falsified)
holds        symmetric_in_sign   (was falsified)
invalidated  negative_exposure_negative   (was holds)
             counterexample: (-1.38109): 1.38109097388468 vs 0
```

Two things happened. The two real failures now hold, and they had to
clear the exact points that falsified them before: a recorded
counterexample replays on every later run, so a bug cannot be fixed by
accident and un-fixed quietly.

And `negative_exposure_negative` went from `holds` to **`invalidated`**.
That is its own verdict, not an ordinary failure: a claim that used to
be supported and no longer is. Fixing the code exposed a belief that
was never true. mathema will not launder that into a plain
`falsified`, because "this used to pass" is information a reviewer
needs.

## 3. Accept the evidence

`nonneg` holds empirically, over 128 seeded trials. Whether that is
enough is a human decision, so there is a verb for making it:

```bash
mathema accept funcs.settle nonneg --as evidence --by "Ada Lovelace"
```

```text
accepting funcs.settle :: nonneg (verdict holds) as evidence, by Ada Lovelace
  - annotate nonneg as accepted evidence at n=128 (bound to form 206704b327da...)
written: annotate nonneg as accepted evidence at n=128 (bound to form 206704b327da...)
```

`accept` prints exactly what it will write and waits for a yes. The
acceptance binds to the form hash, so changing `settle` later drops the
acceptance and asks again: you accepted evidence about *that* code.

## 4. There is no accepting a bug

The invalidated claim is still sitting there. The obvious move is to
wave it through as a known risk, and mathema refuses:

```bash
mathema accept funcs.settle negative_exposure_negative --as risk
```

```text
cannot accept: negative_exposure_negative is invalidated: a falsification is never
accepted as risk, diagnose it (--as discovery), or fix the code until it stops falsifying
```

This is the rule that makes the rest of it worth trusting. A
falsification is either a bug you fix or a belief you correct, and
neither of those is "acknowledged and ignored".

## 5. The discovery fork

Here the belief was wrong: settlements are magnitudes, so a negative
exposure settles *positive*. That is a real discovery about the domain,
and accepting it as one corrects the claim rather than deleting it:

```bash
mathema accept funcs.settle negative_exposure_negative --as discovery --by "Ada Lovelace"
```

```text
  - move negative_exposure_negative to the record's discoveries section
    (superseded_by: negative_exposure_negative_corrected), keeping its
    counterexample as the witness
  - declare the inverted corrected claim
    'negative_exposure_negative_corrected': 'f(x) > 0',
    adjudicated now: holds over 128 trials

declared-layer stanza: REPLACE the old claim in your claims file with this
(the superseded claim stays retained in the record's discoveries section):
  - name: negative_exposure_negative_corrected
    statement: "f(x) > 0"
    route: probe:semi_analytical
```

The old claim is not erased. It moves to the record's `discoveries`
section, and the counterexample that killed it is kept as the witness.
The corrected claim is never guessed at: mathema offers its mechanical
inverse only when the shape is soundly invertible AND the candidate has
just been adjudicated against the live function and holds; anything
else (a chained comparison, a premise, an inverse that fails) records
the discovery with no replacement, and you state what is true yourself
with `--corrected "<law>"`, which is adjudicated the same way before it
is written. A year later the record still says someone believed the
opposite, and why they stopped.

## 6. Owning what nothing can settle

Some claims neither route can decide, and they stay `unknown` rather
than being guessed at. Accepting one as **risk** reclassifies it to
`skipped:unknown_but_accepted`:

```bash
mathema accept funcs.settle some_unknown_claim --as risk --note "monitored"
```

Lenient verification proceeds past it, named in the row as accepted
risk. Strict mode still refuses it. Accepted risk stays visible either
way, which is the difference between owning a gap and hiding one.

## 7. Where the loop ends

The objective is to drive unknowns and skips down until every claim is
proven, holds with accepted evidence, or is an accepted discovery, with
nothing silently dropped on the way. Two commands watch that:

```bash
mathema verify --root .              # strict by default in CI
mathema verify --root . --lenient    # accepted risks proceed
mathema audit mypkg                  # the population view: what is claimed at all
```

`verify` exits 1 when a claim is falsified or, in strict mode,
unresolved, and 2 when it could not run at all. `audit` answers the
question `verify` cannot: not "do the stated claims pass" but "which
functions have nobody stated anything about".

## Where to go deeper

- [Writing claims](authoring.md): the four authoring surfaces and their
  precedence.
- [The claim grammar](grammar.md): every spelling, with a runnable
  example of each.
- [mathema accept](modes/accept.md): all five acceptances, including
  `--as superseded` and `--as historical`.
- [mathema review](modes/review.md): read the verified store by claim,
  the record shape, and the surface-versus-author provenance split.
- [The derive route](derive-route.md): why `midpoint` proved and
  `settle` could only be probed.
