# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A TypeError or AttributeError at an operation on a drawn value is a
draw defect only while f has returned on no draw of the claim: once f
returned, the drawn kind is one f takes, and a later raise is a finding.
A value Python hands out shared (a small int, None, a bool,
an interned str) is never matched by identity as the drawn one."""
import importlib.util
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

FNS = '''
    CALLS = []


    def big_f(v):
        return v == 2


    class Q:
        def __init__(self, v):
            self.v = v

        @property
        def bad(self):
            v = self.v
            return v + "z"


    def b_typo_counted(x):
        CALLS.append(type(x).__name__)
        if x == -1:
            return x.bit_lenght()
        return x


    def a_prop_f(x):
        if big_f(x):
            return Q(x).bad
        return x


    def a_attr_typo_f(x):
        if big_f(x):
            return x.is_integr()
        return x


    class P:
        def __init__(self, v):
            self.v = v

        @property
        def twice(self):
            return self.v + "z"


    def prop_te(x):
        return P(x).twice if x == 1 else x


    def a_deliberate_f(x):
        if big_f(x):
            raise TypeError("too big")
        return x


    def bad_helper(v):
        return v.nope


    def s_alias(x):
        if x == 2:
            return bad_helper(2)
        return x


    def typo_attr_str(x):
        return x.uper()


    def big_pair(a, b):
        return [a] * b


    def q_dict(x):
        return {"a": x}


    def two_num_list(n, xs):
        return xs[:n]
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("defects") / "defect_fns.py"
    path.write_text(textwrap.dedent(FNS))
    spec = importlib.util.spec_from_file_location("defect_fns", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["defect_fns"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("defect_fns", None)


def _row(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    return p


# develop's verdict, a real finding each
@pytest.mark.parametrize("name, text", [
    ("b_typo_counted", "f(x) == x"), ("a_prop_f", "f(x) == x"),
    ("a_attr_typo_f", "f(x) == x"), ("prop_te", "f(x) == x"),
    ("a_deliberate_f", "f(x) == x"), ("s_alias", "f(x) == x"),
])
def test_a_raise_after_f_returned_or_not_on_the_drawn_value_is_a_finding(
        mod, name, text):
    p = _row(getattr(mod, name), text)
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)
    assert "mathema.draw_defect" not in (p.meta or {})


def test_a_raise_on_every_draw_of_a_float_is_a_draw_defect(mod):
    # f never returned on a float: a misspelt method cannot be told from
    # an attribute of a type the probe did not draw (`x.shape`)
    p = _row(mod.typo_attr_str, "f(x) == f(x)")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.draw_defect"]["param"] == "x"


def test_a_draw_defect_names_the_parameter_whose_value_raised(mod):
    p = _row(mod.big_pair, "f(a, b) == f(a, b)")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.draw_defect"]["param"] == "b"
    assert "the draw for b had the wrong shape" in p.note
    assert "the draw for a" not in p.note


def test_a_mapping_result_against_a_number_says_why_it_is_skipped(mod):
    p = _row(mod.q_dict, "f(x) > 0")
    assert p.verdict == "skipped", (p.verdict, p.note)
    assert "isn't meaningful" in p.note
    assert "each kind" not in p.note


def test_a_slice_bound_drawn_as_a_float_is_still_falsified(mod):
    # "slice indices must be integers" names no type: a wrong-shape
    # float draw falsified as on develop, a known gap
    p = _row(mod.two_num_list, "f(n, xs) == f(n, xs)")
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)
