# `mathema claims`

The claim authoring surface for one function: list what's declared,
render the standard claims mathema suggests for it, and adopt a
suggestion into the declared layer. Adoption is an explicit step, which
a person or an agent may take; a suggestion never lives in any record
until it is adopted.

```bash
mathema claims KEY                  # list the declared claims
mathema claims KEY --suggest        # render the suggested standard claims
mathema claims KEY --adopt NAME     # write one into the declared layer
mathema claims KEY --write          # write the policy rows
```

## Arguments

| Flag | Meaning |
|---|---|
| `key` | module-qualified function key (`functions.softmax`) |
| `--suggest` | render the suggested standard claims with laws, in three sections: individual claims, questions with candidate answers, and claims likely to be unknowable |
| `--adopt NAME` | write the named suggestion into `claims/adopted.claims.yaml` |
| `--write` | write the policy rows mathema suggests, what each parameter does with a value that is not there, into `claims/policies.claims.yaml`, each under the name the record prints, a contradicted one with the contradiction in its note |
| `--root` | project root (default: the nearest ancestor holding `.mathema/` within the enclosing git repository, else that repository, else `.`; never the home directory) |
| `--format` | `text` (default) or `json`: emit `--suggest`'s rows columnar, matching the MCP `suggest_claims` tool |
| `--output FILE` | write the report to a file instead of stdout |

## Policy rows

Beside the declared claims, `mathema claims KEY` lists the policy rows
the record carries: what the function does with a missing or absent
input, grouped by state ([missing values](../missing-values.md) says
what each word means). `--write` writes them to
`claims/policies.claims.yaml` under their record names (`missing[x]`,
`missing[xs, null]`, `absent[x]`, `absent[d.note, unset]` for a key
along a path), each with a note saying where it
came from. A row the code contradicts is written too, its note saying
so with the date, and the write line names the three ways out: change
the word, change the code, or accept it as a discovery. A raise no
claim accounts for has no word to write; the write line names the claim
to state instead. Changing a policy is then editing one word.

## Where suggestions live (and where they never do)

Suggestions are helpers for authoring standard claims, determinism,
reproducibility, domain safety, a missing-value policy, inferred from
the function's structure and types. They are rendered for a decision,
not recorded as fact:

- A verified record (`.mathema/verified/`) never contains a suggestion.
  `mathema check` displays suggested claims' adjudications so you can
  see whether one is worth adopting, but only claims you actually
  stated gate an exit code. A *falsified* suggestion is still shown
  prominently: it's real knowledge about the function, and a reason
  not to adopt.
- The declared layer is a consolidation of authoring surfaces
  (docstring claims, decorators, declared YAML), so an adopted
  suggestion goes there, as an ordinary declared claim in
  `claims/adopted.claims.yaml`, indistinguishable from one you wrote
  by hand, and gated like one from then on.

## Worked example

