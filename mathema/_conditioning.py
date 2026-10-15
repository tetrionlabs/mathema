# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The conditioning of a computation at the point where it missed.

When a computation line misses the mathematics, the condition number
`κ` at the witness says whether any float64 computation could have
delivered the result there. A relative error up to about `κ` times the
unit roundoff is what a backward-stable computation loses, so a miss
within `STABILITY_FACTOR · κ · u` is inherent in the inputs (the claim
is true, the representation cannot honour it at those magnitudes); a
larger miss is the code's. `κ` is read from the computation's shape:

- a matrix computation: the 2-norm condition number of the matrix,
  from the exact evaluator;
- a computation whose mathematics runs on exact numbers: the relative
  movement of the exact result under a relative movement of the inputs
  (the first-order condition number of the mathematics itself, whatever
  algorithm the code uses);
- a reduction stated by the claim's words (a sum, a mean, a standard
  deviation): the sum of the terms' magnitudes over the result's
  magnitude (the classic cancellation measure);
- a scalar body derive can lift: `|x f'(x) / f(x)|` from the derivative,
  the largest over the parameters;
- anything else (opaque code): unknown, and said so.

The remedy for an inherent miss is a pseudo-infinity (`let |inf| be B`)
that keeps the computation where `κ · u` stays below the relative
allowance along the claim's unbounded directions, or else a narrower
domain, or accepting the discovery. The binding bounds only the
computation; a proof stays over the claim's full domain.
"""
from __future__ import annotations

import math
import re
from fractions import Fraction

from ._allowance import RELATIVE, STABILITY_FACTOR, UNIT_ROUNDOFF


def _numbers(value) -> list:
    """Every finite real number in a value: a number, a list or tuple of
    them (nested), a numpy array."""
    out: list = []

    def collect(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float, Fraction)):
            try:
                f = float(v)
            except OverflowError:
                return
            if math.isfinite(f):
                out.append(f)
        elif isinstance(v, (list, tuple)):
            for u in v:
                collect(u)
        elif hasattr(v, "ravel"):
            try:
                collect(v.ravel().tolist())
            except Exception:
                return
        elif hasattr(v, "tolist"):
            try:
                collect(v.tolist())
            except Exception:
                return
    collect(value)
    return out


def _is_matrix(value) -> bool:
    return getattr(value, "ndim", None) == 2 or (
        isinstance(value, (list, tuple)) and bool(value)
        and all(isinstance(r, (list, tuple)) for r in value))


def _is_sequence(value) -> bool:
    return getattr(value, "ndim", None) == 1 or (
        isinstance(value, (list, tuple)) and not _is_matrix(value))


def short(x: float) -> str:
    """A number as a short power-of-ten reading: `2e16`, `1e-5`, `3`."""
    if x is None or not math.isfinite(x):
        return "inf" if x is not None and x > 0 else str(x)
    if x == 0:
        return "0"
    text = f"{x:.0e}"
    mantissa, exponent = text.split("e")
    e = int(exponent)
    if -3 <= e <= 3:
        return f"{x:.3g}"
    return f"{mantissa}e{e}"


def _kappa_matrix(point: dict) -> "float | None":
    from ._linalg_eval import FUNCTIONS
    for value in point.values():
        if _is_matrix(value):
            try:
                return float(FUNCTIONS["cond"](value))
            except Exception:
                return None
    return None


def _kappa_reduction(point: dict, reference: float) -> "float | None":
    terms = [abs(v) for value in point.values() for v in _numbers(value)]
    if not terms:
        return None
    try:
        total = math.fsum(terms)
    except OverflowError:
        total = math.inf
    if reference == 0:
        return math.inf if total > 0 else None
    return total / abs(reference)


def _kappa_derivative(fn, facts, point: dict) -> "float | None":
    """`max_p |p f_p(point) / f(point)|` from the lifted body, None when
    the body does not lift or the point is not scalar."""
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .symbolic import lift
    try:
        lifted = _with_timeout(lambda: lift(fn, facts), FAST_TIMEOUT_SECONDS)
    except Exception:
        return None
    if lifted is None or isinstance(lifted.expr, tuple):
        return None
    subs = {}
    for name, value in point.items():
        sym = lifted.params.get(name)
        if sym is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        subs[sym] = sympy.Rational(value) if isinstance(value, float) \
            else sympy.Integer(value)
    try:
        def compute():
            value = lifted.expr.subs(subs)
            worst = 0.0
            for sym, at in subs.items():
                slope = sympy.diff(lifted.expr, sym).subs(subs)
                num = sympy.N(sympy.Abs(at * slope), 30)
                den = sympy.N(sympy.Abs(value), 30)
                if not (num.is_real and den.is_real):
                    return None
                if den == 0:
                    return math.inf if num != 0 else None
                worst = max(worst, float(num / den))
            return worst
        return _with_timeout(compute, FAST_TIMEOUT_SECONDS)
    except Exception:
        return None


#: the claim words that reduce a sequence to a number of the terms' own
#: degree, so the sum of the terms' magnitudes over the result measures
#: their cancellation
_REDUCTIONS = re.compile(r"\b(?:sum|mean|std|dot|norm|cumsum|median|quantile|"
                         r"min|max|trace)\s*\(")


def claim_reduces(cj) -> bool:
    """Whether a side of the claim that runs no code reduces a sequence
    with one of the grammar's reduction words, so the computation it
    stands against is a reduction of its inputs."""
    from ._allowance import code_sides
    left, right = code_sides(cj)
    sides = [s for s, runs in ((getattr(cj, "lhs", "") or "", left),
                               (getattr(cj, "rhs", "") or "", right))
             if not runs]
    return any(_REDUCTIONS.search(str(s)) for s in sides)


#: the relative movement of an input the exact mathematics is read under
_MOVE = Fraction(1, 2 ** 30)
#: the most input numbers moved one at a time before they move together
_MOVE_EACH = 64


def _leaves(value, path=()) -> list:
    """`(path, number)` for every number in a value: a number, nested
    lists or tuples, a numpy array (read as nested lists)."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float, Fraction)):
        return [(path, value)]
    if hasattr(value, "tolist") and not isinstance(value, (list, tuple)):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return [leaf for k, v in enumerate(value)
                for leaf in _leaves(v, path + (k,))]
    return []


