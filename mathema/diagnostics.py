# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Structural diagnostics for one function: the derivability error
code and its blocking constructs, the domain hazards, and the motif
facets that sit alongside them. This module answers questions about
*one* function; anything that compares or matches functions against
each other is out of scope by design, here and in core generally.

Motif detection (`has_clamp`, `has_accumulator_fold`, ...) answers
"does this function contain a specific, named structural pattern", a
containment question, deliberately answered by explicit, legible
checks rather than a similarity score: "this function contains a clamp
on the return path" is a claim a user can check directly, and a tool
whose whole product is legible evidence shouldn't ship the other kind
of explanation.

Every payload carries its own `diagnostic_scheme` plus
`sympy_version`/`mathema_version`, since sympy's own canonical
`Add`/`Mul` ordering and auto-simplification can change between
releases: a consumer comparing two records needs to know whether they
are directly comparable at all.
"""
from __future__ import annotations

import ast

import sympy

from ._math_vocab import _call_name
from .symbolic import classify_loop_header

DIAGNOSTIC_SCHEME = 3
# diagnostic_report()'s own field-layout version. Bump it whenever
# that layout changes; a consumer comparing two records needs to
# know when they are not directly comparable. Scheme 3 dropped the
# fingerprint fields: similarity is not core's concern.


# --- motif library: containment, not similarity, and always AST-based ------
#
# Every motif below scans the raw AST (`facts.tree`) directly, rather
# than a lifted sympy expression, deliberately, for two reasons: a
# sympy tree carries no source-location information at all, so a
# motif's own file/line couldn't come from that layer even in
# principle; and a syntactic pattern (a clamp call, a fold-shaped loop
# header) is real, checkable signal whether or not the *whole* function
# ends up lifting; exactly the functions telemetry most needs to say
# something useful about. `has_accumulator_fold`'s own loop-shape
# classification reuses `mathema.symbolic.classify_loop_header`
# per-loop, independent of whether `lift_fold()`/`lift_sum()` accept
# the *whole* function, a fold-shaped loop sitting next to an
# unrelated branch that blocks full lifting is still a real, reportable
# motif at its own line, not a lift-or-nothing fact.

_CLAMP_CALL_NAMES = ("min", "max", "clip", "minimum", "maximum")


def _source_file(fn) -> str:
    import inspect
    return inspect.getsourcefile(fn) or "<unknown>"


def has_clamp(fn, facts) -> list[dict]:
    """Every min/max/np.clip/np.minimum/np.maximum call anywhere in the
    body, each with its own source line, a syntactic fact, observable
    whether or not the function lifts at all."""
    file = _source_file(fn)
    hits = []
    for node in ast.walk(facts.tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _CLAMP_CALL_NAMES:
                hits.append({"motif": "clamp", "file": file, "line": node.lineno,
                            "detail": f"{name}(...) call"})
    return hits


def has_dot_product_call(fn, facts) -> list[dict]:
    """Every literal `dot(...)` call (e.g. `np.dot(a, b)`) anywhere in
    the body, broader than `lift_dot()`'s own recognition, which
    additionally requires the *whole* function body to be exactly this
    one call; this reports the call's own line regardless."""
    file = _source_file(fn)
    hits = []
    for node in ast.walk(facts.tree):
        if isinstance(node, ast.Call) and _call_name(node) == "dot" and len(node.args) == 2:
            hits.append({"motif": "dot_product", "file": file, "line": node.lineno,
                        "detail": "dot(...) call"})
    return hits


def has_accumulator_fold(fn, facts) -> list[dict]:
    """Every `for` loop anywhere in the body whose header matches a
    recognized fold/sum shape (`mathema.symbolic.classify_loop_header`,
    applied per-loop rather than requiring the whole function to lift)
   , a real motif even when some other, unrelated part of the
    function blocks full lifting (a branch elsewhere, an unsupported
    call in a different statement, ...)."""
    seq_params = {p for p, k in facts.param_kinds.items() if k == "sequence"}
    file = _source_file(fn)
    hits = []
    for node in ast.walk(facts.tree):
        if isinstance(node, ast.For):
            classified = classify_loop_header(node, seq_params)
            if classified is not None:
                kind = classified[0]
                hits.append({"motif": f"loop_{kind}", "file": file, "line": node.lineno,
                            "detail": f"recognized {kind!r}-shaped loop header"})
    return hits


