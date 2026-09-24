# Reason codes

The stable vocabulary for *why* a function is underivable, as printed
in `mathema audit`'s `blocked` column and detail block, carried in
`diagnostic_report()`/`describe --issue` payloads, and served by the
MCP `reason_code` tool. Look one up programmatically with
`mathema.reason_codes.describe_code(code)`.

A code reads `family:detail`: `loop:` codes come from the fold
recognizer, `branch:` codes from branch pruning (the resolvable kind,
`branch:needs-domain(...)`, names the parameters a claim should
declare a domain for), `unsupported:` codes from the expression
reader, and the bare codes (`stateful`, `recursion`, ...) from the
structural read. The `implementation:` group is different in kind: its
codes are not derivability blockers but falsification causes, attached
to a `falsified` claim whose failure is pinned on the implementation
stratum (an overflow, a recursion ceiling, float instability) rather
than on the mathematics; they ride the claim row's `reason` field the
same way, so tooling separates a broken carrier from broken
mathematics without parsing prose. A `+N` suffix on a branch code means N further
distinct blocked kinds occur in the same function; the detail block
lists each one.

The `derive_unlock` tag says what would unlock the derive route, and
whose move it is, nothing is broken either way, since a probe-route
claim adjudicates regardless: `actionable` (the code or the claim can
change to unlock it), `limitation` (the construct is fine, the derive
route doesn't reach it yet, the claim still adjudicates
empirically), or `N/A` (the derive route fundamentally doesn't
apply). Once released, a code is never renamed or repointed; new
codes only ever join.

Codes carry a stable numeric id, `major.minor`: majors are the
structural groups (1 structural blockers, 2 loop, 3 branch,
4 unsupported, 5 implementation), so a lookup can fetch a whole group ("2", or "loop")
or a single code ("2.18") instead of the full table. Ids are additive
only: a new code appends the next minor in its group, and a released
id is never renumbered.

