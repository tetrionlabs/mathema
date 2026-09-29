# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `shape` probe reads a parameter's dimensions from the claim's
binding as well as from a marker, so `for A in R^(30,15)` with a return
marker gets the output check and draws the fixed input size. The
`dimensions_enforced` probe (formerly `shape_enforced`) asks whether the
function rejects a mismatch on a shared dimension, and the
`size_enforced` probe whether it rejects a wrong fixed size a marker
states; a fixed size stated only by a claim's binding emits no row."""
import importlib.util
import re
import textwrap

import pytest

import mathema
from mathema.types import Mat, type_probes


def _load(tmp_path, name, body):
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_shape_probe_reads_a_fixed_binding_and_draws_it(tmp_path):
    pytest.importorskip("numpy")
    m = _load(tmp_path, "shape_binding_mod", '''
        import numpy as np

        from mathema.types import Mat

        SEEN = []


        def transpose(A: np.ndarray) -> Mat(15, 30):
            """The transpose."""
            SEEN.append(tuple(np.shape(A)))
            return A.T


        def not_transposed(A: np.ndarray) -> Mat(15, 30):
            """Claims the transpose's shape, returns the input."""
            return A
    ''')
    rec = mathema.check(m.transpose, claims=["for A in R^(30,15), f(A) == f(A)"])
    (shape,) = [p for p in rec.probes if p.name == "shape"]
    assert shape.verdict == "holds", (shape.verdict, shape.note, shape.counterexample)
    # every draw is 30 by 15: a fixed size stated only by the binding
    # emits no `size_enforced` row, so nothing tries another size
    assert set(m.SEEN) == {(30, 15)}, sorted(set(m.SEEN))
    assert not [p for p in rec.probes if p.name == "size_enforced"]
    rec = mathema.check(m.not_transposed,
                        claims=["for A in R^(30,15), f(A) == f(A)"])
    (shape,) = [p for p in rec.probes if p.name == "shape"]
    assert shape.verdict == "falsified", (shape.verdict, shape.note)
    assert "expected shape (15, 30)" in (shape.counterexample or ""), shape.counterexample


def test_a_shared_name_in_the_binding_binds_the_return_marker(tmp_path):
    pytest.importorskip("numpy")
    m = _load(tmp_path, "shape_named_mod", '''
        import numpy as np

        from mathema.types import Mat


        def transpose(A: np.ndarray) -> Mat("n", "m"):
            """The transpose."""
            return A.T
    ''')
    rec = mathema.check(m.transpose, claims=["for A in R^(m,n), f(A) == f(A)"])
    (shape,) = [p for p in rec.probes if p.name == "shape"]
    assert shape.verdict == "holds", (shape.verdict, shape.note, shape.counterexample)


def test_without_a_binding_or_marker_there_is_no_shape_probe(tmp_path):
    pytest.importorskip("numpy")
    m = _load(tmp_path, "shape_none_mod", '''
        import numpy as np

        from mathema.types import Mat


        def transpose(A: np.ndarray) -> Mat("n", "m"):
            """The transpose."""
            return A.T
    ''')
    rec = mathema.check(m.transpose, claims=["f(A) == f(A)"])
    assert not [p for p in rec.probes if p.name == "shape"]


def test_dimensions_enforced_is_the_shared_dimension_probe():
    def matmul(a: Mat("m", "n"), b: Mat("n", "p")) -> Mat("m", "p"):
        m, n, p = len(a), len(a[0]), len(b[0])
        return [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(p)]
                for i in range(m)]

    names = {p.name for p in type_probes(matmul)}
    assert "dimensions_enforced" in names, names
    assert "shape_enforced" not in names, names
    (probe,) = [p for p in type_probes(matmul) if p.name == "dimensions_enforced"]
    assert "mismatched sizes on shared dims" in probe.statement, probe.statement