def motifs(fn, facts) -> list[dict]:
    """Every motif detector above, bundled, legible, containment-
    based facts: "this function contains a clamp on line 12" is a
    claim a user can check directly."""
    return has_clamp(fn, facts) + has_dot_product_call(fn, facts) + has_accumulator_fold(fn, facts)


# --- critical points: poles, stationary/inflection points, and domain- -----
# --- transition points, over the lifted expression --------------------------

def _pole_hazards(expr: "sympy.Expr", file: str, declared_domain: dict | None = None) -> list[dict]:
    """Intent:
        Pole/singularity detection over expr's own denominators.

    Notes:
        Division is Mul(..., Pow(base, negative_exponent)) in sympy's
        internal representation, so walking for negative-exponent Pow
        nodes finds every division in the tree regardless of how it
        was originally written. When declared_domain doesn't cover a
        variable, the search still runs and the hazard record says so
        explicitly, never silently treating an assumption as a stated
        fact. Can't report a source line: sympy's own tree carries no
        backreference to where a sub-expression came from.
    """
    hazards: list[dict] = []
    seen_denominators: set = set()
    for node in sympy.preorder_traversal(expr):
        if isinstance(node, sympy.Pow) and node.exp.is_negative:
            denominator = node.base
            if denominator in seen_denominators or denominator.is_number:
                continue
            seen_denominators.add(denominator)
            for var in denominator.free_symbols:
                try:
                    roots = sympy.solve(denominator, var)
                except TimeoutError:
                    # let the wall-clock cap set by a caller's _with_timeout
                    # actually stop the loop, rather than being treated as
                    # just another failed root search and moving on to the
                    # next variable unguarded, a bare `except Exception`
                    # here would otherwise consume the alarm's one-shot
                    # signal and leave the rest of this function running
                    # with no cap at all.
                    raise
                except Exception:
                    continue
                domain_note = _pole_domain_note(var.name, declared_domain)
                for root in roots:
                    hazards.append({
                        "kind": "pole", "denominator": str(denominator),
                        "variable": var.name, "at": str(root),
                        "domain": domain_note, "file": file,
                    })
    return hazards


def _pole_domain_note(var_name: str, declared_domain: dict | None) -> str:
    """Intent:
        The declared/assumed domain label for one pole's own variable.

    Notes:
        Factored out of _pole_hazards so a cached, domain-independent
        point list can have this label re-attached fresh by any
        caller, with no recomputation of the pole's own root.
    """
    declared_domain = declared_domain or {}
    if var_name in declared_domain:
        from .grammar import render_domain_bound
        return f"declared: {render_domain_bound(declared_domain[var_name])}"
    return "assumed (-inf, inf), not declared"


def _integer_pole_hazards(expr: "sympy.Expr", file: str,
                          declared_domain: dict | None = None) -> list[dict]:
    """Intent:
        Pole detection for gamma/loggamma calls: both have a pole at
        *every* non-positive integer of their own argument.

    Notes:
        _pole_hazards' denominator walk can never find these, gamma
        isn't represented as a division anywhere in the expression
        tree, so there's no denominator to solve. Unlike a rational
        denominator's finite root set, "every non-positive integer" is
        infinite and can't be enumerated the same way. One hazard
        record per bare-symbol argument instead, `"at": "non-positive
        integers"` naming the whole class rather than a single root,
        still a fixed, domain-independent fact about the expression
        (matching every other hazard here and the cache's own
        assumption that a pole list never depends on declared_domain);
        _pole_safety knows how to decide containment against this
        shape specifically. Scoped to a bare symbol argument
        (`gamma(n)`, not `gamma(n+1)`); an offset argument would need
        solving `arg = k` per candidate integer, real work not
        attempted here; a function shaped that way stays undecided
        rather than guessed at.
    """
    hazards: list[dict] = []
    seen: set = set()
    for node in sympy.preorder_traversal(expr):
        if not (isinstance(node, (sympy.gamma, sympy.loggamma)) and len(node.args) == 1):
            continue
        arg = node.args[0]
        if not isinstance(arg, sympy.Symbol) or arg in seen:
            continue
        seen.add(arg)
        hazards.append({
            "kind": "pole", "denominator": f"{node.func.__name__}({arg})",
            "variable": arg.name, "at": "non-positive integers",
            "domain": _pole_domain_note(arg.name, declared_domain), "file": file,
        })
    return hazards


def domain_hazards(fn, expr: "sympy.Expr", declared_domain: dict | None = None) -> list[dict]:
    """Intent:
        Pole/singularity detection over expr's own denominators, plus
        gamma/loggamma's own non-positive-integer poles, for the given
        function.
    """
    file = _source_file(fn)
    return _pole_hazards(expr, file, declared_domain) + _integer_pole_hazards(
        expr, file, declared_domain)


