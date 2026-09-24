# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Facts about one function: is it pure enough that a claim is
realistically expected, does its docstring pass a checklist, is it
liftable for a derive-route proof, does it depend on state outside its
own parameters, is it exercised by the target's own tests (best-effort,
only if a coverage report already exists). Everything here answers a
question about a single function, standalone, e.g. `mathema.
docstring_report()` calls straight into `docstring_quality()` for just
one function, no sweep involved.

Distinct from `audit.py`, which sweeps a whole population by calling
these primitives across it and shapes the results into audit rows/
rollups; that's "found N functions, called is_pure_enough() on each,
built a table"; this module is what it's calling. Distinct too from
cli.py's per-function "claims X/Y adjudicated": that's the completeness
of ONE already-*declared* claim set, whereas this module (via audit.py)
surfaces functions with *zero* claims, which the declared/verified
store alone can never show."""
from __future__ import annotations

import ast
import inspect
import os
import re
from .analysis import quiet_facts
from .intent import _sections


def _self_use_blocks(tree, self_name: str) -> bool:
    """Does the method's use of `self_name` block a derive-route lift?
    A plain FIELD READ (`self.rate`) and a direct sibling-method call
    (`self.helper(x)`) are the read-only instance vocabulary the lift
    understands, so they do not block. Everything else does: writing a
    field (`self.x = 1`, `self.x += 1`), reaching THROUGH an attribute
    (`self._rng.shuffle(...)`; a two-level chain whose far end may
    mutate), subscripting self, passing self to another callable
    (`helper(self)`), returning it, comparing it; any use where self
    escapes the field-read/sibling-call vocabulary. `cls` keeps the
    old, fully conservative rule (any use blocks): a classmethod's
    `cls()` is legitimately stateful in ways this analysis does not
    attempt to trace."""
    parents: dict = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Name) and node.id == self_name):
            continue
        if self_name == "cls":
            return True
        parent = parents.get(id(node))
        if not isinstance(parent, ast.Attribute):
            return True   # bare self escaping (call arg, return, ...)
        if not isinstance(parent.ctx, ast.Load):
            return True   # self.x = ... / del self.x
        grand = parents.get(id(parent))
        if isinstance(grand, (ast.Attribute, ast.Subscript)):
            return True   # self.attr.deeper / self.attr[...]
        if isinstance(grand, (ast.AugAssign,)) and grand.target is parent:
            return True
    return False


def is_pure_enough(fn) -> bool | None:
    """A purity proxy, not a judgment about claim-worthiness on its
    own: reuses symbolic.py's own derive-route liftability check
    (loop-free, branch-free, non-recursive, scalar parameters, and;
    for a method; read-only over `self`: field reads and sibling
    calls derive; writes or escapes of `self` do not). `None` means mathema couldn't even retrieve the
    source, not a verdict either way, e.g. a function from a C
    extension or built dynamically."""
    from .symbolic import lift, lift_dot, lift_fold, lift_sum

    facts = quiet_facts(fn)
    if facts is None:
        return None
    if facts.params and facts.params[0] in ("self", "cls") \
            and _self_use_blocks(facts.tree, facts.params[0]):
        return False
    try:
        # lift_fold()/lift_dot()/lift_sum(), not just lift(): a
        # recognized linear-fold loop, dot-product, or general-sum
        # loop shape is liftable standalone, the same way lift() is,
        # unlike lift_conditioned()'s branch pruning, none of
        # them need a per-claim domain, so all belong in this
        # domain-free summary too.
        return (lift(fn, facts) is not None or lift_fold(fn, facts) is not None
               or lift_dot(fn, facts) is not None or lift_sum(fn, facts) is not None)
    except Exception:
        return None


def typing_info(fn) -> dict:
    """How much of the signature actually carries type hints, params
    annotated vs total, and whether the return type is. A cheap signal
    on its own (an untyped parameter is exactly where mathema has least
    to go on inferring anything), and the prerequisite for a richer one:
    a bare `str` parameter carries none of a proper `Literal[...]`/
    `Enum` hint's finite-value information. `finite_domains` is
    populated whenever a parameter's own type hint already states its
    entire meaningful value set, exactly the shape `lift_conditioned()`'s
    branch pruning needs, read directly from the signature rather than
    requiring a claim to redeclare it."""
    import inspect

    from .analysis import finite_annotation_domains

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {"params_typed": 0, "params_total": 0, "return_typed": None,
                "finite_domains": {}}
    params = list(sig.parameters.values())
    typed = sum(1 for p in params
                if p.annotation is not inspect.Parameter.empty)
    finite_domains = finite_annotation_domains(fn)
    return_typed = sig.return_annotation is not inspect.Signature.empty
    return {"params_typed": typed, "params_total": len(params),
            "return_typed": return_typed, "finite_domains": finite_domains}


def wrapped_target(fn) -> str | None:
    """Is this function's body exactly one statement; `return
    <call>(...)`, a thin pass-through with no real computation of its
    own (a docstring beforehand doesn't disqualify it, same convention
    lift() already uses)? If so, a best-effort name for what it calls:
    `module.qualname` when the callable can be resolved (a bare-name
    call resolved against fn's own globals, or an attribute call
    resolved against whatever object its root name is bound to,
    `np.sqrt` resolves through the real `np` module object, not by
    guessing), else just the name as written (`self.helper`, `foo`)
    when it can't be. `None` if the body isn't exactly this shape."""


    facts = quiet_facts(fn)
    if facts is None:
        return None
    if facts.tree is None:
        return None
    body = facts.tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
        return None
    call = body[0].value
    if not isinstance(call, ast.Call):
        return None

    g = getattr(fn, "__globals__", {})

    def resolved_name(obj, fallback: str) -> str:
        mod = getattr(obj, "__module__", None)
        qn = getattr(obj, "__qualname__", None)
        return f"{mod}.{qn}" if mod and qn else fallback

    if isinstance(call.func, ast.Name):
        name = call.func.id
        return resolved_name(g[name], name) if name in g else name
    if isinstance(call.func, ast.Attribute):
        attr, base = call.func.attr, call.func.value
        if isinstance(base, ast.Name) and base.id in ("self", "cls"):
            return f"{base.id}.{attr}"   # not resolvable without an instance/class
        if isinstance(base, ast.Name) and base.id in g:
            target = getattr(g[base.id], attr, None)
            if target is not None:
                return resolved_name(target, attr)
        return attr
    return None


# Google/Napoleon-style headers (colon-terminated, no underline) recognized
# alongside intent.py's own numpydoc dash-underlined _sections(), real
# code uses either convention, and a docstring quality check that only
# understood one would misreport every function written in the other.
_DOC_HEADER_GOOGLE = re.compile(
    r"^\s*(Args|Arguments|Parameters|Returns|Yields|Raises|Examples?):\s*$", re.M)


def _raised_exception_names(tree: ast.AST) -> list[str]:
    """Every distinct exception type name a `raise <expr>` statement
    names in this tree, in the order first encountered, `raise
    ValueError(...)` and `raise mod.MyError(...)` both resolve to the
    exception class's own name (`ValueError`, `MyError`), not any
    module/instance prefix. A bare `raise` (re-raise) or a raised
    expression that isn't a name/attribute/call of one (a variable
    holding an exception instance, say) contributes nothing; there's
    no literal type name to look for in the docstring."""
    seen: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        expr = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if isinstance(expr, ast.Name):
            name = expr.id
        elif isinstance(expr, ast.Attribute):
            name = expr.attr
        else:
            continue
        if name not in seen:
            seen.append(name)
    return seen


def docstring_quality(fn) -> dict:
    """A best-practice checklist, not a style grade, has a docstring at
    all, has a real summary (non-empty text before the first recognized
    section header, either convention), documents its parameters (each
    real parameter's name found literally somewhere in the docstring,
    a presence heuristic, not true cross-referencing), documents what it
    returns (only applicable if it actually returns something,
    analyze_source()'s own returns_kind, so a function returning None is
    never penalized for not documenting a return value it doesn't have),
    documents raising (only applicable if the body actually raises at
    least one exception with a resolvable type name; see
    `_raised_exception_names()`; passing requires both a Raises/
    Exceptions section AND every one of those exception names mentioned
    in it by name, not just the section existing). `score`/`applicable`
    let a caller compute "N/M" without redefining what counts,
    `applicable` shrinks when a criterion genuinely doesn't apply (no
    params, no raise, no return value), rather than counting it as a
    failure."""


    facts = quiet_facts(fn)
    if facts is None:
        # no facts.docstring to fall back on, best-effort raw
        # __doc__, which is unindented for a top-level function
        # anyway (indentation only matters for a method/nested
        # function's docstring, exactly the case source access just
        # failed for)
        doc = getattr(fn, "__doc__", None) or ""
        has_doc = bool(doc.strip())
        has_summary = has_doc and bool(_DOC_HEADER_GOOGLE.split(doc)[0].strip())
        return {"has_docstring": has_doc, "has_summary": has_summary,
                "params_documented": None, "params_total": None,
                "documents_return": None, "documents_raises": None,
                "raises_documented": None, "raises_total": None,
                "score": int(has_doc) + int(has_summary),
                "applicable": 1 + int(has_doc)}

    # facts.docstring is ast.get_docstring()'s output, dedented
    # consistently regardless of the function's own source indentation,
    # unlike raw fn.__doc__. _sections()'s numpydoc header regex requires
    # exactly that (`^Parameters` at column 0), so raw __doc__ on an
    # indented method's docstring would silently never match a single
    # section, even a real one.
    doc = facts.docstring or ""
    has_doc = bool(doc.strip())
    lead_text = _DOC_HEADER_GOOGLE.split(doc)[0]
    numpy_sections = set(_sections(doc))
    if numpy_sections:
        # _sections() already strips everything from the first numpydoc
        # header onward out of its own accounting; mirror that here too
        first_numpy_header = re.search(r"^(\w[\w ]*)\n\s*-{3,}\s*$", doc, re.M)
        if first_numpy_header and first_numpy_header.start() < len(lead_text):
            lead_text = doc[:first_numpy_header.start()]
    has_summary = has_doc and bool(lead_text.strip())

    google_headers = {m.group(1) for m in _DOC_HEADER_GOOGLE.finditer(doc)}

    def has_section(*names):
        return (any(n.lower() in numpy_sections for n in names)
               or any(n in google_headers for n in names))

    result: dict[str, object] = {
        "has_docstring": has_doc, "has_summary": has_summary,
        "params_documented": None, "params_total": None,
        "documents_return": None, "documents_raises": None,
        "raises_documented": None, "raises_total": None,
    }
    score, applicable = int(has_doc), 1
    if has_doc:
        score += int(has_summary)
        applicable += 1

    # Scored per parameter/exception, not as one all-or-nothing point,
    # a function with 3 params and 2 documented is 2/3 of the way there,
    # not the same 0/1 as a function with none documented at all; the
    # overall score/applicable should reflect that granularity, the same
    # granularity params_documented/params_total and raises_documented/
    # raises_total already report individually.
    real_params = [p for p in facts.params if p not in ("self", "cls")]
    documented = sum(1 for p in real_params if re.search(rf"\b{re.escape(p)}\b", doc))
    result["params_documented"], result["params_total"] = documented, len(real_params)
    if real_params:
        score += documented
        applicable += len(real_params)

    raised = _raised_exception_names(facts.tree) if facts.tree is not None else []
    if raised:
        raises_doc = has_section("Raises", "Exceptions")
        mentioned = sum(1 for name in raised if re.search(rf"\b{re.escape(name)}\b", doc))
        result["raises_documented"], result["raises_total"] = mentioned, len(raised)
        result["documents_raises"] = raises_doc and mentioned == len(raised)
        score += mentioned
        applicable += len(raised)

    returns_something = facts.returns_kind not in ("none", "unknown")
    if returns_something:
        documents_return = has_section("Returns", "Yields")
        result["documents_return"] = documents_return
        score += int(documents_return)
        applicable += 1

    # Not scored alongside the prose checks above; this is mathema's
    # own claim-authoring surface (authoring.py's "Claims:" docstring
    # block), checked with its own real parser rather than a presence
    # regex, so it can catch a real, easy-to-hit authoring mistake: a
    # claim line missing its `name:` prefix parses to zero claims
    # silently, so a Claims: header can be present with nothing valid
    # actually parsed out of it; a prose-based heuristic could never
    # see that gap.
    from .authoring import parse_docstring_claims

    has_claims_header = bool(re.search(r"^\s*claims:\s*$", doc, re.I | re.M))
    claims_parsed = len(parse_docstring_claims(doc)) if has_claims_header else 0
    result["has_claims_block"] = has_claims_header
    result["claims_parsed"] = claims_parsed if has_claims_header else None

    result.update(score=score, applicable=applicable)
    return result


def docs_checklist(q: dict) -> list[str]:
    """`docstring_quality()`'s result as checkbox-style lines (✓/✗, `·`
    for informational-only); one shared renderer so
    `mathema.DocstringReport.__repr__` and `mathema audit --docs-only`
    can't drift apart on what a checkmark means. No leading indentation;
    callers indent as their own context needs."""
    def mark(ok):
        return "✓" if ok else ("·" if ok is None else "✗")

    lines = [f"{mark(q['has_docstring'])} has a docstring"]
    if q["has_docstring"]:
        lines.append(f"{mark(q['has_summary'])} has a summary")
    if q["params_total"]:
        lines.append(f"{mark(q['params_documented'] == q['params_total'])} "
                     f"params documented ({q['params_documented']}/{q['params_total']})")
    if q["documents_return"] is not None:
        lines.append(f"{mark(q['documents_return'])} documents its return value")
    if q["raises_total"]:
        lines.append(f"{mark(q['documents_raises'])} exceptions documented "
                     f"({q['raises_documented']}/{q['raises_total']})")
    if q.get("has_claims_block"):
        lines.append(f"· Claims: block present ({q['claims_parsed']} parsed)")
    return lines


_NESTED_LOOP_PENALTY = 2   # extra cyclomatic points per level of loop nesting


def structural_complexity(fn) -> dict | None:
    """Loop/branch/recursive-call counts, plus a complexity number in the
    spirit of cyclomatic complexity (decision points + 1: one per
    branch, one per loop) but with a heavier, depth-scaled charge for
    *nested* loops, the standard McCabe formula charges a flat point
    per loop regardless of nesting, which understates the real cost: a
    loop two levels deep is harder to reason about than one four levels
    wide and flat, and a loop three or four levels deep is a different
    order of difficulty again, not just "one more of the same thing."
    Each loop pays `_NESTED_LOOP_PENALTY` points per level of nesting it
    sits at (`LoopFact.depth`), so depth 1 costs 2 extra, depth 2 costs
    4 extra, depth 3 costs 6 extra, and so on; deeper nesting is
    charged more, not the same, each additional level down. `loops` is
    the total loop count including nested ones; `nested_loops` is the
    subset of `loops` that sit inside another loop's body (depth > 0).
    `recursive_calls` counts self-call *sites* in the function's own
    body, not recursion depth or mutual recursion across multiple
    functions; true call-graph cycle detection across a codebase is a
    different, bigger feature, not attempted here. `None` if source
    wasn't available."""
    import ast


    facts = quiet_facts(fn)
    if facts is None:
        return None
    if facts.tree is None:
        return None
    recursive_calls = sum(
        1 for node in ast.walk(facts.tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == facts.name)
    branches, loops = facts.branch_count, len(facts.loops)
    nested_loops = sum(1 for loop in facts.loops if loop.depth > 0)
    nesting_penalty = _NESTED_LOOP_PENALTY * sum(loop.depth for loop in facts.loops)
    return {
        "branches": branches, "loops": loops, "nested_loops": nested_loops,
        "recursive_calls": recursive_calls,
        "cyclomatic": 1 + branches + loops + nesting_penalty,
    }


def claim_floor(fn, facts=None) -> dict | None:
    """Intent:
        The least this function's shape gives you to state: one claim
        per relevant claim family, per target. `{"floor": int,
        "aspects": [[aspect, target], ...]}`, or None when the source
        cannot be retrieved.

    Notes:
        A floor, never a ceiling, a function carrying more claims
        than this is not over its budget, and nothing here divides by
        it. How many claims a function of this shape typically carries
        is a different question, answered by a corpus, not by
        structure.

        Claims answering the same question about the same target count
        once (`convex[x]`/`concave[x]`/`affine[x]` are one aspect,
        see `families.CLAIM_ASPECTS`), while every member of a keyword
        group counts separately, since `stateless` expanding to three
        claims is three separate things to say.

        Deliberately independent of whether the function lifts. Most
        families offer a probe route, so an unliftable function still
        has a floor, a smaller one, because the derive-only families
        drop out on their own structural gates.
    """
    from .families import claim_aspect
    from .suggest import suggest_claims

    if facts is None:
        facts = quiet_facts(fn)
    if facts is None or facts.tree is None:
        return None
    aspects = sorted({claim_aspect(cj.name)
                      for cj in suggest_claims(fn, facts)})
    return {"floor": len(aspects),
            "aspects": [list(pair) for pair in aspects]}


def purity_reason(fn) -> str | None:
    """Why is_pure_enough() said no; `None` means it's liftable (or
    source wasn't available, same as is_pure_enough()'s own `None`).
    Mirrors lift()'s own gate conditions exactly (same `facts` fields,
    same order), so the reason reported here is always consistent with
    what lift() actually did, not a separate guess at why.

    Purity here is specifically "liftable for a *derive-route* proof";
    it says nothing about whether a *probe-route* claim is viable. Probe
    doesn't lift anything; it calls the real function on sampled inputs,
    so branches, loops, and non-numeric parameters are no obstacle to it
    at all. A function reported not-pure here can still be claimed about
    perfectly well on the probe route; this only ever narrows which
    functions can additionally get proof-strength (derive-route)
    evidence, not which functions can be claimed about at all."""
    from .symbolic import lift, lift_dot, lift_fold, lift_sum

    facts = quiet_facts(fn)
    if facts is None:
        return None
    if facts.tree is None:
        return None
    if facts.params and facts.params[0] in ("self", "cls") \
            and _self_use_blocks(facts.tree, facts.params[0]):
        return f"stateful: updates {facts.params[0]} internally"
    if facts.loops and not facts.branch_count \
            and (lift_fold(fn, facts) is not None or lift_sum(fn, facts) is not None):
        return None
    if facts.loops or facts.branch_count:
        complexity = structural_complexity(fn)
        parts = []
        if complexity["branches"]:
            parts.append(f"{complexity['branches']} branch"
                         + ("es" if complexity['branches'] > 1 else ""))
        if complexity["loops"]:
            loop_part = (f"{complexity['loops']} loop"
                         + ("s" if complexity['loops'] > 1 else ""))
            if complexity["nested_loops"]:
                loop_part += f" ({complexity['nested_loops']} nested)"
            parts.append(loop_part)
        return ", ".join(parts)
    if facts.recursion:
        n = structural_complexity(fn)["recursive_calls"]
        return f"recursive ({n} call site{'s' if n != 1 else ''})"
    if not facts.params:
        return "no parameters"
    non_scalar = [p for p, k in facts.param_kinds.items() if k == "sequence"]
    if non_scalar:
        if lift_dot(fn, facts) is not None:
            return None
        return f"non-scalar parameter(s): {', '.join(non_scalar)}"
    try:
        lifted = lift(fn, facts)
    except Exception:
        return "uses unsupported expression syntax"
    if lifted is None:
        return "uses unsupported expression syntax"
    return None


def derivability_report(fn) -> dict | None:
    """Deep-dive diagnosis of *why* a function isn't derivable
    (`mathema audit --deriv-report`), unlike purity_reason()'s single
    summary string, this locates the exact blocking construct (source
    line and a stable, versioned `"category"` code) for an
    unsupported-syntax failure, and for a branch, classifies *each*
    branch's condition individually as either resolvable (naming which
    parameters a claim would need to declare a domain for) or
    structurally blocked (naming why), see _explain_branch().

    purity_reason()'s single generic "uses unsupported expression
    syntax" bucket only reports *that* lifting failed, not *where*:
    it swallows the actual NotSymbolic message and source location. A
    function can fail to lift for a reason several statements away from
    where the failure is easiest to guess at (a tuple return further
    down the body, say, when the real blocker is an earlier ternary);
    this function surfaces the precise statement and category instead
    of requiring that tracing to be done by hand.

    Deliberately raw: every field here is a mechanical fact about the
    function's own source (which construct, which line, which stable
    category name from `symbolic.NotSymbolic`'s fixed vocabulary),
    never an editorial verdict about whether it's worth fixing. A
    caller wanting that judgment call layers it on top of this report,
    not the other way around.

    `None` if the source isn't available at all (same convention as
    purity_reason()/is_pure_enough()). Otherwise a dict with at least
    `"liftable"` (`True` means this function shouldn't have been asked
    about at all; callers should only reach for this on rows where
    `pure is False`) and, when not liftable, a stable `"blocker"` name
    plus blocker-specific raw detail; `"branches"` (a list of
    `{"line", "condition", "kind", ...}`, one per `ast.If` anywhere in
    the body) for the branch case specifically, since a function can
    have several independent branches with different fates."""
    from .symbolic import (_LiftCtx, _affine_locals, _bind_params, _explain_branch,
                           strip_docstring, _unmodified_params, _walk_lift_body,
                           diagnose_fold, lift_dot, lift_fold, lift_sum)
    from .finite_sets import OpaqueRegistry

    facts = quiet_facts(fn)
    if facts is None:
        return None
    if facts.tree is None:
        return None

    if facts.params and facts.params[0] in ("self", "cls") \
            and _self_use_blocks(facts.tree, facts.params[0]):
        return {"liftable": False, "blocker": "stateful", "param": facts.params[0],
               "line": facts.tree.lineno}
    if facts.loops:
        if lift_fold(fn, facts) is not None or lift_sum(fn, facts) is not None:
            return {"liftable": True}
        diagnosis = diagnose_fold(fn, facts)
        first_loop = next((node for node in ast.walk(facts.tree)
                          if isinstance(node, (ast.For, ast.While))), facts.tree)
        if diagnosis is None:
            # every structural check in diagnose_fold passed but
            # lift_fold() still declined, shouldn't happen if the two
            # are kept in sync; report honestly rather than claim a
            # specific reason that isn't real.
            return {"liftable": False, "blocker": "loop", "reason": "unclassified",
                   "line": first_loop.lineno}
        return {"liftable": False, "blocker": "loop", "reason": diagnosis["reason"],
               "hint": diagnosis.get("hint"), "derive_unlock": diagnosis.get("derive_unlock"),
               "line": first_loop.lineno}
    if facts.branch_count:
        body = strip_docstring(facts.tree.body)
        unmodified = _unmodified_params(facts.tree, set(facts.params))
        bound_params, _aggregate = _bind_params(fn, facts)
        affine_locals = _affine_locals(facts.tree, unmodified, bound_params)
        branches = [
            {"line": node.lineno, "condition": ast.unparse(node.test),
             **_explain_branch(node.test, unmodified, affine_locals, bound_params)}
            for node in ast.walk(facts.tree) if isinstance(node, ast.If)
        ]
        return {"liftable": False, "blocker": "branch", "branches": branches,
               "line": branches[0]["line"]}
    if facts.recursion:
        n = structural_complexity(fn)["recursive_calls"]
        first_call = next(node for node in ast.walk(facts.tree)
                         if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                         and node.func.id == facts.name)
        return {"liftable": False, "blocker": "recursion", "recursive_calls": n,
               "line": first_call.lineno}
    if not facts.params:
        return {"liftable": False, "blocker": "no-parameters", "line": facts.tree.lineno}
    non_scalar = [p for p, k in facts.param_kinds.items() if k == "sequence"]
    if non_scalar:
        if lift_dot(fn, facts) is not None:
            return {"liftable": True}
        return {"liftable": False, "blocker": "non-scalar-parameters",
               "params": non_scalar, "line": facts.tree.lineno}

    params, _aggregate2 = _bind_params(fn, facts)
    env = dict(params)
    from .symbolic._normalize import normalized_body
    body = normalized_body(fn, facts)
    # a real ctx/opaque, not the bare `_walk_lift_body(body, env)`
    # this used before, so this retrace recognizes exactly what
    # lift() itself would (callee inlining, opaque values, local
    # symbolic arrays from np.linspace/np.arange): otherwise a
    # function lift() already handles could still be diagnosed here
    # against a *stricter* retrace than what actually ran, reporting
    # a blocker that isn't real. Only reached for a row already
    # known not to lift (see this function's own docstring), so
    # this never contradicts is_pure_enough()/purity_reason().
    from .symbolic._base import _method_ctx_fields
    _sp, _sc = _method_ctx_fields(fn, facts)
    ctx = _LiftCtx(globals_ns=getattr(fn, "__globals__", {}), depth=3,
                   seen=frozenset({id(fn)}), domain={},
                   unmodified=frozenset(_unmodified_params(facts.tree, set(facts.params))),
                   self_param=_sp, self_class=_sc)
    try:
        kind, _result, failure = _walk_lift_body(body, env, ctx, allow_raise=False,
                                                  opaque=OpaqueRegistry())
    except Exception as e:
        return {"liftable": False, "blocker": "internal-error", "message": str(e),
               "line": facts.tree.lineno}
    if kind == "value":
        return {"liftable": True}
    return {"liftable": False, "blocker": "unsupported-construct",
           "line": failure["line"], "statement": failure["statement"],
           "message": failure["message"], "category": failure["category"]}


def scope_dependencies(fn) -> tuple[list[str], list[str], list[str]] | None:
    """`(global_vars, global_funcs, unresolved)`, names a function
    reads that aren't its own parameters/locals, split by what kind of
    dependency they actually are: `global_vars` are a genuine global
    *variable* dependency (real, if hidden, state, a claim about this
    function is only as reliable as that global's current value);
    `global_funcs` are an ordinary reference to a sibling function/
    class/module (normal code structure, not a state dependency at all,
    a different error surface from `global_vars`, not the same one);
    `unresolved` have no binding mathema can find at all (likely a real
    bug, or a name only defined at call time). `None` if source wasn't
    retrievable. This is exactly what analyze_source() already warns
    about on every call, surfaced here as data instead of text, since
    a population sweep wants one row per function, not one interleaved
    warning per function."""


    facts = quiet_facts(fn)
    if facts is None:
        return None
    return facts.global_vars, facts.global_funcs, facts.unresolved


def mutated_globals(fn) -> list[str] | None:
    """Intent:
        Module-level names this function *writes through*, `CACHE[k] = v`,
        `CONFIG.field = x`, rather than merely reads. `None` if the
        source wasn't retrievable.

    Notes:
        Deliberately separate from `scope_dependencies`' `global_vars`,
        which reports names a function *depends on*. Writing is the
        stronger relationship: it makes this function the reason some
        other caller's answer changed. A name appears here and not in
        `global_vars` when the function only ever writes it.
    """
    facts = quiet_facts(fn)
    if facts is None:
        return None
    return facts.mutated_globals


def read_test_coverage(root: str = ".") -> dict[str, set[int]] | None:
    """Best-effort executed-line-numbers-per-file, from an *existing*
    coverage.py report; this never runs the target's tests itself.
    Tries `coverage.json` (coverage.py's own `coverage json` export)
    first, since that needs no import of the `coverage` package at all;
    falls back to a native `.coverage` data file if `coverage` happens
    to be importable. `None` (not `{}`) if neither is available or
    readable; callers must treat that as "unknown", not "nothing was
    covered"."""
    json_path = os.path.join(root, "coverage.json")
    if os.path.exists(json_path):
        import json
        with open(json_path) as fh:
            data = json.load(fh)
        return {os.path.abspath(os.path.join(root, f)): set(info.get("executed_lines", []))
                for f, info in data.get("files", {}).items()}
    cov_path = os.path.join(root, ".coverage")
    if os.path.exists(cov_path):
        try:
            import coverage
        except ImportError:
            return None
        cov = coverage.Coverage(data_file=cov_path)
        try:
            cov.load()
        except Exception:
            return None
        out = {}
        for f in cov.get_data().measured_files():
            try:
                # analysis2() is a 5-tuple (file, statements, excluded,
                # missing, readable); the lines actually RUN are the
                # statements minus the ones missing from execution, the
                # same `executed_lines` sense the JSON path above reads.
                _, statements, _, missing, _ = cov.analysis2(f)
            except Exception:
                continue
            out[os.path.abspath(f)] = set(statements) - set(missing)
        return out
    return None


def suggest_coverage_command(root: str = ".") -> str | None:
    """Best-effort: does this project look like it uses pytest? If so,
    the command that would produce the coverage.json report
    read_test_coverage() already knows how to read, never runs it,
    only detects whether suggesting it makes sense. `None` if nothing
    pytest-shaped is found, no guess is better than a wrong one for a
    project that uses something else entirely. The export runs whatever
    the test run's exit status: a failing test still leaves the lines
    every other test executed.

    Uses `python -m coverage`/`python -m pytest`, not the bare `coverage`/
    `pytest` console scripts; those aren't guaranteed to be on PATH even
    when the packages themselves are installed. Checks whether `coverage`
    is actually importable in *this* process first (mathema is expected
    to run in the same venv as the target project, per the walkthrough)
    and prepends an install step if not, a suggested command that
    fails with "command not found" is worse than no suggestion."""
    import importlib.util

    pytest_shaped = (
        os.path.isdir(os.path.join(root, "tests"))
        or os.path.isdir(os.path.join(root, "test")))
    if not pytest_shaped:
        for cfg in ("pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini"):
            path = os.path.join(root, cfg)
            if not os.path.exists(path):
                continue
            try:
                content = open(path).read()
            except OSError:
                continue
            if "pytest" in content:
                pytest_shaped = True
                break
    if not pytest_shaped:
        return None
    cmd = "python -m coverage run -m pytest; python -m coverage json"
    if importlib.util.find_spec("coverage") is None:
        cmd = "pip install coverage && " + cmd
    return cmd


def is_test_covered(fn, coverage_data: dict[str, set[int]] | None) -> bool | None:
    """`None` means unknown (no coverage report found, or this
    function's file wasn't in it), never conflate that with False."""
    if coverage_data is None:
        return None
    try:
        src_file = inspect.getsourcefile(fn)
        lines, start = inspect.getsourcelines(fn)
    except (TypeError, OSError):
        return None
    if src_file is None:
        return None
    executed = coverage_data.get(os.path.abspath(src_file))
    if executed is None:
        return None
    end = start + len(lines) - 1
    return any(start <= ln <= end for ln in executed)



def function_dependencies(fn, facts=None) -> list[dict]:
    """One-deep dependency records for the verified spec: every callee
    this function references (sibling functions, classes, modules,
    `Facts.global_funcs`' names resolved against the function's own
    globals) plus every signature parameter annotated as a callable,
    each with its dotted key, source file and line (so an agent goes
    straight there, never grepping), and, for a plain function; its
    current `form` hash, which is what freshness checks compare against
    the callee's own verified record. One level deep is enough by
    design: freshness composes, an unchanged callee form means that
    callee's own claims still stand."""
    facts = facts if facts is not None else quiet_facts(fn)
    if facts is None:
        return []
    g = getattr(fn, "__globals__", {}) or {}
    out: list[dict] = []
    # a module-level numeric constant the lift may inline is a real
    # dependency: its exact value rides the record, and the freshness
    # sweep re-adjudicates when it changes (a stale inlined value must
    # never keep a proof alive)
    for name in sorted(set(facts.global_vars)):
        value = g.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.append({"name": name, "kind": "constant", "value": value})
    for name in sorted(set(facts.global_funcs)):
        obj = g.get(name)
        if obj is None:
            continue
        if inspect.isfunction(obj):
            kind = "function"
        elif inspect.isclass(obj):
            kind = "class"
        elif inspect.ismodule(obj):
            kind = "module"
        else:
            kind = "object"
        dep: dict = {"name": name, "kind": kind}
        mod = getattr(obj, "__module__", None)
        qual = getattr(obj, "__qualname__", None)
        if kind == "module":
            dep["key"] = getattr(obj, "__name__", name)
        elif mod and qual:
            dep["key"] = f"{mod}.{qual}"
        try:
            src = inspect.getsourcefile(obj)
            if src:
                dep["file"] = src
        except TypeError:
            pass
        line = getattr(getattr(obj, "__code__", None), "co_firstlineno", None)
        if line is None and kind == "class":
            try:
                line = inspect.getsourcelines(obj)[1]
            except (OSError, TypeError):
                line = None
        if line is not None:
            dep["line"] = line
        if kind == "function":
            callee_facts = quiet_facts(obj)
            if callee_facts is not None:
                dep["form"] = callee_facts.form
        out.append(dep)
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return out
    import collections.abc
    import typing as t
    for p in sig.parameters.values():
        ann = p.annotation
        if ann is inspect.Parameter.empty:
            continue
        origin = t.get_origin(ann)
        if ann in (collections.abc.Callable, t.Callable) \
                or origin in (collections.abc.Callable,):
            # a callable handed in at call time: a real dependency with
            # no resolvable identity until runtime, listed so the
            # dependency surface is complete, never given a form.
            out.append({"name": p.name, "kind": "signature-callable"})
    return out


_BLOCKER_HELP = {
    # one plain sentence per blocker: the simple public help line. The
    # full diagnostic depth (branch-by-branch fates, exact statements)
    # stays in derivability_report()/--deriv-report.
    "stateful": "the method modifies instance state (or self escapes "
                "beyond field reads and sibling calls)",
    "loop": "the loop doesn't match a recognized fold/sum/dot shape",
    "branch": "a branch couldn't be resolved from the declared domain",
    "recursion": "recursive calls can't be lifted",
    "no-parameters": "the function takes no parameters, so there's nothing to quantify over",
    "non-scalar-parameters": "a parameter isn't a scalar (or recognized sequence) of reals",
    "internal-error": "the lifter itself hit an internal error",
    "unsupported-construct": "an expression form the derive vocabulary doesn't cover yet",
}


def unliftable_summary(fn) -> str | None:
    """One short line for an unliftable function: the stable blocker
    code from `derivability_report()`, its most specific detail, the
    source line, and a plain-language help sentence. Deliberately
    called the LIKELY reason, the report names the first blocking
    construct found, and the root cause can sit deeper (a category
    like unsupported-call may itself be a symptom); the full
    branch-by-branch diagnostic stays in `mathema audit --deriv-report`.
    `None` when the function is liftable or the source is unavailable
    (nothing useful to say)."""
    report = derivability_report(fn)
    if not report or report.get("liftable"):
        return None
    blocker = report.get("blocker") or "unsupported-construct"
    detail = ""
    if blocker == "loop" and report.get("reason") not in (None, "unclassified"):
        detail = f": {report['reason']}"
    elif blocker == "unsupported-construct" and report.get("category"):
        detail = f": {report['category']}"
    elif blocker == "branch":
        blocked = [b for b in report.get("branches") or []
                  if b.get("kind") not in (None, "resolvable")]
        if blocked and blocked[0].get("condition"):
            detail = f": if {blocked[0]['condition']}"
    line = f" (line {report['line']})" if report.get("line") else ""
    help_line = _BLOCKER_HELP.get(blocker, "")
    return (f"likely reason: {blocker}{detail}{line}"
            + (f", {help_line}" if help_line else ""))