def test_size_enforced_witnesses_an_accepted_wrong_fixed_size():
    def diag_sum(A: Mat(30, 15)) -> float:
        return float(sum(A[i][i] for i in range(15)))

    (probe,) = [p for p in type_probes(diag_sum) if p.name == "size_enforced"]
    assert probe.verdict == "falsified", (probe.verdict, probe.note)
    assert re.search(r"A is 3[123] by 15 where the shape fixes 30 by 15",
                     probe.counterexample or ""), probe.counterexample
    assert "30 by 15" in probe.statement, probe.statement
    # the witness names distinct wrong sizes only, the smallest and the
    # largest tried, never the same size twice
    entries = probe.counterexample.split("; ")
    assert len(entries) == len(set(entries)) <= 2, entries
    assert all(re.fullmatch(r"A is \d+ by \d+ where the shape fixes 30 by 15", e)
               for e in entries), entries
    assert probe.n == 6, probe.n


def test_a_binding_only_fixed_size_emits_no_size_row_and_passes(tmp_path):
    """A marker gates, a claim binding does not: an unguarded function
    with a fixed-shape claim passes `check` and `verify` on that claim
    alone. Whether the code rejects a wrong shape is the declared
    `excluded_outside_domain(A)` claim's question."""
    from mathema.verify import gate
    pytest.importorskip("numpy")
    m = _load(tmp_path, "binding_only_mod", '''
        import numpy as np


        def frob(A: np.ndarray) -> float:
            """Sum of squares of every entry, whatever the shape."""
            return float((A * A).sum())
    ''')
    rec = mathema.check(m.frob, claims=["for A in R^(30,15), f(A) >= 0"])
    names = {p.name for p in rec.probes}
    assert "size_enforced" not in names, names
    report = gate(rec.probes, strict=False)
    assert report.problems == [], (report.problems, [(p.name, p.verdict) for p in rec.probes])


def test_a_marker_fixed_size_emits_the_row_and_gates():
    from mathema.verify import gate

    def diag_sum(A: Mat(30, 15)) -> float:
        return float(sum(A[i][i] for i in range(15)))

    rec = mathema.check(diag_sum, claims=[])
    (row,) = [p for p in rec.probes if p.name == "size_enforced"]
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert gate(rec.probes, strict=False).problems == ["1 falsified claim(s)"]


def test_size_enforced_gates_exactly_as_dimensions_enforced():
    """Both rows are type probes (surface `types`): a falsified one is a
    falsified claim that fails `check` and `verify` in every mode, the
    same for a wrong fixed size as for a mismatched shared dimension."""
    from mathema.verify import gate

    def matmul(a: Mat("m", "n"), b: Mat("n", "p")) -> Mat("m", "p"):
        m, n, p = len(a), len(a[0]), len(b[0])
        return [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(p)]
                for i in range(m)]

    def diag_sum(A: Mat(30, 15)) -> float:
        return float(sum(A[i][i] for i in range(15)))

    for fn, name in ((matmul, "dimensions_enforced"), (diag_sum, "size_enforced")):
        rec = mathema.check(fn, claims=[])
        (row,) = [p for p in rec.probes if p.name == name]
        assert row.verdict == "falsified", (name, row.verdict, row.note)
        assert row.meta.get("mathema.surface") == "types", (name, row.meta)
        for strict in (False, True):
            report = gate([row], strict=strict)
            assert report.falsified == 1, (name, strict, report)
            assert report.problems == ["1 falsified claim(s)"], (name, strict, report.problems)


def test_size_enforced_holds_when_the_function_refuses_the_size():
    def diag_sum(A: Mat(30, 15)) -> float:
        if len(A) != 30 or len(A[0]) != 15:
            raise ValueError("expected 30 by 15")
        return float(sum(A[i][i] for i in range(15)))

    (probe,) = [p for p in type_probes(diag_sum) if p.name == "size_enforced"]
    assert probe.verdict == "holds", (probe.verdict, probe.note)


def test_size_enforced_is_absent_without_a_fixed_size():
    def matmul(a: Mat("m", "n"), b: Mat("n", "p")) -> Mat("m", "p"):
        return [[0.0] * len(b[0]) for _ in a]

    assert "size_enforced" not in {p.name for p in type_probes(matmul)}
