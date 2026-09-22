# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A Facts without a syntax tree adjudicates, degrading honestly.

`check_conjectures(fn, ..., facts=...)` never calls `analyze_source`
when facts is supplied, and every consumer treats `tree is None` as
valid. This is the seam a non-Python frontend uses: it states what it
honestly can (params, kinds, purity, a namespaced form hash), omits
the tree, and the engine probes normally while the body-lifting derive
routes decline rather than crash. The regression net here keeps that
seam open.
"""
from dataclasses import replace

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim


def _double(x: float) -> float:
    """Twice x."""
    return 2 * x


def _foreign_facts():
    # what a frontend for another language could honestly produce:
    # the real fields, minus the Python tree, with a namespaced form
    facts = analyze_source(_double)
    return replace(facts, tree=None, form="ts:0011223344ab")


def test_probe_route_adjudicates_normally_with_no_tree():
    (p,) = check_conjectures(_double, [claim("for x in [0, 4], f(x) >= 0",
                                             route="probe")],
                             facts=_foreign_facts())
    assert p.verdict == "holds"
    assert p.n > 0


def test_derive_route_degrades_honestly_with_no_tree():
    (p,) = check_conjectures(_double, [claim("for x in [0, 4], f(x) == 2*x",
                                             route="derive")],
                             facts=_foreign_facts())
    # no body to lift: the empirical fallback rescues the claim as
    # evidence, never proof, with the derive gap stated in the record
    # (route supersession: a probe holds supersedes a derive unknown)
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "underivable" in (p.note or "")
    from mathema.reason_codes import ClaimReasonCode, claim_reason_code
    assert claim_reason_code(p) in (ClaimReasonCode.DERIVE_GAP_EMPIRICAL,
                                    None) and "derive" in (p.note or "")


def test_route_best_falls_through_to_the_probe():
    (p,) = check_conjectures(_double, [claim("for x in [0, 4], f(x) == 2*x")],
                             facts=_foreign_facts())
    assert p.verdict == "holds", (p.verdict, p.note)


def test_the_namespaced_form_hash_is_carried_not_recomputed():
    facts = _foreign_facts()
    assert facts.form.startswith("ts:")
    (p,) = check_conjectures(_double, [claim("f(x) >= 0", route="probe")],
                             facts=facts)
    assert p.verdict in ("holds", "falsified")


def _proxy_shaped(impl, params):
    """A callable with an adaptor proxy's exact dunder shape: opaque
    closure body, empty module, injected facts."""
    import inspect

    def proxy(*args, **kwargs):
        return impl(*args, **kwargs)
    proxy.__name__ = impl.__name__
    proxy.__qualname__ = f"ts:src/{impl.__name__}.ts#{impl.__name__}"
    proxy.__module__ = ""
    proxy.__signature__ = inspect.Signature([
        inspect.Parameter(p, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for p in params])
    facts = analyze_source(impl)
    proxy.__mathema_facts__ = replace(facts, tree=None,
                                      form="ts:0011223344ab")
    return proxy


def test_equivalence_honours_injected_facts_on_the_bound_function():
    """`f =:= g` with g a foreign proxy: g's params must come from its
    injected facts, not from analyzing the closure (which has none),
    and the code-vs-code rung must then adjudicate both real
    callables."""
    g = _proxy_shaped(_double, ["x"])
    (p,) = check_conjectures(_double, [claim("for x in [-4, 4], f =:= g",
                                             funcs={"g": g})])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert p.route == "probe"


def test_equivalence_still_skips_on_a_real_arity_mismatch():
    def _two(x: float, y: float) -> float:
        """Sum."""
        return x + y
    g = _proxy_shaped(_two, ["x", "y"])
    (p,) = check_conjectures(_double, [claim("f =:= g", funcs={"g": g})])
    assert p.verdict == "skipped:misspecified"
    assert "arity differs" in (p.note or "")


def test_check_conjectures_honours_the_facts_attribute():
    """The attribute must work at THIS seam too, not only through
    analyze(): verify's sweep and any direct check_conjectures caller
    reach a proxy without passing facts=."""
    proxy = _double
    try:
        _double.__mathema_facts__ = _foreign_facts()
        (p,) = check_conjectures(proxy, [claim("for x in [0, 4], f(x) >= 0",
                                               route="probe")])
        assert p.verdict == "holds"
    finally:
        del _double.__mathema_facts__
