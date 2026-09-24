# `mathema claims`

The claim authoring surface for one function: list what's declared,
render the standard claims mathema suggests for it, and adopt a
suggestion into the declared layer. Adoption is the explicit human
step; a suggestion never lives in any record until someone adopts it.

```bash
mathema claims KEY                  # list the declared claims
mathema claims KEY --suggest        # render the suggested standard claims
mathema claims KEY --adopt NAME     # write one into the declared layer
```

## Arguments

| Flag | Meaning |
|---|---|
| `key` | module-qualified function key (`functions.softmax`) |
| `--suggest` | render the suggested standard claims with laws and exclusivity groups |
| `--adopt NAME` | write the named suggestion into `claims/adopted.claims.yaml` |
| `--root` | project root (default: the nearest ancestor holding `.mathema/` within the enclosing git repository, else that repository, else `.`; never the home directory) |
| `--format` | `text` (default) or `json`: emit `--suggest`'s rows columnar, matching the MCP `suggest_claims` tool |
| `--output FILE` | write the report to a file instead of stdout |

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
without its `Claims:` block.

```
$ mathema claims functions.softmax
functions.softmax: no declared claims (mathema claims --suggest lists candidates)

$ mathema claims functions.softmax --suggest
functions.softmax: 7 suggested claim(s) (adopt with: mathema claims KEY --adopt NAME)
  - is_deterministic: f(scores) == f(scores)  [route best]
  - is_state_safe: f(scores) == f(scores)  [route best]
  - is_numerically_stable: g(f, scores) == 1  [route best]
  - preserves_length: dim(f(scores), 0) == dim(scores, 0)  [route probe]
  - is_permutation_of_input: sorted(f(scores)) == sorted(scores)  [route probe]
  - preserves_type: type(f(scores)) == type(scores)  [route probe]
  - is_sorted_output: is_sorted_output(f(scores))  [route examine]

$ mathema claims functions.softmax --adopt is_deterministic --root .
adopted is_deterministic into ./claims/adopted.claims.yaml: f(scores) == f(scores)

$ mathema claims functions.softmax
functions.softmax: 1 declared claim(s)
  - is_deterministic: f(scores) == f(scores)  [route best]
```

The adopted stanza is plain declared-claims YAML, so it's yours to
edit or delete like anything else in the file:

```yaml
functions.softmax:
  claims:
  - name: is_deterministic
    statement: f(scores) == f(scores)
    route: best
    grammar: mathema
```

## Suggestions that answer one question (aspects)

The suggestion battery volunteers every candidate it knows, so a
scalar function earns both monotonicity directions and all three
curvature answers per parameter. Those are not independent claims:
`monotonic_increasing[x]` and `monotonic_decreasing[x]` answer one
question (which way does f move in x), and `affine[x]`, `convex[x]`,
`concave[x]` answer another (which way does f bend in x). `--suggest`
labels each such member with its `aspect[target]` (`monotonicity[x]`,
`shape[x]`, `symmetry`), in the text row and in the `aspect` JSON
column, so a caller reads one question with a few candidate answers
rather than a flat cross-product. A suggestion no other suggestion
competes with carries an empty aspect. The table is
`mathema.families.CLAIM_ASPECTS`.

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
cols: ["name", "statement", "route", "declared", "aspect"]
```

`declared` is true when that name is already in the declared layer,
and `aspect` names the question a suggestion competes on (`""` when no
other suggestion competes with it, a computed-empty value, never
null). `--output FILE` writes it to a file instead of stdout.
