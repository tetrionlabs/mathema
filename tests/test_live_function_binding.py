# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A second function bound with `funcs=` as a live callable is stored as
a `let` binding when it has an importable path that resolves back to the
same object, so a claim rebuilt from its record binds the same function.
A callable with no such path (a lambda, a nested function, a wrapper
whose name points elsewhere) keeps the law and leaves the binding out."""
import functools

from mathema.conjecture import check_conjectures, claim
from mathema.spec import callable_ref, canonical_claim_text, declare, entry_claims


def doubled(x: float) -> float:
    return 2 * x


def summed(x: float) -> float:
    return x + x


def _wrap(fn):
    @functools.wraps(fn)
    def inner(x):
        return fn(x)
    return inner


wrapped_summed = _wrap(summed)


def _row_verdict(p):
    (rebuilt,) = entry_claims({"claims": [{"name": p.name,
                                           "statement": p.statement}]})
    (again,) = check_conjectures(doubled, [rebuilt])
    return again.verdict


def test_an_importable_function_is_stored_as_a_let_binding():
    ref = callable_ref(summed)
    assert ref is not None and ref.endswith(".summed")
    cj = claim("f(x) == g(x)", funcs={"g": summed})
    assert canonical_claim_text(cj) == f"let g = {ref}, f(x) = g(x)"
    (p,) = check_conjectures(doubled, [cj])
    assert p.verdict == "proven"
    assert p.statement.startswith(f"let g = {ref}, ")
    assert _row_verdict(p) == "proven"


def test_the_let_spelling_and_the_live_binding_are_the_same_claim():
    ref = callable_ref(summed)
    live = claim("f(x) == g(x)", funcs={"g": summed})
    spelled = claim(f"let g = {ref}, f(x) == g(x)")
    assert canonical_claim_text(live) == canonical_claim_text(spelled)


def test_a_lambda_has_no_path_and_keeps_only_the_law():
    cj = claim("f(x) == g(x)", funcs={"g": lambda x: x + x})
    assert callable_ref(cj.funcs["g"]) is None
    assert canonical_claim_text(cj) == "f(x) = g(x)"
    assert "funcs" not in declare(cj)


def test_a_wrapper_whose_name_points_elsewhere_is_not_bound_by_that_name():
    # functools.wraps copies summed's qualname, which resolves to summed,
    # not to the wrapper that would actually be called
    assert callable_ref(wrapped_summed) is None
    assert "funcs" not in declare(claim("f(x) == g(x)",
                                        funcs={"g": wrapped_summed}))


def test_a_name_resolved_from_f_s_module_keeps_its_bare_spelling():
    # a bare call name resolves from f's module again when the claim is
    # rebuilt, so its stored text stays exactly what the author wrote
    (p,) = check_conjectures(doubled, [claim("f(x) == summed(x)")])
    assert p.verdict == "proven"
    assert p.statement == "f(x) = summed(x)"
    assert _row_verdict(p) == "proven"