def _multi_radical(expr) -> bool:
    """Intent:
        Does the expression carry two or more distinct radical terms
        (Pow with a non-integer rational exponent over a non-trivial
        base)? The shape whose derivative defeats solve(), see the
        caller's comment.
    """
    radicals = 0
    for node in sympy.preorder_traversal(expr):
        if (isinstance(node, sympy.Pow) and node.exp.is_Rational
                and not node.exp.is_integer
                and not node.base.is_Symbol and not node.base.is_number):
            radicals += 1
            if radicals >= 2:
                return True
    return False


def _stationary_and_inflection_points(expr: "sympy.Expr", file: str) -> list[dict]:
    """Intent:
        Roots of expr's first and second derivative, per free symbol.

    Notes:
        No realness filtering, matching _pole_hazards. Consumers
        filter defensively.
    """
    if _multi_radical(expr):
        # a sum of two or more radical terms sends solve() into
        # heuristic polynomial gcd over astronomically large integers;
        # C-level arithmetic no wall-clock alarm can interrupt
        # (signals fire between bytecodes; a single big-int gcd can run
        # for minutes). Hints are best-effort by contract, so this
        # family skips the solve outright and sampling stays plain.
        return []
    points: list[dict] = []
    for var in sorted(expr.free_symbols, key=str):
        try:
            roots = sympy.solve(sympy.Eq(sympy.diff(expr, var), 0), var)
        except TimeoutError:
            # see _pole_hazards's own comment on the same pattern: must
            # propagate, not be absorbed as an ordinary failed solve.
            raise
        except Exception:
            roots = []
        for root in roots:
            points.append({"kind": "stationary", "expression": str(expr),
                          "variable": var.name, "at": str(root), "file": file})
        try:
            roots2 = sympy.solve(sympy.Eq(sympy.diff(expr, var, 2), 0), var)
        except TimeoutError:
            raise
        except Exception:
            roots2 = []
        for root in roots2:
            points.append({"kind": "inflection", "expression": str(expr),
                          "variable": var.name, "at": str(root), "file": file})
    return points


def _fractional_power_and_log_hazards(expr: "sympy.Expr", file: str) -> list[dict]:
    """Intent:
        Points where a partial function's own argument crosses zero:
        sqrt/even-root, log, Abs, and sign.

    Notes:
        Same preorder_traversal and dedupe pattern as _pole_hazards, a
        different node shape and equation.
    """
    points: list[dict] = []
    seen: set = set()
    for node in sympy.preorder_traversal(expr):
        if isinstance(node, sympy.Pow) and node.exp.is_rational and not node.exp.is_integer:
            arg = node.base
        elif isinstance(node, (sympy.log, sympy.Abs, sympy.sign)):
            arg = node.args[0]
        else:
            continue
        if arg in seen or arg.is_number:
            continue
        seen.add(arg)
        for var in arg.free_symbols:
            try:
                roots = sympy.solve(arg, var)
            except TimeoutError:
                raise
            except Exception:
                continue
            for root in roots:
                points.append({"kind": "domain_transition", "expression": str(arg),
                              "variable": var.name, "at": str(root), "file": file})
    return points


def _critical_points_over_expr(expr: "sympy.Expr", file: str = "<unknown>",
                               declared_domain: dict | None = None) -> list[dict]:
    """Intent:
        Every analytically discovered point of interest over an
        already-lifted expression: pole, stationary, inflection, and
        domain-transition points.
    """
    return (_pole_hazards(expr, file, declared_domain)
           + _integer_pole_hazards(expr, file, declared_domain)
           + _stationary_and_inflection_points(expr, file)
           + _fractional_power_and_log_hazards(expr, file))


def critical_points(fn, facts=None, declared_domain: dict | None = None) -> list[dict]:
    """Intent:
        Every analytically discovered point of interest in fn's own
        body: poles, stationary points, inflection points, and
        domain-transition points.

    Notes:
        Never raises. Returns [] for anything that does not lift,
        matching domain_hazards's own contract.
    """
    from .analysis import analyze_source
    from .audit import _try_derive_lift

    if facts is None:
        try:
            facts = analyze_source(fn)
        except Exception:
            return []
    try:
        expr = _try_derive_lift(fn, facts)
    except Exception:
        expr = None
    if expr is None:
        return []
    return _critical_points_over_expr(expr, _source_file(fn), declared_domain)


