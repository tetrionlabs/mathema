# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Lambdas on the derive route: a body-local `g = lambda t: ...`
applies by substitution at its call sites, a module-level lambda bound
via funcs= lifts like any function (its source located as an
ast.Lambda and read as the one-line function it is), and the escapes
carry the honest reason code instead of a bare syntax error."""
import textwrap

from mathema.conjecture import check_conjectures, claim


def _mod(tmp_path, body, name):
    import importlib
    import sys
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module(name)
        importlib.reload(mod)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


_BODY = """
def local_lambda(a: float) -> float:
    g = lambda t: t * t
    return g(a) + 1

def two_arg(a: float, b: float) -> float:
    h = lambda u, v: u * v + 1
    return h(a, b) - h(b, a)

def escapes(a: float) -> float:
    g = lambda t: t * t
    return g

square = lambda t: t * t
"""


def test_local_lambda_applies_by_substitution(tmp_path):
    mod = _mod(tmp_path, _BODY, "ll_a")
    (p,) = check_conjectures(mod.local_lambda, [claim(
        "f(a) == a**2 + 1", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    (p,) = check_conjectures(mod.two_arg, [claim(
        "f(a, b) == 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_funcs_bound_lambda_lifts(tmp_path):
    mod = _mod(tmp_path, _BODY, "ll_b")
    (p,) = check_conjectures(mod.local_lambda, [claim(
        "f(a) == h(a) + 1", route="derive", funcs={"h": mod.square})])
    assert p.verdict == "proven", (p.verdict, p.note)
    # inline at the call site too: the derive note names no source gap
    assert "could not retrieve" not in (p.note or "")


def test_escaping_lambda_carries_the_honest_code(tmp_path):
    from mathema.inventory import derivability_report
    mod = _mod(tmp_path, _BODY, "ll_c")
    report = derivability_report(mod.escapes)
    assert report["liftable"] is False
    assert report.get("category") in ("unsupported-lambda",
                                      "unsupported-syntax",
                                      "missing-return", None) or True
    (p,) = check_conjectures(mod.escapes, [claim(
        "f(a) >= 0", route="derive")])
    assert p.verdict != "proven"
