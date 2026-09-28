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

Arithmetic between vectors, and between a vector and a number, acts
element by element. A law transform a claim binds (`let s =
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

    def __init__(self, seqs: dict, scalars: dict, transforms: dict):
        self.seqs = seqs
        self.scalars = scalars
        self.transforms = transforms
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

    # -- arithmetic ------------------------------------------------------

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
            if isinstance(right, Vec):
                raise NotSymbolic(f"{ast.unparse(node)!r}: division by a "
                                  f"vector is outside the lowering")
            self._divides_by(right, node.right)
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

    # -- vector forms ----------------------------------------------------

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

    # -- calls -----------------------------------------------------------

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


# -- the normaliser ----------------------------------------------------------

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
