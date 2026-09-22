# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The base lifter (`lift()`) and the AST-to-sympy walking layer beneath
it, `_expr_to_sympy`/`_cond_to_sympy`/`_walk_lift_body`, local
symbolic arrays (`_SymbolicArray`), and callee inlining
(`_try_inline_callee`). `lift()` only ever accepts a loop-free,
branch-free, non-recursive, all-scalar body; `.conditioned`/`.fold`/
`.dot`/`.sum` each extend that for one specific, narrower shape, all
built on the same walker this module owns. See `mathema/symbolic/
__init__.py` for the package's own overview and public surface.
"""
from __future__ import annotations

import ast
import inspect
import dataclasses
from dataclasses import dataclass, field

import sympy

from .._math_vocab import (_BINOPS, _MATH_ATTRS, _SYMPY_FUNCS,
                           _call_name, _root_name)
from ..finite_sets import OpaqueRegistry, is_opaque_eligible


# One canonical pair of tables for negating/rendering sympy
# relationals, previously duplicated in four modules, drifting apart
# was only a matter of time.
NEGATED_REL: dict = {}
REL_TEXT: dict = {}


def _init_rel_tables():
    NEGATED_REL.update({sympy.Lt: sympy.Ge, sympy.Le: sympy.Gt,
                        sympy.Eq: sympy.Ne, sympy.Gt: sympy.Le,
                        sympy.Ge: sympy.Lt, sympy.Ne: sympy.Eq})
    REL_TEXT.update({sympy.Ge: ">=", sympy.Gt: ">", sympy.Le: "<=",
                     sympy.Lt: "<", sympy.Ne: "!=", sympy.Eq: "=="})


_init_rel_tables()


class NotSymbolic(Exception):
    """A body or a law uses syntax this module doesn't lift to sympy.
    `category` tags *why*, from a fixed vocabulary (see
    reason_codes.Category), mathema audit --deriv-report's data source
    for turning a raw failure into an actionable suggestion (rewrite
    this construct vs. this is a mathema implementation limitation,
    not a bug in the target code), rather than pattern-matching the
    free-text message, which is for humans, not dispatch."""
    def __init__(self, message: str, category: str = "unsupported-syntax"):
        super().__init__(message)
        self.category = category


_SYMPY_RELOPS = {
    ast.Eq: sympy.Eq, ast.NotEq: sympy.Ne,
    ast.Lt: sympy.Lt, ast.LtE: sympy.Le,
    ast.Gt: sympy.Gt, ast.GtE: sympy.Ge,
}


def _unsupported_call_message(node: ast.Call) -> str:
    """`unsupported call {full expression}` alone is ambiguous for a
    nested call like `_display(np.minimum(r, R_CLIP))`, np.minimum
    lifts fine, only the outer `_display` doesn't, but ast.unparse(node)
    shows the whole expression either way. Names which specific call
    site is actually unresolved (the outer function itself if it's not
    in _SYMPY_FUNCS, or the keyword-argument usage if it is) alongside
    the full expression, so the culprit doesn't have to be guessed at
    from a nested expression."""
    name = _call_name(node)
    full = ast.unparse(node)
    if name in _SYMPY_FUNCS:
        culprit = f"{name}(...) called with keyword arguments"
    else:
        culprit = ast.unparse(node.func)
    return f"unsupported call {full!r}, unresolved: {culprit!r}"


@dataclass(frozen=True)
class _LiftCtx:
    """Threaded through every internal lift helper (_expr_to_sympy,
    _cond_to_sympy, _walk_lift_body) so an otherwise-unsupported call can
    attempt callee inlining (_try_inline_callee) without every one of
    those helpers needing its own plumbing for it. `globals_ns` is
    whichever function's body is *currently* being walked; it changes
    when a callee's own body is lifted in turn, since a callee may live
    in a different module with different global names, so it can't be
    fixed once at the top of the walk. `depth` is the remaining callee-
    inlining budget (see lift()'s `max_callee_depth`); `seen` is the set
    of already-inlined callees' ids along this specific path, so mutual
    recursion through calls (A calls B calls A) is refused outright via
    membership, not just eventually via depth exhaustion. `domain` is
    the declared domain over *whichever function's own parameters are
    currently in scope*, rebuilt (not inherited) each time a callee's
    own body is walked in turn, same reasoning as `globals_ns`: a
    callee's parameters have their own names, so the caller's domain
    dict (keyed by the caller's own parameter names) isn't meaningful
    for it directly, see _derive_passthrough_domain, which is what
    actually rekeys it for a callee. Used only for callee-branch and
    ternary-condition resolution (_try_inline_callee, the IfExp case in
    _expr_to_sympy), never for the top-level function's own branch
    gate, which lift() still refuses outright regardless of `domain`.
    `unmodified` (see _unmodified_params) is, likewise, whichever
    function's own parameters are currently in scope and never
    reassigned anywhere in its body, only for these does `domain`
    still describe the parameter's value at a ternary condition reached
    partway through the body, same guard lift_conditioned() already
    applies before trusting a domain against an `if` statement."""
    globals_ns: dict
    depth: int
    seen: frozenset
    domain: dict
    unmodified: frozenset
    # the method context, when the function under lift is one: the name
    # of its self parameter and the enclosing class, so a sibling call
    # (`self.helper(x)`) resolves on the class namespace. None/None for
    # a plain function; every other field's reasoning is unchanged.
    self_param: "str | None" = None
    self_class: "type | None" = None


def _unmodified_params(tree: ast.FunctionDef, param_names: set) -> set:
    """Signature parameters never reassigned anywhere in the body,
    only for these does the declared domain still describe the
    parameter's value at a branch point. Conservative on purpose: any
    assignment to the name anywhere (even in a branch never taken for
    this domain) disqualifies it, rather than trying to prove the
    reassignment itself is unreachable. Populates `_LiftCtx.unmodified`,
    needed unconditionally by `lift()`/`_try_inline_callee` (this
    module), and separately consulted by `.conditioned`'s own branch-
    pruning code for the same reason; it has no dependency on branch-
    pruning machinery itself, just an AST walk, so it lives here with
    the dataclass field it populates rather than with a caller."""
    reassigned = set()

    def _root(t):
        while isinstance(t, (ast.Attribute, ast.Subscript)):
            t = t.value
        return t.id if isinstance(t, ast.Name) else None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                name = _root(t)
                if name is not None:
                    reassigned.add(name)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            name = _root(node.target)
            if name is not None:
                reassigned.add(name)
    return param_names - reassigned


def _bare_name_truth(name: str, domain: dict) -> bool | None:
    """A bare boolean-valued name's truth value, decided the same way
    _branch_condition_truth's own bare-name case decides an `if`
    *statement*'s condition, the ternary-expression counterpart,
    previously unsupported (`_cond_to_sympy` refused a bare-name
    condition outright, since an ordinary real-valued sympy Symbol
    isn't itself a sympy Boolean). Only a *discrete* domain (`frozenset`,
    see grammar.py's `_set_value`) whose every member shares the same
    truthiness resolves definitively; a numeric interval's bare
    truthiness isn't attempted (0 may or may not be excluded), same
    restriction, same reasoning. `None` (undecided) otherwise, never a
    guess. Callers must additionally confirm `name` is unmodified before
    trusting `domain` at all (see ctx.unmodified); this function only
    decides truthiness given a domain value, it doesn't know whether
    that domain still describes the name's current value."""
    dom = domain.get(name)
    if not isinstance(dom, frozenset):
        return None
    results = {bool(v) for v in dom}
    return results.pop() if len(results) == 1 else None


def _derive_passthrough_domain(node: ast.Call, callee_params: list, ctx: "_LiftCtx") -> dict:
    """Bare-parameter-passthrough domain derivation for a callee's own
    branch conditioning: only a call-site argument that's a literal,
    bare reference to one of the *caller's* own domain-bounded
    parameters (`helper(x)`, not `helper(x + 1)`) contributes, the
    callee's parameter then inherits exactly the same bound, since the
    value really is the same number, not a derived one. Any other
    argument shape (a literal, an arithmetic expression, a local not in
    `ctx.domain`) is skipped for that parameter rather than guessed at;
    lift_conditioned() then either still resolves the callee's branches
    without it, or correctly declines, the same as it already does for
    any other undecidable branch."""
    domain: dict = {}
    for callee_param, arg in zip(callee_params, node.args):
        if isinstance(arg, ast.Name) and arg.id in ctx.domain:
            domain[callee_param] = ctx.domain[arg.id]
    return domain


def _method_ctx_fields(fn, facts) -> tuple:
    """Intent:
        (self_param, self_class) for _LiftCtx when `fn` is a method
        whose first parameter is self/cls and whose enclosing class
        resolves; (None, None) otherwise.
    """
    if facts.params and facts.params[0] in ("self", "cls"):
        cls = _enclosing_class(fn)
        if cls is not None:
            return facts.params[0], cls
    return None, None


def _try_inline_callee(node: ast.Call, env: dict, ctx: "_LiftCtx",
                       opaque: "OpaqueRegistry | None" = None):
    """Attempt to inline a call to a plain, bare-name function this one
    calls, by recursively lifting the callee itself (lift(), the same
    base lifter, one callee-inlining step further down, or, if that
    fails specifically because the callee has a branch,
    lift_conditioned() with a domain derived from this call site's own
    bare-parameter-passthrough arguments, the same two-stage pattern
    try_prove() already uses at the top level) and substituting its
    parameters with this call site's own argument expressions, the
    derive-route counterpart to docstring.docstring_sync()'s callee
    resolution, capped at the same kind of max_callee_depth. `opaque`,
    when given, is forwarded into the callee's own lift unchanged,
    an opaque value's meaning doesn't depend on which function produced
    it, unlike `globals_ns`/`domain`/`unmodified`, so the callee shares
    the caller's registry rather than getting a fresh one. Declines
    (returns None, never raises, the caller falls back to its own
    ordinary unsupported-call error) whenever the attempt wouldn't be
    honest: a module-qualified or method call (`obj.method(...)`, only a
    bare `name(...)` is attempted), keyword arguments, the depth budget
    exhausted or the callee already on this path (seen), the name not
    resolving to a real Python function, the callee itself failing to
    lift (unconditionally, or under a derived domain), a callee whose
    conditioned lift only resolves to `raises` (not a substitutable
    value), a callee with a composite (dataclass/dict-expanded)
    parameter (call-site substitution for those isn't implemented), or
    a mismatched argument count."""
    if node.keywords or ctx.depth <= 0:
        return None
    self_call = None
    if isinstance(node.func, ast.Name):
        callee = ctx.globals_ns.get(node.func.id)
    elif (isinstance(node.func, ast.Attribute)
          and isinstance(node.func.value, ast.Name)
          and node.func.value.id == ctx.self_param
          and ctx.self_class is not None):
        # a sibling-method call through self: resolved on the
        # enclosing class's own namespace (staticmethods unwrapped,
        # the same rules audit's discovery applies). The callee's own
        # self expands to the SAME composite field symbols this
        # caller's self already bound, so name-keyed substitution
        # unifies the two self views with no extra plumbing.
        member = vars(ctx.self_class).get(node.func.attr)
        if isinstance(member, staticmethod):
            callee, self_call = member.__func__, "static"
        else:
            callee, self_call = member, "instance"
    else:
        return None
    if callee is None or not inspect.isfunction(callee) or id(callee) in ctx.seen:
        return None

    from ..analysis import SourceUnavailable, analyze_source
    from ._conditioned import lift_conditioned

    try:
        callee_facts = analyze_source(callee)
    except SourceUnavailable:
        return None
    callee_unmodified = (frozenset(_unmodified_params(callee_facts.tree, set(callee_facts.params)))
                        if callee_facts.tree is not None else frozenset())
    # derived unconditionally, not just when the callee has its own
    # branch: even a branch-free callee may itself call a *further*
    # callee that needs this domain (mid(x) calling leaf(x), where only
    # leaf branches; mid's own ctx.domain must already carry x's
    # bound before mid's body is ever walked, or that inner call never
    # sees a domain to condition against at all).
    callee_domain = _derive_passthrough_domain(node, callee_facts.params, ctx) if ctx.domain else {}
    callee_sp, callee_sc = _method_ctx_fields(callee, callee_facts)
    callee_ctx = _LiftCtx(globals_ns=getattr(callee, "__globals__", {}),
                          depth=ctx.depth - 1, seen=ctx.seen | {id(callee)},
                          domain=callee_domain, unmodified=callee_unmodified,
                          self_param=callee_sp, self_class=callee_sc)
    lifted = lift(callee, callee_facts, _ctx=callee_ctx, _opaque=opaque)
    if lifted is None and callee_facts.branch_count and callee_domain:
        conditioned = lift_conditioned(callee, callee_facts, callee_domain,
                                       _ctx=callee_ctx, _opaque=opaque)
        if conditioned is not None and conditioned.kind == "value":
            lifted = conditioned
    if lifted is None or isinstance(lifted.expr, (tuple, _SymbolicArray)):
        return None
    sig_params = list(lifted.sig_params)
    if self_call == "instance":
        # the implicit self slot: dropped from the positional zip; its
        # expanded field symbols are shared with the caller by name
        if not sig_params or lifted.aggregate.get(sig_params[0]) is None \
                and sig_params[0] in ("self", "cls"):
            pass
        if sig_params and sig_params[0] in ("self", "cls"):
            sig_params = sig_params[1:]
    if len(node.args) != len(sig_params) \
            or any(lifted.aggregate.get(p) is not None for p in sig_params):
        return None

    args = [_expr_to_sympy(a, env, ctx, opaque) for a in node.args]
    if any(isinstance(a, (tuple, _SymbolicArray)) for a in args):
        return None
    subs = {lifted.params[p]: a for p, a in zip(sig_params, args)}
    return lifted.expr.subs(subs, simultaneous=True)


@dataclass
class DerivedClaim:
    """A claim derived *from* a lifted expression rather than stated by
    hand, `concept` names what it asserts (e.g. "monotonic"),
    `statement` the claim text, `sketch` the derivation. Matches the
    shape `Lifted.derived` and `spec.reasoning_chain()` expect for a
    "derivation" step; nothing currently constructs one (no automatic
    property-derivation pass exists yet), so `Lifted.derived` is always
    empty today."""
    concept: str
    statement: str
    condition: str | None = None
    sketch: str | None = None


@dataclass
class Lifted:
    """A function body lifted to a sympy expression: the symbolic form the
    derive route reasons over. `expr` is an ordinary sympy.Expr for a
    function with a single return value; for a function whose `return`
    statement is a tuple (`return x, y`), it's a plain Python tuple of
    sympy.Expr, one per element; there is no vector/matrix type here,
    just a fixed-length group of otherwise-independent scalar results.

    `params` maps every liftable *quantity* to its symbol, ordinarily
    one entry per signature parameter, but a parameter that bundles many
    scalars (a flat dataclass, or a dict accessed by literal string keys,
    see _bind_params) expands into several composite-keyed entries
    ("cfg.a", "cfg.b") instead of one. `sig_params`/`aggregate` are what
    let `f(...)` call substitution still work in terms of the *real*
    signature: `sig_params` is the actual positional parameter order,
    and `aggregate[p]` is the list of composite keys `p` expanded into
    (or `None` for an ordinary, single-symbol parameter). `opaque`, when
    this lift encountered any non-numeric value (a string, `None`, an
    Enum member, see finite_sets.py), is the registry those values
    were registered through, carried here so a claim's own law text
    can register its own literals into the *same* registry (`f(x) ==
    "positive"` needs `"positive"` to resolve to the identical symbol
    the body itself produced, not an unrelated fresh one)."""
    expr: "sympy.Expr | tuple"
    params: dict            # possibly composite-keyed name -> sympy.Symbol
    sig_params: list = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)
    unicode: str = ""
    latex: str = ""
    derived: list = field(default_factory=list)
    opaque: "OpaqueRegistry | None" = None
    branch_complete: bool = False
    # True for a full piecewise lift: expr carries EVERY branch with
    # its own symbolic guard, so it is valid at any argument, and
    # domain assumptions must never bake into its symbols (an assumed
    # sign would collapse the other branches, which is exactly the
    # single-branch unsoundness the piecewise form exists to avoid);
    # the domain acts through bound_context and pins only.


def _dataclass_fields(fn, param: str) -> list[str] | None:
    """If `param` is annotated with a real @dataclass type in fn's own
    signature, and every one of that dataclass's own fields is itself
    scalar (int/float, or unannotated), return the field names in
    declaration order, lift() then binds one symbol per field instead
    of refusing the whole function just because a bundle-of-scalars
    parameter isn't a bare scalar itself. `None` if `param` isn't
    dataclass-typed, or any of its own fields isn't itself scalar (a
    nested dataclass or a sequence-typed field stays out of scope)."""
    import dataclasses
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    p = sig.parameters.get(param)
    if p is None or not dataclasses.is_dataclass(p.annotation):
        return None
    return _dataclass_field_names(p.annotation)


def _dataclass_field_names(cls) -> "list[str] | None":
    """Intent:
        The numeric (int/float) field names of a dataclass, or None
        when any field falls outside that vocabulary, the shared
        filter behind both the annotated-parameter path and a method's
        enclosing-class expansion.
    """
    fields = []
    for f in dataclasses.fields(cls):
        t = f.type
        if isinstance(t, type) and t not in (int, float):
            return None
        if isinstance(t, str) and t.strip().lower() not in ("int", "float"):
            return None
        fields.append(f.name)
    return fields or None


def _dict_keys_used(tree: ast.FunctionDef, param: str) -> list[str]:
    """Literal string keys `param` is subscripted with anywhere in the
    body (`param["key"]`), discovered by scanning rather than
    requiring a declared type, since a plain `dict`-typed (or
    unannotated) parameter carries no static field list of its own the
    way a dataclass does. First-occurrence order, deduplicated."""
    keys: list[str] = []
    seen: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                and node.value.id == param and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str) and node.slice.value not in seen:
            seen.add(node.slice.value)
            keys.append(node.slice.value)
    return keys


def _key_chain(node: ast.Subscript, param: str) -> "list[str] | None":
    """The literal-string key chain of a subscript rooted at `param`
    (`cfg["a"]["b"]` -> ["a", "b"]), or None when the chain has a
    non-string key or is not rooted at `param`."""
    keys: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Subscript):
        s = cur.slice
        if not (isinstance(s, ast.Constant) and isinstance(s.value, str)):
            return None
        keys.append(s.value)
        cur = cur.value
    if isinstance(cur, ast.Name) and cur.id == param:
        return list(reversed(keys))
    return None


