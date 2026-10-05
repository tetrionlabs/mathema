# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An exact witness checked on its own terms.

A derive disproof names a witness point. When every float draw passes,
the witness is checked here by exact evaluation that does not go through
the solver that found it:

- a rational witness is a `Fraction`;
- an algebraic witness is the unique root of a squarefree rational
  polynomial inside a rational isolating interval, verified by a sign
  change and a Sturm count, and computed with as an element of the
  field it generates (`Algebraic`): sums, products and quotients are
  polynomials reduced modulo the defining polynomial, and a sign is
  read by bisecting the isolating interval until an interval
  enclosure of the element excludes zero;
- a transcendental value is enclosed in certified interval balls
  (`mpmath.iv`): a ball strictly on one side of zero certifies a sign,
  and opposite signs at the two ends of an interval over which the
  expression is continuous certify a root inside it. A ball never
  certifies an exact zero.

Whatever cannot be certified this way is reported as undecided.
"""
from __future__ import annotations

from fractions import Fraction

#: bisection steps a sign is refined through before it is undecided
SIGN_REFINEMENTS = 400


class Undecided(Exception):
    """An exact evaluation that cannot be carried out or certified."""


# polynomials over Q, coefficient lists from the constant term up

def _trim(c: list) -> list:
    c = list(c)
    while c and c[-1] == 0:
        c.pop()
    return c


def _add(a: list, b: list) -> list:
    n = max(len(a), len(b))
    return _trim([(a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0)
                  for i in range(n)])


def _scale(a: list, k) -> list:
    return _trim([k * v for v in a])


def _mul(a: list, b: list) -> list:
    if not a or not b:
        return []
    out = [Fraction(0)] * (len(a) + len(b) - 1)
    for i, u in enumerate(a):
        for j, v in enumerate(b):
            out[i + j] += u * v
    return _trim(out)


def _divmod(a: list, b: list) -> tuple:
    a, b = _trim(a), _trim(b)
    if not b:
        raise ZeroDivisionError("polynomial division by zero")
    q = [Fraction(0)] * max(len(a) - len(b) + 1, 1)
    r = [Fraction(v) for v in a]
    while len(r) >= len(b) and r:
        k = r[-1] / b[-1]
        shift = len(r) - len(b)
        q[shift] = k
        for i, v in enumerate(b):
            r[shift + i] -= k * v
        r = _trim(r)
    return _trim(q), r


def _derivative(a: list) -> list:
    return _trim([i * a[i] for i in range(1, len(a))])


def _gcd(a: list, b: list) -> list:
    a, b = _trim(a), _trim(b)
    while b:
        a, b = b, _divmod(a, b)[1]
    return _scale(a, 1 / a[-1]) if a else a


def _inverse(c: list, p: list) -> list:
    """The inverse of c modulo p, or Undecided when they share a factor."""
    r0, r1 = _trim(p), _trim(c)
    s0, s1 = [], [Fraction(1)]
    while r1:
        q, r = _divmod(r0, r1)
        r0, r1 = r1, r
        s0, s1 = s1, _add(s0, _scale(_mul(q, s1), -1))
    if len(r0) != 1:
        raise Undecided("a zero divisor of the field")
    return _divmod(_scale(s0, 1 / r0[0]), p)[1]


def _eval(c: list, x):
    out = Fraction(0)
    for v in reversed(c):
        out = out * x + v
    return out


def _eval_range(c: list, lo: Fraction, hi: Fraction) -> tuple:
    """An enclosure `(low, high)` of c over [lo, hi], by interval Horner."""
    a = b = Fraction(0)
    for v in reversed(c):
        products = (a * lo, a * hi, b * lo, b * hi)
        a, b = min(products) + v, max(products) + v
    return a, b


def _sturm_count(p: list, lo: Fraction, hi: Fraction) -> int:
    """The number of distinct real roots of squarefree p in (lo, hi]."""
    seq = [_trim(p), _derivative(p)]
    while seq[-1] and len(seq[-1]) > 1:
        r = _divmod(seq[-2], seq[-1])[1]
        if not r:
            break
        seq.append(_scale(r, -1))

    def changes(x):
        signs = [s for s in ((_eval(q, x) > 0) - (_eval(q, x) < 0)
                             for q in seq) if s]
        return sum(1 for u, v in zip(signs, signs[1:]) if u != v)
    return changes(lo) - changes(hi)


class _Root:
    """The unique root of squarefree p in the open interval (lo, hi)."""

    def __init__(self, p: list, lo: Fraction, hi: Fraction):
        self.p, self.lo, self.hi = p, lo, hi

    def bisect(self) -> bool:
        """Halve the interval; True when the root turned out rational."""
        m = (self.lo + self.hi) / 2
        pm = _eval(self.p, m)
        if pm == 0:
            self.lo = self.hi = m
            return True
        if (_eval(self.p, self.lo) > 0) == (pm > 0):
            self.lo = m
        else:
            self.hi = m
        return False


class Algebraic:
    """An element c(alpha) of Q(alpha), alpha a `_Root`."""

    __slots__ = ("root", "c")

    def __init__(self, root: _Root, c: list):
        self.root = root
        self.c = _divmod(c, root.p)[1]

    def _lift(self, other) -> "Algebraic":
        if isinstance(other, Algebraic):
            if other.root is not self.root:
                raise Undecided("two different algebraic numbers")
            return other
        if isinstance(other, (int, Fraction)) and not isinstance(other, bool):
            return Algebraic(self.root, [Fraction(other)])
        if isinstance(other, bool):
            return Algebraic(self.root, [Fraction(int(other))])
        raise Undecided(f"an algebraic number with a {type(other).__name__}")

    def __add__(self, other):
        try:
            o = self._lift(other)
        except Undecided:
            return NotImplemented
        return Algebraic(self.root, _add(self.c, o.c))

    __radd__ = __add__

    def __neg__(self):
        return Algebraic(self.root, _scale(self.c, -1))

    def __pos__(self):
        return self

    def __sub__(self, other):
        try:
            o = self._lift(other)
        except Undecided:
            return NotImplemented
        return Algebraic(self.root, _add(self.c, _scale(o.c, -1)))

    def __rsub__(self, other):
        return (-self) + other

    def __mul__(self, other):
        try:
            o = self._lift(other)
        except Undecided:
            return NotImplemented
        return Algebraic(self.root, _mul(self.c, o.c))

    __rmul__ = __mul__

    def _inverted(self) -> "Algebraic":
        if not self.c:
            raise ZeroDivisionError("division by zero")
        return Algebraic(self.root, _inverse(self.c, self.root.p))

    def __truediv__(self, other):
        try:
            o = self._lift(other)
        except Undecided:
            return NotImplemented
        return self * o._inverted()

    def __rtruediv__(self, other):
        return self._inverted() * other

    def __pow__(self, k):
        if isinstance(k, Fraction) and k.denominator == 1:
            k = int(k)
        if not isinstance(k, int):
            raise Undecided("an algebraic number to a non-integer power")
        base = self if k >= 0 else self._inverted()
        out = Algebraic(self.root, [Fraction(1)])
        for _ in range(abs(k)):
            out = out * base
        return out

    def sign(self) -> int:
        if not self.c:
            return 0
        if len(self.c) == 1:
            return (self.c[0] > 0) - (self.c[0] < 0)
        root = self.root
        for _ in range(SIGN_REFINEMENTS):
            if root.lo == root.hi:
                v = _eval(self.c, root.lo)
                return (v > 0) - (v < 0)
            low, high = _eval_range(self.c, root.lo, root.hi)
            if low > 0:
                return 1
            if high < 0:
                return -1
            root.bisect()
        raise Undecided("the sign of an algebraic number")

    def __abs__(self):
        return -self if self.sign() < 0 else self

    def _cmp(self, other) -> int:
        return (self - other).sign()

    def __eq__(self, other):
        try:
            return self._cmp(other) == 0
        except Undecided:
            return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __lt__(self, other):
        return self._cmp(other) < 0

    def __le__(self, other):
        return self._cmp(other) <= 0

    def __gt__(self, other):
        return self._cmp(other) > 0

    def __ge__(self, other):
        return self._cmp(other) >= 0

    def __bool__(self):
        return self.sign() != 0

    __hash__ = None  # type: ignore[assignment]

    def __float__(self):
        return float((self.root.lo + self.root.hi) / 2) if len(self.c) > 1 \
            else float(self.c[0] if self.c else 0)

    def __repr__(self):
        return f"Algebraic({self.c}, root of {self.root.p} in [{self.root.lo}, {self.root.hi}])"


def sign_of(value) -> int:
    """The exact sign of an int, Fraction or `Algebraic`."""
    if isinstance(value, Algebraic):
        return value.sign()
    if isinstance(value, (int, Fraction)):
        return (value > 0) - (value < 0)
    raise Undecided(f"the sign of a {type(value).__name__}")


def exact_number(value, timeout: float):
    """Intent:
        The sympy number `value` as an exact number: a `Fraction` when it
        is rational, an `Algebraic` (with an isolating interval verified
        by a sign change and a Sturm count) when it is a real algebraic
        number, else `Undecided`.
    """
    import sympy

    from ._timeout import _with_timeout
    value = sympy.sympify(value)
    if value.is_Rational:
        return Fraction(int(value.p), int(value.q))
    if value.is_real is not True or value.is_algebraic is not True:
        raise Undecided(f"{value} is not a real algebraic number")
    t = sympy.Dummy("t")
    try:
        poly = _with_timeout(
            lambda: sympy.Poly(sympy.minimal_polynomial(value, t), t),
            timeout)
        approx = Fraction(str(sympy.N(value, 60)))
    except TimeoutError:
        raise Undecided(f"no minimal polynomial for {value} in time")
    except Exception as exc:
        raise Undecided(f"no minimal polynomial for {value} ({exc})")
    p = _trim([Fraction(int(c.p), int(c.q))
               for c in reversed(poly.all_coeffs())])
    if len(_gcd(p, _derivative(p))) != 1:
        raise Undecided("the defining polynomial is not squarefree")
    eps = Fraction(1, 10 ** 40)
    lo, hi = approx - eps, approx + eps
    if _eval(p, lo) == 0 or _eval(p, hi) == 0 \
            or (_eval(p, lo) > 0) == (_eval(p, hi) > 0) \
            or _sturm_count(p, lo, hi) != 1:
        raise Undecided(f"no isolating interval for {value}")
    root = _Root(p, lo, hi)
    return Algebraic(root, [Fraction(0), Fraction(1)])


def relation_fails(left, right, relation: str) -> bool:
    """Intent:
        Whether `left relation right` is false for exact scalars, decided
        by the exact sign of their difference; `Undecided` for anything
        that is not an int, a Fraction or an `Algebraic`.
    """
    if isinstance(left, bool):
        left = int(left)
    if isinstance(right, bool):
        right = int(right)
    s = sign_of(left - right)
    holds = {"==": s == 0, "!=": s != 0, "<=": s <= 0, ">=": s >= 0,
             "<": s < 0, ">": s > 0}.get(relation)
    if holds is None:
        raise Undecided(f"the relation {relation}")
    return not holds


def interval_pieces(bound) -> list:
    """Intent:
        A real domain bound as `[(lo, hi, closed_lo, closed_hi), ...]`
        with each finite end read exactly as written (a float end as
        the shortest decimal that reads back as it), or `Undecided` for
        a bound that is not a union of intervals.
    """
    import math
    pieces = getattr(bound, "pieces", None) or (
        (bound,) if isinstance(bound, (tuple, list)) else ())
    out = []
    for piece in pieces:
        if not (isinstance(piece, (tuple, list)) and len(piece) == 2):
            raise Undecided("a domain that is not a union of intervals")
        ends = []
        for end in piece:
            if isinstance(end, float) and math.isinf(end):
                ends.append(end)
            elif isinstance(end, (int, float, Fraction)):
                ends.append(Fraction(repr(end)) if isinstance(end, float)
                            else Fraction(end))
            else:
                raise Undecided("a domain end that is not a number")
        out.append((ends[0], ends[1], getattr(piece, "closed_lo", True),
                    getattr(piece, "closed_hi", True)))
    if not out:
        raise Undecided("a domain that is not a union of intervals")
    return out


def _above(value, end, closed: bool) -> bool:
    if isinstance(end, float):
        return end < 0
    s = sign_of(value - end)
    return s > 0 or (closed and s == 0)


def _below(value, end, closed: bool) -> bool:
    if isinstance(end, float):
        return end > 0
    s = sign_of(value - end)
    return s < 0 or (closed and s == 0)


def in_bound(value, bound) -> bool:
    """Whether the exact `value` lies in the interval bound."""
    return any(_above(value, lo, clo) and _below(value, hi, chi)
               for lo, hi, clo, chi in interval_pieces(bound))


# certified interval balls over a lifted expression

#: sympy functions continuous wherever their ball evaluation is finite
_BALL_FUNCTIONS = ("sin", "cos", "tan", "exp", "log", "sqrt", "atan",
                   "sinh", "cosh", "tanh", "asin", "acos")


def ball(expr, at: dict, prec: int):
    """Intent:
        An `mpmath.iv` enclosure of the sympy expression `expr` with each
        symbol in `at` set to the exact rational (or rational interval
        `(lo, hi)`) it maps to, at `prec` bits; `Undecided` for an
        operation outside the continuous whitelist or an enclosure that
        is not finite.
    """
    import sympy
    from mpmath import iv
    iv.prec = prec

    def num(q: Fraction):
        return iv.mpf(q.numerator) / iv.mpf(q.denominator)

    def walk(e):
        if e.is_Symbol:
            if e not in at:
                raise Undecided(f"a free {e}")
            v = at[e]
            if isinstance(v, tuple):
                return iv.mpf([num(v[0]).a, num(v[1]).b])
            return num(v)
        if e.is_Rational:
            return num(Fraction(int(e.p), int(e.q)))
        if e is sympy.pi:
            return iv.pi
        if e is sympy.E:
            return iv.e
        if e.is_Add:
            out = iv.mpf(0)
            for a in e.args:
                out = out + walk(a)
            return out
        if e.is_Mul:
            out = iv.mpf(1)
            for a in e.args:
                out = out * walk(a)
            return out
        if e.is_Pow:
            base, k = e.args
            if k.is_Integer:
                b = walk(base)
                if int(k) < 0 and b.a <= 0 <= b.b:
                    raise Undecided("a pole inside the ball")
                return b ** int(k)
            if k == sympy.Rational(1, 2):
                b = walk(base)
                if b.a < 0:
                    raise Undecided("a square root of a ball reaching below 0")
                return iv.sqrt(b)
            raise Undecided(f"the power {e}")
        name = type(e).__name__.lower()
        if name in _BALL_FUNCTIONS and len(e.args) == 1:
            arg = walk(e.args[0])
            if name == "log" and arg.a <= 0:
                raise Undecided("a logarithm of a ball reaching 0")
            if name == "tan":
                c = iv.cos(arg)
                if c.a <= 0 <= c.b:
                    raise Undecided("a pole of tan inside the ball")
            if name in ("asin", "acos") and (arg.a < -1 or arg.b > 1):
                raise Undecided(f"{name} outside [-1, 1]")
            return getattr(iv, name)(arg)
        raise Undecided(f"no certified ball for {type(e).__name__}")

    out = walk(sympy.sympify(expr))
    import mpmath
    if not (mpmath.isfinite(out.a) and mpmath.isfinite(out.b)):
        raise Undecided("an enclosure that is not finite")
    return out


def certified_sign(expr, at: dict) -> int:
    """The sign of `expr` at an exact rational point, certified by balls
    at rising precision; `Undecided` when every ball straddles zero."""
    for prec in (53, 200, 1000):
        b = ball(expr, at, prec)
        if b.a > 0:
            return 1
        if b.b < 0:
            return -1
    raise Undecided("a ball that never excludes zero")


def rational_near(value, digits: int = 40) -> Fraction:
    """A rational within about 10^-digits of the sympy number `value`."""
    import sympy
    return Fraction(str(sympy.N(value, digits + 10)))
