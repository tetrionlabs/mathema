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
note funcs.settle: nonneg, symmetric_in_sign falsified on first adjudication. A declared claim is kept until a human decides it (fix the code, `mathema accept funcs.settle <claim> --as discovery`, or supersede it). To try a spelling first, `mathema check funcs.settle --claim "..."` adjudicates it and writes nothing.
ok   funcs.midpoint: no baseline record; 2 proven, 0 holds, 0 falsified
FAIL funcs.settle: no baseline record; 1 proven, 1 holds, 2 falsified  <- 2 falsified claim(s)
0 fresh (form unchanged, skipped), 2 adjudicated, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
```

`midpoint` proves on the derive route. Each row also counts one
`proven` claim nobody wrote, `dependencies_current`, which `verify`
adds itself. `settle` fails, and the record under
`.mathema/verified/funcs.settle.yaml` says precisely how (trimmed to
the three declared claims):

```yaml
    - name: "negative_exposure_negative"
      statement: "for x in [-5.0, -1.0]:float|missing, f(x) <= 0"
      verdict: "holds"
      n: 34
      route: "probe"
      # ...
    - name: "nonneg"
      statement: "for x in [-5.0, 5.0]:float|missing, f(x) >= 0"
      verdict: "falsified"
      n: 1
      counterexample: "(-5): -5.0 vs 0"
      route: "probe"
      # ...
        mathema.counterexample_args:
          - -5.0
      # ...
    - name: "symmetric_in_sign"
      statement: "for x in [-5.0, 5.0]:float|missing, f(x) = f(-x)"
      verdict: "falsified"
      n: 1
      counterexample: "(-5): -5.0 vs 5.0"
      route: "probe"
      # ...
        mathema.counterexample_args:
          - -5.0
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
FAIL funcs.settle: form changed; 1 proven, 2 holds, 0 falsified, 1 invalidated  <- 1 invalidated claim(s)
1 fresh (form unchanged, skipped), 1 adjudicated, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
```

`midpoint` is skipped as `fresh`: its form hash has not moved, so there
is nothing to re-adjudicate. `settle` changed, so it is swept again,
and the record now keeps the arc (trimmed):

```yaml
    - name: "negative_exposure_negative"
      statement: "for x in [-5.0, -1.0]:float|missing, f(x) <= 0"
      verdict: "invalidated"
      n: 1
      counterexample: "(-5): 5.0 vs 0"
      # ...
        mathema.previous_verdict: "holds"
        mathema.regressed_to: "falsified"
    - name: "nonneg"
      statement: "for x in [-5.0, 5.0]:float|missing, f(x) >= 0"
      verdict: "holds"
      n: 130
      # ...
        mathema.previous_verdict: "falsified"
    - name: "symmetric_in_sign"
      statement: "for x in [-5.0, 5.0]:float|missing, f(x) = f(-x)"
      verdict: "holds"
      n: 130
      # ...
        mathema.previous_verdict: "falsified"
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

`mathema.previous_verdict` is one step: the verdict immediately before
this one, not a history. The record has no history field because the
record is in git. `mathema review` reports which verdicts flipped
between two refs, and `git log .mathema/verified` lists every commit
that changed a record.

## 3. Accept the evidence

`nonneg` holds empirically, over 130 seeded trials. Whether that is
enough is a human decision, so there is a verb for making it:

```bash
mathema accept funcs.settle nonneg --as evidence --by "Ada Lovelace"
```

```text
accepting funcs.settle :: nonneg (verdict holds) as evidence, by Ada Lovelace
  - annotate nonneg as accepted evidence at n=130 (bound to form 206704b327da...)
write this acceptance? [y/N] y
written: annotate nonneg as accepted evidence at n=130 (bound to form 206704b327da...)
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
cannot accept: negative_exposure_negative is invalidated: a falsification is never accepted as risk, diagnose it (--as discovery), or fix the code until it stops falsifying
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
accepting funcs.settle :: negative_exposure_negative (verdict invalidated) as discovery, by Ada Lovelace
  - move negative_exposure_negative to the record's discoveries section (superseded_by: negative_exposure_negative_corrected), keeping its counterexample as the witness
  - declare the inverted corrected claim 'negative_exposure_negative_corrected': 'for x in [-5.0, -1.0]:float|missing, f(x) > 0', adjudicated now: holds over 130 trials
  - rewrite claims/demo.claims.yaml: replace declared claim 'negative_exposure_negative' with 'negative_exposure_negative_corrected'
write this acceptance? [y/N] y
written: move negative_exposure_negative to the record's discoveries section (superseded_by: negative_exposure_negative_corrected), keeping its counterexample as the witness; declare the inverted corrected claim 'negative_exposure_negative_corrected': 'for x in [-5.0, -1.0]:float|missing, f(x) > 0', adjudicated now: holds over 130 trials; rewrite claims/demo.claims.yaml: replace declared claim 'negative_exposure_negative' with 'negative_exposure_negative_corrected'
declared layer: claims/demo.claims.yaml now declares negative_exposure_negative_corrected in place of negative_exposure_negative (the superseded claim stays in the record's discoveries section):
  - name: negative_exposure_negative_corrected
    statement: "for x in [-5.0, -1.0]:float|missing, f(x) > 0"
    route: probe
```

The old claim is not erased. It moves to the record's `discoveries`
section, the counterexample that killed it is kept as the witness, and
`claims/demo.claims.yaml` is rewritten to declare the corrected claim
in its place.
The corrected claim is never guessed at: mathema offers its mechanical
inverse only when the shape is soundly invertible AND the candidate has
just been adjudicated against the live function and holds; anything
else (a chained comparison, a premise, an inverse that fails) records
the discovery with no replacement, and you state what is true yourself
with `--corrected "<law>"`, which is adjudicated the same way before it
is written. A year later the record still says someone believed the
opposite, and why they stopped.

With the bug fixed, the evidence accepted and the wrong belief corrected,
the sweep passes:

```bash
mathema verify --root .
```

```text
ok   funcs.midpoint: fresh
ok   funcs.settle: claims changed; 1 proven, 3 holds, 0 falsified
1 fresh (form unchanged, skipped), 1 adjudicated, 0 problem(s)
grammars detected: mathema; verified by this run: mathema
```

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

`verify` exits 1 when a claim is falsified or unknown or, in strict
mode, skipped or accepted as risk, and 2 when it could not run at all. `audit` answers the
question `verify` cannot: not "do the stated claims pass" but "which
functions have nobody stated anything about".

## Where to go deeper

- [Writing claims](authoring.md): the four authoring surfaces and their
  precedence.
- [The claim grammar](grammar.md): every spelling, with a runnable
  example of each.
- [mathema accept](modes/accept.md): every acceptance, including
  `--as superseded` and `--as historical`.
- [mathema review](modes/review.md): read the verified store by claim,
  the record shape, and the surface-versus-author provenance split.
- [The derive route](derive-route.md): why `midpoint` proved and
  `settle` could only be probed.