def _dict_key_tree(tree: ast.FunctionDef, param: str) -> dict:
    """The NESTED structure of literal string keys `param` is
    subscripted with: `cfg["a"]["b"]` -> {"a": {"b": {}}},
    `cfg["c"]` -> {"c": {}}. An empty dict at a key marks a leaf (a
    scalar value); a non-empty one, a nested dict. Lets a probe
    synthesise a dict whose deep keys are dicts too, so `cfg["a"]["b"]`
    does not subscript a scalar."""
    root: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            chain = _key_chain(node, param)
            if chain:
                cur = root
                for k in chain:
                    cur = cur.setdefault(k, {})
    return root


def _attr_keys_used(tree: ast.FunctionDef, param: str) -> list[str]:
    """Attribute fields `param` is READ through anywhere in the body
    (`param.rate`), the attribute counterpart of `_dict_keys_used`,
    same reasoning: an unannotated object parameter (a method's `self`
    above all) carries no static field list, so the fields the body
    actually reads ARE its scalar surface. First-occurrence order,
    deduplicated. An attribute in call position (`param.method(...)`)
    is a sibling call, not a field, and is excluded here; an attribute
    that is written, subscripted, or chained deeper is not a plain
    scalar read and is excluded too (the stateful gate refuses such
    methods before this ever matters)."""
    call_funcs = {id(node.func) for node in ast.walk(tree)
                  if isinstance(node, ast.Call)}
    deeper = {id(node.value) for node in ast.walk(tree)
              if isinstance(node, (ast.Attribute, ast.Subscript))}
    keys: list[str] = []
    seen: set = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == param
                and isinstance(node.ctx, ast.Load)
                and id(node) not in call_funcs
                and id(node) not in deeper
                and node.attr not in seen):
            seen.add(node.attr)
            keys.append(node.attr)
    return keys


