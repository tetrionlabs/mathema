# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The shared function/constant vocabulary both `grammar.py` (claim-law
text -> sympy) and `symbolic.py` (code -> sympy) parse against, plus the
`d(...)@{x=a}` evaluation-bar sentinel `grammar.py` produces and
`symbolic.py` consumes. Neither of those two modules may import this
vocabulary from the other: `grammar.py`'s own AST walker needs it to
resolve law text, and `symbolic.py`'s own lifter needs the identical
table to resolve code, so whichever module owned it, the other would
have to import back from it. Living in its own module with no
dependency on either breaks that cycle; this is the one and only
reason this module exists; it adds no behavior of its own.
"""
from __future__ import annotations

import ast
import operator

import sympy

_SYMPY_FUNCS = {
    "abs": sympy.Abs, "min": sympy.Min, "max": sympy.Max,
    # sympy's own capitalization, accepted as synonyms so a claim
    # written the way sympy prints (`Abs(x)`, `Min(a, b)`) lifts the
    # same as the lowercase spelling
    "Abs": sympy.Abs, "Min": sympy.Min, "Max": sympy.Max,
    # np.minimum/np.maximum are numpy's elementwise two-argument min/max,
    # a different function from np.min/np.max (which reduce over an array,
    # like bare min(xs)/max(xs), and aren't lifted at all), same
    # _call_name() module-qualified resolution as sin/sqrt/etc. routes
    # "minimum"/"maximum" here regardless of whether the call was spelled
    # np.minimum(...) or numpy.minimum(...). Mapped to the same sympy.Min/
    # Max as bare min/max, so _resolve_clamps() (symbolic.py) treats an
    # np.minimum/np.maximum clamp identically to a hand-written one.
    "minimum": sympy.Min, "maximum": sympy.Max,
    "sqrt": sympy.sqrt, "exp": sympy.exp, "log": sympy.log,
    "log10": lambda x: sympy.log(x, 10),
    "log2": lambda x: sympy.log(x, 2),
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
    "asin": sympy.asin, "acos": sympy.acos, "atan": sympy.atan,
    # the two-argument arctangent (math.atan2(y, x)): the full-plane
    # angle, pervasive in any position/azimuth/phase computation;
    # sympy.atan2 carries the same quadrant semantics
    "atan2": sympy.atan2,
    "sinh": sympy.sinh, "cosh": sympy.cosh, "tanh": sympy.tanh,
    # the greatest common divisor (math.gcd): exact over the integer
    # lattice a `subset Z` domain declares
    "gcd": sympy.gcd,
    # sympy.factorial/gamma generalize continuously to any real/complex
    # argument (factorial(x) = gamma(x+1)), while math.factorial only
    # accepts a non-negative int and raises otherwise, a claim whose
    # declared domain includes a non-integer or negative value can
    # therefore get a derive-route verdict for an input the real
    # function would never reach via the probe route. A real, narrow
    # gap (not this table's job to close): a caller declaring such a
    # domain around a factorial/gamma call gets a mathematically correct
    # answer about the continuous extension, not about math.factorial's
    # own narrower domain.
    "factorial": sympy.factorial, "gamma": sympy.gamma, "lgamma": sympy.loggamma,
    # special functions with exact sympy homes but no math-module
    # counterpart: claim text (and scipy/mpmath-shaped bodies resolved
    # by name) can state identities and bounds over them, and the
    # derive route reasons exactly where sympy's rules reach
    "zeta": sympy.zeta, "polygamma": sympy.polygamma,
    "besselj": sympy.besselj, "bessely": sympy.bessely,
    "elliptic_k": sympy.elliptic_k, "elliptic_e": sympy.elliptic_e,
    # the error function, math.erf(x), resolved via _call_name the
    # same way sin/sqrt/etc. are for any module in _MATH_MODULES. The
    # standard normal CDF is a direct affine transform of this
    # (`Phi(x) = (1 + erf(x/sqrt(2))) / 2`), so this one entry unblocks
    # any normal-CDF/quantile-shaped claim across statistics, finance,
    # and engineering-reliability code, not a domain-specific addition.
    "re": sympy.re, "im": sympy.im,
    "conjugate": sympy.conjugate, "arg": sympy.arg,
    "erf": sympy.erf,
    # erf's direct complement (`erfc(x) = 1 - erf(x)`), same module,
    # same reasoning, its own math.erfc/sympy.erfc pair.
    "erfc": sympy.erfc,
    # `||x||` (grammar.py) lifts to a call to this same name. There is no
    # vector/matrix type in the law grammar yet, so norm and abs are one
    # function until that lands, not a claim that ||x|| and |x| mean
    # the same thing mathematically.
    "norm": sympy.Abs,
    "floor": sympy.floor, "ceil": sympy.ceiling,
    # a bare type cast wrapping an already-numeric expression is common
    # in real code (`return float(np.sqrt(...))`, a defensive return-type
    # annotation, not a mathematical operation); sympy.sympify is a
    # no-op identity on an expression that's already a sympy object, so
    # this unwraps the cast rather than treating it as an unsupported
    # call. `int` is deliberately NOT included here: truncation actually
    # changes the value (int(3.7) != 3.7), so treating it as identity
    # would silently prove something false.
    "float": sympy.sympify,
    # np.clip(x, lo, hi)/np.clip(x, lo, None)/np.clip(x, None, hi) is a
    # clamp, floor at `lo`, ceiling at `hi`, expressible directly as
    # nested Min/Max with no new primitive needed. `_resolve_clamps()`
    # (symbolic.py) resolves a Min/Max against a declared domain exactly
    # the way it does for a hand-written `min(1.0, x)`, so a clipped
    # expression becomes provable under a domain the same way.
    # A bound given as Python `None` (only-lower or only-upper clipping)
    # isn't itself a numeric AST literal `_expr_to_sympy` can lift, so
    # np.clip(x, lo, None) must be spelled as plain min(x, ...)-shaped
    # code instead; both bounds must be real expressions here.
    "clip": lambda x, lo, hi: sympy.Min(sympy.Max(x, lo), hi),
}
_MATH_ATTRS = {"pi": sympy.pi, "e": sympy.E, "oo": sympy.oo, "infinity": sympy.oo}

# The probe route's float mirror of the derive route's _MATH_ATTRS
# constants: a bare `pi`/`e` (one that is NOT a real parameter, a
# parameter of that name always wins, on both routes) evaluates to its
# real value, so probe agrees with derive instead of sampling it as a
# random free variable (a live soundness bug: it falsified true claims).
# oo/infinity stay out; a float inf in a probe COMPARISON is a
# separate question, and they appear only in limit/domain positions the
# derive route owns.
import math as _math   # noqa: E402

MATH_CONSTANTS = {"pi": _math.pi, "e": _math.e}
# "infinity" is a second, independent spelling of "oo" (both map to the
# identical sympy.oo object) rather than something "oo" gets normalized
# to first, unlike tau below, "infinity" isn't a plausible ordinary
# variable name, so recognizing it directly here, the same way "oo"
# itself already is, is safe. Fixes a real, silent-wrong-answer bug
# this had before it was added: `lim f(x) as x -> infinity == 0` never
# resolved "infinity" to the constant at all, silently treating it as
# an ordinary free variable instead (never taking a limit), and could
# return a confidently wrong `falsified` with a sampled counterexample
# rather than even a `skipped`.
# `tau` is deliberately not here: unlike `pi`, it isn't universally a
# fixed constant in the way this table's other entries are (a common
# ordinary variable name too, a time-constant in engineering/physics
# among other uses), so it's left as a plain identifier, `grammar.py`'s
# `\tau` -> `τ` Greek-letter mapping treats it the same as `\alpha`, not
# as a constant either.
# grammar.py's own `d(...)@{x=a}` evaluation-bar sugar expands to a call
# carrying this sentinel name as a marker argument; symbolic.py's `d`
# handler is the only consumer. One shared constant now that both
# modules can depend on this one without depending on each other.
_D_AT_SENTINEL = "__at__"

# the Cauchy principal-value marker: an unevaluated wrapper a claim's
# PV(integrate(...)) form parses to. Kept a bare sympy Function so it
# survives simplify untouched; the decision procedure resolves it via
# Integral.principal_value(), and the residue machinery via the
# indented-contour half-residue formula.
_PV_FUNC = sympy.Function("P.V.")
_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    # Python floor division: exactly floor(a/b) for the real-valued
    # reading the lift works in (Python's own // agrees with
    # floor(a/b) for ints and floats alike, including negatives)
    ast.FloorDiv: lambda a, b: sympy.floor(a / b),
}


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _call_name(node: ast.Call) -> str | None:
    """Resolve a call's function name for the safe-func table: bare
    `sin(x)` and module-qualified `math.sin(x)`/`np.sin(x)`/`numpy.sin(x)`
    all resolve to `'sin'`; numpy's scalar elementwise functions are the
    same operations `math`'s are, over the same scalar-parameter scope
    lift() already requires, so they get the same treatment. Uses
    analysis.py's own _MATH_MODULES rather than a second, separately
    maintained list, analyze_source()'s "known name" classification and
    lift()'s "known call" classification must agree, or a function can be
    reported liftable/known here and then fail to actually lift, or the
    reverse."""
    from .analysis import _MATH_MODULES

    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute) and _root_name(f.value) in _MATH_MODULES:
        return f.attr
    return None
