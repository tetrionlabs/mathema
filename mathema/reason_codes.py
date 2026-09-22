# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The public reason-code registry: a stable, versioned vocabulary for
*why* a function didn't lift (`ReasonCode`/`Category`) and for *why*
one claim's own adjudication was skipped (`ClaimReasonCode`), plus
`build_issue_record()`/`issue()`, which build a real CDD spec record
(`spec.to_spec()`) around whichever of those applies and attach the
rest of the diagnostic depth under the record's own `meta` field.

This does not introduce a new vocabulary for either registry.
`inventory.derivability_report()` already computes exactly
`ReasonCode`'s eight `blocker` values, `symbolic.NotSymbolic` already
tags `Category`'s finer-grained values, and `conjecture.check_conjectures()`
already has its own closed set of skip sites, two of them already
tagged in `Probe.meta` (`mathema.foreign_grammar`, `mathema.derive_status`),
the rest identifiable from the exact note text it already writes.
`ClaimReasonCode` names what's already there.

Once released, these names are public interface: never renamed, and
never repointed at a different meaning. A new value is added as a new
name; an existing one is never redefined underneath code that already
depends on it.
"""
from __future__ import annotations

from .records import classify_verdict


class ReasonCode:
    """The eight values `inventory.derivability_report()`'s own
    `blocker` field can take, exactly as it already writes them,
    named here, not reinvented."""
    STATEFUL = "stateful"
    LOOP = "loop"
    BRANCH = "branch"
    RECURSION = "recursion"
    NO_PARAMETERS = "no-parameters"
    NON_SCALAR_PARAMETERS = "non-scalar-parameters"
    INTERNAL_ERROR = "internal-error"
    UNSUPPORTED_CONSTRUCT = "unsupported-construct"

    ALL = (STATEFUL, LOOP, BRANCH, RECURSION, NO_PARAMETERS,
          NON_SCALAR_PARAMETERS, INTERNAL_ERROR, UNSUPPORTED_CONSTRUCT)


class Category:
    """`symbolic.NotSymbolic.category`'s own vocabulary, only
    meaningful alongside `ReasonCode.UNSUPPORTED_CONSTRUCT`, naming
    which specific unsupported-syntax shape was hit. `UNSUPPORTED_SYNTAX`
    is `NotSymbolic`'s own default when no more specific category is
    given; the rest are the specific categories currently raised
    anywhere in the derive-route lifting code."""
    UNSUPPORTED_SYNTAX = "unsupported-syntax"
    UNSUPPORTED_CALL = "unsupported-call"
    UNSUPPORTED_ATTRIBUTE = "unsupported-attribute"
    UNBOUND_NAME = "unbound-name"
    TERNARY = "ternary"
    TUPLE_IN_EXPRESSION = "tuple-in-expression"
    INVALID_TUPLE_INDEX = "invalid-tuple-index"
    ARRAY_INDEX_MISMATCH = "array-index-mismatch"
    NON_NUMERIC_CONSTANT = "non-numeric-constant"

    ALL = (UNSUPPORTED_SYNTAX, UNSUPPORTED_CALL, UNSUPPORTED_ATTRIBUTE,
          UNBOUND_NAME, TERNARY, TUPLE_IN_EXPRESSION, INVALID_TUPLE_INDEX,
          ARRAY_INDEX_MISMATCH, NON_NUMERIC_CONSTANT)


class ClaimReasonCode:
    """Why one claim's own adjudication came back `skipped` (blocked,
    with reason) or stayed `unknown` (attempted, undecided),
    formalizes `conjecture.check_conjectures()`'s own existing skip
    sites, not a new taxonomy. Meaningful mainly alongside verdict
    `skipped`. An ordinary `falsified` claim's sketch/counterexample is
    the full story and carries no code; the one exception is a
    falsification whose stratum pins the failure on the implementation
    (`meta["mathema.stratum"]`), which carries its `implementation:`
    cause so tooling can separate a broken carrier from broken
    mathematics without parsing prose.

    `DERIVE_TIMEOUT` is the one real code change behind this registry,
    not just a name: a derive-route wall-clock cutoff
    (`symbolic._proof_support._prove_relation`'s own `_with_timeout`)
    used to come back indistinguishable from sympy simply failing to
    decide on its own; both were a bare `undecided`. It now carries
    `meta["mathema.timeout"]` (`"fast"` or `"extensive"`, the tier that
    was in effect), propagated through to the claim's own `Probe.meta`
    alongside the existing `mathema.derive_status`.

    `NO_EVALUABLE_INPUTS` is the one code here that's genuinely
    probe-route-specific (every synthesized trial raised before a
    comparison was ever made); everything else is checked before, or
    independent of, the route split."""
    FOREIGN_GRAMMAR = "foreign-grammar"
    UNSUPPORTED_MULTI_FUNCTION = "unsupported-multi-function"
    DERIVE_UNDECIDED = "derive-undecided"
    DERIVE_UNLIFTABLE = "derive-unliftable"
    DERIVE_TIMEOUT = "derive-timeout"
    UNKNOWN_ROUTE = "unknown-route"
    UNKNOWN_RELATION = "unknown-relation"
    UNKNOWN_EXCEPTION_TYPE = "unknown-exception-type"
    INVALID_CONJECTURE = "invalid-conjecture"
    NO_EVALUABLE_INPUTS = "no-evaluable-inputs"
    # a HOLDS verdict that rests on the empirical fallback because the
    # derive route could not settle the claim: the record is evidence,
    # not proof, and a caller measuring derive-route coverage needs the
    # gap machine-readable (previously only skipped/unknown verdicts
    # ever carried a code, so holds-rescued gaps, the bulk of a
    # corpus's open-proof population, were invisible to tooling)
    DERIVE_GAP_EMPIRICAL = "derive-gap-empirical"
    # a conditional claim (`assuming X holds, ...`) whose premise could
    # not be discharged. The claim itself was never attempted; there
    # is nothing wrong with it, only with what it rests on, so these
    # sit alongside the undecided codes rather than the blocked ones.
    MISSING_PREREQUISITE = "missing-prerequisite"
    UNMET_PREREQUISITE = "unmet-prerequisite"
    AMBIGUOUS_PREREQUISITE = "ambiguous-reference"
    DEPENDENCY_CYCLE = "dependency-cycle"

    ALL = (FOREIGN_GRAMMAR, UNSUPPORTED_MULTI_FUNCTION, DERIVE_UNDECIDED,
          DERIVE_UNLIFTABLE, DERIVE_TIMEOUT, UNKNOWN_ROUTE, UNKNOWN_RELATION,
          UNKNOWN_EXCEPTION_TYPE, INVALID_CONJECTURE, NO_EVALUABLE_INPUTS,
          DERIVE_GAP_EMPIRICAL, MISSING_PREREQUISITE, UNMET_PREREQUISITE,
          AMBIGUOUS_PREREQUISITE, DEPENDENCY_CYCLE)


class LoopReason:
    """The fold recognizer's own decline slugs (`symbolic.diagnose_fold`
    and `_lift_fold_impl`'s `reason` field), exactly as they are
    already written, named here, not reinvented. Rendered composed as
    `loop:<value>` by `blocked_code()`. A loop decline can also carry a
    `Category` value when one of the loop's own pieces hit an
    unsupported construct."""
    NO_LOOP = "no-loop"
    MULTIPLE_LOOPS = "multiple-loops"
    NOT_A_FOLD = "not-a-fold"
    GUARDED_FOLD = "guarded-fold"
    BRANCH_ELSEWHERE = "branch-elsewhere"
    RECURSION = "recursion"
    WRONG_SEQUENCE_PARAM_COUNT = "wrong-sequence-param-count"
    EXTRA_STATEMENTS = "extra-statements"
    NON_SIMPLE_INIT = "non-simple-init"
    NON_SIMPLE_LOOP_HEADER = "non-simple-loop-header"
    FIRST_ELEMENT_INIT_WRONG_ITERATION = "first-element-init-wrong-iteration"
    PARTIAL_SEQ_INIT = "partial-seq-init"
    EXTERNAL_INIT_WRONG_ITERATION = "external-init-wrong-iteration"
    UNRECOGNIZED_LOOP_HEADER = "unrecognized-loop-header"
    MULTI_STATEMENT_LOOP_BODY = "multi-statement-loop-body"
    NON_SIMPLE_UPDATE = "non-simple-update"
    NO_RETURN_VALUE = "no-return-value"
    NON_AFFINE_UPDATE = "non-affine-update"
    ADDITIVE_CONSTANT_UPDATE = "additive-constant-update"
    TUPLE_IN_EXPRESSION = "tuple-in-expression"
    UNCLASSIFIED = "unclassified"

    ALL = (NO_LOOP, MULTIPLE_LOOPS, NOT_A_FOLD, GUARDED_FOLD,
          BRANCH_ELSEWHERE, RECURSION, WRONG_SEQUENCE_PARAM_COUNT,
          EXTRA_STATEMENTS, NON_SIMPLE_INIT, NON_SIMPLE_LOOP_HEADER,
          FIRST_ELEMENT_INIT_WRONG_ITERATION, PARTIAL_SEQ_INIT,
          EXTERNAL_INIT_WRONG_ITERATION, UNRECOGNIZED_LOOP_HEADER,
          MULTI_STATEMENT_LOOP_BODY, NON_SIMPLE_UPDATE, NO_RETURN_VALUE,
          NON_AFFINE_UPDATE, ADDITIVE_CONSTANT_UPDATE, TUPLE_IN_EXPRESSION,
          UNCLASSIFIED)


class BranchReason:
    """Why one branch condition can or cannot be pruned
    (`symbolic._explain_branch`'s `code` field). `NEEDS_DOMAIN` is the
    resolvable kind, pruning settles the branch once a claim declares
    a specific-enough domain for the named parameters; the rest are the
    structurally blocked kinds. Rendered composed as `branch:<value>`
    (`branch:needs-domain(scale)` names the parameters) by
    `blocked_code()`."""
    NEEDS_DOMAIN = "needs-domain"
    BARE_LOCAL_NAME = "bare-local-name"
    TWO_NAMES_COMPARE = "two-names-compare"
    NON_LITERAL_COMPARE = "non-literal-compare"
    UNTRACEABLE_LOCAL = "untraceable-local"
    OPAQUE_EXPRESSION = "opaque-expression"
    NO_PARAMETER_DEPENDENCE = "no-parameter-dependence"
    NON_AFFINE_ESSENTIAL = "non-affine-essential"
    NON_AFFINE_REFINABLE = "non-affine-refinable"
    UNRECOGNIZED_SHAPE = "unrecognized-shape"
    COMPOSITE = "composite"

    ALL = (NEEDS_DOMAIN, BARE_LOCAL_NAME, TWO_NAMES_COMPARE,
          NON_LITERAL_COMPARE, UNTRACEABLE_LOCAL, OPAQUE_EXPRESSION,
          NO_PARAMETER_DEPENDENCE, NON_AFFINE_ESSENTIAL,
          NON_AFFINE_REFINABLE, UNRECOGNIZED_SHAPE, COMPOSITE)


def blocked_code(report: dict | None) -> str | None:
    """The compact underivability code for one
    `inventory.derivability_report()` dict: `stateful`, `recursion`,
    `no-parameters`, `non-scalar-parameters`, `internal-error`,
    `loop:<LoopReason>`, `branch:<BranchReason>` (with
    `(param, ...)` naming the domains to declare for the resolvable
    kind, and a `+N` suffix when several distinct blocked kinds occur),
    or `unsupported:<Category>`. `None` for a derivable function or a
    missing report. The lookup for every code is `describe_code()`."""
    if not report or report.get("liftable"):
        return None
    blocker = report.get("blocker")
    if blocker == "loop":
        return f"loop:{report.get('reason') or LoopReason.UNCLASSIFIED}"
    if blocker == "branch":
        branches = report.get("branches") or []
        blocked = [b for b in branches if b.get("kind") == "blocked"]
        if not blocked:
            needs = sorted({p for b in branches
                            for p in b.get("needs_domain_for") or []})
            suffix = f"({', '.join(needs)})" if needs else ""
            return f"branch:{BranchReason.NEEDS_DOMAIN}{suffix}"
        codes: list[str] = []
        for b in blocked:
            c = b.get("code") or BranchReason.UNRECOGNIZED_SHAPE
            if c not in codes:
                codes.append(c)
        extra = f"+{len(codes) - 1}" if len(codes) > 1 else ""
        return f"branch:{codes[0]}{extra}"
    if blocker == "unsupported-construct":
        return (f"unsupported:"
                f"{report.get('category') or Category.UNSUPPORTED_SYNTAX}")
    return blocker


_ACTIONABLE = "actionable"
_LIMITATION = "limitation"
_NOT_APPLICABLE = "N/A"

# the one lookup table behind every compact code: what it means, whether
# changing the code or the claim can fix it (`actionable`), it is a
# recognizer limitation (`mathema-limitation`), or the derive route
# fundamentally does not apply (`not-applicable`), and the generic hint.
# docs/reason-codes.md renders this table verbatim (a test holds the two
# together), and the MCP lookup tool serves it.
CODE_TABLE: dict[str, dict] = {
    "stateful": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "the method modifies instance state, or lets self "
                   "escape the read-only field/sibling-call vocabulary",
        "hint": "reading fields and calling sibling methods derives "
                "fine; a write to self (or passing self elsewhere) "
                "does not; keep the numeric core read-only, or "
                "extract it into a stateless function"},
    "recursion": {
        "derive_unlock": _LIMITATION,
        "meaning": "the function calls itself",
        "hint": "recursive definitions are not derivable today; an "
                "iterative or closed-form equivalent is"},
    "no-parameters": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "nothing to quantify over",
        "hint": "a zero-parameter function has no input space to state "
                "claims about; probing can still check a constant value "
                "claim"},
    "non-scalar-parameters": {
        "derive_unlock": _LIMITATION,
        "meaning": "a sequence parameter outside the recognized shapes",
        "hint": "sequence functions derive only through the recognized "
                "loop shapes (fold, dot product, pure sum); anything "
                "else stays empirical"},
    "internal-error": {
        "derive_unlock": _LIMITATION,
        "meaning": "the derivability analysis itself failed",
        "hint": "worth reporting: describe --issue builds the payload"},
    "loop:no-loop": {
        "derive_unlock": _LIMITATION,
        "meaning": "the loop analysis ran on a function with no loop",
        "hint": "usually a sign the body's shape confused the "
                "recognizer; worth reporting"},
    "loop:multiple-loops": {
        "derive_unlock": _LIMITATION,
        "meaning": "more than one loop in the body",
        "hint": "only a single-loop body is recognized; split the "
                "function so each loop is its own function"},
    "loop:not-a-fold": {
        "derive_unlock": _LIMITATION,
        "meaning": "the loop is not an accumulator fold",
        "hint": "only 'acc = f(acc, item)' accumulation loops are "
                "recognized"},
    "loop:guarded-fold": {
        "derive_unlock": _LIMITATION,
        "meaning": "the accumulator update sits under an if",
        "hint": "a conditional update has no single closed form; state "
                "the guarded region as its own claim instead"},
    "loop:branch-elsewhere": {
        "derive_unlock": _LIMITATION,
        "meaning": "a non-guard branch outside the loop",
        "hint": "leading raise-guards are stripped and proved around; "
                "any other branching alongside a loop blocks the fold "
                "read"},
    "loop:recursion": {
        "derive_unlock": _LIMITATION,
        "meaning": "the loop body also recurses",
        "hint": "not derivable regardless of the loop's own shape"},
    "loop:wrong-sequence-param-count": {
        "derive_unlock": _LIMITATION,
        "meaning": "not exactly one sequence parameter",
        "hint": "the fold read needs one sequence parameter to iterate"},
    "loop:extra-statements": {
        "derive_unlock": _LIMITATION,
        "meaning": "statements besides init, loop, and return",
        "hint": "extra work outside the loop is not part of a "
                "recognized fold; move it out or fold it into the "
                "return expression"},
    "loop:non-simple-init": {
        "derive_unlock": _LIMITATION,
        "meaning": "the accumulator's initialization is not a single "
                   "assignment",
        "hint": "initialize the accumulator in one plain assignment "
                "before the loop"},
    "loop:non-simple-loop-header": {
        "derive_unlock": _LIMITATION,
        "meaning": "the for-header does not iterate a plain name or "
                   "recognized slice",
        "hint": "iterate the sequence parameter directly (or xs[1:])"},
    "loop:first-element-init-wrong-iteration": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "acc starts at xs[0] but the loop iterates all of xs",
        "hint": "iterating the whole sequence double-counts xs[0]; "
                "change the loop to iterate xs[1:]"},
    "loop:partial-seq-init": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "acc starts from part of the sequence",
        "hint": "initialize from xs[0] and iterate xs[1:], or from a "
                "constant and iterate all of xs"},
    "loop:external-init-wrong-iteration": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "constant init but the loop skips part of the "
                   "sequence",
        "hint": "a constant-initialized fold should iterate the whole "
                "sequence; change the loop, or initialize from xs[0]"},
    "loop:unrecognized-loop-header": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "the iterated expression is not a recognized shape",
        "hint": "iterate the sequence parameter, xs[1:], or "
                "range(<expr>) with a derivable <expr>"},
    "loop:multi-statement-loop-body": {
        "derive_unlock": _LIMITATION,
        "meaning": "more than one statement in the loop body",
        "hint": "only a single accumulator update per iteration is "
                "recognized; inline temporaries into the update"},
    "loop:non-simple-update": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "the update is not a single assignment to the "
                   "accumulator",
        "hint": "write the update as one 'acc = <expr>' (or augmented) "
                "assignment"},
    "loop:no-return-value": {
        "derive_unlock": _LIMITATION,
        "meaning": "the function does not return the accumulator",
        "hint": "a fold is recognized by returning a value built from "
                "its accumulator"},
    "loop:non-affine-update": {
        "derive_unlock": _LIMITATION,
        "meaning": "the update is not linear in item and accumulator",
        "hint": "only 'acc = A*item + B*acc' updates have the "
                "recognized closed form; a multiplicative fold does "
                "not derive today"},
    "loop:additive-constant-update": {
        "derive_unlock": _LIMITATION,
        "meaning": "the linear update carries a constant term",
        "hint": "a pure linear combination of item and accumulator is "
                "recognized today; the constant-term extension is "
                "tractable but not built"},
    "loop:tuple-in-expression": {
        "derive_unlock": _LIMITATION,
        "meaning": "a tuple value inside the loop's own expressions",
        "hint": "track one scalar accumulator per function"},
    "loop:unclassified": {
        "derive_unlock": _LIMITATION,
        "meaning": "the fold recognizer declined without a specific "
                   "reason",
        "hint": "worth reporting: describe --issue builds the payload"},
    "branch:needs-domain": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "every branch resolves once the named parameters "
                   "have declared domains",
        "hint": "declare a domain for the named parameter(s) in the "
                "claim, e.g. 'for x in [0, 1], s in {\"a\"}, ...'"},
    "branch:bare-local-name": {
        "derive_unlock": _LIMITATION,
        "meaning": "a bare local name's truthiness guards the branch",
        "hint": "only comparisons are traced through locals; compare "
                "explicitly ('if flag == 1:')"},
    "branch:two-names-compare": {
        "derive_unlock": _LIMITATION,
        "meaning": "two names compared and at least one is not an "
                   "unmodified parameter",
        "hint": "pruning supports 'param <op> literal' and 'param <op> "
                "param' between unmodified parameters"},
    "branch:non-literal-compare": {
        "derive_unlock": _LIMITATION,
        "meaning": "the comparand is not a literal value",
        "hint": "compare against a literal, or bind the comparand as "
                "its own parameter"},
    "branch:untraceable-local": {
        "derive_unlock": _LIMITATION,
        "meaning": "the condition's local is not traceable to "
                   "unmodified parameters",
        "hint": "only straight-line assignments from unmodified "
                "parameters are traced before the first branch"},
    "branch:opaque-expression": {
        "derive_unlock": _LIMITATION,
        "meaning": "neither side reduces to parameters or a literal",
        "hint": "rewrite the condition over the function's own "
                "parameters"},
    "branch:no-parameter-dependence": {
        "derive_unlock": _LIMITATION,
        "meaning": "the condition's TRACED form contains no unmodified "
                   "parameter; either it genuinely uses none (a module "
                   "flag, a constant guard) or the trace lost the "
                   "dependence on the way",
        "hint": "a claim's domain can only settle conditions over "
                "unmodified parameters; rewrite the condition over "
                "them, or accept the branch as unprunable"},
    "branch:non-affine-essential": {
        "derive_unlock": _LIMITATION,
        "meaning": "the condition is transcendental in the parameters",
        "hint": "no reparameterization linearizes it; a domain whose "
                "interval evaluation settles the guard outright can "
                "still work"},
    "branch:non-affine-refinable": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "the condition is polynomial but not affine",
        "hint": "reparameterize to one combined variable, or declare a "
                "tighter domain that settles the guard"},
    "branch:unrecognized-shape": {
        "derive_unlock": _LIMITATION,
        "meaning": "the condition's shape is outside the grammar",
        "hint": "only and/or/not, a bare parameter, or a single "
                "comparison are recognized"},
    "branch:composite": {
        "derive_unlock": _LIMITATION,
        "meaning": "an and/or chain with several distinct blocked parts",
        "hint": "each joined condition must be prunable on its own; "
                "see the per-branch detail"},
    "unsupported:unsupported-syntax": {
        "derive_unlock": _LIMITATION,
        "meaning": "a statement or expression outside the derive "
                   "route's read",
        "hint": "the named statement is the blocker; the rest of the "
                "body reads fine"},
    "unsupported:unsupported-comprehension": {
        "derive_unlock": _LIMITATION,
        "meaning": "a comprehension outside the recognized sum(...) "
                   "shapes (a built list/dict value, a dict/set comp)",
        "hint": "sum(<generator>) derives; rewrite the aggregation "
                "as sum(...) or an explicit accumulator loop; a "
                "comprehension VALUE is vector-valued and out of scope"},
    "unsupported:unsupported-lambda": {
        "derive_unlock": _LIMITATION,
        "meaning": "a lambda outside the recognized shapes",
        "hint": "assign the lambda to a local and call it, bind it "
                "via funcs=, or use it inside sum(map/filter(...))"},
    "unsupported:unsupported-call": {
        "derive_unlock": _LIMITATION,
        "meaning": "a call with no symbolic mapping",
        "hint": "only the mapped math vocabulary derives; the claim "
                "still adjudicates empirically"},
    "unsupported:unsupported-attribute": {
        "derive_unlock": _LIMITATION,
        "meaning": "an attribute access with no symbolic meaning",
        "hint": "only mapped module attributes (math.pi, ...) derive"},
    "unsupported:unbound-name": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "a name with no binding anywhere",
        "hint": "define or import the name; an unresolved name also "
                "fails the gate"},
    "unsupported:ternary": {
        "derive_unlock": _LIMITATION,
        "meaning": "a conditional expression in an unsupported position",
        "hint": "an if/else statement over a prunable condition can "
                "take its place"},
    "unsupported:tuple-in-expression": {
        "derive_unlock": _LIMITATION,
        "meaning": "a tuple value used inside an expression",
        "hint": "return and compute one scalar per function"},
    "unsupported:invalid-tuple-index": {
        "derive_unlock": _LIMITATION,
        "meaning": "a tuple indexed outside its known length",
        "hint": "usually a real bug in the code being read"},
    "unsupported:array-index-mismatch": {
        "derive_unlock": _LIMITATION,
        "meaning": "an array indexed inconsistently with its "
                   "construction",
        "hint": "only same-length elementwise array reads derive"},
    "unsupported:non-numeric-constant": {
        "derive_unlock": _LIMITATION,
        "meaning": "a non-numeric constant in a numeric position",
        "hint": "string/bytes/None values have no numeric reading; a "
                "finite domain claim can still cover them"},
    "unsupported:unsupported-statement": {
        "derive_unlock": _LIMITATION,
        "meaning": "a statement kind the derive route has no reading "
                   "for where only assignment/return/if/for/raise "
                   "belong (a while, try, with, del, ...)",
        "hint": "the named statement is the blocker; restructure "
                "around it or rely on probe evidence"},
    "unsupported:missing-return": {
        "derive_unlock": _ACTIONABLE,
        "meaning": "the function body never returns a value",
        "hint": "a derive-route claim is about the returned value; "
                "add the return (or the claim belongs on a function "
                "that has one)"},
    # group 5, implementation: not derivability blockers at all. These
    # attach to a FALSIFIED claim through its stratum and say which
    # machine-level failure pinned the falsification on the
    # implementation. derive_unlock is N/A throughout: nothing here
    # gates the derive route.
    "implementation:overflow": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "the call overflowed at an admitted point",
        "hint": "the carrier is too narrow for the domain; widen the "
                "representation, guard the range, or narrow the "
                "claim's domain below the overflow threshold"},
    "implementation:recursion-depth": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "the call exhausted the recursion limit at an "
                   "admitted point",
        "hint": "an iterative rewrite removes the ceiling; otherwise "
                "narrow the claim's domain below the depth that "
                "exhausts the stack"},
    "implementation:memory": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "the call exhausted memory at an admitted point",
        "hint": "narrow the claim's domain, or bound the allocation "
                "the input size drives"},
    "implementation:nan": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "the call returned a non-finite value where the "
                   "exact value is finite",
        "hint": "stated only when an exact-arithmetic result exists "
                "to compare against; clamp or reorder the operation "
                "that loses the value"},
    "implementation:numerical-instability": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "proven exactly in real arithmetic, numerically "
                   "unstable in the declared domain",
        "hint": "narrow the domain, cap infinity with a pseudo "
                "infinity binding, widen the tolerance to accept the "
                "risk, or clamp the fragile operation"},
    "implementation:sub-epsilon-boundary": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "a raise at a floating-point boundary; the same "
                   "inputs nudged within epsilon evaluate cleanly",
        "hint": "a clamp at the raising operation's argument removes "
                "the fragility"},
    "implementation:representation": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "machine spellings of one mathematical point "
                   "disagree (int versus float versus bool)",
        "hint": "normalize the input representation at entry, or "
                "state the intended representation in the claim"},
    "implementation:accidental-crash": {
        "derive_unlock": _NOT_APPLICABLE,
        "meaning": "an unguarded crash on arbitrary input, not a "
                   "deliberate rejection",
        "hint": "guard the input and raise the declared exception, or "
                "narrow the claim to the inputs the function accepts"},
}


# The numeric hierarchy over the code vocabulary: every code carries a
# stable "major.minor" id, majors being the structural groups
# (1 structural blockers, 2 loop, 3 branch, 4 unsupported), so a caller
# can fetch or filter whole groups ("2") or single codes ("2.23")
# without shipping the entire table. Same contract as the codes
# themselves: ADDITIVE ONLY, a new code appends the next minor in its
# group; an id, once released, is never renumbered or reassigned.
CODE_IDS: dict[str, str] = {
    "stateful": "1.1",
    "recursion": "1.2",
    "no-parameters": "1.3",
    "non-scalar-parameters": "1.4",
    "internal-error": "1.5",
    "loop:no-loop": "2.1",
    "loop:multiple-loops": "2.2",
    "loop:not-a-fold": "2.3",
    "loop:guarded-fold": "2.4",
    "loop:branch-elsewhere": "2.5",
    "loop:recursion": "2.6",
    "loop:wrong-sequence-param-count": "2.7",
    "loop:extra-statements": "2.8",
    "loop:non-simple-init": "2.9",
    "loop:non-simple-loop-header": "2.10",
    "loop:first-element-init-wrong-iteration": "2.11",
    "loop:partial-seq-init": "2.12",
    "loop:external-init-wrong-iteration": "2.13",
    "loop:unrecognized-loop-header": "2.14",
    "loop:multi-statement-loop-body": "2.15",
    "loop:non-simple-update": "2.16",
    "loop:no-return-value": "2.17",
    "loop:non-affine-update": "2.18",
    "loop:additive-constant-update": "2.19",
    "loop:tuple-in-expression": "2.20",
    "loop:unclassified": "2.21",
    "branch:needs-domain": "3.1",
    "branch:bare-local-name": "3.2",
    "branch:two-names-compare": "3.3",
    "branch:non-literal-compare": "3.4",
    "branch:untraceable-local": "3.5",
    "branch:opaque-expression": "3.6",
    "branch:no-parameter-dependence": "3.7",
    "branch:non-affine-essential": "3.8",
    "branch:non-affine-refinable": "3.9",
    "branch:unrecognized-shape": "3.10",
    "branch:composite": "3.11",
    "unsupported:unsupported-syntax": "4.1",
    "unsupported:unsupported-comprehension": "4.2",
    "unsupported:unsupported-lambda": "4.3",
    "unsupported:unsupported-call": "4.4",
    "unsupported:unsupported-attribute": "4.5",
    "unsupported:unbound-name": "4.6",
    "unsupported:ternary": "4.7",
    "unsupported:tuple-in-expression": "4.8",
    "unsupported:invalid-tuple-index": "4.9",
    "unsupported:array-index-mismatch": "4.10",
    "unsupported:non-numeric-constant": "4.11",
    "unsupported:unsupported-statement": "4.12",
    "unsupported:missing-return": "4.13",
    "implementation:overflow": "5.1",
    "implementation:recursion-depth": "5.2",
    "implementation:memory": "5.3",
    "implementation:nan": "5.4",
    "implementation:numerical-instability": "5.5",
    "implementation:sub-epsilon-boundary": "5.6",
    "implementation:representation": "5.7",
    "implementation:accidental-crash": "5.8",
}


CODE_GROUPS = {"1": "structural", "2": "loop", "3": "branch",
               "4": "unsupported", "5": "implementation"}
_GROUP_MAJORS = {v: k for k, v in CODE_GROUPS.items()}


def select_codes(query) -> dict:
    """The CODE_TABLE subset a query names: exact code names
    ("loop:non-affine-update"), numeric ids ("2.23"), whole groups by
    major ("2") or by name ("loop", "branch", "unsupported",
    "structural"), singly, or several as an iterable or a
    comma-separated string. Each returned entry carries its id.
    Unknown selectors are reported under "unknown" by the MCP tool;
    here they are simply absent from the result."""
    if isinstance(query, str):
        parts = [q.strip() for q in query.split(",") if q.strip()]
    else:
        parts = [str(q).strip() for q in query]
    by_id = {v: k for k, v in CODE_IDS.items()}
    out: dict = {}

    def _add(name):
        entry = describe_code(name)
        if entry is not None:
            out[name] = {"id": CODE_IDS.get(name), **entry}

    for q in parts:
        major = _GROUP_MAJORS.get(q, q if q in CODE_GROUPS else None)
        if major is not None:
            for name, cid in CODE_IDS.items():
                if cid.split(".", 1)[0] == major:
                    _add(name)
        elif q in by_id:
            _add(by_id[q])
        else:
            _add(q)
    return out


def split_code(code: "str | None") -> tuple:
    """Intent:
        A decorated compact code as its parts: (bare CODE_TABLE key,
        parameter list, +N count). `branch:needs-domain(a, b)+2` ->
        ("branch:needs-domain", ["a", "b"], 2). The compact payload's
        `blocker`/`blocker_params`/`blocker_more` columns are exactly
        these three, so the column is a real enum and no consumer
        parses decorations again.
    """
    if not code:
        return None, [], 0
    more = 0
    base = code
    if "+" in base:
        base, _plus, n = base.rpartition("+")
        try:
            more = int(n)
        except ValueError:
            base, more = code, 0
    params: list = []
    if "(" in base:
        base, _paren, inner = base.partition("(")
        params = [p.strip() for p in inner.rstrip(")").split(",")
                  if p.strip()]
    return base, params, more


def describe_code(code: str) -> dict | None:
    """The `CODE_TABLE` entry for one compact code, tolerant of the
    composed decorations `blocked_code()` adds: a parameter list
    (`branch:needs-domain(scale)`) and a `+N` multiplicity suffix are
    stripped before lookup. A `loop:<Category>` code (a loop whose own
    pieces hit an unsupported construct) falls back to the matching
    `unsupported:<Category>` entry. `None` for an unknown code."""
    base = code.split("(", 1)[0]
    if "+" in base:
        base = base.split("+", 1)[0]
    entry = CODE_TABLE.get(base)
    if entry is not None:
        return {"id": CODE_IDS.get(base), **entry}
    if base.startswith("loop:"):
        fallback = CODE_TABLE.get("unsupported:" + base[len("loop:"):])
        if fallback is not None:
            return {"id": CODE_IDS.get("unsupported:" + base[len("loop:"):]),
                    **fallback}
    return None


def claim_reason_code(probe) -> str | None:
    """`ClaimReasonCode` for a skipped or unknown `Probe`, read off whatever
    `check_conjectures()` already recorded for it, `meta` tags where
    they exist, the note text otherwise (not every skip site is
    meta-tagged today). `None` for any other verdict, or a skip this
    function doesn't recognize."""
    verdict_class = classify_verdict(probe.verdict)
    meta = probe.meta or {}
    if verdict_class == "holds" and meta.get("mathema.derive_status") in (
            "undecided", "unliftable"):
        # empirical evidence rescued a derive gap: real, but not proof;
        # the one non-skip verdict that carries a code, so coverage
        # tooling can count open proof gaps without parsing notes
        return ClaimReasonCode.DERIVE_GAP_EMPIRICAL
    if verdict_class == "falsified":
        # a falsification is not an ambiguous gap and normally carries
        # no code; a stratum that pins the failure on the
        # implementation is the exception, and its cause is the code
        stratum = meta.get("mathema.stratum") or {}
        cause = stratum.get("cause")
        if cause in CODE_TABLE:
            return cause
        return None
    if verdict_class not in ("skipped", "unknown"):
        return None
    premise = meta.get("mathema.premise")
    if premise in (ClaimReasonCode.MISSING_PREREQUISITE,
                   ClaimReasonCode.UNMET_PREREQUISITE,
                   ClaimReasonCode.AMBIGUOUS_PREREQUISITE,
                   ClaimReasonCode.DEPENDENCY_CYCLE):
        # the premise, not the claim, is what could not be settled
        return premise
    if "mathema.foreign_grammar" in meta:
        return ClaimReasonCode.FOREIGN_GRAMMAR
    if meta.get("mathema.probe_gap"):
        # the probe route could not evaluate the function at all,
        # input synthesis failed, or a parameter (a string, say) has no
        # domain to sample from
        return ClaimReasonCode.NO_EVALUABLE_INPUTS
    if meta.get("mathema.timeout"):
        return ClaimReasonCode.DERIVE_TIMEOUT
    if meta.get("mathema.derive_status") == "undecided":
        return ClaimReasonCode.DERIVE_UNDECIDED
    if meta.get("mathema.derive_status") == "unliftable":
        return ClaimReasonCode.DERIVE_UNLIFTABLE
    note = probe.note or ""
    if "does not yet lift multi-function or != claims" in note:
        return ClaimReasonCode.UNSUPPORTED_MULTI_FUNCTION
    if "unknown route" in note:
        return ClaimReasonCode.UNKNOWN_ROUTE
    if "unknown relation" in note:
        return ClaimReasonCode.UNKNOWN_RELATION
    if "unknown exception type" in note:
        return ClaimReasonCode.UNKNOWN_EXCEPTION_TYPE
    if "no evaluable inputs" in note:
        return ClaimReasonCode.NO_EVALUABLE_INPUTS
    if meta.get("mathema.invalid_conjecture"):
        # the statement never parsed/validated far enough to be
        # adjudicated at all, stamped in meta at the catch site, so
        # this never guesses from note prose (a record predating the
        # stamp simply reports no code here)
        return ClaimReasonCode.INVALID_CONJECTURE
    return None


def build_issue_record(fn, claims=None, *, include_source: bool = False,
                       include_falsified: bool = False,
                       root: str = ".") -> dict | None:
    """A real CDD spec record for `fn` (`spec.to_spec()`, the same
    shape `mathema.write_spec()` writes to `.mathema/verified/`), built by
    calling `mathema.check()` directly, `claims` passes straight
    through to it: omitted (`None`) defaults to
    `suggest_claims(fn)`'s own proposals; an explicit list
    checks exactly those; an explicit empty list (`claims=[]`) checks
    nothing at all (see `mathema.check()`'s own docstring for this same
    three-way distinction). Whichever applies, the resulting `claims`
    list carries real verdicts, sketches, routes, and domains from an
    actual adjudication, not a separate parallel shape.

    `None` if nothing about the result is worth reporting. A `skipped`
    or `unknown` claim is always worth reporting: blocked or undecided,
    either way mathema itself couldn't establish it, a real gap in
    its own evidence. A `falsified` claim is not
    a failure by itself (`evidence-ladder.md`: "falsified is not a bug
    report by itself... either the implementation is wrong or the claim
    was wrong, a discovery"), with no diagnose-and-accept workflow
    built yet (`cdd.md`'s loop, step 4; `verified-schema.md`'s
    `claims[].accepted` has no equivalent here), every falsification is
    permanently undiagnosed, so whether it counts is an explicit
    reporting choice, `include_falsified`:
    lenient (the default) treats it as a pending discovery, not
    reportable; `include_falsified=True` treats an undiagnosed falsification as
    something needing a look, the same posture `evidence-ladder.md`
    already documents for a `skipped` domain-enforcement claim.

    The diagnostic depth beyond the CDD record itself lives entirely
    under `meta`, `record-schema.md`'s own namespaced extension field:
    `meta["mathema.diagnostic_report"]` (`diagnostics.diagnostic_report()`'s
    own output, always present) and `meta["mathema.issue"]`
    (`failing_claims`, the names of whichever claims are pending per the
    rule above; there can be more than one, plus a `source` block
    when `include_source=True`, never partially: the raw text, the
    blocking line/column, and `inventory.scope_dependencies()`'s
    sibling-function/global names, all gated together since they're
    the same privacy class as the source text itself)."""
    import mathema
    from .analysis import SourceUnavailable, analyze_source
    from .diagnostics import diagnostic_report
    from .inventory import derivability_report, scope_dependencies
    from .spec import to_spec

    try:
        facts = analyze_source(fn)
    except SourceUnavailable:
        return None
    if facts.tree is None:
        return None

    record = mathema.check(fn, claims=claims)
    probes = record.probes

    diag = diagnostic_report(fn, facts)
    pending_verdicts = (("skipped", "unknown", "falsified")
                       if include_falsified else ("skipped", "unknown"))
    failing_claims = [p.name for p in probes
                     if classify_verdict(p.verdict) in pending_verdicts]

    if not failing_claims and diag["liftable"]:
        return None

    record.meta["mathema.diagnostic_report"] = diag
    issue_meta = {"failing_claims": failing_claims}
    if include_source:
        report = derivability_report(fn) or {}
        global_vars, global_funcs, unresolved = scope_dependencies(fn) or ([], [], [])
        issue_meta["source"] = {
            "text": facts.source,
            "line": report.get("line"),
            "column": None,
            "dependencies": {"global_vars": global_vars, "global_funcs": global_funcs,
                             "unresolved": unresolved},
        }
    record.meta["mathema.issue"] = issue_meta
    # an issue record is a diagnostic bundle, not the verified store:
    # suggested-claim outcomes are exactly what a reader triaging a
    # failure wants to see
    spec = to_spec(record, include_suggestions=True)
    # an issue file travels (it is built to be attached to a tracker),
    # so its paths are made portable exactly like the verified store's
    from .spec import _relativize_record_paths
    _relativize_record_paths(spec, root)
    return spec


def _default_confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def issue(fn, claims=None, *, include_source: bool = False,
          include_falsified: bool = False,
         root: str = ".", confirm=None) -> str | None:
    """Build an issue record for `fn` (`build_issue_record()`), print
    its exact JSON payload, then ask for explicit confirmation before
    writing it to `<root>/.mathema/issues/<key>-<timestamp>.json`.
    Returns the written path, or `None` if there's nothing to report
    or the write was declined.

    Never makes a network request; this only reads `fn`'s own source
    and writes a local file; there is no code path here that reaches
    the network at all. Source is included in the payload only for
    this one call, when `include_source=True` is passed explicitly; it
    is never remembered or defaulted on for a later call.
    `include_falsified` is the same reporting posture
    `build_issue_record()` documents
    for an undiagnosed `falsified` claim.

    `confirm`, when given, replaces the default `input()`-based y/n
    prompt with any `str -> bool` callable, so a caller can answer the
    confirmation programmatically."""
    import datetime
    import json
    import os

    from .authoring import _fn_key

    payload = build_issue_record(fn, claims, include_source=include_source,
                                 include_falsified=include_falsified,
                                 root=root)
    if payload is None:
        print(f"mathema issue: {getattr(fn, '__name__', fn)!r}, nothing to report")
        return None

    text = json.dumps(payload, indent=2, default=str)
    print(text)

    key = _fn_key(fn)
    timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    issues_dir = os.path.join(root, ".mathema", "issues")
    path = os.path.join(issues_dir, f"{key}-{timestamp}.json")

    ask = confirm or _default_confirm
    if not ask(f"Write this to {path}?"):
        print("mathema issue: not written")
        return None

    os.makedirs(issues_dir, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    print(f"mathema issue: wrote {path}")
    print("Attach this file to a new GitHub issue, drag it into the "
         "issue body, or use the failure-report issue template's own "
         "attachment field.")
    return path
