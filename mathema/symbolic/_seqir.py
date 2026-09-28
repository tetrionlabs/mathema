# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Lowering claims about vectors to sums over a sequence of symbolic
length.

A vector parameter `x` of length `L` is the sequence `x[0], ...,
x[L - 1]`; a vector-valued expression is represented by its element at
position `i` (`c*x[i]` for `c * x`) together with its length, and a
reduction closes the index into a sum over every position:

| claim word | lowering |
|---|---|
| `sum(v)` | `Sum(v[i], (i, 0, L - 1))` |
| `mean(v)` | `sum(v) / L` |
| `var(v, ddof=k)` | `Sum((v[i] - mean(v))**2) / (L - k)`, defined for `L > k` |
| `std(v, ddof=k)` | `sqrt(var(v, ddof=k))` |
| `prod(v)` | `Product(v[i], (i, 0, L - 1))` |
| `count(v)`, `len(v)`, `dim(v)` | `L` |
| `cumsum(v)`, `cumprod(v)` | the vector whose element `i` is the sum (product) of `v[0..i]` |
| `dot(v, w)`, `v @ w` | `Sum(v[i]*w[i])` |
| `min(v)`, `max(v)` | a number known through its bounds (see below) |
| `cummax(v)`, `cummin(v)` | a fresh sequence `m` known through its bounds (see below) |

Arithmetic between vectors, and between a vector and a number, acts
element by element; dividing by a vector divides element by element,
and needs each element of the divisor to be nonzero.

A least element, a greatest element and a running extremum have no
closed form as a sum, so each lowers to a fresh symbol that `Bounds`
knows only through facts: `min(v)` is at most every element of `v`
and is one of them, so it is at most `mean(v)`; `cummax(v)[i]` is at
least `v[i]` and is one of `v[0..i]`, so it lies within `v`'s element
bounds, and for a positive `v`, `0 < v[i] / cummax(v)[i] <= 1`
(`cummin` mirrors each). `order_by_bounds` decides an ordering that
involves them from those facts alone. A law transform a claim binds (`let s =
mathema.f.scale_seq`) and a reversal (`returns[::-1]`) rewrite every
element of the sequence they act on by structural replacement, and a
transform that changes nothing is refused rather than read as the
identity.

sympy does not split a sum over `+` or pull a constant out of it, so
`linear_sums` does: `Sum(c*x[i] + k)` becomes `c*Sum(x[i]) + k*L`,
a product's constant factors become powers (`Product(c*x[i])` is
`c**L * Product(x[i])`), and a sum read in reverse order is read
forward. Each sum's index is renamed by its nesting depth, so two sums
over the same terms compare equal.

Where a lowered expression has no value (a division by a quantity that
can be zero, a variance of fewer than `ddof + 1` positions), the
lowering records an obligation; a proof stands only where every
obligation is met by the claim's premises (see `Obligations`).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

import sympy

from .._math_vocab import _SYMPY_FUNCS
from ._base import NotSymbolic, _exact_numeric_literal
from ._seq_common import map_sequence_elements

#: the index a vector-valued expression's element is written at
INDEX = sympy.Symbol("i", integer=True, nonnegative=True)

#: the claim words whose argument is a vector and whose value a number
REDUCTIONS = frozenset({"sum", "mean", "var", "std", "prod", "count",
                        "len", "dim"})
#: running reductions: a vector of partial sums or products
RUNNING = frozenset({"cumsum", "cumprod"})
#: the least and greatest element of a vector
EXTREMA = frozenset({"min", "max"})
#: running extrema: a vector of partial maxima or minima
RUNNING_EXTREMA = frozenset({"cummax", "cummin"})
#: elementwise functions a vector is mapped through, and the sign
#: their argument needs for a value: sqrt a nonnegative argument, log a
#: positive one
_NEEDS_SIGN = {"sqrt": "nonnegative", "log": "positive",
               "log2": "positive", "log10": "positive"}
_ELEMENTWISE = frozenset({"abs", "Abs", "exp", "sin", "cos", "tan",
                          "sinh", "cosh", "tanh", "float"}) \
    | frozenset(_NEEDS_SIGN)


@dataclass(frozen=True)
class Vec:
    """A vector-valued expression: its element at `INDEX`, and the
    length symbol of the sequence it runs over."""
    elem: sympy.Expr
    length: sympy.Expr