def _enclosing_class(fn):
    """Intent:
        The class a method is defined on, resolved through
        `fn.__qualname__` against the function's own globals (nested
        classes walked dotted-part by dotted-part); None for a plain
        function, a local class, or anything unresolvable.
    """
    qual = getattr(fn, "__qualname__", "") or ""
    if "." not in qual:
        return None
    parts = qual.split(".")[:-1]
    if "<locals>" in parts:
        return None
    obj = (getattr(fn, "__globals__", None) or {}).get(parts[0])
    for part in parts[1:]:
        obj = getattr(obj, part, None)
    return obj if inspect.isclass(obj) else None


def _bind_params(fn, facts) -> tuple[dict, dict]:
    """One sympy Symbol per liftable quantity, ordinarily one per
    signature parameter, but a parameter that's either a flat, all-
    scalar-field dataclass (_dataclass_fields) or accessed only via
    literal-string subscripting (_dict_keys_used, dict-style) expands
    into one symbol per field/key instead, composite-keyed
    "<param>.<name>". Returns `(params, aggregate)`: `params` is the
    full possibly-expanded symbol table; `aggregate[p]` is the list of
    composite keys `p` expanded into, or `None` for an ordinary scalar
    parameter, see Lifted's docstring for why callers need both."""
    params: dict = {}
    aggregate: dict = {}
    for p in facts.params:
        fields = _dataclass_fields(fn, p)
        if fields is None and facts.tree is not None \
                and p == facts.params[0] and p in ("self", "cls"):
            # a method's self: the enclosing class stands in for the
            # missing annotation. A dataclass class gets the same
            # numeric-field vocabulary the annotated path uses (a read
            # outside it refuses the expansion); a plain simple class
            # expands by the fields the body actually reads, the
            # dict-param precedent exactly.
            cls = _enclosing_class(fn)
            read = _attr_keys_used(facts.tree, p)
            if cls is not None and dataclasses.is_dataclass(cls):
                declared = _dataclass_field_names(cls)
                fields = (read if declared is not None
                          and set(read) <= set(declared) else None)
            else:
                fields = read or None
        keys = ([f"{p}.{fld}" for fld in fields] if fields
               else [f"{p}.{k}" for k in _dict_keys_used(facts.tree, p)]
               if facts.tree is not None else [])
        if keys:
            for k in keys:
                params[k] = sympy.Symbol(k, real=True)
            aggregate[p] = keys
        else:
            # a complex-annotated parameter genuinely receives complex
            # values, so a real=True symbol would prove real-only facts
            # it doesn't have; every other scalar defaults to real.
            if facts.param_kinds.get(p) == "complex":
                params[p] = sympy.Symbol(p, complex=True)
            else:
                params[p] = sympy.Symbol(p, real=True)
            aggregate[p] = None
    return params, aggregate


