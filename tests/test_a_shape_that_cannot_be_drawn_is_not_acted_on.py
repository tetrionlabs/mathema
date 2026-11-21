# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A shape read from the code changes what is drawn only when the probe
can draw it for the claim. A string use with no domain or language to
draw strings from is noted, not acted on: the parameter is drawn as an
unannotated parameter is, and a TypeError or AttributeError on that draw
is a draw defect only while f has returned on no draw."""
import importlib.util
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

FNS = '''
    def tname(v):
        return type(v).__name__


    def helper_bad(v):
        return v + "s"


    def num_ok_str_bad(x):
        if isinstance(x, str):
            return x.upper() + "!"
        return x


    def k_str_bad(x):
        if tname(x) == "str":
            return x + "!"
        return x


    def callee_te(x):
        if x == 2:
            return helper_bad(x)
        return x


    def comp_te(x):
        return [x + "a" for _ in range(1)] if x == -1 else x


    def gen_te(x):
        def g():
            yield x + "a"
        return list(g()) if x == 0 else x


    def upper_vac(x):
        return x.upper()


    def k_accident_list(x):
        if tname(x) == "list" and len(x) > 3:
            return x + "units"
        return x
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("strings") / "string_use_fns.py"
    path.write_text(textwrap.dedent(FNS))
    spec = importlib.util.spec_from_file_location("string_use_fns", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["string_use_fns"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("string_use_fns", None)


def _row(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    return p


# develop's verdict for each
@pytest.mark.parametrize("name, text, verdict", [
    ("num_ok_str_bad", "f(x) == x", "holds"),
    ("k_str_bad", "f(x) == x", "holds"),
    ("callee_te", "f(x) == x", "falsified"),
    ("comp_te", "f(x) == x", "falsified"),
    ("gen_te", "f(x) == x", "falsified"),
    ("k_accident_list", "f(x) == x", "falsified"),
])
def test_a_string_use_with_nothing_to_draw_strings_from_keeps_develops_verdict(
        mod, name, text, verdict):
    p = _row(getattr(mod, name), text)
    assert p.verdict == verdict, (p.verdict, p.note, p.counterexample)


def test_a_string_use_raising_on_every_draw_is_a_draw_defect(mod):
    # develop's witness, x = 2 raising AttributeError at `x.upper()`, is a
    # wrong-shape draw
    p = _row(mod.upper_vac, "f(x) == f(x)")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.draw_defect"]["param"] == "x"


def test_the_row_says_a_string_use_was_seen_and_how_to_bind_it(mod):
    p = _row(mod.num_ok_str_bad, "f(x) == x")
    assert ("a string use of x was seen, and no string is drawn without a "
            "domain; to draw strings, bind it (for x in L[...])") in p.note