@dataclass
class Obligations:
    """Intent:
        What a lowered expression needs in order to have a value:
        `min_length` maps a length symbol to the fewest positions the
        expression is defined for, and `nonzero` lists each quantity
        it divides by, as `(expression, claim text)`.
    """
    min_length: dict = field(default_factory=dict)
    nonzero: list = field(default_factory=list)

    def need_length(self, length, least: int) -> None:
        if isinstance(length, sympy.Symbol):
            self.min_length[length] = max(self.min_length.get(length, 1),
                                          least)

    def merge(self, other: "Obligations") -> None:
        for sym, least in other.min_length.items():
            self.need_length(sym, least)
        self.nonzero.extend(other.nonzero)


def _sign_kwargs(e) -> dict:
    """The sympy sign assumptions an expression's own assumptions
    entail, for a symbol that takes one of its values."""
    if e.is_positive:
        return {"positive": True}
    if e.is_negative:
        return {"negative": True}
    if e.is_nonnegative:
        return {"nonnegative": True}
    if e.is_nonpositive:
        return {"nonpositive": True}
    return {}


class Bounds:
    """Intent:
        What one claim's lowering knows about the quantities with no
        closed form: `elements` maps a sequence's `IndexedBase` to the
        domain its elements are drawn from (a `Domain` without axes,
        or None); `extremum(kind, v)` is the symbol for `min(v)` or
        `max(v)` and `running(kind, v)` the `IndexedBase` for
        `cummax(v)` or `cummin(v)`, one per distinct vector, shared by
        every side of the claim lowered with this book.
    """

    def __init__(self, elements: "dict | None" = None):
        self.elements = dict(elements or {})
        self.extrema: dict = {}
        self.running_bases: dict = {}
        self._extremum_keys: dict = {}
        self._running_keys: dict = {}

    def extremum(self, kind: str, v: "Vec", text: str):
        key = (kind, v.elem, v.length)
        if key not in self._extremum_keys:
            sym = sympy.Symbol(f"{kind}({text})", real=True,
                               **_sign_kwargs(v.elem))
            self._extremum_keys[key] = sym
            self.extrema[sym] = (kind, v)
        return self._extremum_keys[key]

    def running(self, kind: str, v: "Vec", text: str):
        key = (kind, v.elem, v.length)
        if key not in self._running_keys:
            base = sympy.IndexedBase(f"{kind}({text})", real=True,
                                     **_sign_kwargs(v.elem))
            self._running_keys[key] = base
            self.running_bases[base] = (kind, v)
        return self._running_keys[key]


def _fresh_index():
    return sympy.Dummy("k", integer=True, nonnegative=True)


def _reduce(kind, elem, length):
    j = _fresh_index()
    body = elem.xreplace({INDEX: j})
    if kind == "sum":
        return sympy.Sum(body, (j, 0, length - 1))
    return sympy.Product(body, (j, 0, length - 1))


def _running(kind, elem, length):
    j = _fresh_index()
    body = elem.xreplace({INDEX: j})
    op = sympy.Sum if kind == "cumsum" else sympy.Product
    return Vec(op(body, (j, 0, INDEX)), length)


def _reverse(value: Vec, base_lengths: dict) -> Vec:
    """Every element `x[k]` of every sequence in `value` read at
    `x[L - 1 - k]`."""
    elements = [e for e in value.elem.atoms(sympy.Indexed)
                if e.base in base_lengths]
    if not elements:
        raise NotSymbolic("the reversal leaves the expression unchanged: "
                          "no element of a sequence appears in it")
    mapped = value.elem.xreplace({
        e: e.base[base_lengths[e.base] - 1 - e.indices[0]]
        for e in elements})
    return Vec(mapped, value.length)