def _with_moved(point: dict, moves: dict):
    """`point` with the numbers at the paths in `moves` (param, index
    path) multiplied by `1 + sign * _MOVE`, every number exact."""
    def rebuild(value, path, param):
        if hasattr(value, "tolist") and not isinstance(value, (list, tuple)):
            value = value.tolist()
        if isinstance(value, (list, tuple)):
            return [rebuild(v, path + (k,), param) for k, v in enumerate(value)]
        if isinstance(value, bool) or not isinstance(value, (int, float,
                                                             Fraction)):
            return value
        try:
            exact = Fraction(value)
        except (TypeError, ValueError, OverflowError):
            return value
        sign = moves.get((param, path))
        return exact * (1 + sign * _MOVE) if sign and exact else exact
    return {p: rebuild(v, (), p) for p, v in point.items()}


def _kappa_mathematics(exact_at, point: dict) -> "float | None":
    """The first-order condition number of the mathematics at `point`:
    how far the exact result moves, relative to itself, per relative
    movement of the inputs. Each input number is moved on its own (the
    componentwise condition number, which a cancelling pair cannot hide
    from); past `_MOVE_EACH` numbers they move together under random
    signs instead. `exact_at(point)` evaluates the claim's sides with f
    run on the exact numbers, None when it cannot."""
    import random
    base = exact_at(point)
    if base is None:
        return None
    base_entries = [_exact_entries(side) for side in base]
    leaves = [(p, path) for p, v in point.items() for path, _n in _leaves(v)]
    if not leaves:
        return None
    if len(leaves) <= _MOVE_EACH:
        trials = [{leaf: 1} for leaf in leaves]
    else:
        rng = random.Random(0x5EED)
        trials = [{leaf: rng.choice((-1, 1)) for leaf in leaves}
                  for _ in range(3)]
    moved_total = [None if b is None else [Fraction(0)] * len(b)
                   for b in base_entries]
    for moves in trials:
        after = exact_at(_with_moved(point, moves))
        if after is None:
            return None
        for k, side in enumerate(after):
            entries = _exact_entries(side)
            if moved_total[k] is None or entries is None \
                    or len(entries) != len(moved_total[k]):
                moved_total[k] = None
                continue
            for n, (b, a) in enumerate(zip(base_entries[k], entries)):
                moved_total[k][n] += abs(a - b)
    worst = None
    for k, totals in enumerate(moved_total):
        if totals is None:
            continue
        for b, total in zip(base_entries[k], totals):
            if b == 0:
                if total != 0:
                    return math.inf
                continue
            try:
                kappa = float(total / abs(b) / _MOVE)
            except OverflowError:
                kappa = math.inf
            worst = kappa if worst is None else max(worst, kappa)
    return worst


