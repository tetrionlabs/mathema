# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One-sided limits and the two-sided default: a bare finite limit
point reads as the two-sided limit (left and right must agree), a
trailing sign on the point (`0+`, `0-`, `0^-`) claims one side, and a
variable whose declared domain lies entirely on one side of the point
resolves to the limit from inside the domain. A sympy-internal crash
on a limit is a clean unliftable message, never a raw error."""
import math

from mathema.claims import check_conjectures, claim
from mathema.grammar import normalize


def _v(fn, law):
    return check_conjectures(fn, [claim(law, route="derive")])[0]


def signum_ish(x):
    return abs(x) / x


def test_direction_sugar_normalizes_to_the_quoted_fourth_argument():
    assert normalize("lim(f(x), x, 0+) == 1") == "lim(f(x), x, 0, '+') == 1"
    assert normalize("lim(f(x), x -> 0-) == 1") == "lim(f(x), x, 0, '-') == 1"
    assert normalize("lim(f(x), x, 0^-) == 1") == "lim(f(x), x, 0, '-') == 1"
    assert normalize("lim f(x) as x -> 0+ == 1").startswith("lim(f(x), x, 0, '+')")


def test_direction_sugar_leaves_plain_points_alone():
    assert normalize("lim(f(x), x, 0) == 1") == "lim(f(x), x, 0) == 1"
    assert normalize("lim(f(x), x, a+b) == 1") == "lim(f(x), x, a+b) == 1"
    assert normalize("lim(f(x), x, -oo) == 0") == "lim(f(x), x, -oo) == 0"


def test_two_sided_default_refuses_a_split_limit():
    # left limit -1, right limit 1: claiming == 1 must not prove
    p = _v(signum_ish, "lim(f(x), x, 0) == 1")
    assert p.verdict != "proven"
    assert "does not exist" in (p.sketch or "") + (p.note or "")


def test_explicit_one_sided_points_prove_their_sides():
    assert _v(signum_ish, "lim(f(x), x, 0+) == 1").verdict == "proven"
    assert _v(signum_ish, "lim(f(x), x, 0-) == -1").verdict == "proven"


def test_domain_on_one_side_resolves_the_direction():
    # x in [0.1, 100]: approaching 0 means from inside the domain, the
    # right, where 1/x -> oo
    def inv(x):
        return 1 / x
    p = _v(inv, "for x in [0.1, 100], lim(f(x), x, 0) == oo")
    assert p.verdict == "proven"


def test_interior_two_sided_limit_still_proves():
    def sinc(x):
        return math.sin(x) / x
    assert _v(sinc, "lim(f(x), x, 0) == 1").verdict == "proven"


def test_a_sympy_limit_crash_is_a_clean_unliftable_not_a_raw_error():
    def powfn(x, p):
        return x ** p
    pr = _v(powfn, "lim(f(x,p), x, 0) == 0")
    assert pr.verdict in ("unknown", "skipped")
    assert "could not evaluate this limit" in (pr.sketch or "") + (pr.note or "")

def test_undirected_finite_limit_resolves_one_sided_when_other_side_leaves_reals(tmp_path):
    # the two-sidedness regression from the proof corpus: a plain
    # lim(f(beta), beta, 1) at a pole whose other side is complex used
    # to fail outright ("limit does not exist"). Exactly one side
    # real-valid -> that side is the honest reading, and the resolved
    # direction is rendered explicitly in the record (terse input,
    # explicit output). Explicit 1-/1+ spellings unchanged.
    import sys
    import textwrap
    path = tmp_path / "limmod.py"
    path.write_text(textwrap.dedent('''
        import math

        def lorentz_gamma_factor(beta: float) -> float:
            if beta >= 1 or beta <= -1:
                raise ValueError("beta must satisfy |beta| < 1")
            return 1 / math.sqrt(1 - beta ** 2)

        def doppler_redshift(beta: float) -> float:
            if beta >= 1 or beta <= -1:
                raise ValueError("beta must satisfy |beta| < 1")
            return math.sqrt((1 + beta) / (1 - beta)) - 1
        '''))
    sys.path.insert(0, str(tmp_path))
    try:
        import importlib
        mod = importlib.import_module("limmod")
        importlib.reload(mod)
        for fn in (mod.lorentz_gamma_factor, mod.doppler_redshift):
            (p,) = check_conjectures(fn, [claim(
                "lim(f(beta), beta, 1) == oo", route="derive")])
            assert p.verdict == "proven", (fn.__name__, p.verdict, p.note)
            rendered = (p.sketch or "") + (p.note or "")
            assert "one-sided" in rendered and "below" in rendered
        (p,) = check_conjectures(mod.lorentz_gamma_factor, [claim(
            "lim(f(beta), beta, 1-) == oo", route="derive")])
        assert p.verdict == "proven", (p.verdict, p.note)
        # a genuine two-sided disagreement between two REAL sides still
        # declines rather than picking a side
        (p,) = check_conjectures(mod.lorentz_gamma_factor, [claim(
            "lim(1/(beta - 1) + f(0), beta, 1) == oo", route="derive")])
        assert p.verdict != "proven", (p.verdict, p.note)
    finally:
        sys.path.remove(str(tmp_path))
        del sys.modules["limmod"]


# --- branched functions: the limit of a Piecewise ---------------------------

def step_up(x: float) -> float:
    if x < 0:
        return 0.0
    return 1.0


def sign_step(x: float) -> float:
    return 1.0 if x > 0 else -1.0


def relu(x: float) -> float:
    if x > 0:
        return x
    return 0.0


def test_a_jump_has_no_two_sided_limit():
    p = _v(step_up, "lim(f(x), x, 0) == 1")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    p = _v(step_up, "lim(f(x), x, 0) == 0")
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_a_one_sided_limit_of_a_branch_takes_the_branch_on_that_side():
    """At the jump itself the function takes the else-branch value, but
    the limit from above is the branch just to the right."""
    for law, expected in (("lim(f(x), x -> 0+) == 1", "proven"),
                          ("lim(f(x), x -> 0+) == -1", None),
                          ("lim(f(x), x -> 0-) == -1", "proven"),
                          ("lim(f(x), x -> 0-) == 1", None)):
        p = _v(sign_step, law)
        if expected:
            assert p.verdict == expected, (law, p.verdict, p.sketch)
        else:
            assert p.verdict != "proven", (law, p.verdict, p.sketch)


def test_a_continuous_branch_point_still_has_its_limit():
    p = _v(relu, "lim(f(x), x, 0) == 0")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _v(step_up, "lim(f(x), x, oo) == 1")
    assert p.verdict == "proven", (p.verdict, p.sketch)