class Lowering:
    """Intent:
        The lowering of one claim: `seqs` maps each vector name to its
        `(IndexedBase, length symbol)`, `scalars` each number name to
        its symbol, `transforms` each bound law transform name to
        `("scale" | "shift" | "reverse")`. `lower(node)` returns a
        sympy number or a `Vec`, recording what it needs in
        `obligations`.

    Raises:
        NotSymbolic: from `lower`, for a construct outside the
            lowering, naming it.
    """

    def __init__(self, seqs: dict, scalars: dict, transforms: dict,
                 bounds: "Bounds | None" = None):
        self.seqs = seqs
        self.scalars = scalars
        self.transforms = transforms
        self.bounds = bounds if bounds is not None else Bounds()
        self.obligations = Obligations()
        self._bases = {ib: length for ib, length in seqs.values()}

    def lower(self, node):
        if isinstance(node, ast.Expression):
            return self.lower(node.body)
        if isinstance(node, ast.Constant) and not isinstance(node.value,
                                                             bool) \
                and isinstance(node.value, (int, float)):
            return _exact_numeric_literal(node.value)
        if isinstance(node, ast.Name):
            if node.id in self.seqs:
                ib, length = self.seqs[node.id]
                return Vec(ib[INDEX], length)
            if node.id in self.scalars:
                return self.scalars[node.id]
            if node.id == "pi":
                return sympy.pi
            raise NotSymbolic(f"the name {node.id!r} has no value here")
        if isinstance(node, ast.UnaryOp):
            v = self.lower(node.operand)
            if isinstance(node.op, ast.USub):
                return Vec(-v.elem, v.length) if isinstance(v, Vec) else -v
            if isinstance(node.op, ast.UAdd):
                return v
        if isinstance(node, ast.BinOp):
            return self._binop(node)
        if isinstance(node, ast.Subscript):
            return self._subscript(node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return self._call(node)
        raise NotSymbolic(f"{ast.unparse(node)!r} is outside the sequence "
                          f"lowering")

    # arithmetic

    def _binop(self, node: ast.BinOp):
        left, right = self.lower(node.left), self.lower(node.right)
        if isinstance(node.op, ast.MatMult):
            if isinstance(left, Vec) and isinstance(right, Vec):
                return self._dot(left, right, node)
            raise NotSymbolic(f"{ast.unparse(node)!r}: `@` needs two "
                              f"vectors here")
        ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
               ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
               ast.Pow: lambda a, b: a ** b}
        op = ops.get(type(node.op))
        if op is None:
            raise NotSymbolic(f"unsupported operator in "
                              f"{ast.unparse(node)!r}")
        if isinstance(node.op, ast.Div):
            self._divides_by(right.elem if isinstance(right, Vec)
                             else right, node.right)
        if isinstance(node.op, ast.Pow):
            if isinstance(right, Vec):
                raise NotSymbolic(f"{ast.unparse(node)!r}: a vector "
                                  f"exponent is outside the lowering")
            if not (right.is_integer and right.is_nonnegative):
                raise NotSymbolic(f"{ast.unparse(node)!r}: only a whole, "
                                  f"nonnegative power is lowered")
        if isinstance(left, Vec) or isinstance(right, Vec):
            length = self._same_length(left, right, node)
            le = left.elem if isinstance(left, Vec) else left
            re_ = right.elem if isinstance(right, Vec) else right
            return Vec(op(le, re_), length)
        return op(left, right)

    def _same_length(self, left, right, node):
        lengths = {v.length for v in (left, right) if isinstance(v, Vec)}
        if len(lengths) != 1:
            raise NotSymbolic(f"{ast.unparse(node)!r} combines vectors of "
                              f"lengths that are not known to be equal")
        return next(iter(lengths))

    def _divides_by(self, value, node) -> None:
        if value.is_nonzero:
            return
        self.obligations.nonzero.append((value, ast.unparse(node)))

    def _dot(self, left: Vec, right: Vec, node):
        length = self._same_length(left, right, node)
        return _reduce("sum", left.elem * right.elem, length)

    # vector forms

    def _subscript(self, node: ast.Subscript):
        value = self.lower(node.value)
        if not isinstance(value, Vec):
            raise NotSymbolic(f"{ast.unparse(node)!r}: only a vector is "
                              f"indexed")
        s = node.slice
        if isinstance(s, ast.Slice) and s.lower is None and s.upper is None \
                and isinstance(s.step, ast.UnaryOp) \
                and isinstance(s.step.op, ast.USub) \
                and isinstance(s.step.operand, ast.Constant) \
                and s.step.operand.value == 1:
            return _reverse(value, self._bases)
        raise NotSymbolic(f"{ast.unparse(node)!r}: only the reversal "
                          f"`[::-1]` of a vector is lowered")

    # calls

    def _call(self, node: ast.Call):
        name = node.func.id
        if name in self.transforms:
            return self._transform(name, node)
        keywords = {k.arg: k.value for k in node.keywords}
        if name == "dim" and len(node.args) == 2 and not keywords \
                and isinstance(node.args[1], ast.Constant) \
                and node.args[1].value == 0:
            v = self.lower(node.args[0])
            if isinstance(v, Vec):
                return v.length
            raise NotSymbolic(f"{ast.unparse(node.args[0])!r} is not a "
                              f"vector")
        if name in REDUCTIONS or name in RUNNING:
            if len(node.args) != 1 or set(keywords) - {"ddof"} \
                    or (keywords and name not in ("std", "var")):
                raise NotSymbolic(f"{ast.unparse(node)!r}: one vector "
                                  f"argument (and `ddof=` on std and var) "
                                  f"is lowered")
            v = self.lower(node.args[0])
            if not isinstance(v, Vec):
                raise NotSymbolic(f"{ast.unparse(node.args[0])!r} is not a "
                                  f"vector")
            if name in RUNNING:
                return _running(name, v.elem, v.length)
            return self._reduction(name, v, keywords.get("ddof"), node)
        if name in EXTREMA and node.args and not keywords:
            values = [self.lower(a) for a in node.args]
            if len(values) == 1 and isinstance(values[0], Vec):
                return self.bounds.extremum(name, values[0],
                                            ast.unparse(node.args[0]))
            if len(values) > 1 and not any(isinstance(v, Vec)
                                           for v in values):
                return (sympy.Min if name == "min" else sympy.Max)(*values)
            raise NotSymbolic(f"{ast.unparse(node)!r}: {name} of one vector, "
                              f"or of several numbers, is lowered")
        if name in RUNNING_EXTREMA:
            if len(node.args) != 1 or keywords:
                raise NotSymbolic(f"{ast.unparse(node)!r}: one vector "
                                  f"argument is lowered")
            v = self.lower(node.args[0])
            if not isinstance(v, Vec):
                raise NotSymbolic(f"{ast.unparse(node.args[0])!r} is not a "
                                  f"vector")
            base = self.bounds.running(name, v, ast.unparse(node.args[0]))
            return Vec(base[INDEX], v.length)
        if name == "dot" and len(node.args) == 2 and not keywords:
            left, right = (self.lower(a) for a in node.args)
            if isinstance(left, Vec) and isinstance(right, Vec):
                return self._dot(left, right, node)
            raise NotSymbolic(f"{ast.unparse(node)!r}: dot needs two "
                              f"vectors here")
        if name in _ELEMENTWISE and len(node.args) == 1 and not keywords:
            v = self.lower(node.args[0])
            fn = (lambda e: e) if name == "float" else _SYMPY_FUNCS[name]
            if isinstance(v, Vec):
                if name in _NEEDS_SIGN:
                    raise NotSymbolic(f"{ast.unparse(node)!r}: {name} of a "
                                      f"vector needs every element's sign")
                return Vec(fn(v.elem), v.length)
            sign = _NEEDS_SIGN.get(name)
            if sign == "nonnegative" and v.is_nonnegative is not True:
                raise NotSymbolic(f"{ast.unparse(node)!r}: the argument of "
                                  f"sqrt is not known to be nonnegative")
            if sign == "positive" and v.is_positive is not True:
                raise NotSymbolic(f"{ast.unparse(node)!r}: the argument of "
                                  f"{name} is not known to be positive")
            return fn(v)
        raise NotSymbolic(f"{ast.unparse(node)!r} is outside the sequence "
                          f"lowering")

    def _reduction(self, name: str, v: Vec, ddof_node, node):
        length = v.length
        if name in ("count", "len", "dim"):
            return length
        if name == "sum":
            return _reduce("sum", v.elem, length)
        if name == "prod":
            return _reduce("prod", v.elem, length)
        mean = _reduce("sum", v.elem, length) / length
        if name == "mean":
            return mean
        ddof = 0
        if ddof_node is not None:
            try:
                ddof = ast.literal_eval(ddof_node)
            except (ValueError, SyntaxError):
                ddof = None
            if not isinstance(ddof, int) or isinstance(ddof, bool) \
                    or ddof < 0:
                raise NotSymbolic(f"{ast.unparse(node)!r}: ddof must be a "
                                  f"whole, nonnegative literal")
        self.obligations.need_length(length, ddof + 1)
        var = _reduce("sum", (v.elem - mean) ** 2, length) / (length - ddof)
        return var if name == "var" else sympy.sqrt(var)

    def _transform(self, name: str, node: ast.Call):
        kind = self.transforms[name]
        want = 1 if kind == "reverse" else 2
        if len(node.args) != want or node.keywords:
            raise NotSymbolic(f"{ast.unparse(node)!r}: the transform takes "
                              f"{want} argument(s)")
        v = self.lower(node.args[0])
        if not isinstance(v, Vec):
            raise NotSymbolic(f"{ast.unparse(node.args[0])!r} is not a "
                              f"vector")
        if kind == "reverse":
            return _reverse(v, self._bases)
        c = self.lower(node.args[1])
        if isinstance(c, Vec):
            raise NotSymbolic(f"{ast.unparse(node.args[1])!r}: the "
                              f"transform's constant must be a number")
        mapper = (lambda e, k: k * e) if kind == "scale" \
            else (lambda e, k: e + k)
        elem = v.elem
        for base in {e.base for e in elem.atoms(sympy.Indexed)
                     if e.base in self._bases}:
            elem = map_sequence_elements(elem, base, mapper, (c,))
        if elem == v.elem:
            raise NotSymbolic(f"{ast.unparse(node)!r} leaves the vector "
                              f"unchanged")
        return Vec(elem, v.length)