_critical_points_cache: dict[str, list[dict]] = {}
# Module-level dict, not functools.lru_cache: Facts is an ordinary
# (non-frozen) dataclass, not hashable. Keyed on facts.form alone.
# Content-addressed, rename-invariant, cross-process-safe. Also
# domain-independent: declared_domain only ever affects a pole's own
# label text (_pole_domain_note, computed fresh every call), never the
# actual differentiation/solving this memoizes.


def _cached_critical_points(fn, facts) -> list[dict]:
    """Intent:
        critical_points(fn, facts, declared_domain=None), memoized by
        facts.form.

    Notes:
        Only the expensive full-lift-chain path is memoized. The cheap
        direct-lift-only fast path (~0.1s) is already fast enough that
        a cache buys nothing.

        A caller wraps this whole call in `_with_timeout`, if the
        wall-clock cap fires mid-search, that's caught here and cached
        as `[]` too, not just a successful result. Without this, a
        function whose critical-point search genuinely takes longer
        than the cap would redo, and re-block for, the same doomed
        search on every subsequent call in this process: the point of
        caching is to make that search happen at most once per form,
        whether it finished or timed out.
    """
    from ._timeout import _WallClockExpired
    key = facts.form
    if key not in _critical_points_cache:
        try:
            _critical_points_cache[key] = critical_points(fn, facts, declared_domain=None)
        except (TimeoutError, _WallClockExpired):
            # _WallClockExpired, not just TimeoutError: the alarm fires
            # INSIDE this call and is only converted to the public
            # TimeoutError at _with_timeout's own boundary, which sits
            # above this frame. Catching TimeoutError alone could never
            # fire from here, so the doomed search was never recorded
            # and every later call redid it, exactly what this cache
            # exists to prevent.
            _critical_points_cache[key] = []
            raise
    return _critical_points_cache[key]


def _critical_points_cache_clear() -> None:
    """Intent:
        Reset the critical-points cache. Test isolation only.
    """
    _critical_points_cache.clear()


# --- operations of interest: a raw statistical facet, not a curated one ----

def operations_of_interest(expr: "sympy.Expr") -> dict[str, int]:
    """A raw bag-of-operation-kind count over `expr`'s own tree,
    distinct from the curated, named motif library above (which is
    containment-based and legible); this is just counts, input for
    further analysis alongside the motif library and the branch/loop
    counts of `inventory.structural_complexity`, not an explanation
    on its own."""
    counts = {
        "negative_or_fractional_powers": 0,
        "log_or_exp": 0,
        "trig": 0,
        "comparisons": 0,
        "piecewise_branches": 0,
    }
    for node in sympy.preorder_traversal(expr):
        if isinstance(node, sympy.Pow) and (node.exp.is_negative or
                                            (node.exp.is_rational and not node.exp.is_integer)):
            counts["negative_or_fractional_powers"] += 1
        elif isinstance(node, (sympy.log, sympy.exp)):
            counts["log_or_exp"] += 1
        elif isinstance(node, (sympy.sin, sympy.cos, sympy.tan)):
            counts["trig"] += 1
        elif isinstance(node, sympy.core.relational.Relational):
            counts["comparisons"] += 1
        elif isinstance(node, sympy.Piecewise):
            counts["piecewise_branches"] += len(node.args)
    return counts


# --- diagnostic_report: the opt-in bundle ------------------------------------
#
# Deliberately stops at computing this *one* function's own raw facts,
# the blocker, the motifs, the hazards. Matching a function
# against a corpus of other functions (finding similar past failures,
# surfacing claims that worked on related shapes) is a different,
# accumulate-shaped, decide-shaped concern than answering a question
# about a single function in front of you right now, and stays out of
# core for that reason: a corpus that grows with data held over time is
# a different kind of tool than this one.

