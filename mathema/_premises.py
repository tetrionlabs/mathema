# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's `assuming` clause as every executed route reads it.

A premise narrows the domain a claim quantifies over: a sampled point
that violates any conjunct neither confirms nor denies the claim. Three
pieces serve every route that samples points:

- `compile_premises` turns the parsed conjuncts into compiled
  comparisons, `admits` asks whether one evaluated point satisfies them
  all (an evaluation error is a rejection), and the reductions a
  premise names are computed exactly (`_exact_premises`).
- `premise_draws` and `solve_equality` put a draw on an equality
  premise's surface, which random draws essentially never reach:
  `x == c` draws c, `dim(a) == 0` the empty sequence, `det(a) == 0` a
  singular matrix, a zero spread (`std(a) == 0`, `var(a) == 0`,
  `max(a) == min(a)`) a constant sequence, and any other scalar
  equality is solved for one variable so that coordinate is computed
  from the others.
- `PremiseGuard` carries all of this to a claim family's own trials:
  it places a drawn point on the surface, decides admission, and wraps
  the function so a call at a point outside the premises raises
  `PremiseRejected` instead of running.
"""
from __future__ import annotations

import ast
import contextlib
import contextvars
import operator
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["PremiseRejected", "PremiseGuard", "compile_premises", "admits",
           "premise_draws", "solve_equality", "place_solved", "active",
           "current", "unguarded"]


class PremiseRejected(BaseException):
    """A call at a point outside the claim's premises, stopped before
    the function ran. A `BaseException` so no trial's own
    `except Exception` reads it as the function raising."""


@dataclass(frozen=True)
class Conjunct:
    """One compiled premise conjunct: both sides as code objects, the
    comparison, and the names the conjunct reads."""
    left: Any
    right: Any
    op: Callable
    names: frozenset


@dataclass(frozen=True)
class CompiledPremises:
    """Every conjunct of a premise, and the free names (neither a
    parameter nor a known function) the conjuncts read."""
    conjuncts: tuple
    aux: frozenset


def _premise_op(scalar_op, relation: str, tolerance: float, rel_tol: float):
    """Intent:
        A premise relation as the probe filters with it: `scalar_op`
        between two numbers, and between a vector or matrix and
        anything the relation element by element, a number
        broadcasting (`x != 0` holds when some element of `x` is not
        0, the vector is not the zero vector).
    """
    from ._linalg_eval import is_array
    from .probing import relation_holds_elementwise

    def op(a, b):
        if not (is_array(a) or is_array(b)):
            return scalar_op(a, b)
        return bool(relation_holds_elementwise(
            a, b, relation,
            tolerance if relation in ("==", "!=") else 0.0,
            rel_tol=rel_tol))
    return op


def _names(src: str) -> frozenset:
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        return frozenset()
    return frozenset(n.id for n in ast.walk(tree) if isinstance(n, ast.Name))


#: the names a claim reads as its tolerance
_EPSILON_NAMES = frozenset({"eps", "epsilon", "ε"})


def _epsilon_as_value(src: str, tolerance: float, kinds) -> str:
    """`src` with each `ε` (`eps`, `epsilon`) that is not a parameter
    replaced by the tolerance it names, so `assuming x ~= 1`, read as
    `abs((x) - (1)) <= ε`, filters with a number."""
    names = _EPSILON_NAMES - set(kinds)
    if not (_names(src) & names):
        return src

    class _Value(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in names:
                return ast.copy_location(ast.Constant(value=tolerance), node)
            return node
    tree = _Value().visit(ast.parse(src, mode="eval"))
    return ast.unparse(ast.fix_missing_locations(tree))


def compile_premises(cj, assumption, kinds, extra) -> CompiledPremises:
    """Intent:
        The conjuncts of `assumption` (the parsed `assuming` clause of
        `cj`) compiled over the parameters `kinds` and the bound
        function letters `extra`: `==` and `!=` compare within the
        claim's tolerance, every relation applies element by element
        to vectors and matrices.

    Raises:
        InvalidConjecture: a conjunct is not an expression the probe
            evaluates.
        KeyError: a conjunct's relation is not a comparison.
    """
    from .conjecture import DEFAULT_TOLERANCE, _declared_rel_tol, _validate
    from .probing import _close, values_differ
    tol = cj.tolerance if cj.tolerance is not None else DEFAULT_TOLERANCE
    rel = _declared_rel_tol(cj)
    conjuncts: list = []
    aux: set = set()
    for acj in assumption:
        lhs = _epsilon_as_value(acj.lhs, tol, kinds)
        rhs = _epsilon_as_value(acj.rhs, tol, kinds)
        code_l, aux_l = _validate(lhs, set(kinds), extra)
        code_r, aux_r = _validate(rhs, set(kinds), extra)
        scalar = {"<=": operator.le, ">=": operator.ge,
                  "<": operator.lt, ">": operator.gt,
                  "==": lambda a, b, t=tol, r=rel:
                      _close(a, b, tolerance=t, rel_tol=r),
                  "!=": lambda a, b, t=tol, r=rel:
                      values_differ(a, b, tolerance=t, rel_tol=r),
                  }[acj.relation]
        conjuncts.append(Conjunct(
            code_l, code_r, _premise_op(scalar, acj.relation, tol, rel),
            _names(acj.lhs) | _names(acj.rhs)))
        aux |= aux_l | aux_r
    return CompiledPremises(tuple(conjuncts), frozenset(aux))


def admits(compiled: CompiledPremises, env: dict,
           ignore: frozenset = frozenset()) -> bool:
    """Whether the point bound in `env` satisfies every conjunct of
    `compiled`, skipping a conjunct that reads a name in `ignore`. An
    evaluation error is a rejection. `env` carries the parameters, the
    function vocabulary and the exact premise words."""
    try:
        return all(
            c.op(eval(c.left, {"__builtins__": {}}, env),
                 eval(c.right, {"__builtins__": {}}, env))
            for c in compiled.conjuncts if not (c.names & ignore))
    except Exception:
        return False


_WORDS: dict = {}


def premise_words() -> dict:
    """The premise vocabulary: the claim vocabulary with its reductions
    computed exactly (`_exact_premises`)."""
    if not _WORDS:
        from ._exact_premises import premise_functions
        from ._linalg_eval import FUNCTIONS
        _WORDS.update(premise_functions(FUNCTIONS))
    return _WORDS


# --- draws on an equality premise's surface ----------------------------


def _constant(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _constant(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.Constant) \
            and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    return None


def _call_on(node, name: str, kinds) -> "tuple[str, list, dict] | None":
    """`(param, rest, keywords)` when `node` is `name(param, ...)` with
    a parameter as its first argument, else None."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == name and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in kinds):
        return (node.args[0].id, node.args[1:],
                {k.arg: k.value for k in node.keywords})
    return None


