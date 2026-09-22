# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""L8: the probe route reaches two more shapes. A relation over a
matrix/array-valued return (`0 <= f(X) <= 1`) is adjudicated ELEMENTWISE
(a scalar broadcasts across the matrix), and a dict-taking function has
its mapping parameter synthesised (with the string keys the body reads)
instead of skipped."""
import textwrap

import pytest

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.probing import relation_holds_elementwise


def _load(tmp_path, body, name="m"):
    import importlib.util

    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law):
    (pr,) = check_conjectures(fn, [claim(law)])
    return pr


# --- the elementwise comparator -------------------------------------------

def test_relation_holds_elementwise_broadcasts_and_reduces():
    # a scalar broadcasts across a nested list, and the relation holds
    # iff it holds at every element.
    assert relation_holds_elementwise(0, [[0.1, 0.9], [0.5, 1.0]], "<=", 1e-9)
    assert not relation_holds_elementwise(0, [[0.1, -0.2]], "<=", 1e-9)
    assert relation_holds_elementwise([[1.0, 2.0]], [[1.0, 2.0]], "==", 1e-9)
    # a value that does not order is unanswerable, not false
    assert relation_holds_elementwise(1j, 2, "<", 1e-9) is None
    # mismatched shapes are unanswerable, not false
    assert relation_holds_elementwise([1, 2, 3], [1, 2], "==", 1e-9) is None


# --- matrix-valued / elementwise laws -------------------------------------

def test_elementwise_matrix_law_holds_and_falsifies(tmp_path):
    pytest.importorskip("numpy")
    mod = _load(tmp_path, '''
        import numpy as np
        from mathema.types import Mat

        def clamp01(X: Mat("n", "n")):
            """Every element into [0, 1]."""
            return np.clip(np.asarray(X, dtype=float), 0.0, 1.0)

        def keep(X: Mat("n", "n")):
            """Unchanged; elements can exceed 1."""
            return np.asarray(X, dtype=float)
    ''')
    good = _one(mod.clamp01, "for X in R^(n*n), 0 <= f(X) <= 1")
    assert good.verdict == "holds"
    assert good.route == "probe"

    bad = _one(mod.keep, "for X in R^(n*n), 0 <= f(X) <= 1")
    assert bad.verdict == "falsified"
    assert bad.counterexample


# --- dict parameters -------------------------------------------------------

def test_dict_param_is_detected_and_synthesised(tmp_path):
    mod = _load(tmp_path, '''
        def total(d: dict) -> float:
            """Sum of the values."""
            return float(sum(d.values()))

        def weighted(cfg) -> float:
            """Reads specific keys (unannotated dict)."""
            return cfg["price"] * cfg["qty"]
    ''')
    # the mapping parameter is classified dict, from the annotation and
    # from the string-key / .values() usage.
    assert analyze_source(mod.total).param_kinds["d"] == "dict"
    assert analyze_source(mod.weighted).param_kinds["cfg"] == "dict"

    # synthesised as a dict, so summing its values does not crash
    assert _one(mod.total, "total(d) >= -1e9").verdict == "holds"
    # the specific keys the body reads are present in the synthesised dict
    p = _one(mod.weighted, 'weighted(cfg) == cfg["price"] * cfg["qty"]')
    assert p.verdict == "holds"


def test_dict_param_law_falsifies_with_a_dict_witness(tmp_path):
    mod = _load(tmp_path, '''
        def diff(cfg: dict) -> float:
            """Claims non-negativity, but a - b can be negative."""
            return cfg["a"] - cfg["b"]
    ''')
    pr = _one(mod.diff, "diff(cfg) >= 0")
    assert pr.verdict == "falsified"
    assert "'a'" in (pr.counterexample or "") and "'b'" in (pr.counterexample or "")


def test_dict_return_subscript_still_works(tmp_path):
    mod = _load(tmp_path, '''
        def stats(x: float) -> dict:
            """A summary dict."""
            return {"sq": x * x, "abs": abs(x)}
    ''')
    assert _one(mod.stats, 'f(x)["sq"] >= 0').verdict == "holds"


def test_nested_dict_param_is_synthesised_as_nested(tmp_path):
    # `cfg["inner"]["x"]` needs cfg["inner"] to be a dict, not a scalar;
    # the key tree drives a nested synthesis so the deep access works.
    mod = _load(tmp_path, '''
        def nested(cfg: dict) -> float:
            """A nested value."""
            return cfg["inner"]["x"]
    ''')
    pr = _one(mod.nested, 'nested(cfg) == cfg["inner"]["x"]')
    assert pr.verdict == "holds"


def test_dict_valued_comparison_holds_and_falsifies(tmp_path):
    # a dict literal is allowed in a law; the probe compares the dict
    # return against it (a derive route declines and falls back).
    mod = _load(tmp_path, '''
        def good(x: float) -> dict:
            """Output equals the claimed dict."""
            return {"a": x, "b": x}

        def bad(x: float) -> dict:
            """Output differs from the claimed dict."""
            return {"a": x, "b": x + 1.0}
    ''')
    assert _one(mod.good, 'f(x) == {"a": x, "b": x}').verdict == "holds"
    pr = _one(mod.bad, 'f(x) == {"a": x, "b": x}')
    assert pr.verdict == "falsified"
    assert pr.counterexample