def diagnostic_report(fn, facts, *, declared_domain: dict | None = None) -> dict:
    """Every facet above, bundled, **never computed by default**, no
    wiring into `check()`/`write_spec()`'s own automatic path; a caller opts
    in per function, e.g. a harness that logs this alongside every
    failure it sees across many functions over time.

    `liftable` is a property of `fn` itself: whether it has a full,
    unconditional closed-form lift (`audit._try_derive_lift`). It is
    independent of any particular claim's own verdict against `fn`;
    a claim can still be `proven` via branch-pruning or a case-split
    fallback on a function this flag reports `False` for (the
    unconditional lift fails, but a narrower one under the claim's own
    domain succeeds), and a claim can come back `skipped` on a function
    this flag reports `True` for (it lifts cleanly, but that specific
    relation's sign or equality still can't be settled).

    Always returns a real, structured dict, never bare `None`, even a
    function that doesn't lift at all carries a stable `error_code`
    (`inventory.derivability_report()`'s own raw `blocker`) and its
    blocking constructs. This is the primary case, not a fallback:
    telemetry exists to find out where and why real code fails, not
    only to catalog what already works.

    `sympy_version`/`mathema_version` are stamped so a consumer
    comparing two records knows what produced each, and
    `diagnostic_scheme` versions this function's own field layout: a
    change to it means two records are not directly comparable.

    No source of any kind (raw text, line, column) lives here at
    all. That's a different kind of depth than the plain facts above,
    entirely a caller's own decision (privacy, size, whether the
    reader already has the code), and it lives one layer up in whatever
    builds a fuller report around this (see
    `reason_codes.build_issue_record`'s own `include_source`)."""
    from . import __version__ as _mathema_version
    from .audit import _try_derive_lift
    from .inventory import derivability_report, wrapped_target
    from .reason_codes import blocked_code

    lift_expr = _try_derive_lift(fn, facts, extra_domain=declared_domain)
    versions = {"sympy_version": sympy.__version__, "mathema_version": _mathema_version}
    wraps = wrapped_target(fn)

    # one stable key set on both branches: a consumer can read every
    # field without first branching on `liftable`, and an empty list
    # means "computed, nothing found" rather than "never looked".
    # Motifs ride both branches deliberately; they are AST-based
    # precisely so they still say something about a function that
    # does NOT lift, which is the case telemetry most needs.
    base = {
        "diagnostic_scheme": DIAGNOSTIC_SCHEME,
        "liftable": lift_expr is not None,
        "error_code": None,
        "error_category": None,
        "blocked": None,
        "constructs": [],
        "wraps": wraps,
        "motifs": motifs(fn, facts),
        "operations_of_interest": {},
        "domain_hazards": [],
        **versions,
    }

    if lift_expr is None:
        report = derivability_report(fn) or {}
        out = {
            **base,
            "error_code": report.get("blocker"),
            "error_category": report.get("category"),
            "blocked": blocked_code(report),
            "constructs": _blocking_constructs(report),
        }
        if facts.branch_count and not declared_domain:
            # honest about what "liftable: False" means for a branchy
            # body diagnosed with NO domain in hand: claim-time
            # adjudication conditions the lift on the claim's own
            # declared bounds and may succeed where this read-only
            # sweep could not; pass declared_domain= to see that view
            out["liftable_note"] = (
                "branch-conditioned derivation may still succeed under a "
                "claim's declared domain; this field reflects the "
                "domain-free read")
        return out

    return {
        **base,
        "operations_of_interest": operations_of_interest(lift_expr),
        "domain_hazards": domain_hazards(fn, lift_expr, declared_domain),
    }


def _blocking_constructs(report: dict) -> list[dict]:
    """Intent:
        The per-construct detail for an underivable function, one entry
        per blocking construct: `{line, code, hint, derive_unlock}` (branch
        entries add `condition`, and the resolvable kind
        `needs_domain_for`). The human hint text lives HERE and in the
        reason-code lookup, the CLI prints only the codes.
    """
    from .reason_codes import blocked_code, describe_code

    if not report or report.get("liftable"):
        return []
    blocker = report.get("blocker")
    out = []
    if blocker == "branch":
        for b in report.get("branches") or []:
            if b.get("kind") == "blocked":
                code = f"branch:{b.get('code') or 'unrecognized-shape'}"
            else:
                needs = b.get("needs_domain_for") or []
                code = ("branch:needs-domain"
                        + (f"({', '.join(needs)})" if needs else ""))
            entry = {"line": b.get("line"), "code": code,
                     "condition": b.get("condition"),
                     "hint": b.get("reason") or (describe_code(code) or {}).get("hint"),
                     "derive_unlock": (describe_code(code) or {}).get("derive_unlock")}
            if b.get("needs_domain_for"):
                entry["needs_domain_for"] = b["needs_domain_for"]
            out.append(entry)
        return out
    code = blocked_code(report)
    if code is None:
        return []
    generic = describe_code(code) or {}
    hint = report.get("hint") or report.get("message") or generic.get("hint")
    out.append({"line": report.get("line"), "code": code, "hint": hint,
                "derive_unlock": report.get("derive_unlock") or generic.get("derive_unlock")})
    return out
