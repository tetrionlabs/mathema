# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The built-in stateless claims call a function the way its signature
accepts: a keyword-only parameter by keyword (`f(a, b=b)`), every other
one positionally, so the claim reaches the function rather than
misfitting its signature."""
import random

import mathema
from mathema.conjecture import check_conjectures, claim


def shifted(a, *, b=1):
    return a + b


def noisy_shift(a, *, b=1):
    return a + b + random.random()


def plain(a, b=1):
    return a + b


def _rows(fn, keyword):
    return {p.name: p for p in mathema.check(fn, claims=[keyword]).probes}


def test_stateless_members_call_a_keyword_only_parameter_by_keyword():
    rows = _rows(shifted, "stateless")
    for name in ("is_deterministic", "is_state_safe"):
        p = rows[name]
        assert p.verdict == "proven", (name, p.verdict, p.note)
        assert p.statement == "f(a, b=b) = f(a, b=b)", p.statement


def test_a_nondeterministic_keyword_only_function_is_falsified():
    p = _rows(noisy_shift, "stateless")["is_deterministic"]
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_positional_signature_keeps_the_positional_call():
    rows = _rows(plain, "stateless")
    assert rows["is_deterministic"].statement == "f(a, b) = f(a, b)"
    assert rows["is_deterministic"].verdict == "proven"


def test_is_repeatable_children_reach_a_keyword_only_function():
    (p,) = check_conjectures(shifted, [claim("is_repeatable(f)",
                                             route="best")])
    assert p.verdict == "proven", (p.verdict, p.note, p.meta)
    assert p.meta["mathema.children"] == {"is_deterministic": "proven",
                                          "is_state_safe": "proven"}