def _spread_param(node, kinds) -> "tuple[str, int] | None":
    """`(param, ddof)` when `node` measures the spread of one sequence
    parameter, zero exactly when the sequence is constant:
    `std(a, ...)`, `var(a, ...)` (ddof from the keyword or the second
    argument, 0 when absent) and `max(a) - min(a)`."""
    for name in ("std", "var"):
        found = _call_on(node, name, kinds)
        if found is None:
            continue
        p, rest, keywords = found
        if set(keywords) - {"ddof"}:
            return None
        ddof_node = keywords.get("ddof", rest[0] if rest else None)
        ddof = 0 if ddof_node is None else _constant(ddof_node)
        if not isinstance(ddof, int) or ddof < 0 or len(rest) > 1:
            return None
        return p, ddof
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
        hi = _call_on(node.left, "max", kinds)
        lo = _call_on(node.right, "min", kinds)
        if hi and lo and hi[0] == lo[0] and not (hi[1] or lo[1]
                                                  or hi[2] or lo[2]):
            return hi[0], 0
    return None


def _constant_sequence_draw(param: str, ddof: int, domain: dict):
    """A draw of a constant sequence for `param`: the length is the
    trial's planned size or the usual 2..8 band (at least `ddof + 1`),
    and the element comes from the parameter's declared element bound,
    its ends and midpoint included."""
    import math
    import random as _random

    from .probing import _synth
    bound = (domain or {}).get(param)
    corners: list = []
    if bound is not None:
        from .claim_families import _interval_ends
        ends = _interval_ends(bound)
        if ends is not None and all(math.isfinite(e) for e in ends):
            corners = [ends[0], ends[1], (ends[0] + ends[1]) / 2]

    def draw(rng: _random.Random, size):
        n = size if size is not None else rng.randint(1, 8)
        n = max(n, ddof + 1)
        if corners and rng.random() < 0.5:
            c = rng.choice(corners)
        else:
            c = _synth("float", rng, bound)
        return [c] * n
    return draw