| Id | Code | Derive unlock | Meaning | Hint |
|---|---|---|---|---|
| 3.2 | `branch:bare-local-name` | limitation | a bare local name's truthiness guards the branch | only comparisons are traced through locals; compare explicitly ('if flag == 1:') |
| 3.11 | `branch:composite` | limitation | an and/or chain with several distinct blocked parts | each joined condition must be prunable on its own; see the per-branch detail |
| 3.1 | `branch:needs-domain` | actionable | every branch resolves once the named parameters have declared domains | declare a domain for the named parameter(s) in the claim, e.g. 'for x in [0, 1], s in {"a"}, ...' |
| 3.7 | `branch:no-parameter-dependence` | limitation | the condition's TRACED form contains no unmodified parameter; either it genuinely uses none (a module flag, a constant guard) or the trace lost the dependence on the way | a claim's domain can only settle conditions over unmodified parameters; rewrite the condition over them, or accept the branch as unprunable |
| 3.8 | `branch:non-affine-essential` | limitation | the condition is transcendental in the parameters | no reparameterization linearizes it; a domain whose interval evaluation settles the guard outright can still work |
| 3.9 | `branch:non-affine-refinable` | actionable | the condition is polynomial but not affine | reparameterize to one combined variable, or declare a tighter domain that settles the guard |
| 3.4 | `branch:non-literal-compare` | limitation | the comparand is not a literal value | compare against a literal, or bind the comparand as its own parameter |
| 3.6 | `branch:opaque-expression` | limitation | neither side reduces to parameters or a literal | rewrite the condition over the function's own parameters |
| 3.3 | `branch:two-names-compare` | limitation | two names compared and at least one is not an unmodified parameter | pruning supports 'param <op> literal' and 'param <op> param' between unmodified parameters |
| 3.10 | `branch:unrecognized-shape` | limitation | the condition's shape is outside the grammar | only and/or/not, a bare parameter, or a single comparison are recognized |
| 3.5 | `branch:untraceable-local` | limitation | the condition's local is not traceable to unmodified parameters | only straight-line assignments from unmodified parameters are traced before the first branch |
| 5.1 | `implementation:overflow` | N/A | the call overflowed at an admitted point | the carrier is too narrow for the domain; widen the representation, guard the range, or narrow the claim's domain below the overflow threshold |
| 5.2 | `implementation:recursion-depth` | N/A | the call exhausted the recursion limit at an admitted point | an iterative rewrite removes the ceiling; otherwise narrow the claim's domain below the depth that exhausts the stack |
| 5.3 | `implementation:memory` | N/A | the call exhausted memory at an admitted point | narrow the claim's domain, or bound the allocation the input size drives |
| 5.4 | `implementation:nan` | N/A | the call returned a non-finite value where the exact value is finite | stated only when an exact-arithmetic result exists to compare against; clamp or reorder the operation that loses the value |
| 5.5 | `implementation:numerical-instability` | N/A | proven exactly in real arithmetic, numerically unstable in the declared domain | narrow the domain, cap infinity with a pseudo infinity binding, widen the tolerance to accept the risk, or clamp the fragile operation |
| 5.6 | `implementation:sub-epsilon-boundary` | N/A | a raise at a floating-point boundary; the same inputs nudged within epsilon evaluate cleanly | a clamp at the raising operation's argument removes the fragility |
| 5.7 | `implementation:representation` | N/A | machine spellings of one mathematical point disagree (int versus float versus bool) | normalize the input representation at entry, or state the intended representation in the claim |
| 5.8 | `implementation:accidental-crash` | N/A | an unguarded crash on arbitrary input, not a deliberate rejection | guard the input and raise the declared exception, or narrow the claim to the inputs the function accepts |
| 1.5 | `internal-error` | limitation | the derivability analysis itself failed | worth reporting: describe --issue builds the payload |
| 2.19 | `loop:additive-constant-update` | limitation | the linear update carries a constant term | a pure linear combination of item and accumulator is recognized today; the constant-term extension is tractable but not built |
| 2.5 | `loop:branch-elsewhere` | limitation | a non-guard branch outside the loop | leading raise-guards are stripped and proved around; any other branching alongside a loop blocks the fold read |
| 2.13 | `loop:external-init-wrong-iteration` | actionable | constant init but the loop skips part of the sequence | a constant-initialized fold should iterate the whole sequence; change the loop, or initialize from xs[0] |
| 2.8 | `loop:extra-statements` | limitation | statements besides init, loop, and return | extra work outside the loop is not part of a recognized fold; move it out or fold it into the return expression |
| 2.11 | `loop:first-element-init-wrong-iteration` | actionable | acc starts at xs[0] but the loop iterates all of xs | iterating the whole sequence double-counts xs[0]; change the loop to iterate xs[1:] |
| 2.4 | `loop:guarded-fold` | limitation | the accumulator update sits under an if | a conditional update has no single closed form; state the guarded region as its own claim instead |
| 2.15 | `loop:multi-statement-loop-body` | limitation | more than one statement in the loop body | only a single accumulator update per iteration is recognized; inline temporaries into the update |
| 2.2 | `loop:multiple-loops` | limitation | more than one loop in the body | only a single-loop body is recognized; split the function so each loop is its own function |
| 2.1 | `loop:no-loop` | limitation | the loop analysis ran on a function with no loop | usually a sign the body's shape confused the recognizer; worth reporting |
| 2.17 | `loop:no-return-value` | limitation | the function does not return the accumulator | a fold is recognized by returning a value built from its accumulator |
| 2.18 | `loop:non-affine-update` | limitation | the update is not linear in item and accumulator | only 'acc = A*item + B*acc' updates have the recognized closed form; a multiplicative fold does not derive today |
| 2.9 | `loop:non-simple-init` | limitation | the accumulator's initialization is not a single assignment | initialize the accumulator in one plain assignment before the loop |
| 2.10 | `loop:non-simple-loop-header` | limitation | the for-header does not iterate a plain name or recognized slice | iterate the sequence parameter directly (or xs[1:]) |
| 2.16 | `loop:non-simple-update` | actionable | the update is not a single assignment to the accumulator | write the update as one 'acc = <expr>' (or augmented) assignment |
| 2.3 | `loop:not-a-fold` | limitation | the loop is not an accumulator fold | only 'acc = f(acc, item)' accumulation loops are recognized |
| 2.12 | `loop:partial-seq-init` | actionable | acc starts from part of the sequence | initialize from xs[0] and iterate xs[1:], or from a constant and iterate all of xs |
| 2.6 | `loop:recursion` | limitation | the loop body also recurses | not derivable regardless of the loop's own shape |
| 2.20 | `loop:tuple-in-expression` | limitation | a tuple value inside the loop's own expressions | track one scalar accumulator per function |
| 2.21 | `loop:unclassified` | limitation | the fold recognizer declined without a specific reason | worth reporting: describe --issue builds the payload |
| 2.14 | `loop:unrecognized-loop-header` | actionable | the iterated expression is not a recognized shape | iterate the sequence parameter, xs[1:], or range(<expr>) with a derivable <expr> |
| 2.7 | `loop:wrong-sequence-param-count` | limitation | not exactly one sequence parameter | the fold read needs one sequence parameter to iterate |
| 1.3 | `no-parameters` | N/A | nothing to quantify over | a zero-parameter function has no input space to state claims about; probing can still check a constant value claim |
| 1.4 | `non-scalar-parameters` | limitation | a sequence parameter outside the recognized shapes | sequence functions derive only through the recognized loop shapes (fold, dot product, pure sum); anything else stays empirical |
| 1.2 | `recursion` | limitation | the function calls itself | a single-parameter recurrence of the recognized shape is solved, and a claim over a small integer range is checked exhaustively; any other recursion is not derivable, and an iterative or closed-form equivalent is |
| 1.1 | `stateful` | N/A | the method modifies instance state, or lets self escape the read-only field/sibling-call vocabulary | reading fields and calling sibling methods derives fine; a write to self (or passing self elsewhere) does not; keep the numeric core read-only, or extract it into a stateless function |
| 4.10 | `unsupported:array-index-mismatch` | limitation | an array indexed inconsistently with its construction | only same-length elementwise array reads derive |
| 4.9 | `unsupported:invalid-tuple-index` | limitation | a tuple indexed outside its known length | usually a real bug in the code being read |
| 4.11 | `unsupported:non-numeric-constant` | limitation | a non-numeric constant in a numeric position | string/bytes/None values have no numeric reading; a finite domain claim can still cover them |
| 4.12 | `unsupported:unsupported-statement` | limitation | a statement kind the derive route has no reading for where only assignment/return/if/for/raise belong (a while, try, with, del, ...) | the named statement is the blocker; restructure around it or rely on probe evidence |
| 4.13 | `unsupported:missing-return` | actionable | the function body never returns a value | a derive-route claim is about the returned value; add the return (or the claim belongs on a function that has one) |
| 4.7 | `unsupported:ternary` | limitation | a conditional expression in an unsupported position | an if/else statement over a prunable condition can take its place |
| 4.8 | `unsupported:tuple-in-expression` | limitation | a tuple value used inside an expression | return and compute one scalar per function |
| 4.6 | `unsupported:unbound-name` | actionable | a name with no binding anywhere | define or import the name; an unresolved name also fails the gate |
| 4.5 | `unsupported:unsupported-attribute` | limitation | an attribute access with no symbolic meaning | only mapped module attributes (math.pi, ...) derive |
| 4.2 | `unsupported:unsupported-comprehension` | limitation | a comprehension outside the recognized sum(...) shapes (a built list/dict value, a dict/set comp) | sum(<generator>) derives; rewrite the aggregation as sum(...) or an explicit accumulator loop; a comprehension VALUE is vector-valued and out of scope |
| 4.3 | `unsupported:unsupported-lambda` | limitation | a lambda outside the recognized shapes | assign the lambda to a local and call it, bind it via funcs=, or use it inside sum(map/filter(...)) |
| 4.4 | `unsupported:unsupported-call` | limitation | a call with no symbolic mapping | only the mapped math vocabulary derives; the claim still adjudicates empirically |
| 4.1 | `unsupported:unsupported-syntax` | limitation | a statement or expression outside the derive route's read | the named statement is the blocker; the rest of the body reads fine |

Probe-route claims remain viable on any function regardless of these
codes; they gate proof-strength (derive-route) evidence only, never
whether a claim can be written at all.