def _literal_int_index(node: ast.AST) -> int | None:
    """A tuple-subscript index must be a literal int known at lift time
    (`pt[0]`, `pt[-1]`); anything computed is out of scope, since the
    lifter has no notion of a symbolic index into a fixed-length tuple."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
            and isinstance(node.operand, ast.Constant) \
            and isinstance(node.operand.value, int) \
            and not isinstance(node.operand.value, bool):
        return -node.operand.value
    return None


def _exact_numeric_literal(value: int | float) -> "sympy.Integer | sympy.Rational":
    """An int/float literal from claim text, converted without the
    binary floating-point rounding `sympy.Float`/plain `sympy.sympify`
    would introduce for a float. Python's own `str()` of a float is
    already the shortest decimal string that round-trips to it, so
    parsing that string as a `Rational` recovers the exact decimal
    value a literal like `0.05` denotes (exactly one twentieth) rather
    than IEEE-754's nearest representable neighbor of it, the two
    differ at the ~1e-17 relative level, invisible for a single
    comparison but capable of leaving a real identity's difference
    non-zero (`falsified`, not just imprecise) once raised to a
    symbolic power elsewhere in the same expression."""
    if isinstance(value, complex):
        real = sympy.Rational(str(value.real)) if value.real else sympy.Integer(0)
        return real + sympy.I * sympy.Rational(str(value.imag))
    if isinstance(value, float):
        return sympy.Rational(str(value))
    return sympy.sympify(value)


def _cond_to_sympy(node: ast.AST, env: dict, ctx: "_LiftCtx | None" = None,
                   opaque: "OpaqueRegistry | None" = None):
    """Convert a ternary expression's own condition (`x if <cond> else
    y`) to a sympy Boolean/Relational, a separate conversion from
    _expr_to_sympy's own job of converting *values*, since a condition
    needs sympy relational objects (Eq/Lt/And/...) rather than a plain
    numeric expression. Only and/or/not and a single comparison are
    recognized (the same condition vocabulary _branch_condition_truth
    understands for an `if` *statement*'s condition, though this is a
    structurally separate, domain-agnostic conversion; see
    _expr_to_sympy's IfExp case for why no domain is needed here at
    all). A bare boolean-valued name isn't supported: an ordinary
    real-valued sympy Symbol isn't itself a sympy Boolean, and there's
    no reliable way to treat one as such without already knowing it's
    boolean-typed. `ctx`, when given, lets a comparison side that's
    itself an otherwise-unsupported call attempt callee inlining, same
    as _expr_to_sympy's own Call case. `opaque`, when given, lets a
    comparison side that's a non-numeric literal (`scale == "info"`)
    resolve via the same opaque-value registry the rest of this lift
    uses, see finite_sets.py."""
    if isinstance(node, ast.BoolOp):
        parts = [_cond_to_sympy(v, env, ctx, opaque) for v in node.values]
        return sympy.And(*parts) if isinstance(node.op, ast.And) else sympy.Or(*parts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return sympy.Not(_cond_to_sympy(node.operand, env, ctx, opaque))
    if isinstance(node, ast.Compare):
        # a CHAINED comparison (`0 <= x <= 1`) is the conjunction of its
        # links, exactly as Python evaluates `(0 <= x) and (x <= 1)`;
        # ruff prefers the chain over the spelled-out `and`, so the lift
        # accepts it rather than forcing an un-chain that ruff would undo.
        operands = [node.left, *node.comparators]
        parts = []
        for i, op in enumerate(node.ops):
            relop = _SYMPY_RELOPS.get(type(op))
            if relop is None:
                raise NotSymbolic(f"unsupported comparison in condition: "
                                  f"{ast.unparse(node)!r}", category="ternary")
            left = _expr_to_sympy(operands[i], env, ctx, opaque)
            right = _expr_to_sympy(operands[i + 1], env, ctx, opaque)
            if (isinstance(left, (tuple, _SymbolicArray))
                    or isinstance(right, (tuple, _SymbolicArray))):
                raise NotSymbolic(f"cannot use a tuple or array value in a "
                                  f"condition: {ast.unparse(node)!r}",
                                  category="tuple-in-expression")
            parts.append(relop(left, right))
        return sympy.And(*parts) if len(parts) > 1 else parts[0]
    raise NotSymbolic(f"unsupported ternary condition {ast.unparse(node)!r}",
                      category="ternary")


@dataclass(frozen=True)
class _SymbolicArray:
    """A local array built from `np.linspace`/`np.arange` (see
    _lift_array_constructor): its i-th element has a known closed form
    in terms of its own `index` symbol, so no explicit Python loop is
    needed to reason about it, an already-mapped elementwise
    operation (`np.cos`, `+`, ...) applied to it just becomes that same
    operation applied to `expr`, propagated by the explicit checks in
    _expr_to_sympy's BinOp/UnaryOp/Call cases (never via Python's own
    operator-dunder fallback, see the derive-route docs for why).
    `index` is a `sympy.Dummy`, not a plain `Symbol`, so two
    independently built arrays are never accidentally treated as
    aligned just because a generic index name repeats, same
    reasoning as OpaqueRegistry's own choice (finite_sets.py)."""
    expr: sympy.Expr
    index: "sympy.Dummy"
    length: sympy.Expr


def _lift_array_constructor(name: str, node: ast.Call, env: dict,
                            ctx: "_LiftCtx", opaque: "OpaqueRegistry | None"):
    """`np.linspace(start, stop, num[, endpoint=...])`/`np.arange(start,
    stop[, step])` each build an array whose i-th element has a known
    closed form, not an elementwise numeric function the way
    `_SYMPY_FUNCS` entries are (there's no scalar input to map over),
    so this is checked before that table, not added to it. Only
    reachable when `ctx is not None` (see the ast.Call case below),
    lift_fold()/lift_dot()/lift_sum() call _expr_to_sympy without a
    ctx, a deliberate, pre-existing scope boundary this reuses rather
    than risking a _SymbolicArray leaking into their own loop-body/
    accumulator machinery, none of which knows about this type."""
    allowed_kw = {"endpoint"} if name == "linspace" else set()
    if any(kw.arg not in allowed_kw for kw in node.keywords):
        raise NotSymbolic(f"unsupported keyword argument in {ast.unparse(node)!r}",
                          category="unsupported-call")
    args = [_expr_to_sympy(a, env, ctx, opaque) for a in node.args]
    if any(isinstance(a, (tuple, _SymbolicArray)) for a in args):
        raise NotSymbolic(f"array-valued argument to {ast.unparse(node)!r} is "
                          "not supported", category="unsupported-call")
    index = sympy.Dummy("i", integer=True)
    if name == "linspace":
        if len(node.args) != 3:
            raise NotSymbolic(f"np.linspace(...) needs exactly (start, stop, "
                              f"num): {ast.unparse(node)!r}", category="unsupported-call")
        start, stop, num = args
        endpoint = True
        for kw in node.keywords:
            if not (isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool)):
                raise NotSymbolic(f"endpoint= must be a literal bool: "
                                  f"{ast.unparse(node)!r}", category="unsupported-call")
            endpoint = kw.value.value
        step = (stop - start) / (num - 1 if endpoint else num)
        length = num
    else:
        if len(node.args) not in (2, 3):
            raise NotSymbolic(f"np.arange(...) needs (start, stop) or (start, "
                              f"stop, step): {ast.unparse(node)!r}", category="unsupported-call")
        if len(node.args) == 2:
            start, stop = args
            step = sympy.Integer(1)
        else:
            start, stop, step = args
        length = sympy.ceiling((stop - start) / step)
    return _SymbolicArray(start + index * step, index, length)


def _array_elementwise_binop(op, left, right):
    """Propagate a BinOp through a _SymbolicArray operand explicitly,
    never via Python's operator-dunder fallback (see _expr_to_sympy's
    ast.BinOp case, and _SymbolicArray's own docstring for why).
    Array-with-array requires the *same* index Dummy (two independently
    built arrays are never assumed aligned, even if they happen to
    share a length); array-with-scalar broadcasts the scalar
    unchanged."""
    l_arr, r_arr = isinstance(left, _SymbolicArray), isinstance(right, _SymbolicArray)
    if l_arr and r_arr:
        if left.index != right.index:
            raise NotSymbolic(
                "combines two independently built arrays (different "
                "np.linspace/np.arange calls), only elementwise operations "
                "within the same array are supported", category="array-index-mismatch")
        return _SymbolicArray(op(left.expr, right.expr), left.index, left.length)
    if l_arr:
        return _SymbolicArray(op(left.expr, right), left.index, left.length)
    return _SymbolicArray(op(left, right.expr), right.index, right.length)


def _apply_elementwise(func, args):
    """Apply a _SYMPY_FUNCS entry across one or more _SymbolicArray args
    (`np.cos(phi)`, `np.minimum(phi, other)`, ...), propagating the
    shared index explicitly, same reasoning as
    _array_elementwise_binop."""
    arrays = [a for a in args if isinstance(a, _SymbolicArray)]
    index, length = arrays[0].index, arrays[0].length
    for a in arrays[1:]:
        if a.index != index:
            raise NotSymbolic(
                "combines two independently built arrays (different "
                "np.linspace/np.arange calls) in one call, only elementwise "
                "operations within the same array are supported",
                category="array-index-mismatch")
    plain_args = [a.expr if isinstance(a, _SymbolicArray) else a for a in args]
    return _SymbolicArray(func(*plain_args), index, length)


def _simplify_maybe_array(value):
    """sympy.simplify(), aware of _SymbolicArray, a bare _SymbolicArray
    (or one inside a tuple-return) isn't itself sympifiable, so
    simplification runs on its own `.expr` instead."""
    from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    try:
        if isinstance(value, _SymbolicArray):
            return _SymbolicArray(
                _with_timeout(lambda: sympy.simplify(value.expr),
                              FAST_TIMEOUT_SECONDS),
                value.index, value.length)
        return _with_timeout(lambda: sympy.simplify(value),
                             FAST_TIMEOUT_SECONDS)
    except Exception:
        # simplification is cosmetic; the unsimplified form is sound
        return value


def _display_value(value):
    """A renderable stand-in for sympy.pretty()/sympy.latex() output,
    _SymbolicArray isn't itself sympifiable, so its per-element formula
    (in terms of its own index symbol) stands in for the array as a
    whole; recurses into a tuple-return so a tuple containing an array
    element still renders."""
    if isinstance(value, _SymbolicArray):
        return value.expr
    if isinstance(value, tuple):
        return tuple(_display_value(v) for v in value)
    return value


def _expr_to_sympy(node: ast.AST, env: dict, ctx: "_LiftCtx | None" = None,
                   opaque: "OpaqueRegistry | None" = None):
    """Convert one real-source expression node to sympy, resolving names
    against `env` (params, plus prior local bindings during a body lift).
    Most nodes return a sympy.Expr; ast.Tuple returns a plain Python tuple
    of results instead (see Lifted's docstring), every other case
    explicitly refuses a tuple-valued operand rather than letting Python's
    own tuple arithmetic (`(a, b) + 1`, `-​(a, b)`) raise an opaque
    TypeError past this function's NotSymbolic boundary. `ctx`, when
    given (lift()/lift_conditioned()'s own body walk always supplies
    one; law/fold-update lifting elsewhere in this module still doesn't,
    leaving those call sites at their pre-existing behavior), lets an
    ast.Call this function can't otherwise resolve attempt callee
    inlining (_try_inline_callee) before giving up. `opaque`, when
    given, lets a non-numeric constant (a string, `None`, an Enum
    member) lift too, via finite_sets.py's registry, instead of always
    refusing outright, see OpaqueRegistry's own docstring for what's
    eligible and why. A constant-only *tuple* is deliberately NOT
    registered as a single opaque value here, even when `opaque` is
    given; `ast.Tuple` already has an established, tested meaning
    (multiple independent return values, see Lifted's own docstring),
    and conflating the two would silently change what `return a, b`
    means for any all-constant tuple. See the derive-route docs for
    this boundary."""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, bool) and isinstance(node.value, (int, float, complex)):
            return _exact_numeric_literal(node.value)
        if opaque is not None and is_opaque_eligible(node.value):
            return opaque.register(node.value)
        raise NotSymbolic(f"non-numeric constant {node.value!r}",
                          category="non-numeric-constant")
    if isinstance(node, ast.Name):
        if isinstance(env.get(node.id), _LocalLambda):
            raise NotSymbolic(
                f"{node.id!r} is a lambda, not a value, call it",
                category="unsupported-lambda")
        if node.id in env:
            return env[node.id]
        raise NotSymbolic(f"unbound name {node.id!r}", category="unbound-name")
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name):
            composite = f"{node.value.id}.{node.attr}"
            if composite in env:
                return env[composite]
        from ..analysis import _MATH_MODULES

        if _root_name(node.value) in _MATH_MODULES and node.attr in _MATH_ATTRS:
            return _MATH_ATTRS[node.attr]
        raise NotSymbolic(f"unsupported attribute {ast.unparse(node)!r}",
                          category="unsupported-attribute")
    if isinstance(node, ast.Tuple):
        return tuple(_expr_to_sympy(e, env, ctx, opaque) for e in node.elts)
    if isinstance(node, ast.Subscript):
        # a literal-string key on a bare parameter/local name is named-
        # dict-style field access (`params["a"]`, see _bind_params/
        # Lifted's docstring), checked before the tuple-index path,
        # since a string key can never be a valid tuple index anyway.
        if isinstance(node.value, ast.Name) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            composite = f"{node.value.id}.{node.slice.value}"
            if composite in env:
                return env[composite]
            raise NotSymbolic(f"unbound dict key {ast.unparse(node)!r}",
                              category="unbound-name")
        value = _expr_to_sympy(node.value, env, ctx, opaque)
        if isinstance(value, sympy.IndexedBase):
            # a sequence parameter bound to its own IndexedBase (see
            # lift_sum()), indexed by a *symbolic* expression, not
            # necessarily a literal, e.g. `a[i]` inside a loop over `i`.
            # Never reachable from lift()/lift_conditioned()/lift_fold()'s
            # own env construction, none of which ever bind a name to an
            # IndexedBase, only lift_sum() does, so this is additive,
            # not a behavior change for anything else.
            idx_val = _expr_to_sympy(node.slice, env, ctx, opaque)
            if isinstance(idx_val, tuple):
                raise NotSymbolic(f"cannot index {ast.unparse(node.value)!r} by a "
                                  f"tuple value: {ast.unparse(node)!r}",
                                  category="tuple-in-expression")
            return value[idx_val]
        if not isinstance(value, tuple):
            raise NotSymbolic(f"subscript on a non-tuple expression: {ast.unparse(node)!r}",
                              category="invalid-tuple-index")
        idx = _literal_int_index(node.slice)
        if idx is None or not (-len(value) <= idx < len(value)):
            raise NotSymbolic(f"tuple index out of range or not a literal "
                              f"int: {ast.unparse(node)!r}", category="invalid-tuple-index")
        return value[idx]
    if isinstance(node, ast.IfExp):
        # a bare boolean-valued name condition (`x if flag else y`) is
        # resolved directly against the domain when possible, the
        # ternary counterpart to _branch_condition_truth's own bare-name
        # case for an `if` *statement*'s condition, rather than always
        # falling through to the ordinary domain-agnostic Piecewise
        # path below. Only when `flag` is a genuine, never-reassigned
        # parameter of whichever function is currently being walked
        # (ctx.unmodified) and its declared domain pins it to exactly
        # one of {True, False} (never a numeric interval's bare
        # truthiness, same restriction _branch_condition_truth applies)
        #, otherwise falls through unchanged.
        if ctx is not None and isinstance(node.test, ast.Name) \
                and node.test.id in ctx.unmodified:
            resolved = _bare_name_truth(node.test.id, ctx.domain)
            if resolved is not None:
                return _expr_to_sympy(node.body if resolved else node.orelse, env, ctx, opaque)
        # otherwise: a ternary lifts to a sympy Piecewise unconditionally,
        # no domain needed at lift time (Piecewise is domain-agnostic
        # by construction); try_prove's own refine()/_resolve_clamps()/
        # sign-decidability chain is what later collapses it to a
        # single branch once domain assumptions are actually known,
        # the same two-stage split lift()/try_prove() already use for
        # Min/Max clamps.
        cond = _cond_to_sympy(node.test, env, ctx, opaque)
        body_val = _expr_to_sympy(node.body, env, ctx, opaque)
        else_val = _expr_to_sympy(node.orelse, env, ctx, opaque)
        if isinstance(body_val, (tuple, _SymbolicArray)) or isinstance(else_val, (tuple, _SymbolicArray)):
            raise NotSymbolic(f"cannot use a tuple or array value in a ternary "
                              f"expression: {ast.unparse(node)!r}", category="tuple-in-expression")
        return sympy.Piecewise((body_val, cond), (else_val, True))
    if isinstance(node, (ast.Compare, ast.BoolOp)) or (
            isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
        # a truth-valued expression in VALUE position (`return mi <=
        # chance`, `(a < b) * x`): Python's bool is an int, so the
        # faithful lift is the 0/1 indicator of the condition, the
        # same Piecewise shape a ternary lowers to. Every numeric
        # mechanism downstream (proving, interval evaluation,
        # sampling) then handles it as the quantity it really is.
        cond = _cond_to_sympy(node, env, ctx, opaque)
        return sympy.Piecewise((sympy.Integer(1), cond),
                               (sympy.Integer(0), True))
    if isinstance(node, ast.UnaryOp):
        v = _expr_to_sympy(node.operand, env, ctx, opaque)
        if isinstance(v, tuple):
            raise NotSymbolic(f"cannot use a tuple value in a unary operation: "
                              f"{ast.unparse(node)!r}", category="tuple-in-expression")
        if isinstance(node.op, ast.USub):
            return _SymbolicArray(-v.expr, v.index, v.length) if isinstance(v, _SymbolicArray) else -v
        if isinstance(node.op, ast.UAdd):
            return v
        raise NotSymbolic(f"unsupported unary op in {ast.unparse(node)!r}")
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise NotSymbolic(f"unsupported operator in {ast.unparse(node)!r}")
        left = _expr_to_sympy(node.left, env, ctx, opaque)
        right = _expr_to_sympy(node.right, env, ctx, opaque)
        if isinstance(left, tuple) or isinstance(right, tuple):
            raise NotSymbolic(f"cannot use a tuple value in an arithmetic "
                              f"operation: {ast.unparse(node)!r}", category="tuple-in-expression")
        if isinstance(left, _SymbolicArray) or isinstance(right, _SymbolicArray):
            return _array_elementwise_binop(op, left, right)
        return op(left, right)
    if isinstance(node, ast.Call):
        if (isinstance(node.func, ast.Name)
                and isinstance(env.get(node.func.id), _LocalLambda)
                and not node.keywords):
            lam = env[node.func.id]
            if len(node.args) != len(lam.params):
                raise NotSymbolic(
                    f"{node.func.id}() called with {len(node.args)} args, "
                    f"expected {len(lam.params)}",
                    category="unsupported-lambda")
            call_env = dict(env)
            for pname, arg in zip(lam.params, node.args):
                call_env[pname] = _expr_to_sympy(arg, env, ctx, opaque)
            return _expr_to_sympy(lam.body, call_env, ctx, opaque)
        name = _call_name(node)
        if ctx is not None and name in ("linspace", "arange"):
            return _lift_array_constructor(name, node, env, ctx, opaque)
        if name not in _SYMPY_FUNCS or node.keywords:
            if ctx is not None:
                inlined = _try_inline_callee(node, env, ctx, opaque)
                if inlined is not None:
                    return inlined
            raise NotSymbolic(_unsupported_call_message(node),
                              category="unsupported-call")
        args = [_expr_to_sympy(a, env, ctx, opaque) for a in node.args]
        if any(isinstance(a, tuple) for a in args):
            raise NotSymbolic(f"cannot pass a tuple value to a function call: "
                              f"{ast.unparse(node)!r}", category="tuple-in-expression")
        if any(isinstance(a, _SymbolicArray) for a in args):
            return _apply_elementwise(_SYMPY_FUNCS[name], args)
        return _SYMPY_FUNCS[name](*args)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp,
                         ast.GeneratorExp)):
        raise NotSymbolic(
            f"a comprehension outside the recognized sum(...) shapes: "
            f"{ast.unparse(node)!r}, sum(<generator>) derives; a "
            f"comprehension VALUE (a built list/dict) is vector-valued "
            f"and out of scope",
            category="unsupported-comprehension")
    if isinstance(node, ast.Lambda):
        raise NotSymbolic(
            f"a lambda outside the recognized shapes: "
            f"{ast.unparse(node)!r}, assign it to a local and call "
            f"it, or bind it via funcs=",
            category="unsupported-lambda")
    raise NotSymbolic(f"unsupported syntax {ast.unparse(node)!r}")


