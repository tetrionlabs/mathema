# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness lies inside each parameter's declared type. A `str`
parameter is called with strings, a `Vec` parameter with a vector and
a `Mat` parameter with a matrix, sized so shared dimension names
agree; a magnitude corner is a number, so it is only ever tried for a
number. A raise at an input outside the parameter's type says nothing
about the function, and is never a counterexample."""
import ast
import math
import re
import sys

import numpy as np
import pytest

from mathema import enforce_dimensions
from mathema.conjecture import check_conjectures, claim
from mathema.types import Mat, Vec


def ticker_exchange(symbol: str) -> str:
    return symbol.split(".")[1]


def portfolio_variance(weights: Vec("n"), cov: Mat("n", "n")) -> float:
    w = np.asarray(weights)
    return float(w @ np.asarray(cov) @ w)


def factor_exposure(weights: Vec("n"), betas: Mat("n", "k")) -> Vec("k"):
    return list(np.asarray(betas) @ np.asarray(weights))


@enforce_dimensions()
def guarded_variance(weights: Vec("n"), cov: Mat("n", "n")) -> float:
    w = np.asarray(weights)
    return float(w @ np.asarray(cov) @ w)


def _witness_values(counterexample: str) -> dict:
    """`name = value` pairs of a witness text, each value read as a
    Python literal."""
    head = counterexample.split(": f raised")[0]
    out = {}
    for name, text in re.findall(
            r"(\w+) = (.+?)(?=, \w+ = |$)", head):
        out[name] = ast.literal_eval(text)
    return out


def test_a_string_parameter_is_falsified_only_at_a_string():
    (p,) = check_conjectures(ticker_exchange, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    witness = _witness_values(p.counterexample)
    assert isinstance(witness["symbol"], str), p.counterexample
    assert "IndexError" in p.counterexample, p.counterexample


def test_a_vector_and_a_matrix_parameter_draw_a_vector_and_a_matrix():
    for fn in (portfolio_variance, guarded_variance):
        (p,) = check_conjectures(fn, [claim(
            "for weights in [-1e6, 1e6]^n, cov in [-1e6, 1e6]^(n,n), "
            "is_defined(f)")])
        assert p.verdict == "holds", (fn.__name__, p.verdict,
                                      p.counterexample, p.note)


def test_a_vector_and_a_matrix_over_the_whole_line_meet_the_overflow():
    for fn in (portfolio_variance, guarded_variance):
        (p,) = check_conjectures(fn, [claim("is_defined(f)")])
        assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
        witness = _witness_values(_witness_head(p.counterexample))
        weights, cov = witness["weights"], witness["cov"]
        assert len(cov) == len(weights) == len(cov[0]), p.counterexample
        assert max(abs(e) for e in _elements(weights)) >= 1e154, \
            p.counterexample
        assert "returned inf" in p.counterexample, p.counterexample


def test_a_shaped_witness_is_a_vector_and_a_matrix_sharing_n():
    # betas @ weights needs k == n: it raises at consistent shapes
    (p,) = check_conjectures(factor_exposure, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    witness = _witness_values(p.counterexample)
    weights, betas = witness["weights"], witness["betas"]
    assert all(isinstance(v, float) for v in weights), p.counterexample
    assert all(isinstance(row, list) for row in betas), p.counterexample
    assert len(betas) == len(weights), p.counterexample


# --- a marked array meets the magnitude corners a list meets ---------

def norm_vec(v: Vec("n")) -> float:
    return math.sqrt(sum(x * x for x in v))


def norm_list(v: list) -> float:
    return math.sqrt(sum(x * x for x in v))


def doubled_sum_vec(v: Vec("n")) -> float:
    return 2 * sum(v)


def doubled_sum_list(v: list) -> float:
    return 2 * sum(v)


def grand_total(m: Mat("n", "k")) -> float:
    return sum(sum(row) for row in m)


def _elements(value) -> list:
    if isinstance(value, (list, tuple)):
        return [e for v in value for e in _elements(v)]
    return [value]


def _witness_head(counterexample: str) -> str:
    return re.split(r": f (raised|returned)", counterexample)[0]


@pytest.mark.parametrize("fn", [norm_vec, norm_list])
def test_a_vector_and_its_list_twin_overflow_at_a_large_element(fn):
    (p,) = check_conjectures(fn, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    witness = _witness_values(_witness_head(p.counterexample))
    elements = _elements(witness["v"])
    assert isinstance(witness["v"], list), p.counterexample
    assert max(abs(e) for e in elements) >= 1e154, p.counterexample
    assert "returned inf" in p.counterexample, p.counterexample


@pytest.mark.parametrize("fn", [doubled_sum_vec, doubled_sum_list])
def test_a_sequence_meets_the_largest_double(fn):
    (p,) = check_conjectures(fn, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    witness = _witness_values(_witness_head(p.counterexample))
    elements = _elements(witness["v"])
    assert isinstance(witness["v"], list), p.counterexample
    assert max(abs(e) for e in elements) == sys.float_info.max, \
        p.counterexample
    assert "returned inf" in p.counterexample, p.counterexample


def test_a_matrix_meets_the_same_sign_pair_at_the_largest_double():
    (p,) = check_conjectures(grand_total, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    witness = _witness_values(_witness_head(p.counterexample))
    m = witness["m"]
    assert all(isinstance(row, list) for row in m), p.counterexample
    assert len({len(row) for row in m}) == 1, p.counterexample
    assert max(abs(e) for e in _elements(m)) == sys.float_info.max, \
        p.counterexample


def test_a_bounded_vector_stays_inside_its_element_range():
    (p,) = check_conjectures(doubled_sum_vec, [
        claim("for v in [-1e6, 1e6]^n, is_defined(f)")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)


# --- every parameter kind is drawn inside its type -------------------

pd = pytest.importorskip("pandas")

#: every value a recording function below is called with
_DRAWN: list = []


def takes_list(v: list):
    _DRAWN.append(v)
    return 1.0


def takes_list_of_lists(v: list[list[float]]):
    _DRAWN.append(v)
    return 1.0


def takes_tuple(v: tuple):
    _DRAWN.append(v)
    return 1.0


def takes_set(v: set):
    _DRAWN.append(v)
    return 1.0


def takes_frozenset(v: frozenset):
    _DRAWN.append(v)
    return 1.0


def takes_dict(v: dict):
    _DRAWN.append(v)
    return 1.0


def takes_vec(v: Vec("n")):
    _DRAWN.append(v)
    return 1.0


def takes_mat(v: Mat("n", "k")):
    _DRAWN.append(v)
    return 1.0


def takes_ndarray(v: np.ndarray):
    _DRAWN.append(v)
    return 1.0


def takes_dataframe(v: pd.DataFrame):
    _DRAWN.append(v)
    return 1.0


def takes_float(v: float):
    _DRAWN.append(v)
    return 1.0


def takes_int(v: int):
    _DRAWN.append(v)
    return 1.0


def takes_bool(v: bool):
    _DRAWN.append(v)
    return 1.0


def takes_complex(v: complex):
    _DRAWN.append(v)
    return 1.0


def takes_str(v: str):
    _DRAWN.append(v)
    return 1.0


def takes_anything(v):
    _DRAWN.append(v)
    return 1.0

def _drawn(fn) -> tuple:
    """Every value the `is_defined` region probe calls `fn` with, and
    `fn`'s facts; `fn` is called as the family calls it, through its
    runtime types."""
    import random

    from mathema.analysis import analyze_source
    from mathema.claim_families import _region_probe
    from mathema.runtime_types import calling
    facts = analyze_source(fn)
    _DRAWN.clear()
    _region_probe(calling(fn, facts), facts, claim("is_defined(f)"), {},
                  random.Random(0), 60, "is_defined")
    seen = list(_DRAWN)
    assert seen, fn.__name__
    return seen, facts


def _is_real(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _real_list(v) -> bool:
    return isinstance(v, list) and all(_is_real(e) for e in v)


def _real_matrix(v) -> bool:
    return (isinstance(v, list) and len(v) >= 1
            and all(_real_list(r) for r in v)
            and len({len(r) for r in v}) == 1)


#: the function, the kind analysis reads its parameter as, and what
#: every draw must be
KIND_TABLE = [
    (takes_list, "sequence", _real_list),
    (takes_list_of_lists, "sequence", _real_matrix),
    (takes_tuple, "sequence",
     lambda v: isinstance(v, tuple) and all(_is_real(e) for e in v)),
    (takes_set, "sequence",
     lambda v: isinstance(v, set) and all(_is_real(e) for e in v)),
    (takes_frozenset, "sequence",
     lambda v: isinstance(v, frozenset) and all(_is_real(e) for e in v)),
    (takes_dict, "dict", lambda v: isinstance(v, dict)),
    (takes_vec, "sequence", _real_list),
    (takes_mat, "sequence", _real_matrix),
    (takes_ndarray, "vec", lambda v: isinstance(v, np.ndarray) and v.ndim == 1),
    (takes_dataframe, "table", lambda v: isinstance(v, pd.DataFrame)),
    (takes_float, "scalar", _is_real),
    (takes_int, "int", lambda v: isinstance(v, int) and not isinstance(v, bool)),
    (takes_bool, "bool", lambda v: isinstance(v, bool)),
    # int and float are members of complex in Python's numeric tower
    (takes_complex, "complex",
     lambda v: isinstance(v, (int, float, complex)) and not isinstance(v, bool)),
    (takes_str, "string", lambda v: isinstance(v, str)),
    (takes_anything, "unknown", _is_real),
]


@pytest.mark.parametrize("fn, kind, inside", KIND_TABLE,
                         ids=[row[0].__name__ for row in KIND_TABLE])
def test_every_parameter_kind_is_drawn_inside_its_type(fn, kind, inside):
    seen, facts = _drawn(fn)
    assert facts.param_kinds["v"] == kind, (fn.__name__, facts.param_kinds)
    outside = [v for v in seen if not inside(v)]
    assert not outside, (fn.__name__, outside[:3])


def add_to(items: set) -> int:
    items.add(1.0)
    return len(items)


def test_a_set_parameter_is_never_witnessed_by_a_list():
    (p,) = check_conjectures(add_to, [claim("is_defined(f)")])
    assert "AttributeError" not in (p.counterexample or ""), p.counterexample
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)