# the normaliser

def _split_sum(s):
    """One sum split over `+`, each term's index-free factors pulled
    out, and the sum of an index-free term counted."""
    if len(s.limits) != 1:
        return s
    (var, lo, hi), = s.limits
    out = sympy.S.Zero
    for term in sympy.Add.make_args(sympy.expand(s.function)):
        factors = sympy.Mul.make_args(term)
        dep = [a for a in factors if var in a.free_symbols]
        ind = [a for a in factors if var not in a.free_symbols]
        count = hi - lo + 1
        out += sympy.Mul(*ind) * (sympy.Sum(sympy.Mul(*dep), (var, lo, hi))
                                  if dep else count)
    return out


def _split_product(p):
    """One product's index-free factors taken out as powers of the
    number of terms."""
    if len(p.limits) != 1:
        return p
    (var, lo, hi), = p.limits
    factors = sympy.Mul.make_args(sympy.factor_terms(p.function))
    dep = [a for a in factors if var in a.free_symbols]
    ind = [a for a in factors if var not in a.free_symbols]
    count = hi - lo + 1
    rest = sympy.Product(sympy.Mul(*dep), (var, lo, hi)) if dep \
        else sympy.S.One
    return sympy.Mul(*[a ** count for a in ind]) * rest


def _read_forward(s, lengths: dict):
    """A sum or product over `0..L-1` whose every element is read at
    `x[L - 1 - k]`, read at `x[k]` instead (the same terms in the
    other order)."""
    if len(s.limits) != 1:
        return s
    (var, lo, hi), = s.limits
    if lo != 0:
        return s
    elements = [e for e in s.function.atoms(sympy.Indexed)
                if e.base in lengths and var in e.free_symbols]
    if not elements or any(
            sympy.expand(e.indices[0] - (lengths[e.base] - 1 - var)) != 0
            or sympy.expand(hi - (lengths[e.base] - 1)) != 0
            for e in elements):
        return s
    return type(s)(s.function.xreplace({var: hi - var}), (var, lo, hi))


