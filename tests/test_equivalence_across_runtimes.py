# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`f =:= g` compares two Python forms. When either side's facts were
read by a frontend other than the Python one (its provenance names
another frontend, or its form hash sits in another frontend's
namespace), the claim is answered by a registered equivalence family,
or skipped with that reason when no family gives a verdict; the
built-in ladder never runs on such a pair."""
import inspect
from dataclasses import replace

import pytest

from mathema import families
from mathema.analysis import analyze_source
from mathema.claims import check_conjectures, claim
from tests._equivalence_rows import claim_row

REASON = "equivalence across runtimes needs the equivalence family"


def _halve(x):
    if x < 0:
        raise ValueError("negative")
    return x / 2.0


def _halve_elsewhere(x):
    if x < 0:
        raise ArithmeticError("negative")
    return x / 2.0


def _halve_again(y):
    if y < 0:
        raise ValueError("negative")
    return y / 2.0


def _served(impl, *, provenance=None, form=None):
    """A callable standing for `impl` as a runtime adaptor serves it: an
    opaque body, and facts carrying the stated provenance or form."""
    def proxy(*args):
        return impl(*args)
    proxy.__name__ = impl.__name__
    proxy.__signature__ = inspect.signature(impl)
    facts = analyze_source(impl)
    proxy.__mathema_facts__ = replace(
        facts, tree=None,
        form=form if form is not None else facts.form,
        provenance=provenance)
    return proxy


OTHER_FRONTEND = {"frontend": {"name": "sample", "language": "js",
                               "version": "1"}, "koine_hash": "koine-0:00"}


def _foreign_by_provenance(impl):
    return _served(impl, provenance=OTHER_FRONTEND)


def _foreign_by_form(impl):
    return _served(impl, form="ext:0011223344ab")


@pytest.fixture
def equivalence_family():
    registered = []

    def register(route_fn, handles=True):
        class _Family:
            def can_handle(self, fn, facts, claim_name):
                return handles

            def routes(self):
                return {"equivalence": route_fn}
        families.register("equivalence", _Family())
        registered.append(True)
    yield register
    if registered:
        families._REGISTRY.pop("equivalence", None)


def _check(f, g, law="for x in [-4, 4], f =:= g"):
    p = claim_row(check_conjectures(f, [claim(law, funcs={"g": g})]))
    return p


@pytest.mark.parametrize("serve", [_foreign_by_provenance, _foreign_by_form])
def test_a_side_from_another_frontend_is_skipped_without_a_family(serve):
    p = _check(_halve, serve(_halve_elsewhere))
    assert p.verdict == "skipped", (p.verdict, p.note)
    assert p.route == "equivalence"
    assert REASON in (p.note or "")
    assert "mathema.equivalence.rung" not in (p.meta or {})


def test_differently_named_refusals_across_runtimes_are_not_falsified():
    p = _check(_halve, _foreign_by_provenance(_halve_elsewhere),
               law="for x in [-4, -1], f =:= g")
    assert p.verdict == "skipped", (p.verdict, p.note)
    assert p.counterexample is None


def test_the_foreign_side_may_be_on_the_left():
    p = _check(_foreign_by_provenance(_halve), _halve_elsewhere)
    assert p.verdict == "skipped", (p.verdict, p.note)
    assert REASON in (p.note or "")


def test_a_registered_family_answers_a_pair_across_runtimes(equivalence_family):
    def decide(fn, facts, gfn, gfacts, **kwargs):
        return {"verdict": "holds", "route": "probe:algorithmic", "n": 11,
                "note": "decided by the registered family"}
    equivalence_family(decide)
    p = _check(_halve, _foreign_by_provenance(_halve_elsewhere))
    assert p.verdict == "holds" and p.route == "probe:algorithmic"
    assert p.n == 11
    assert "registered family" in (p.note or "")


@pytest.mark.parametrize("handles", [True, False])
def test_a_declining_family_leaves_the_pair_skipped(equivalence_family,
                                                    handles):
    equivalence_family(lambda fn, facts, gfn, gfacts, **kwargs: None,
                       handles=handles)
    p = _check(_halve, _foreign_by_provenance(_halve_elsewhere))
    assert p.verdict == "skipped", (p.verdict, p.note)
    assert REASON in (p.note or "")
    assert "mathema.equivalence.rung" not in (p.meta or {})


def test_two_python_functions_still_run_the_ladder():
    p = _check(_halve, _halve_again)
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.meta["mathema.equivalence.rung"] == "form"


def test_two_python_functions_with_different_refusals_are_still_falsified():
    p = _check(_halve, _halve_elsewhere, law="for x in [-4, -1], f =:= g")
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.parametrize("provenance,form", [
    ({"frontend": {"name": "python"}}, None),
    ({"frontend": "python"}, None),
    (None, "doc:0011aabb"),
    (None, "py:0011aabb"),
    ({"frontend": {"name": "python"}}, "koine-1:0011aabb"),
])
def test_facts_read_by_the_python_frontend_are_not_foreign(provenance, form):
    p = _check(_halve, _served(_halve_again, provenance=provenance,
                               form=form))
    assert p.verdict != "skipped", (p.verdict, p.note)
    assert "mathema.equivalence.rung" in (p.meta or {})
