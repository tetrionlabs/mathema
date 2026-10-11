# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The form step of `f =:= g` proves only from two form hashes mathema
computed itself from Python source. A form string that arrives any
other way (injected facts, facts built by hand) is an identity label,
not a canonical form of the body, so a pair carrying one falls through
to the symbolic and sampled steps."""
import inspect
from dataclasses import replace

from mathema.analysis import analyze_source
from mathema.claims import check_conjectures, claim

SUPPLIED_FORM = "ext:85b0e1bf68f8accc"


def _twice(x):
    return 2.0 * x


def _twice_plus_one(x):
    return 2.0 * x + 1.0


def _opaque(body, form):
    """A callable with no readable body, whose facts carry `form`."""
    proxy = lambda *args: body(*args)  # noqa: E731
    proxy.__name__ = "scale"
    proxy.__signature__ = inspect.Signature([
        inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD)])
    proxy.__mathema_facts__ = replace(analyze_source(body), tree=None,
                                      form=form)
    return proxy


def test_equal_supplied_forms_of_different_bodies_are_not_proven():
    fa = _opaque(_twice, SUPPLIED_FORM)
    fb = _opaque(_twice_plus_one, SUPPLIED_FORM)
    (p,) = check_conjectures(fa, [claim("for x in [-1, 1], f =:= g",
                                        funcs={"g": fb})])
    assert p.meta.get("mathema.equivalence.rung") != "form"
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_equal_supplied_forms_of_equal_bodies_reach_sampling():
    def twice_again(x):
        return x * 2.0
    fa = _opaque(_twice, SUPPLIED_FORM)
    fb = _opaque(twice_again, SUPPLIED_FORM)
    (p,) = check_conjectures(fa, [claim("for x in [-1, 1], f =:= g",
                                        funcs={"g": fb})])
    assert p.meta["mathema.equivalence.rung"] == "sampled"
    assert p.verdict == "holds", (p.verdict, p.note)


def test_hand_built_facts_with_a_python_shaped_form_are_not_trusted():
    """Copying a computed form onto other facts does not carry the
    trust: the form step reads where the form came from, not its
    shape."""
    real = analyze_source(_twice).form
    fa = _opaque(_twice, real)
    fb = _opaque(_twice_plus_one, real)
    (p,) = check_conjectures(fa, [claim("for x in [-1, 1], f =:= g",
                                        funcs={"g": fb})])
    assert p.meta.get("mathema.equivalence.rung") != "form"
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_computed_forms_still_prove_at_the_form_step():
    def twice_renamed(y):
        return 2.0 * y
    (p,) = check_conjectures(_twice, [claim("f =:= g",
                                            funcs={"g": twice_renamed})])
    assert p.verdict == "proven"
    assert p.meta["mathema.equivalence.rung"] == "form"