def _exact_entries(value) -> "list | None":
    """The exact numbers a side holds (a number, or nested lists), None
    for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, Fraction)):
        return [Fraction(value)]
    if isinstance(value, (list, tuple)):
        out: list = []
        for v in value:
            part = _exact_entries(v)
            if part is None:
                return None
            out.extend(part)
        return out
    return None


def condition_at(fn, facts, point: dict, reference: float,
                 reduces: bool = True, exact_at=None) -> "tuple":
    """Intent:
        `(kappa, how)` at the executed point: the condition number and
        the shape it was read from (`"matrix"`, `"mathematics"`,
        `"reduction"`, `"derivative"`), or `(None, None)` for code
        mathema cannot read. `reference` is the exact result's
        magnitude. `exact_at`, when given, evaluates the claim's sides
        with f run on exact numbers at a point, which reads the
        conditioning of the mathematics itself. The reduction reading
        applies only where the claim's own words make the computation a
        reduction of its inputs (`reduces`): the sum of the terms'
        magnitudes says nothing about code whose result does not scale
        with them.
    """
    values = list(point.values())
    if any(_is_matrix(v) for v in values):
        kappa = _kappa_matrix(point)
        return (kappa, "matrix") if kappa is not None else (None, None)
    if exact_at is not None:
        kappa = _kappa_mathematics(exact_at, point)
        if kappa is not None:
            return kappa, "mathematics"
    if any(_is_sequence(v) for v in values):
        if not reduces:
            return None, None
        kappa = _kappa_reduction(point, reference)
        return (kappa, "reduction") if kappa is not None else (None, None)
    kappa = _kappa_derivative(fn, facts, point)
    return (kappa, "derivative") if kappa is not None else (None, None)


def scale_of(point: dict) -> float:
    """The largest magnitude among the point's numbers."""
    numbers = [abs(v) for value in point.values() for v in _numbers(value)]
    return max(numbers) if numbers else 0.0


def inherent(kappa: "float | None", error: float) -> "bool | None":
    """Whether a relative miss of `error` is what the conditioning
    explains; None when κ is unknown."""
    if kappa is None:
        return None
    if math.isinf(kappa):
        return True
    return error <= STABILITY_FACTOR * kappa * UNIT_ROUNDOFF


def _dims_text(bound, value=None) -> str:
    """The `^n` or `^(m,n)` a bound states, else the shape of the value
    drawn for an unbound parameter (`^n` for a sequence, `^(m,n)` for a
    matrix), else nothing."""
    dims = getattr(bound, "dims", None) or ()
    if not dims and value is not None:
        if _is_matrix(value):
            return "^(m,n)"
        if _is_sequence(value):
            return "^n"
        return ""
    if not dims:
        return ""
    if len(dims) == 1:
        return f"^{dims[0]}"
    return "^(" + ",".join(str(d) for d in dims) + ")"


def _power_of_ten_below(x: float) -> "float | None":
    if not (x > 0) or math.isinf(x):
        return None
    return 10.0 ** math.floor(math.log10(x))


def _magnitude_bound(kappa: "float | None", scale: float) -> "float | None":
    """The power of ten below the input magnitude where `κ · u` meets the
    relative allowance, κ growing with the inputs' magnitude from its
    value `kappa` at magnitude `scale`; None when no smaller magnitude
    would help."""
    if kappa is None or kappa <= 0 or scale <= 0 or math.isinf(kappa):
        return None
    ceiling = RELATIVE / UNIT_ROUNDOFF
    # in logarithms, so no step overflows
    exponent = math.log10(scale) + math.log10(ceiling) - math.log10(kappa)
    bound = 10.0 ** math.floor(exponent) if exponent < 308 else None
    if bound is None or bound >= scale:
        return None
    return bound


