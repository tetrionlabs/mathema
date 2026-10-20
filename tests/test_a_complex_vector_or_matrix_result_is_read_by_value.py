# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function returning a vector or matrix of complex numbers has a
value, read as a complex array, the same way with numpy installed or
not: `is_finite` and `is_real` decide it by value (finite when both
parts of every entry are, real when every imaginary part is zero), and
the structural families (symmetric, diagonal, positive definite, ...)
decline a complex matrix with the reason. None of them reads the value
as a raise of f."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_CLAIMS = r'''
import json, math, sys
if BLOCK:
    sys.modules["numpy"] = None
from mathema.conjecture import check_conjectures, claim


def off_the_axis(x: float) -> list:
    return [complex(x, 1.0), complex(x, 0.0)]


def on_the_axis(x: float) -> list:
    return [complex(x, 0.0), complex(2 * x, 0.0)]


def imaginary_nan(x: float) -> list:
    return [complex(x, math.nan)]


def hermitian(x: float) -> list:
    return [[complex(1.0, 0.0), complex(x, 1.0)],
            [complex(x, -1.0), complex(2.0, 0.0)]]


def doubled(x: float) -> list:
    return [complex(x, 1.0) * 2, complex(x, 0.0)]


def complex_symmetric(x: float) -> list:
    return [[complex(1.0, 1.0), complex(x, 2.0)],
            [complex(x, 2.0), complex(3.0, 0.0)]]


rows = [
    (complex_symmetric, "trace(f(x)) >= 4"),
    (complex_symmetric, "trace(f(x)) <= 4"),
    (complex_symmetric, "det(f(x)) >= -100"),
    (off_the_axis, "norm(f(x)) >= 0"),
    (off_the_axis, "is_real(f(x))"),
    (off_the_axis, "is_finite(f(x))"),
    (on_the_axis, "is_real(f(x))"),
    (on_the_axis, "is_finite(f(x))"),
    (imaginary_nan, "is_finite(f(x))"),
    (hermitian, "is_real(f(x))"),
    (hermitian, "is_finite(f(x))"),
    (hermitian, "is_symmetric(f(x))"),
    (hermitian, "is_diagonal(f(x))"),
    (hermitian, "is_positive_definite(f(x))"),
    (doubled, "f(x) == f(x)"),
]
out = {}
for fn, text in rows:
    (p,) = check_conjectures(fn, [claim("for x in [0, 1], " + text)])
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


def test_no_complex_result_is_read_as_a_raise(rows):
    for key, (verdict, _route, note, witness) in rows.items():
        if key.startswith("complex_symmetric") or "norm" in key:
            # these rows are judged by their own tests below: an
            # ordering on a complex trace or det, and a norm
            continue
        assert "raised" not in witness and "TypeError" not in note, \
            (key, verdict, witness, note)


def test_a_complex_vector_is_real_only_on_the_axis(rows):
    verdict, route, note, witness = rows["off_the_axis: is_real(f(x))"]
    assert verdict == "falsified", (note, witness)
    assert witness.endswith("result is not real"), witness
    verdict, route, note, _ = rows["on_the_axis: is_real(f(x))"]
    assert (verdict, route) == ("holds", "probe:algorithmic"), note


def test_a_complex_vector_is_finite_when_both_parts_are(rows):
    for key in ("off_the_axis: is_finite(f(x))",
                "on_the_axis: is_finite(f(x))",
                "hermitian: is_finite(f(x))"):
        verdict, route, note, _ = rows[key]
        assert (verdict, route) == ("holds", "probe:algorithmic"), (key, note)
    verdict, _, note, witness = rows["imaginary_nan: is_finite(f(x))"]
    assert verdict == "falsified", note
    assert witness.endswith("result is not finite"), witness


def test_a_complex_matrix_is_not_real(rows):
    verdict, _, note, witness = rows["hermitian: is_real(f(x))"]
    assert verdict == "falsified", note
    assert witness.endswith("result is not real"), witness


@pytest.mark.parametrize("prop", ["is_symmetric", "is_diagonal",
                                  "is_positive_definite"])
def test_a_structural_family_declines_a_complex_matrix(rows, prop):
    verdict, _, note, _ = rows[f"hermitian: {prop}(f(x))"]
    assert verdict == "unknown", (prop, note)
    assert (f"the result is a complex matrix, and {prop} is read over "
            f"real matrices only") in note, note


def test_a_value_claim_on_a_complex_vector_holds(rows):
    verdict, _, note, _ = rows["doubled: f(x) == f(x)"]
    assert verdict == "holds", note


def complex_of(A):
    return [[complex(v, 1.0) for v in row] for row in A]


def test_a_real_matrix_claim_names_the_complex_value_returned():
    pytest.importorskip("numpy")
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(complex_of, [claim(
        "for A in R^(n,n), f(A) == f(A)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "f returned the complex value [[" in p.counterexample, \
        p.counterexample
    assert "TypeError" not in p.counterexample, p.counterexample


@pytest.mark.parametrize("law", ["trace(f(x)) >= 4", "trace(f(x)) <= 4",
                                 "det(f(x)) >= -100"])
def test_an_ordering_on_a_complex_value_is_not_decided(rows, law, request):
    # the trace and determinant of this matrix are complex numbers, which
    # have no order: the claim is misspecified; without numpy the claim's
    # trace and det cannot be computed at all, so it stays unknown
    verdict, _, note, _ = rows[f"complex_symmetric: {law}"]
    expected = ("unknown" if "numpy blocked" in request.node.callspec.id
                else "skipped:misspecified")
    assert verdict == expected, (law, note)


def test_the_norm_of_a_complex_vector_is_real(rows):
    verdict, _, note, _ = rows["off_the_axis: norm(f(x)) >= 0"]
    assert verdict == "holds", note
