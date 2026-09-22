# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The tier ladder: five real, independently-inspectable representations
of the same function, as mathema's own pipeline already computes them,
named here as one shared, ordered concept rather than left scattered
across `identity.py`/`analysis.py`/`symbolic.py`/sympy's own printers,
each used ad hoc by whichever caller happened to need it.

    source     , the raw AST, exactly as written
    normalized , alpha-renamed AST (params/locals -> v0, v1, ...),
                   the literal thing identity.form_hash() hashes
    structural , Facts-level control-flow classification only (a loop's
                   kind, a branch's presence), no expression text at all
    lifted     , the real post-lift sympy expression's own tree
                   (Piecewise/Add/Sum/Pow/Symbol as actual tree nodes)
    canonical  , the same lifted result, pretty-printed as standard
                   math notation, a flat rendering, not a tree

`source`/`normalized`/`structural` are three different labelings of the
*same* control-flow topology, built from the AST. `mathema/_tier_text.py`
owns the plain-text layout these renderers feed labels into.
`lifted`/`canonical` describe a genuinely
different shape, the post-lift sympy result's own tree, not the
original branch/loop shape with fancier labels, because after
lifting, control flow has already been transformed into data.

Every render function here returns a `Rendered(text, available)` pair
and never silently substitutes a different tier's output when the
requested one isn't meaningful or isn't liftable; unavailability is
always stated, with the real reason, not papered over. This mirrors the
same "decline rather than guess" posture the derive route itself has
throughout `symbolic.py`.

This module is deliberately read-only and one-directional (AST/lift
result -> text). Going the *other* way, starting from a mathematical
statement and lowering it through structural form down to real code;
is a genuinely separate, much larger feature (a symbolic-to-code
compiler pass), not attempted here. This module's own tier boundaries
are chosen so that future work doesn't have to be redesigned around
them, but building the reverse direction is out of scope for this
module entirely.
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass

import sympy

TIERS = ("source", "normalized", "structural", "lifted", "canonical")


@dataclass(frozen=True)
class Rendered:
    """One tier's rendering of one fragment: `text` is always a string
    (either the real rendering, or a human-readable reason it isn't
    available), `available` says which. Never conflate the two, a
    caller must check `available` before treating `text` as the real
    thing, not a diagnostic message standing in for it."""
    text: str
    available: bool = True


def _humanize_opaque(expr, opaque):
    """Substitute every opaque-registry symbol appearing in `expr` with
    a plain sympy Symbol named after the real value it stands for
    (`sympy.Symbol(repr(value))`, so a string value prints quoted, the
    way a reader would actually write it), without this, `canonical`
    tier would print the registry's own internal `Dummy` name
    (`__opaque2`) instead of the value it represents (`'info'`). A
    no-op when `opaque` is `None` or `expr` has no opaque symbols at
    all."""
    if opaque is None:
        return expr
    subs = {s: sympy.Symbol(repr(opaque.value_of(s))) for s in expr.free_symbols
           if opaque.is_opaque_symbol(s)}
    return expr.subs(subs) if subs else expr


def unparse_normalized(node: ast.AST, name_map: dict) -> str:
    """`node` (any AST fragment, not necessarily a whole function)
    rendered with every bound name in `name_map` substituted for its
    alpha-normalized form, the same substitution
    `identity.normalized()` applies to a whole function, applied here to
    one fragment so a single expression can be shown at the
    `normalized` tier without re-deriving the whole function's own
    binding-order mapping each time (the caller computes `name_map`
    once per function, via `identity.local_names()`, and passes it to
    every `render_*` call for that function)."""
    from .identity import _Alpha

    renamed = copy.deepcopy(node)
    _Alpha(name_map).visit(renamed)
    return ast.unparse(renamed)


def render_label(node: ast.expr, tier: str, *, env: dict | None = None,
                 opaque=None, name_map: dict | None = None) -> Rendered:
    """Render one *expression fragment* (an `ast.expr`) at a given tier.

    `source`/`normalized` are always available (pure AST unparsing;
    `normalized` needs `name_map`, the whole function's own binding-
    order rename table, computed once by the caller via
    `identity.local_names()`; omitting it when the tier is
    `"normalized"` is a caller error, not a soft-declined case, since
    every function has one). `canonical` attempts the *existing* lift
    primitive (`symbolic._expr_to_sympy`, not reimplemented here) and
    renders the result via `grammar.render_canonical()` (mathema's own
    claim-grammar spelling, not sympy's) on success; on `NotSymbolic`, or a
    tuple-valued result (no single scalar to render), `available`
    is `False` and `text` carries the real reason, never a silent
    fallback to `source` rendering.

    `structural`/`lifted` aren't meaningful for a bare expression
    fragment (they describe whole-function shapes), `available=False`
    with a note saying so; a caller wanting a structural or lifted view
    of a loop header or branch condition specifically should use
    `render_loop_header`/`render_condition` instead, and of a whole
    function's own closed form should use
    `_tier_text.render_lifted_plain`."""
    if tier == "source":
        return Rendered(ast.unparse(node))
    if tier == "normalized":
        if name_map is None:
            raise ValueError("render_label: tier 'normalized' needs name_map")
        return Rendered(unparse_normalized(node, name_map))
    if tier == "canonical":
        from .grammar import render_canonical
        from .symbolic import NotSymbolic, _expr_to_sympy

        if env is None:
            return Rendered("(no scope available to lift this fragment)", False)
        try:
            result = _expr_to_sympy(node, env, opaque=opaque)
        except NotSymbolic as e:
            return Rendered(str(e), False)
        if isinstance(result, tuple):
            return Rendered("a tuple-valued fragment has no single "
                            "canonical form", False)
        return Rendered(render_canonical(_humanize_opaque(result, opaque))[0])
    if tier in ("structural", "lifted"):
        return Rendered(f"tier {tier!r} describes a whole-function shape, "
                        "not a bare expression fragment", False)
    raise ValueError(f"render_label: unknown tier {tier!r}")


# The loop-header shapes symbolic.classify_loop_header() recognizes,
# and their own canonical-notation templates, kept in sync with that
# function by hand (same "kept in sync" discipline diagnose_fold()
# already uses relative to lift_fold()): a shape added there without a
# matching template here degrades honestly (falls through to the
# "unrecognized" case below), never silently wrong, but won't get a
# pretty rendering until this table catches up.
LOOP_KIND_LABEL = {
    "item": "fold", "index": "sum-loop", "enumerate": "sum-loop",
    "scalar_index": "sum-loop",
}


def render_loop_header(for_stmt: ast.For, tier: str, *, seq_params: frozenset = frozenset(),
                       kind_label: str | None = None, name_map: dict | None = None) -> Rendered:
    """Render a single `for` statement's own header (target + iterable,
    never its body) at a given tier. `source` unparses
    `for_stmt.target`/`for_stmt.iter` directly; `normalized` unparses an
    alpha-renamed *copy* of the same two nodes via `name_map` (the loop
    target is itself a binding `identity.local_names()` already
    includes, so a loop header at `normalized` tier must apply this
    substitution or it disagrees with what `form_hash` actually
    hashes). Omitting `name_map` when `tier == "normalized"` is a
    caller error, not a soft-declined case, same as `render_label`.

    `structural` returns `kind_label` if the caller already classified
    this loop (via `Facts.loops`' own `LoopFact.kind`, or a finer
    `symbolic.classify_loop_header()` result), the fixed vocabulary
    `"fold"`/`"sum-loop"`/`"loop"` (a recognized-but-unclassified
    accumulator), falling back to the generic `"loop"` label if no
    classification was given at all, still `available=True` (a bare
    `for` statement's presence is always a real, statable fact, even
    when its finer shape isn't recognized).

    `canonical` reclassifies via `symbolic.classify_loop_header()`
    directly (needs `seq_params`, the set of this function's own
    sequence-kind parameter names) and renders a fixed template per
    recognized kind (`"item"` -> `∀ <item> ∈ <seq>`, `"index"`/
    `"enumerate"`/`"scalar_index"` -> `∀ <idx> ∈ [<lo>, <hi>)`). If
    that declines, also tries `lift_fold()`'s own two loop-iterable
    shapes (`seq_one_colon`/`bare_seq_name`) against each candidate
    in `seq_params`; `classify_loop_header` is built specifically for
    `lift_sum()`'s own recognized shapes and doesn't cover
    `lift_fold()`'s `for item in seq[1:]:`/`for item in seq:`, one of
    the most common liftable loop shapes, so both recognizers are tried
    before declining. `available=False` with the real reason only once
    *neither* recognizer matches."""
    if tier == "source":
        return Rendered(f"for {ast.unparse(for_stmt.target)} in "
                        f"{ast.unparse(for_stmt.iter)}:")
    if tier == "normalized":
        from .identity import _Alpha

        if name_map is None:
            raise ValueError("render_loop_header: tier 'normalized' needs name_map")
        target = copy.deepcopy(for_stmt.target)
        it = copy.deepcopy(for_stmt.iter)
        alpha = _Alpha(name_map)
        alpha.visit(target)
        alpha.visit(it)
        return Rendered(f"for {ast.unparse(target)} in {ast.unparse(it)}:")
    if tier == "structural":
        return Rendered(kind_label or "loop")
    if tier == "canonical":
        from .symbolic import bare_seq_name, classify_loop_header, seq_one_colon

        classified = classify_loop_header(for_stmt, set(seq_params))
        if classified is not None:
            kind, seq_name, item_name, idx_name = classified
            if kind == "item":
                return Rendered(f"∀ {item_name} ∈ {seq_name}")
            if kind == "enumerate":
                return Rendered(f"∀ {idx_name} ∈ [0, len({seq_name}))  "
                                f"({item_name} = {seq_name}[{idx_name}])")
            # "index" (range(len(seq))) or "scalar_index" (range(<expr>))
            bound = f"len({seq_name})" if kind == "index" else ast.unparse(seq_name)
            return Rendered(f"∀ {idx_name} ∈ [0, {bound})")
        if isinstance(for_stmt.target, ast.Name):
            item_name = for_stmt.target.id
            for seq_name in seq_params:
                if seq_one_colon(for_stmt.iter, seq_name):
                    return Rendered(f"∀ {item_name} ∈ {seq_name}[1:]  "
                                    f"(i.e. i ∈ [1, len({seq_name})))")
                if bare_seq_name(for_stmt.iter, seq_name):
                    return Rendered(f"∀ {item_name} ∈ {seq_name}")
        return Rendered("this loop header shape isn't recognized by "
                        "the derive route", False)
    raise ValueError(f"render_loop_header: unknown tier {tier!r}")


def render_condition(test_node: ast.expr, tier: str, *, env: dict | None = None,
                     opaque=None, name_map: dict | None = None) -> Rendered:
    """Render an `if` statement's own test expression at a given tier;
    `source`/`normalized` as `render_label` does (a condition is still
    just an expression fragment at those two tiers); `structural` is a
    fixed `"branch"` label, condition-shape-independent (the whole
    point of the structural tier is to say *that* a branch exists, not
    what it tests); `canonical` attempts `symbolic._cond_to_sympy`
    (the *existing* condition-lifting primitive) and renders the
    resulting sympy relational/boolean via `grammar.render_canonical()`,
    `available=False` with the
    real reason on `NotSymbolic`, same posture as `render_label`."""
    if tier in ("source", "normalized"):
        return render_label(test_node, tier, env=env, opaque=opaque, name_map=name_map)
    if tier == "structural":
        return Rendered("branch")
    if tier == "canonical":
        from .grammar import render_canonical
        from .symbolic import NotSymbolic, _cond_to_sympy

        if env is None:
            return Rendered("(no scope available to lift this condition)", False)
        try:
            result = _cond_to_sympy(test_node, env, opaque=opaque)
        except NotSymbolic as e:
            return Rendered(str(e), False)
        return Rendered(render_canonical(_humanize_opaque(result, opaque))[0])
    if tier == "lifted":
        return Rendered("tier 'lifted' describes a whole-function shape, "
                        "not a bare condition", False)
    raise ValueError(f"render_condition: unknown tier {tier!r}")