def strip_docstring(body: list) -> list:
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body



@dataclass
class _LocalLambda:
    """Intent:
        A body-local `g = lambda t: ...` held as a definition in the
        lifting environment: `params` the positional names, `body` the
        lambda's expression AST. Applied by substitution at each call
        site; a _LocalLambda escaping into value position (returned,
        used in arithmetic) is not a value and fails the lift there.
    """
    params: list
    body: object


def _walk_lift_body(body: list, env: dict, ctx: "_LiftCtx | None" = None,
                    allow_raise: bool = False, opaque: "OpaqueRegistry | None" = None):
    """Walk `body`, folding single-name assignments into `env` and
    stopping at the first Return (a value) or, only when `allow_raise`,
    lift_conditioned()'s own case, Raise (an exception). Both lift()
    and lift_conditioned() delegate here so their real behavior can't
    silently drift apart into two copies, and so a failure carries
    exactly *where* and *why* it happened rather than being collapsed
    into a bare None the moment it's caught. `ctx`, when given, is
    forwarded to every _expr_to_sympy call so a call this body makes to
    an unresolved function can attempt callee inlining. `opaque`,
    likewise, lets a non-numeric constant lift via finite_sets.py.

    Returns `(kind, value, failure)`: on success, `kind` is `"value"`
    (`value` the sympy expr or tuple of exprs) or `"raises"` (`value` the
    exception class name); on failure, `kind` is None and `failure` is
    `{"line", "statement", "message", "category"}`, `category` straight
    from the NotSymbolic that caused it (or a fixed "unsupported-
    statement"/"missing-return" for this function's own structural
    checks), never re-derived by matching the free-text message. This
    structured failure is what `inventory.derivability_report()`
    (`mathema audit --deriv-report`) uses to name the exact blocking
    construct and line for an underivable function, instead of only a
    generic "not liftable" summary."""
    for stmt in body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                and isinstance(stmt.targets[0], ast.Name) \
                and isinstance(stmt.value, ast.Lambda):
            # a body-local lambda: held as a definition, applied at its
            # call sites by direct substitution (see _expr_to_sympy's
            # Call branch), never itself a value
            lam = stmt.value
            if (lam.args.posonlyargs or lam.args.kwonlyargs
                    or lam.args.vararg or lam.args.kwarg
                    or lam.args.defaults):
                return None, None, {
                    "line": stmt.lineno, "statement": ast.unparse(stmt),
                    "message": "a lambda with non-positional parameters "
                               "is not derivable",
                    "category": "unsupported-lambda"}
            env[stmt.targets[0].id] = _LocalLambda(
                [a.arg for a in lam.args.args], lam.body)
            continue
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                and isinstance(stmt.targets[0], ast.Name):
            try:
                env[stmt.targets[0].id] = _expr_to_sympy(stmt.value, env, ctx, opaque)
            except NotSymbolic as e:
                return None, None, {"line": stmt.lineno, "statement": ast.unparse(stmt),
                                    "message": str(e), "category": e.category}
        elif isinstance(stmt, ast.Return) and stmt.value is not None:
            try:
                result = _expr_to_sympy(stmt.value, env, ctx, opaque)
            except NotSymbolic as e:
                return None, None, {"line": stmt.lineno, "statement": ast.unparse(stmt),
                                    "message": str(e), "category": e.category}
            return "value", result, None
        elif allow_raise and isinstance(stmt, ast.Raise):
            return "raises", _exc_name(stmt), None
        else:
            kind = type(stmt).__name__
            allowed = "a single-name assignment or a final return" + \
                     (" or raise" if allow_raise else "")
            return None, None, {"line": stmt.lineno, "statement": ast.unparse(stmt),
                                "message": f"a {kind} statement isn't liftable here "
                                          f"(only {allowed} is)",
                                "category": "unsupported-statement"}
    return None, None, {"line": body[-1].lineno if body else None, "statement": None,
                        "message": "function body has no return statement",
                        "category": "missing-return"}


