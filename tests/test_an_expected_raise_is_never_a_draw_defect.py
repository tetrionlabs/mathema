# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `raises(...)` claim is judged on the raise it states: a raise of the
type the claim expects is a pass, however the parameter was drawn, and
only a raise the claim does not expect can be a draw defect."""
import importlib.util
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

FNS = '''
    def n01_real_part(x):
        return x.real_part


    def n17_call_it(x):
        return x(1)


    def n20_plus_str(x):
        return x + "s"


    def n22_nope(x):
        return x.nope


    def n25_join(x):
        return x.join(["a", "b"])


    def n28_startswith(x):
        return x.startswith("a")
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("raises") / "expected_raise_fns.py"
    path.write_text(textwrap.dedent(FNS))
    spec = importlib.util.spec_from_file_location("expected_raise_fns", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["expected_raise_fns"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("expected_raise_fns", None)


# develop holds each
@pytest.mark.parametrize("name, text", [
    ("n20_plus_str", "raises(f(x), TypeError)"),
    ("n17_call_it", "raises(f(x), TypeError)"),
    ("n01_real_part", "raises(f(x), AttributeError)"),
    ("n22_nope", "raises(f(x), AttributeError)"),
    ("n25_join", "raises(f(x), AttributeError)"),
    ("n28_startswith", "raises(f(x), AttributeError)"),
])
def test_the_raise_a_claim_expects_holds(mod, name, text):
    (p,) = check_conjectures(getattr(mod, name), [claim(text, route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert "mathema.draw_defect" not in (p.meta or {})