def _canonical_indices(e, depth: int = 0):
    """`e` with each sum's and product's index renamed by its nesting
    depth, so equal sums are equal expressions."""
    if isinstance(e, (sympy.Sum, sympy.Product)):
        rename = {var: sympy.Symbol(f"_k{depth + n}", integer=True,
                                    nonnegative=True)
                  for n, (var, _lo, _hi) in enumerate(e.limits)}
        function = e.function.xreplace(rename)
        limits = [(rename[var], lo.xreplace(rename), hi.xreplace(rename))
                  for var, lo, hi in e.limits]
        inner = _canonical_indices(function, depth + len(limits))
        return type(e)(inner, *[(v, _canonical_indices(lo, depth),
                                 _canonical_indices(hi, depth))
                                for v, lo, hi in limits])
    if not e.args or isinstance(e, (sympy.Indexed, sympy.Symbol)):
        return e
    return e.func(*[_canonical_indices(a, depth) for a in e.args])


def linear_sums(e, lengths: "dict | None" = None):
    """Intent:
        `e` with every sum split over `+`, every index-free factor
        pulled out of a sum or a product, `Sum(k) = k * (number of
        terms)`, reversed reads made forward, and indices renamed
        canonically; repeated until nothing changes.
    """
    lengths = lengths or {}
    prev = None
    e = _canonical_indices(e)
    while prev != e:
        prev = e
        e = e.replace(lambda s: isinstance(s, (sympy.Sum, sympy.Product)),
                      lambda s: _read_forward(s, lengths))
        e = e.replace(lambda s: isinstance(s, sympy.Sum), _split_sum)
        e = e.replace(lambda s: isinstance(s, sympy.Product), _split_product)
        e = _canonical_indices(e)
    return e