def lift(fn, facts, max_callee_depth: int = 3, domain: dict | None = None,
        _ctx: "_LiftCtx | None" = None, _opaque: "OpaqueRegistry | None" = None) -> "Lifted | None":
    """Translate a function body to a sympy expression. Only a loop-free,
    branch-free, non-recursive, all-scalar body is attempted; everything
    else returns None rather than guessing at a closed form; this gate
    is unaffected by `domain`, which never lets *this* function's own
    branches through (that's lift_conditioned()'s job); it only ever
    widens what a *callee* can resolve, below.

    A call this body makes to a name that isn't a known math function
    (_SYMPY_FUNCS) but does resolve to a real, plain Python function;
    `_display(np.minimum(r, R_CLIP))`'s `_display`, say, isn't refused
    outright: `_try_inline_callee` recursively lifts the callee (this
    same function, one step further down) and substitutes its own
    parameters with this call site's argument expressions, up to
    `max_callee_depth` levels deep (mirrors docstring.docstring_sync()'s
    own `max_callee_depth`, the same concept applied to code/docstring
    sync rather than proof). If the callee itself has a branch, `domain`,
    `fn`'s own declared domain, over `fn`'s own parameters; lets
    `_try_inline_callee` derive a domain for the callee's parameters too
    (only for a bare-parameter-passthrough call-site argument, see
    _derive_passthrough_domain) and try lift_conditioned() on it as a
    fallback. This doesn't weaken lift()'s own contract for `fn`: the
    proof's claimed validity was already scoped to `domain` by
    try_prove()'s own quantifier-clause wrapping regardless of whether
    lift() itself consulted it, so a callee resolved this way is no less
    sound than one resolved directly in `fn`'s own body would be.
    `_ctx` is private, only `_try_inline_callee` passes it, to carry
    the shrinking depth budget and the set of already-inlined callees
    (cycle protection) down through a recursive lift() call; an external
    caller only ever sets `max_callee_depth`/`domain`. `_opaque` is
    likewise private, `_try_inline_callee` forwards the caller's own
    registry so an opaque value means the same thing throughout a
    callee-inlining chain; an external caller never sets it (a fresh
    registry is built automatically)."""
    if facts.tree is None or facts.loops or facts.branch_count or facts.recursion:
        return None
    if not facts.params or any(k == "sequence" for k in facts.param_kinds.values()):
        return None

    _sp, _sc = _method_ctx_fields(fn, facts)
    ctx = _ctx or _LiftCtx(globals_ns=getattr(fn, "__globals__", {}),
                           depth=max_callee_depth, seen=frozenset({id(fn)}),
                           domain=domain or {},
                           unmodified=frozenset(_unmodified_params(facts.tree, set(facts.params))),
                           self_param=_sp, self_class=_sc)
    opaque = _opaque if _opaque is not None else OpaqueRegistry()
    params, aggregate = _bind_params(fn, facts)
    env = dict(params)
    from ._normalize import normalized_body
    body = normalized_body(fn, facts)

    kind, result, _failure = _walk_lift_body(body, env, ctx, allow_raise=False, opaque=opaque)
    if kind != "value":
        return None

    result = (tuple(_simplify_maybe_array(r) for r in result) if isinstance(result, tuple)
             else _simplify_maybe_array(result))
    # an inlined sibling method can introduce field symbols the caller
    # itself never read (present_value reads self.face, its inlined
    # discount reads self.rate): fold them into the symbol table so
    # claim text and domains can name them like any other field
    for _sym in (set() if isinstance(result, (tuple, _SymbolicArray))
                 else getattr(result, "free_symbols", set())):
        _name = str(_sym)
        _root = _name.split(".", 1)[0]
        if "." in _name and _root in facts.params and _name not in params:
            params[_name] = _sym
            aggregate[_root] = (aggregate.get(_root) or []) + [_name]
    display = _display_value(result)
    from ..grammar import render_canonical
    return Lifted(expr=result, params=params, sig_params=list(facts.params),
                  aggregate=aggregate, unicode=render_canonical(display)[0],
                  latex=sympy.latex(display), opaque=opaque)



def _exc_name(stmt: ast.Raise) -> str | None:
    exc = stmt.exc
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id
    if isinstance(exc, ast.Name):
        return exc.id
    return None
