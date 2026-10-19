# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_finite(f(x))` and `is_real(f(x))` on a function that returns a
number are decided the same way whether numpy is installed or not: a
real number is finite when it is neither an infinity nor a NaN, a
complex number when both its parts are, and a real number is real
where a complex one is not."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mathema.matrices as M

ROOT = Path(__file__).resolve().parent.parent

_CLAIMS = r'''
import json, math, sys
if BLOCK:
    sys.modules["numpy"] = None
from mathema.conjecture import check_conjectures, claim


def guarded_sqrt(variance: float) -> float:
    if variance < 0:
        raise ValueError("variance is negative")
    return math.sqrt(variance)


def doubled(x: float) -> float:
    return x * 2.0


def unbounded(x: float) -> float:
    return math.inf


def as_complex(x: float) -> complex:
    return complex(x, 1.0)


def complex_infinite(x: float) -> complex:
    return complex(x, math.inf)


rows = [
    (guarded_sqrt, "is_finite(f(variance))"),
    (doubled, "is_finite(f(x))"),
    (unbounded, "is_finite(f(x))"),
    (as_complex, "is_finite(f(x))"),
    (complex_infinite, "is_finite(f(x))"),
    (doubled, "is_real(f(x))"),
    (as_complex, "is_real(f(x))"),
]
out = {}
for fn, text in rows:
    (p,) = check_conjectures(fn, [claim(text)])
    out[f"{fn.__name__}: {text}"] = [p.verdict, p.route, p.note or "",
                                     p.counterexample or ""]
print(json.dumps({"numpy": "numpy" in sys.modules
                  and sys.modules["numpy"] is not None, "rows": out}))
'''


def _run(block: bool, folder: Path) -> dict:
    script = folder / "claims.py"
    script.write_text(f"BLOCK = {block}\n" + _CLAIMS)
    done = subprocess.run([sys.executable, str(script)], cwd=ROOT,
                          env={**os.environ, "PYTHONPATH": str(ROOT)},
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module", params=[True, False],
                ids=["numpy blocked", "numpy as installed"])
def rows(request, tmp_path_factory):
    got = _run(request.param, tmp_path_factory.mktemp("claims"))
    if request.param:
        assert got["numpy"] is False
    return got["rows"]


def test_a_finite_scalar_result_holds(rows):
    for key in ("doubled: is_finite(f(x))",
                "guarded_sqrt: is_finite(f(variance))"):
        verdict, route, note, _ = rows[key]
        assert (verdict, route) == ("holds", "probe:algorithmic"), (key, note)
        assert "no evaluable inputs" not in note, (key, note)


def test_the_guarded_row_still_states_its_working_domain(rows):
    note = rows["guarded_sqrt: is_finite(f(variance))"][2]
    assert "the working domain is variance in [0, oo)" in note, note


def test_an_infinite_scalar_result_is_falsified(rows):
    verdict, _, note, witness = rows["unbounded: is_finite(f(x))"]
    assert verdict == "falsified", note
    assert "result is not finite" in witness, witness


def test_a_complex_result_is_finite_when_both_parts_are(rows):
    verdict, _, note, _ = rows["as_complex: is_finite(f(x))"]
    assert verdict == "holds", note
    verdict, _, note, witness = rows["complex_infinite: is_finite(f(x))"]
    assert verdict == "falsified", note
    assert "result is not finite" in witness, witness


def test_a_real_scalar_result_is_real_and_a_complex_one_is_not(rows):
    verdict, _, note, _ = rows["doubled: is_real(f(x))"]
    assert verdict == "holds", note
    verdict, _, note, witness = rows["as_complex: is_real(f(x))"]
    assert verdict == "falsified", note
    assert "result is not real" in witness, witness


_SCALARS = [
    (3, True, True), (2.5, True, True), (-0.0, True, True),
    (math.nan, False, True), (math.inf, False, True),
    (-math.inf, False, True),
    (1 + 2j, True, False), (1 + 0j, True, False),
    (complex(math.inf, 0.0), False, False),
    (complex(0.0, math.nan), False, False),
]


@pytest.mark.parametrize("value,finite,real", _SCALARS,
                         ids=[repr(v[0]) for v in _SCALARS])
def test_the_pure_python_checks_decide_a_number(monkeypatch, value,
                                                finite, real):
    monkeypatch.setattr(M, "_numpy", lambda: None)
    assert M.PROPERTIES["is_finite"].check(value) is finite
    assert M.PROPERTIES["is_real"].check(value) is real


_VECTORS = [[1.0, 2.0], [1, 2.5], [1.0, 2j], [[1.0, 0.0], [0.0, 1.0]],
            [[1.0, 1j], [0.0, 1.0]]]


@pytest.mark.parametrize("value", _VECTORS, ids=[repr(v) for v in _VECTORS])
def test_the_pure_python_is_real_reads_a_vector_or_matrix(monkeypatch,
                                                          value):
    monkeypatch.setattr(M, "_numpy", lambda: None)
    flat = value if not isinstance(value[0], list) else \
        [v for row in value for v in row]
    assert M.PROPERTIES["is_real"].check(value) is \
        (not any(isinstance(v, complex) for v in flat))


@pytest.mark.parametrize("value", [v for v, _, _ in _SCALARS] + _VECTORS,
                         ids=[repr(v) for v, _, _ in _SCALARS]
                         + [repr(v) for v in _VECTORS])
def test_numpy_and_pure_python_agree_on_numbers(monkeypatch, value):
    pytest.importorskip("numpy")
    with_numpy = {n: M.PROPERTIES[n].check(value)
                  for n in ("is_finite", "is_real")}
    monkeypatch.setattr(M, "_numpy", lambda: None)
    without = {n: M.PROPERTIES[n].check(value)
               for n in ("is_finite", "is_real")}
    assert with_numpy == without