def normalised(e, lengths: "dict | None" = None):
    """`linear_sums` of `e`, simplified."""
    e = linear_sums(e, lengths)
    try:
        e = sympy.simplify(e)
    except Exception:
        return e
    return _canonical_indices(e)


# orderings through the bounds of extrema

_FLIP = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}


def _free_elements(e, lengths) -> list:
    """The elements of sequences `e` reads outside any sum: `x[i]`,
    `x[L - 1 - i]`, `x[0]`, but not the `x[k]` a sum runs over."""
    allowed = {INDEX} | set(lengths)
    return [a for a in e.atoms(sympy.Indexed)
            if a.indices[0].free_symbols <= allowed]


def _element_domain(bounds: Bounds, base, depth: int = 0):
    """The domain every element of `base` lies in: a sequence's own
    element domain, and for a running extremum the domain of the plain
    sequence it runs over (it is one of that sequence's elements)."""
    if base in bounds.elements:
        return bounds.elements[base]
    if base in bounds.running_bases and depth < 8:
        _kind, v = bounds.running_bases[base]
        if isinstance(v.elem, sympy.Indexed) and v.elem.indices[0] == INDEX:
            return _element_domain(bounds, v.elem.base, depth + 1)
    return None


def _elementwise(e, strict: bool, bounds: Bounds, lengths, context: dict,
                 extensive: bool) -> "tuple[bool, str]":
    """Intent:
        Whether `e >= 0` (`e > 0` when `strict`) holds at every
        position `i`: each element `e` reads is replaced by a number
        bounded as that element is, a running extremum `m = cummax(v)`
        at `i` by `v[i] + d` with `d >= 0` (`cummin`: `v[i] - d`), and a
        ratio `v[i] / m[i]` of a positive `v` by a number in `(0, 1]`
        (`cummin`: at least 1); the relation is then decided over those
        numbers. Returns `(proven, the facts used)`.

    Notes:
        The replacement forgets how the numbers relate beyond the
        facts stated, so a proof over them holds for the elements; a
        relation that is not proven here may still be true.
    """
    from ..domain import Interval
    from ._proof_support import _domain_assumptions, _prove_relation
    params = dict(context.get("params") or {})
    domain = dict(context.get("domain") or {})
    used: list = []
    names = iter(range(10 ** 6))

    def fresh(bound):
        name = f"_b{next(names)}"
        sym = sympy.Symbol(name, real=True)
        params[name] = sym
        if bound is not None:
            domain[name] = bound
        return sym
    for base, (kind, v) in bounds.running_bases.items():
        m = base[INDEX]
        if m not in e.atoms(sympy.Indexed):
            continue
        sign = v.elem.is_positive
        if sign:
            ratio = fresh(Interval(0, 1, False, True) if kind == "cummax"
                          else Interval(1, sympy.oo, True, False))
            replaced = e.subs(v.elem / m, ratio)
            if replaced != e:
                e = replaced
                used.append(f"0 < {v.elem} / {base}[i] <= 1"
                            if kind == "cummax"
                            else f"{v.elem} / {base}[i] >= 1")
        if m in e.atoms(sympy.Indexed):
            slack = fresh(Interval(0, sympy.oo, True, False))
            e = e.xreplace({m: v.elem + slack if kind == "cummax"
                            else v.elem - slack})
            used.append(f"{base}[i] {'>=' if kind == 'cummax' else '<='} "
                        f"{v.elem}")
    for atom in _free_elements(e, lengths):
        dom = _element_domain(bounds, atom.base)
        e = e.xreplace({atom: fresh(dom)})
    for sym, (kind, v) in bounds.extrema.items():
        if sym in e.free_symbols:
            e = e.xreplace({sym: fresh(None)})
    if any(isinstance(a, sympy.Indexed) and a.indices[0].has(INDEX)
           for a in e.atoms(sympy.Indexed)):
        return False, "an element is read at a position the facts do not bound"
    subs, ctx, assumed, pins = _domain_assumptions(params, domain)
    e = e.xreplace(subs)
    if pins:
        e = e.subs(pins)
    extra = context.get("q")
    q = sympy.And(*[c for c in (ctx, extra) if c is not None]) \
        if (ctx is not None or extra is not None) else None
    result = _prove_relation(e, sympy.S.Zero, ">" if strict else ">=",
                             domain, q, assumed, extensive=extensive)
    return result.status == "proven", ", ".join(used)