`functions.py` holds the `softmax` from the
[`check` worked example](check.md#worked-example-softmax-start-to-finish),
without its `Claims:` block:

<!-- example: adopt file=functions.py -->
```python
import math
from typing import Annotated
from mathema.types import Shape

def softmax(scores: Annotated[list[float], Shape("n")]) -> Annotated[list, Shape("n")]:
    """Turn a vector of real-valued scores into a probability distribution."""
    if not scores:
        raise ValueError("softmax needs at least one score")
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]
```

<!-- example: adopt session -->
```
$ mathema claims functions.softmax
functions.softmax: no declared claims (to list candidates, run: mathema claims functions.softmax --suggest)
$ mathema claims functions.softmax --suggest
functions.softmax: 10 suggested claim(s) (adopt with: mathema claims KEY --adopt NAME)
  effects: no side effects
 individual claims:
  - is_deterministic: f(scores) == f(scores)  [route best]
  - is_state_safe: f(scores) == f(scores)  [route best]
  - is_empty_safe[scores]: is_empty_safe(scores)  [route examine]
  - is_dimension_safe[f]: is_dimension_safe(f)  [route examine]
  - preserves_length: dim(f(scores), 0) == dim(scores, 0)  [route probe]
  - is_permutation_of_input: sorted(f(scores)) == sorted(scores)  [route probe]
  - preserves_type: type(f(scores)) == type(scores)  [route probe]
  - is_sorted_output: is_sorted_output(f(scores))  [route examine]
  - raises[scores]: raises(f(scores), ValueError)  [route best]
  - is_missing_safe[f]: is_missing_safe(f)  [route examine]
$ mathema claims functions.softmax --adopt is_deterministic --root .
adopted is_deterministic into ./claims/adopted.claims.yaml: f(scores) == f(scores)
$ mathema claims functions.softmax
functions.softmax: 1 declared claim(s)
  - is_deterministic: f(scores) == f(scores)  [route best]
```

The adopted stanza is plain declared-claims YAML, so it's yours to
edit or delete like anything else in the file:

<!-- example: adopt run -->
```bash
cat claims/adopted.claims.yaml
```

<!-- example: adopt output -->
```yaml
functions.softmax:
  claims:
  - name: is_deterministic
    statement: f(scores) == f(scores)
    route: best
    grammar: mathema
```

## The three sections

`--suggest` lists its suggestions in three sections.

- **Individual claims** stand alone: each answers a question no other
  suggestion answers.
- **Questions with candidate answers.** The battery volunteers every
  candidate it knows, so a scalar function earns both monotonicity
  directions and all three curvature answers per parameter. Those are
  not independent claims: `monotonic_increasing[x]` and
  `monotonic_decreasing[x]` answer one question (which way does f move
  in x), and `affine[x]`, `convex[x]`, `concave[x]` answer another
  (which way does f bend in x). Each question is listed by its
  `aspect[target]` (`monotonicity[x]`, `shape[x]`, `symmetry`) with
  its candidate answers under it. More than one answer may hold (an
  affine function is convex and concave too), so adopt every answer
  that does; they are never contradictions. The table is
  `mathema.families.CLAIM_ASPECTS`.
- **Likely to be unknowable.** `is_state_safe`, `is_deterministic` and
  `is_reproducible` are decided by reading the function's source. When
  that reading meets something it cannot read (`getattr`, a library
  function it has no entry for), the suggestion is listed here with that
  reason on the line below it. It is never adopted unless named.

The effects the reading finds are always shown, on a line under the
count. `is_state_safe` is suggested only for a function with no side
effects at its default values: when the reading already sees a write,
the effects line states it and there is nothing to adopt. For a function
that stores a rate in the environment:

<!-- example: env-write file=rates.py -->
```python
import os


def remember(rate: float) -> float:
    """Store the rate for later runs and return it."""
    os.environ["R"] = str(rate)
    return rate
```

<!-- example: env-write run -->
```bash
mathema claims rates.remember --suggest --root .
```

<!-- example: env-write output match=subset -->
```text
rates.remember: 12 suggested claim(s) (adopt with: mathema claims KEY --adopt NAME)
  effects: changes os.environ (os.environ['R'] = ...)
 individual claims:
```

A stronger relation, a genuine contradiction where adopting a second
member is not a refinement but a conflict, lives in the separate
`mathema.families.EXCLUSIVE_GROUPS`: `--adopt` refuses a member whose
exclusive group already has a declared member, naming the clash. No
exclusive group is populated today, since every shipped family that
shares a question does so as alternatives (affine implies both convex
and concave, so those three are alternatives, not rivals), not as a
contradiction.

## Relation to `enforce_domain`

The [`enforce_domain` decorator](../authoring.md) works from the same
declared layer in the other direction: it reads every parameter
interval already declared on the function's claims and wraps the
function with runtime guards, so arguments outside the declared domain
raise `DomainError` instead of silently computing. A function whose
domain is actually enforced has answered the domain-safety question a
suggestion would otherwise be asking.

## `--format json`

`mathema claims KEY --suggest --format json` emits the suggestions
columnar, the same shape and columns the MCP `suggest_claims` tool
returns:

```
cols: ["name", "statement", "route", "declared", "aspect", "section", "reason"]
```

`declared` is true when that name is already in the declared layer,
and `aspect` names the question a suggestion answers (`""` when no
other suggestion answers it, a computed-empty value, never null).
`section` is `individual`, `question` or `unknowable`, and `reason`
is the one-line reason for an `unknowable` row (`""` on every other
row). `--output FILE` writes it to a file instead of stdout.
