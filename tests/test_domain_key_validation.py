# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A domain key that doesn't match any real parameter (a typo, most
commonly) used to be silently ignored on both routes, the derive
route's _domain_assumptions() only ever iterates real params and never
cross-checks the domain dict's own keys, and probing.py's
domain_enforced battery did the identical silent `continue`. Either way,
a claim's own declared restriction was never actually applied, and
nothing said so: a claim could come back holds/falsified against an
unintentionally-unrestricted sample. check_conjectures() now validates
every cj_domain key against facts.params before any dispatch, on both
routes."""
from mathema.conjecture import check_conjectures, claim


def line(x: float) -> float:
    return 3.0 * x + 2.0


def test_mistyped_quantifier_key_is_skipped_not_silently_unrestricted():
    results = check_conjectures(
        line, [claim("for xyz in [0, 1], f(x) >= 0", route="probe")])
    assert results[0].verdict == "skipped"
    assert "xyz" in results[0].note
    assert "x" in results[0].note


def test_mistyped_domain_dict_key_is_skipped_on_the_derive_route():
    results = check_conjectures(
        line, [claim("f(x) == 3.0 * x + 2.0", route="derive")],
        domain={"xyz": (0, 1)})
    assert results[0].verdict == "skipped"
    assert "xyz" in results[0].note


def test_correctly_named_domain_key_is_unaffected():
    results = check_conjectures(
        line, [claim("for x in [0, 1], f(x) >= 0", route="probe")])
    assert results[0].verdict == "holds"