def _mean_of(v: "Vec"):
    j = _fresh_index()
    return sympy.Sum(v.elem.xreplace({INDEX: j}), (j, 0, v.length - 1)) \
        / v.length


def order_by_bounds(lhs, rhs, relation: str, bounds: Bounds,
                    lengths: dict, context: "dict | None" = None,
                    extensive: bool = False) -> "tuple[str, str] | None":
    """Intent:
        Decide `lhs <relation> rhs` (an ordering between numbers) where
        either side involves a least or greatest element or a running
        extremum, from their facts alone. `lengths` maps each
        sequence's `IndexedBase` to its length symbol; `context` holds
        the claim's own scalar `params`, `domain` and `q` facts.
        Returns `("proven", sketch)`, `("undecided", reason)`, or None
        when neither side involves one.

    Notes:
        With `s = min(v)` (the difference linear in `s`, `R` the other
        side solved for it): `s >= R` holds exactly when every element
        of `v` is at least `R`; `s <= R` holds when `R` is `mean(v)`,
        or when every element is at most `R`. `max(v)` mirrors each.
        An ordering with no extremum but an element of a running
        extremum at every position is decided element by element.
    """
    context = context or {}
    diff = sympy.expand(lhs - rhs)
    rel = relation
    if rel in ("<", "<="):
        diff, rel = -diff, _FLIP[rel]
    strict = rel == ">"
    present = [s for s in bounds.extrema if s in diff.free_symbols]
    running = any(a.base in bounds.running_bases
                  for a in diff.atoms(sympy.Indexed))
    if not present and not running:
        return None
    if not present:
        ok, used = _elementwise(diff, strict, bounds, lengths, context,
                                extensive)
        if ok:
            return "proven", f"element by element from {used}"
        return "undecided", "the element bounds do not settle it"
    if len(present) > 1:
        return "undecided", ("an ordering between two extrema is outside "
                             "the bound lemmas")
    s = present[0]
    kind, v = bounds.extrema[s]
    a = diff.coeff(s)
    rest = sympy.expand(diff - a * s)
    if s in rest.free_symbols or not a.is_number or a == 0:
        return "undecided", f"{s} does not enter the relation linearly"
    # diff = a*s + rest, so diff >= 0 is s >= R when a > 0, s <= R when
    # a < 0, with R = -rest/a
    bound = -rest / a
    above = bool(a > 0)
    word = "least" if kind == "min" else "greatest"
    if (kind == "min") == above:
        # min(v) >= R or max(v) <= R: every element is on that side
        e = (v.elem - bound) if kind == "min" else (bound - v.elem)
        ok, used = _elementwise(e, strict, bounds, lengths, context,
                                extensive)
        if ok:
            return "proven", (f"every element of {s.name[4:-1]} is "
                              f"{'at least' if kind == 'min' else 'at most'}"
                              f" {bound}, so its {word} element is"
                              + (f" ({used})" if used else ""))
        return "undecided", (f"the element bounds do not show every element "
                             f"{'>=' if kind == 'min' else '<='} {bound}")
    if not strict:
        gap = normalised(bound - _mean_of(v), lengths)
        if gap == 0:
            return "proven", (f"the {word} element of a vector is "
                              f"{'at most' if kind == 'min' else 'at least'}"
                              f" its mean")
    e = (bound - v.elem) if kind == "min" else (v.elem - bound)
    ok, used = _elementwise(e, strict, bounds, lengths, context, extensive)
    if ok:
        return "proven", (f"every element is "
                          f"{'at most' if kind == 'min' else 'at least'} "
                          f"{bound}, so its {word} element is"
                          + (f" ({used})" if used else ""))
    return "undecided", (f"neither the mean nor the element bounds place "
                         f"the {word} element")
