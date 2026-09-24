# The evidence ladder

Evidence isn't binary, and the most useful thing a verification tool can do
is tell you honestly how strong each piece of it is. mathema ranks every
supported claim by how it was established, from a proof that covers every
input in the declared domain down to a sentence someone wrote in a docstring,
and it never lets a weaker result be reported as a stronger one.

<div class="mx-figure">
<svg class="mx-diagram" viewBox="0 0 640 330" role="img" aria-labelledby="ladder-title ladder-desc" xmlns="http://www.w3.org/2000/svg">
  <title id="ladder-title">The evidence ladder</title>
  <desc id="ladder-desc">Six rungs, strongest at the top: derive, derive extensive, informed probing, probing, documented, declared.</desc>
  <g class="mx-d-rail"><line x1="40" y1="20" x2="40" y2="310"/><line x1="600" y1="20" x2="600" y2="310"/></g>
  <g class="mx-d-rung mx-d-strong"><rect x="60" y="20" width="520" height="40" rx="3"/><text x="80" y="45" class="mx-d-label">derive</text><text x="560" y="45" class="mx-d-verdict" text-anchor="end">proven</text></g>
  <g class="mx-d-rung mx-d-strong"><rect x="60" y="70" width="520" height="40" rx="3"/><text x="80" y="95" class="mx-d-label">derive:extensive</text><text x="560" y="95" class="mx-d-verdict" text-anchor="end">proven</text></g>
  <g class="mx-d-rung"><rect x="60" y="120" width="520" height="40" rx="3"/><text x="80" y="145" class="mx-d-label">probe:semi_analytical · probe:algorithmic</text><text x="560" y="145" class="mx-d-verdict" text-anchor="end">holds (n=…)</text></g>
  <g class="mx-d-rung"><rect x="60" y="170" width="520" height="40" rx="3"/><text x="80" y="195" class="mx-d-label">probe</text><text x="560" y="195" class="mx-d-verdict" text-anchor="end">holds (n=…)</text></g>
  <g class="mx-d-rung mx-d-weak"><rect x="60" y="220" width="520" height="40" rx="3"/><text x="80" y="245" class="mx-d-label">documented</text><text x="560" y="245" class="mx-d-verdict" text-anchor="end">stated deliberately</text></g>
  <g class="mx-d-rung mx-d-weak"><rect x="60" y="270" width="520" height="40" rx="3"/><text x="80" y="295" class="mx-d-label">declared</text><text x="560" y="295" class="mx-d-verdict" text-anchor="end">inferred from a summary</text></g>
</svg>
</div>

## The rungs, strongest first

| Rung | Verdict | What established it |
|---|---|---|
| `derive` | `proven` | The function's body was lifted to a symbolic expression and the claim settled over the whole declared domain. |
| `derive:extensive` | `proven` | The same, reached only by the deeper search you opt into with `extensive=True`. |
| `probe:semi_analytical`, `probe:algorithmic` | `holds (n=...)` | The real function survived `n` trials whose inputs were chosen by analysis, such as the points where a denominator vanishes, or by a technique specific to the claim. |
| `probe` | `holds (n=...)` | The real function survived `n` seeded random trials. |
| `documented` | none | Stated intent that a person has accepted with `mathema accept --intent`. |
| `declared` | none | Stated intent (a docstring summary, an `Intent:` block, an `intent:` field) that no person has accepted yet, the weakest rung there is. |

The two informed probing routes share a rung because they draw on different
sources of information without either being stronger than the other. The
ladder is defined in the engine as `mathema.conjecture.EVIDENCE_LADDER`, and
a route mathema does not recognise, such as one from a verification
technique you have plugged in yourself, ranks below everything it does.

## A proof is the mathematics; `[float]` is the code

A `proven` from the derive route means the claim holds in exact real
arithmetic over the declared domain, and nothing more. It does not say
the float implementation gets the same answer. That is a separate
claim, and mathema makes it for you: every claim the derive route
proves spawns a companion named `<name>[float]`, in the numerical
stability family, adjudicated on the probe route against the real code.
The companion runs the relation at every corner of the declared domain
and at sampled interior points. A raise, a `NaN`, or an `inf` or a loss
of precision where the relation fails on the executed values falsifies
it, with that point as the witness. An unbounded direction runs to the
claim's `|inf|` when one is declared, and otherwise out to `1e308`,
sampled log-uniformly so moderate magnitudes are visited too.

```python
import mathema
from mathema.conjecture import claim


def one(x: float) -> float:
    """One, computed the long way round."""
    return (x + 1.0) - x


for law, route in [("for x in [0, 1e6], f(x) == 1", "derive"),
                   ("f(x) == 1", "derive"),
                   ("f(x) == 1", "derive:math_only")]:
    rec = mathema.check(one, claims=[claim(law, name="one", route=route)])
    for p in rec.probes:
        print(f"{route:16} {p.name:10} {p.verdict:9} "
              f"{p.counterexample or ''}".rstrip())
```

```text
derive           one        proven
derive           one[float] holds
derive           one        proven
derive           one[float] falsified x=-1e+308
derive:math_only one        proven
```

`(x + 1) - x` is `1` for every real `x`, so all three proofs stand. In
float64 the `+ 1` is lost once `|x|` passes `2^53`, so the companion of
the unbounded claim is falsified, and its row names the stratum:
mathematics sound, implementation numerically unstable. Two claims, two
verdicts, and the companion gates `mathema verify` like any other claim.
The remedies are the ordinary ones: narrow the domain, declare the
`|inf|` the code has to reach, fix the code, accept the companion as a
discovery with `mathema accept`, or state the claim with
`route="derive:math_only"` (`[derive:math_only]` in a docstring), which
proves the mathematics alone, spawns no companion, and records the
opt-out on the proof's row.

The companion is written to the verified record beside its parent, with
`meta.mathema.companion_of` naming it. It is never part of the declared
layer: it is respawned from its parent on every adjudication, so it does
not enter the claims fingerprint and is not repopulated as a claim of
its own. A limit or an integral is a statement about the mathematics and
spawns no companion.

## What sits off the ladder

The ladder ranks how a claim came to be *supported*. Four other outcomes are
reported alongside it, and none of them is a weak form of support:

| Verdict | Means |
|---|---|
| `falsified` | A counterexample was found by running the function, and it is kept permanently. A falsification is equally definitive whichever route found it. |
| `unknown` | An adjudication ran and decided nothing either way, for instance a proof attempt that could not close. |
| `skipped` | The claim could not be adjudicated at all, for a reason the record names. |
| `invalidated` | A claim that was once `proven` or `holds` could no longer be established after the code changed, and the record says what it used to be. |

A `falsified` verdict is knowledge rather than failure: it tells you exactly
where the function and the claim part ways, and the
[accept workflow](modes/accept.md) lets a person decide whether that is a bug
in the code or a discovery about the specification.

## Why the rungs are kept apart

A result that holds on a thousand random inputs and a result that holds for
every input are different kinds of knowledge, and a report that blurs them is
telling you what you want to hear. So every verdict carries its route, a
`holds` always carries its trial count, a derive attempt that cannot close
hands the claim to the probe route with the reason it stopped kept in the
record (a sampled `holds` never passes itself off as a proof), and a symbolic
disproof that nothing can reproduce against the real function, even compared
exactly, comes back `unknown` and flagged instead of `falsified`, since it
more likely points at a fault in the engine than in your code.

[Claim-driven development](cdd.md) has the full verdict vocabulary, and
[the derive route](derive-route.md) covers which functions can reach the top
rung.