def infinity_words(bound: float) -> str:
    """`let |inf| be B` as the claim grammar spells it."""
    from .records import PseudoInfinity
    return PseudoInfinity(bound, "claim").render()


def narrowing(point: dict, cj_domain: dict, kappa: float, how: str,
              scale: float) -> "str | None":
    """Intent:
        The claim words that keep `κ · u` below the relative allowance:
        for a reduction or a lifted body, whose κ grows with the inputs'
        magnitude, the parameters carrying that magnitude bounded to
        `[-B, B]` with `B` the power of ten below where the allowance is
        met; for a matrix, the premise `assuming cond(A) < B`. None when
        no narrower bound would help.
    """
    if kappa is None or kappa <= 0 or scale <= 0:
        return None
    ceiling = RELATIVE / UNIT_ROUNDOFF
    if how == "matrix":
        bound = _power_of_ten_below(ceiling)
        names = [p for p, v in point.items() if _is_matrix(v)]
        if bound is None or not names:
            return None
        return ", ".join(f"assuming cond({p}) < {short(bound)}" for p in names)
    bound = _magnitude_bound(kappa, scale)
    if bound is None:
        return None
    wide = [p for p, v in point.items()
            if any(abs(x) >= scale / 10 for x in _numbers(v))]
    if not wide:
        return None
    parts = []
    for p in wide:
        dims = _dims_text((cj_domain or {}).get(p), point.get(p))
        parts.append(f"{p} in [-{short(bound)}, {short(bound)}]{dims}")
    return "for " + ", ".join(parts)


def infinity_candidate(found: "dict | None") -> "float | None":
    """The `B` a conditioning record gives for `let |inf| be B`: the
    power of ten below where `κ · u` meets the relative allowance, for
    a loss whose κ grows with the inputs' magnitude and is read (no
    matrix), where `narrowing` would bound the inputs to `[-B, B]`.
    None when the record gives none."""
    if not found or found.get("how") in (None, "matrix"):
        return None
    if not (found.get("inherent") is True or (
            found.get("inherent") is None and found.get("kappa") is not None)):
        return None
    return _magnitude_bound(found.get("kappa"), found.get("scale") or 0.0)


def infinity_floor(names: list, cj_domain: dict) -> "float | None":
    """Intent:
        The least magnitude a `let |inf| be B` must reach so that every
        parameter in `names` keeps the ends its domain states: the
        largest finite end among them, 0 where none is stated. None
        when a parameter's values (a number, or a container's elements)
        are not one real interval, where `|inf|` has no single range to
        bound.
    """
    from .probing import _element_range
    floor = 0.0
    for name in names:
        span = _element_range((cj_domain or {}).get(name), (0.0, 0.0))
        if span is None:
            return None
        floor = max(floor, abs(span[0]), abs(span[1]))
    return floor


def at_miss(fn, facts, point: dict, gap: float, reference: float,
            cj_domain: "dict | None" = None,
            mathematics: "bool | None" = True,
            reduces: bool = True, exact_at=None) -> dict:
    """Intent:
        What the conditioning says about a computation-line miss at
        `point`, where the computed value missed the exact `reference`
        by `gap`: a record with `kappa`, `how`, `scale` (the inputs'
        largest magnitude), `error` (the relative miss), `inherent`
        (True, False, or None for opaque code), `words` (the sentence
        the note carries) and `narrow` (the claim words that keep the
        computation within reach, or None). `mathematics` is whether the
        claim is known to hold at the point in exact arithmetic (a
        proof, a trusted row, or f run on the exact numbers); None when
        that could not be decided, where an ill-conditioned draw says
        the representation could not have delivered the result, not
        that the claim is true there.
    """
    scale = scale_of(point)
    kappa, how = condition_at(fn, facts, point, reference, reduces, exact_at)
    if reference:
        error = gap / abs(reference)
    elif scale:
        error = gap / scale
    else:
        error = math.inf if gap else 0.0
    verdict = inherent(kappa, error)
    if verdict is True and mathematics is None:
        words = (f"ill-conditioned here (κ ≈ {short(kappa)}): float64 "
                 f"cannot deliver this result at inputs of magnitude "
                 f"{short(scale)}, and whether the claim holds there in "
                 f"exact arithmetic was not decided (derive cannot read f)")
        verdict = None
    elif verdict is True and kappa is not None and math.isinf(kappa):
        words = (f"ill-conditioned here (the exact result is 0 at inputs "
                 f"of magnitude {short(scale)}): no float64 computation "
                 f"can deliver it exactly")
    elif verdict is True:
        words = (f"ill-conditioned here (κ ≈ {short(kappa)}): no float64 "
                 f"computation can deliver this result at inputs of "
                 f"magnitude {short(scale)}")
    elif verdict is False:
        words = (f"f loses more than the conditioning explains "
                 f"(κ ≈ {short(kappa)}, error {short(error)})")
    else:
        words = ("conditioning unknown here: derive cannot read f, so "
                 "whether this loss is inherent is not decided")
    narrow = narrowing(point, cj_domain or {}, kappa, how, scale) \
        if verdict is True or (verdict is None and kappa is not None) else None
    return {"kappa": kappa, "how": how, "scale": scale, "error": error,
            "inherent": verdict, "words": words, "narrow": narrow}