def _band(node, kinds: dict) -> "tuple[str, float] | None":
    """`(name, centre)` when `node` is `abs(name - c)` or `abs(c - name)`
    for a scalar parameter `name` and a number `c`, else None."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "abs" and len(node.args) == 1
            and not node.keywords):
        return None
    inner = node.args[0]
    if not (isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.Sub)):
        return None
    for name, other in ((inner.left, inner.right), (inner.right, inner.left)):
        if isinstance(name, ast.Name) and name.id in kinds \
                and kinds[name.id] in ("scalar", "unknown", "float") \
                and _constant(other) is not None:
            return name.id, float(_constant(other))
    return None


def _band_draw(centre: float, width: float, bound):
    """Draws inside `[centre - width, centre + width]`, the two ends and
    the centre first among them, each kept inside the declared `bound`
    when that is an interval."""
    ends = _bound_ends(bound)

    def inside(v: float) -> float:
        if ends is None:
            return v
        lo, hi, _c_lo, _c_hi = ends
        return min(max(v, lo), hi)

    def draw(rng, size):
        u = rng.random()
        if u < 0.25:
            return inside(centre - width)
        if u < 0.5:
            return inside(centre + width)
        if u < 0.6:
            return inside(centre)
        return inside(centre + width * (2 * rng.random() - 1))
    return draw


def premise_draws(assumption, kinds: dict, domain: "dict | None" = None,
                  tolerance: "float | None" = None) -> dict:
    """Intent:
        Draws that satisfy an equality premise by construction, for the
        premises random sampling essentially never lands on, keyed by
        parameter: `dim(a) == 0` (or `dim(a, 0) == 0`) draws the empty
        sequence, `det(a) == 0` a singular square matrix, `x == c` the
        constant itself, and a zero spread (`std(a, ddof=k) == 0`,
        `var(a, ...) == 0`, `max(a) == min(a)`, `max(a) - min(a) == 0`)
        a constant sequence whose element comes from the declared
        bound in `domain`; a band `abs(x - c) <= t` (what `x ~= c`
        reads as, `t` then the claim's `tolerance`, 1e-9 by default)
        draws inside `[c - t, c + t]`, its ends first among them. Each
        draw is `draw(rng, size)`, `size` the trial's planned first-axis
        size for the parameter, or None.

    Notes:
        A length premise `dim(a) == k` for k > 0 is not here: the
        shape plan already sizes the draw. The rejection filter still
        checks every conjunct, so a draw that misses another conjunct
        is a wasted trial, never a wrong verdict.
    """
    def dim_param(node):
        found = _call_on(node, "dim", kinds)
        if found is None:
            return None
        p, rest, keywords = found
        if keywords or len(rest) > 1 or (rest and _constant(rest[0]) != 0):
            return None
        return p

    def det_param(node):
        found = _call_on(node, "det", kinds)
        return found[0] if found and not (found[1] or found[2]) else None

    def draw_for(node, c):
        if isinstance(node, ast.Name) and node.id in kinds:
            value = int(c) if kinds[node.id] == "int" \
                and float(c).is_integer() else c
            return node.id, lambda rng, size, v=value: v
        seq = dim_param(node)
        if seq is not None and c == 0:
            return seq, lambda rng, size: []
        mat = det_param(node)
        if mat is not None and c == 0:
            from .matrices import _synth_singular
            return mat, (lambda rng, size:
                         _synth_singular(size or rng.randint(1, 5), rng))
        spread = _spread_param(node, kinds)
        if spread is not None and c == 0:
            return spread[0], _constant_sequence_draw(*spread, domain or {})
        return None

    out: dict = {}
    for acj in assumption or ():
        if acj.relation in ("<=", "<") and acj.rhs:
            try:
                left = ast.parse(acj.lhs, mode="eval").body
                right = ast.parse(acj.rhs, mode="eval").body
            except SyntaxError:
                continue
            band = _band(left, kinds)
            width = _constant(right)
            if width is None and isinstance(right, ast.Name) \
                    and right.id in _EPSILON_NAMES and right.id not in kinds:
                from .conjecture import DEFAULT_TOLERANCE
                width = tolerance if tolerance is not None else DEFAULT_TOLERANCE
            if band is not None and width is not None and float(width) > 0:
                name, centre = band
                out.setdefault(name, _band_draw(centre, float(width),
                                                (domain or {}).get(name)))
            continue
        if acj.relation != "==" or not acj.rhs:
            continue
        try:
            left = ast.parse(acj.lhs, mode="eval").body
            right = ast.parse(acj.rhs, mode="eval").body
        except SyntaxError:
            continue
        hi, lo = _call_on(left, "max", kinds), _call_on(right, "min", kinds)
        if not hi:
            hi, lo = _call_on(right, "max", kinds), _call_on(left, "min", kinds)
        if hi and lo and hi[0] == lo[0] and not (hi[1] or lo[1]
                                                  or hi[2] or lo[2]):
            out.setdefault(hi[0], _constant_sequence_draw(hi[0], 0,
                                                          domain or {}))
            continue
        for side, other in ((left, right), (right, left)):
            c = _constant(other)
            found = draw_for(side, c) if c is not None else None
            if found is not None:
                out.setdefault(*found)
                break
    return out


def solve_equality(assumption, kinds) -> "tuple | None":
    """Intent:
        The first scalar equality conjunct of `assumption` solved for
        one variable, parameters first: `(name, others, compute)`, where
        `compute(*values_of_others)` is that variable's value on the
        surface. None when no equality has a single solution.

    Notes:
        Each solve runs under the fast wall-clock cap.
    """
    import sympy as _sp

    from . import _timeout as _timeout_mod
    from ._timeout import _with_timeout
    from .grammar import _node_to_sympy
    for acj in assumption or ():
        if acj.relation != "==" or not acj.rhs:
            continue
        try:
            l_expr = _node_to_sympy(ast.parse(acj.lhs, mode="eval").body, {})
            r_expr = _node_to_sympy(ast.parse(acj.rhs, mode="eval").body, {})
        except Exception:
            continue
        surface = l_expr - r_expr
        syms = {str(s): s for s in surface.free_symbols}
        for p_name in [p for p in kinds if p in syms] + \
                      [a for a in sorted(syms) if a not in kinds]:
            try:
                sols = _with_timeout(
                    lambda: _sp.solve(_sp.Eq(surface, 0), syms[p_name]),
                    _timeout_mod.FAST_TIMEOUT_SECONDS)
            except Exception:
                continue
            if len(sols) == 1:
                others = sorted(set(syms) - {p_name})
                try:
                    compute = _sp.lambdify(
                        [syms[o] for o in others], sols[0], "math")
                except Exception:
                    continue
                return p_name, others, compute
    return None


def place_solved(solved, env: dict, domain: dict) -> bool:
    """Intent:
        Put the point bound in `env` on the solved equality's surface:
        the solved variable is computed from the others and written to
        `env`. False when that value falls outside the variable's own
        declared bound (the point is not a trial); True otherwise,
        including when the value could not be computed (the filter
        then decides).
    """
    from .domain import domain_contains
    p_name, others, compute = solved
    try:
        sv = compute(*[env[o] for o in others if o in env])
    except Exception:
        sv = None
    if isinstance(sv, (int, float)) and not isinstance(sv, bool) and sv == sv:
        bound = (domain or {}).get(p_name)
        if bound is not None and not domain_contains(sv, bound):
            return False
        env[p_name] = sv
    return True


# --- the guard a claim family's trials run under -----------------------


@dataclass
class PremiseGuard:
    """Intent:
        A claim's premises as a claim family's own trials apply them:
        `place` puts a drawn point on an equality premise's surface,
        `admits_point` decides whether a point is inside the premises,
        and `wrap` returns the function guarded so a call outside them
        raises `PremiseRejected` without running. `admitted` and
        `rejected` count the points decided.

    Notes:
        `ignore` names parameters whose conjuncts are not applied: a
        family whose trials deliberately set a parameter outside the
        domain (a missing value, the empty sequence, a string off the
        corpus) still has its other parameters held to the premises.
    """
    compiled: CompiledPremises
    params: tuple
    domain: dict
    draws: dict = field(default_factory=dict)
    solved: "tuple | None" = None
    base_env: dict = field(default_factory=dict)
    array_params: frozenset = frozenset()
    bind_env: "Callable | None" = None
    ignore: frozenset = frozenset()
    seed: int = 0
    admitted: int = 0
    rejected: int = 0

    def __post_init__(self):
        import random as _random
        self._aux_rng = _random.Random(self.seed)

    def env_for(self, point: dict) -> dict:
        """The evaluation namespace of the premises at `point`."""
        from . import _linalg_eval
        env = dict(self.base_env)
        for p, v in point.items():
            if p in self.array_params and isinstance(v, (list, tuple)):
                try:
                    v = _linalg_eval.as_array(v)
                except Exception:
                    pass
            env[p] = v
        if self.bind_env is not None:
            try:
                self.bind_env(env, {p: point[p] for p in self.params
                                    if p in point})
            except Exception:
                pass
        for a_name in self.compiled.aux:
            if a_name not in env:
                env[a_name] = self._aux_rng.uniform(-5, 5)
        return {**env, **premise_words()}

    def admits_point(self, point: dict) -> bool:
        """Whether `point` (parameter to value) is inside the premises;
        counted in `admitted` or `rejected`."""
        ok = admits(self.compiled, self.env_for(point), self.ignore)
        if ok:
            self.admitted += 1
        else:
            self.rejected += 1
        return ok

    def place(self, point: dict, rng, only: "frozenset | None" = None,
              solve: bool = True) -> "dict | None":
        """`point` with each premise-drawn parameter redrawn on its
        surface and, when `solve`, the solved equality's variable
        computed from the others; `only` limits the redrawn parameters.
        None when the solved value falls outside its declared bound."""
        placed = dict(point)
        for p, draw in self.draws.items():
            if p in placed and p not in self.ignore \
                    and (only is None or p in only):
                placed[p] = draw(rng, None)
        if solve and self.solved is not None \
                and self.solved[0] in placed and self.solved[0] not in self.ignore \
                and (only is None or self.solved[0] in only):
            if not place_solved(self.solved, placed, self.domain):
                return None
        return placed

    def place_args(self, args: list, rng, only=None,
                   solve: bool = True) -> "list | None":
        """`place` for positional values in parameter order."""
        placed = self.place(dict(zip(self.params, args)), rng, only, solve)
        if placed is None:
            return None
        return [placed.get(p, a) for p, a in zip(self.params, args)] \
            + list(args[len(self.params):])

    def wrap(self, fn):
        """`fn` guarded by the premises (see `PremiseRejected`)."""
        return _Guarded(fn, self)


class _Guarded:
    """A callable that runs its function only at a point inside the
    guard's premises; attributes and the signature are the function's
    own."""

    def __init__(self, fn, guard: PremiseGuard):
        self.__wrapped__ = fn
        self._premise_guard = guard

    def __call__(self, *args, **kwargs):
        guard = self._premise_guard
        point = dict(zip(guard.params, args))
        point.update({k: v for k, v in kwargs.items() if k in guard.params})
        if not guard.admits_point(point):
            raise PremiseRejected()
        return self.__wrapped__(*args, **kwargs)

    def __getattr__(self, name):
        if name in ("__wrapped__", "_premise_guard"):
            raise AttributeError(name)
        return getattr(self.__wrapped__, name)


def unguarded(fn):
    """`fn` without a premise guard around it."""
    while isinstance(fn, _Guarded):
        fn = fn.__wrapped__
    return fn


_ACTIVE: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_premise_guard", default=None)


@contextlib.contextmanager
def active(guard: "PremiseGuard | None"):
    """Make `guard` the one `current()` returns inside the block."""
    token = _ACTIVE.set(guard)
    try:
        yield guard
    finally:
        _ACTIVE.reset(token)


def current() -> "PremiseGuard | None":
    """The premise guard of the claim whose family trials are running,
    or None."""
    return _ACTIVE.get()


# --- a premise read as a narrower domain -------------------------------


def _bound_ends(bound) -> "tuple[float, float, bool, bool] | None":
    """`(lo, hi, closed_lo, closed_hi)` of a scalar interval bound (None
    reads as the whole real line), None for any other bound shape."""
    import math

    from .domain import Domain, _sentinel_piece, numeric_excluded
    if bound is None:
        return -math.inf, math.inf, False, False
    if isinstance(bound, Domain) and bound.base_type == "R" \
            and not [p for p in bound.pieces if not _sentinel_piece(p)] \
            and not numeric_excluded(bound) and not bound.dims:
        return -math.inf, math.inf, False, False
    if isinstance(bound, tuple) and len(bound) == 2 \
            and all(isinstance(e, (int, float)) and not isinstance(e, bool)
                    for e in bound):
        return (float(bound[0]), float(bound[1]),
                getattr(bound, "closed_lo", True),
                getattr(bound, "closed_hi", True))
    return None


def narrowed_domain(domain: dict, assumption, kinds,
                    keep: frozenset = frozenset()) -> "tuple[dict, bool]":
    """Intent:
        The declared `domain` with each premise conjunct that bounds one
        scalar parameter by a number (`x > 0.5`, `2 >= y`, `x == 0`)
        folded into that parameter's interval, parameters in `keep`
        left as declared. Returns `(domain, complete)`: `complete` is
        True when every conjunct was folded, so the returned domain is
        exactly the premise region; otherwise the returned domain
        contains it.

    Notes:
        A conjunct is `(lhs, relation, rhs)` source text. Only an
        interval bound (or none) narrows; a union, an exclusion, a
        discrete set or a vector space stays as declared and leaves the
        result incomplete, as does an empty intersection.
    """
    import math

    from .domain import Interval
    out = dict(domain or {})
    complete = True
    flip = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "=="}
    for lhs, rel, rhs in assumption or ():
        try:
            left = ast.parse(lhs, mode="eval").body
            right = ast.parse(rhs, mode="eval").body
        except (SyntaxError, TypeError):
            complete = False
            continue
        if isinstance(left, ast.Name) and _constant(right) is not None:
            name, value, op = left.id, _constant(right), rel
        elif isinstance(right, ast.Name) and _constant(left) is not None \
                and rel in flip:
            name, value, op = right.id, _constant(left), flip[rel]
        else:
            complete = False
            continue
        if name not in kinds or name in keep or op not in flip \
                or kinds.get(name) not in ("scalar", "unknown", "int",
                                            "float"):
            complete = False
            continue
        ends = _bound_ends(out.get(name))
        if ends is None:
            complete = False
            continue
        lo, hi, c_lo, c_hi = ends
        v = float(value)
        if op in (">", ">=", "==") and (v > lo or (v == lo and op == ">")):
            lo, c_lo = v, op != ">"
        if op in ("<", "<=", "==") and (v < hi or (v == hi and op == "<")):
            hi, c_hi = v, op != "<"
        if lo > hi or (lo == hi and not (c_lo and c_hi)):
            complete = False
            continue
        out[name] = Interval(lo, hi, closed_lo=c_lo and math.isfinite(lo),
                             closed_hi=c_hi and math.isfinite(hi))
    return out, complete
