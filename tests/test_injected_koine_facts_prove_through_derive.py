# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A callable whose injected facts carry only a KOINE document (no
syntax tree, nothing read off a body) has its claims proven through the
derive route, as the Python function the document was written from
does, and is lifted from its document when a claim binds it as a
helper."""
import inspect
import warnings

import mathema
from mathema.analysis import Facts, analyze_source
from mathema.koine import Document, koine_hash
from mathema.koine._render import materialise, render
from mathema.symbolic import try_prove
from tests._koine_docs import golden, koine_fixture

koine_py = koine_fixture()

GROWTH_CLAIMS = ["for r in [-1, 5], for x in [-10, 10], f(x, r) == x * (1 + r)",
                 "for r in [-5, -1.5], raises(f(x, r), ValueError)"]


def _only_the_document(d: Document) -> Facts:
    """Facts stating the function's name, parameters, kinds and form,
    and its body only as the document: no tree, no loops, no branches,
    no guards."""
    params = d.parameter_names
    kinds = {p: "sequence" if d.parameter_kind(p) == "kind::sequence" else "scalar"
             for p in params}
    return Facts(name=d.name, signature="(" + ", ".join(params) + ")", params=params,
                 param_kinds=kinds, returns_kind="scalar", docstring=None, source="",
                 effects=[], is_pure=True, loops=[], comprehensions=[], recursion=False,
                 branch_count=0, call_groups={"math": [], "builtin": [], "external": []},
                 max_loop_depth=0, lines=0, form=koine_hash(d), sigh="0" * 12, koine=d)


def _stand_in(d: Document):
    """A callable that computes the document's function through an
    opaque wrapper and carries only the document as its facts."""
    impl = materialise(render(d))
    names = ", ".join(d.parameter_names)
    scope = {"impl": impl}
    exec(f"def stand_in({names}):\n    return impl({names})\n", scope)
    fn = scope["stand_in"]
    fn.__name__ = d.name
    fn.__signature__ = inspect.signature(impl)
    fn.__mathema_facts__ = _only_the_document(d)
    return fn


def _claims(rec):
    return {p.name: (p.verdict, p.route) for p in rec.probes
            if not p.name.endswith("[float]") and p.name != "purity"
            and (p.meta or {}).get("mathema.surface") != "mathema"}


def test_the_growth_claims_are_proven_through_derive_from_the_document():
    fn = _stand_in(golden("growth_py"))
    assert fn.__mathema_facts__.tree is None
    rec = mathema.check(fn, claims=GROWTH_CLAIMS)
    assert set(_claims(rec).values()) == {("proven", "derive")}, _claims(rec)
    assert len(_claims(rec)) == 2


def test_the_document_proves_what_the_python_function_proves():
    from_document = _claims(mathema.check(_stand_in(golden("growth_py")), claims=GROWTH_CLAIMS))
    from_python = _claims(mathema.check(koine_py.growth, claims=GROWTH_CLAIMS))
    assert from_document == from_python


def test_a_fold_is_proven_through_derive_from_the_document():
    claim = "assuming len(xs) >= 1, for alpha in [0, 1], f(xs, 1.0) == xs[-1]"
    rec = mathema.check(_stand_in(golden("ema_first_py")), claims=[claim])
    assert list(_claims(rec).values()) == [("proven", "derive")], _claims(rec)


def test_a_helper_bound_by_a_claim_is_lifted_from_its_document():
    g = _stand_in(golden("growth_py"))

    def double(x: float) -> float:
        return 2 * x
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        facts = analyze_source(double)
    assert try_prove(double, facts, "f(g(x, 2))", "6 * x", "==",
                     funcs={"g": g}).status == "proven"