#: the characters a word of a printed command carries unquoted in any
#: POSIX shell; anything else (a companion's brackets, a space) is quoted
_PLAIN_WORD = re.compile(r"[A-Za-z0-9_.,:/=+-]+")


def command_word(word: str) -> str:
    """A word of a printed command as a shell reads it back: as it is
    when plain, else in double quotes (`"shift[float]"`)."""
    if _PLAIN_WORD.fullmatch(word):
        return word
    escaped = re.sub(r'(["\\$`])', r"\\\1", word)
    return f'"{escaped}"'


def whole_claim_option(key: str, parent: str) -> str:
    """The option that accepts the claim `parent` whole as a discovery,
    its row and its computation line together."""
    return (f"to accept the whole claim as a discovery, keeping both "
            f"lines, run: mathema accept {key} {command_word(parent)} "
            f"--as discovery")


def _infinity_option(offer: str) -> str:
    return ("if inputs this large are out of scope, bound the computation "
            f"alone (the claim keeps its domain): {offer}")


def fixes(found: "dict | None", row: str, key: str,
          parent: "str | None" = None, whole: bool = False,
          offer: "str | None" = None) -> list:
    """Intent:
        The fixes a falsified computation line offers under what its
        conditioning says, each the text of one option. `row` is the
        line's own name and `parent` the claim it is the computation of
        (`shift[float]` of `shift`), None where the claim is its own
        computation line. A loss the conditioning explains (or a claim
        that is its own line) offers the claim words that keep the
        computation within reach, when there are any, and the command
        that records the loss as a discovery of `row`. A computation
        line whose loss is the code's, or not known to be inherent
        (`found` None where no conditioning was read), is not accepted
        alone: it offers fixing the code, and narrowing the claim's
        domain knowingly by superseding `parent`, and, where `whole`
        (`parent` is proven), accepting `parent` whole as a discovery.
        `offer` is the `let |inf| be B` a run of the claim under it
        showed holding on this line, offered after fixing the code where
        the loss is not inherent, and in place of the narrowing where
        it is.
    """
    found = found or {}
    bound = [_infinity_option(offer)] if offer else []
    if parent is not None and found.get("inherent") is not True:
        return ["fix the code", *bound,
                *([whole_claim_option(key, parent)] if whole else []),
                f"to narrow the domain knowingly, edit {parent}, then run: "
                f"mathema accept {key} {command_word(parent)} --as superseded"]
    out = list(bound)
    if not bound and found.get("narrow"):
        out.append("if inputs this large are out of scope, narrow the "
                   f"domain: {found['narrow']}")
    out.append(f"if the loss is accepted, run: mathema accept {key} "
               f"{command_word(str(row))} --as discovery")
    return out


def finding_words(key: str, point_text: str, found: dict) -> str:
    """The sentence a definition row's record carries for a loss its
    conditioning explains."""
    return (f"{key} loses {short(found['error'])} of the result at "
            f"{point_text}, within what its conditioning explains "
            f"(ill-conditioned there, κ ≈ {short(found['kappa'])}): a "
            f"finding about its computation; the row stands")
