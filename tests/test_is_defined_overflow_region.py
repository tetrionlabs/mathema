# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_defined` checked by execution samples inside the function's
recorded `is_overflow_safe` region when one exists, a library row or
the project's own claim alike, and otherwise runs to the carrier's
reach, where an overflow is no value. Overflow outside the region is
reported by `is_overflow_safe`, not `is_defined`.

The execution half runs when the derive half declines: a function with
Python source has its totality settled by the mathematics (exp is
total), so the project function here is one mathema cannot read (built
with `exec`), checked by execution alone."""
import textwrap

import pytest

np = pytest.importorskip("numpy")

import mathema  # noqa: E402
from mathema.conjecture import claim  # noqa: E402


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_EX = '''
    import numpy as np

    exec("def ex(x):\\n    return float(np.exp(x))\\n")
'''

_SOURCED = '''
    import numpy as np

    def ex(x):
        return float(np.exp(x))
'''

_REGION = "x <= 709.782712893384"


def _defined(fn, *extra):
    rec = mathema.check(fn, claims=[claim("is_defined(f)"), *extra])
    (p,) = [p for p in rec.probes if p.name.startswith("is_defined")]
    return p


def test_a_project_overflow_row_keeps_is_defined_inside_it(tmp_path):
    ex = _load(tmp_path, _EX, "ov_ex_in").ex
    p = _defined(ex, claim(_REGION, name="is_overflow_safe"))
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
    assert "overflow-safe region" in (p.note or ""), p.note


def test_without_the_row_is_defined_meets_the_overflow(tmp_path):
    ex = _load(tmp_path, _EX, "ov_ex_out").ex
    p = _defined(ex)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "is_overflow_safe" in (p.note or "") + (p.counterexample or ""), \
        (p.note, p.counterexample)


def test_a_claims_file_row_counts_under_verify(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "ovmod.py").write_text(textwrap.dedent(_EX))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "ovmod.claims.yaml").write_text(textwrap.dedent(f"""
        ovmod.ex:
          claims:
            - name: is_overflow_safe
              statement: "{_REGION}"
            - name: defined
              statement: "is_defined(f)"
    """))
    result = verify_project(str(tmp_path))
    rows = {e["key"]: {c["claim"]: c["verdict"] for c in e["claims"]}
            for e in result.keys}
    assert rows["ovmod.ex"]["defined"] == "holds", rows["ovmod.ex"]
    assert rows["ovmod.ex"]["is_overflow_safe"] == "holds", rows["ovmod.ex"]


def test_the_mathematics_still_proves_totality(tmp_path):
    ex = _load(tmp_path, _SOURCED, "ov_ex_math").ex
    rec = mathema.check(ex, claims=["is_defined(f)"])
    (p,) = [p for p in rec.probes if p.name.startswith("is_defined")]
    assert p.verdict == "proven", (p.verdict, p.note)
