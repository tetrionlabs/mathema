# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`tau` is an ordinary variable (not a forced constant, unlike `pi`) on
both routes; `\\tau` is another Greek-letter identifier spelling, not a
constant either. `conjecture._SAFE_FUNCS` (the probe route's real-Python
vocabulary) now covers every `_math_vocab._SYMPY_FUNCS` (the derive
route's) entry with a direct `math` module equivalent, so a claim using
one of them can be adjudicated on either route, `factorial`
included, evaluated as gamma(x + 1) so both routes compute the same
continuous extension the derive route proves about. Every function
name either route recognizes is reserved as a bare variable, but a
call-form use of the same name works fine in the very same claim, and a
`let`-bound override of a built-in name keeps working after the
reservation extension."""
from mathema.conjecture import check_conjectures, claim
from mathema.grammar import is_reserved, normalize, render_law_expr


def double(x: float) -> float:
    return 2 * x


def double_named_tau(tau: float) -> float:
    return 2 * tau


def test_tau_is_an_ordinary_variable_not_a_forced_constant():
    assert normalize("f(x) == tau") == "f(x) == tau"
    cj = claim("for tau in [0, 10], f(tau) == 2*tau")
    result = check_conjectures(double_named_tau, [cj], extensive=False)[0]
    assert result.verdict == "proven"   # default best route: it lifts


def test_backslash_tau_is_a_greek_letter_not_a_constant():
    assert normalize(r"f(x) == \tau") == "f(x) == τ"
    assert render_law_expr(normalize(r"f(\tau) + 1")) == "f(τ) + 1"
    assert render_law_expr(normalize(r"f(\tau) + 1"), unicode=False) == "f(\\tau) + 1"


def test_new_safe_funcs_entries_evaluate_against_a_real_function():
    import math

    def g(x: float) -> float:
        return math.asin(x)

    result = check_conjectures(
        g, [claim("for x in [-1, 1], f(x) == asin(x)", route="probe")],
        extensive=False)[0]
    assert result.verdict == "holds"


def test_gamma_and_erf_are_probe_checkable_now():
    import math

    def gamma_fn(x: float) -> float:
        return math.gamma(x)

    def erf_fn(x: float) -> float:
        return math.erf(x)

    r1 = check_conjectures(
        gamma_fn, [claim("for x in [1, 5], f(x) == gamma(x)", route="probe")],
        extensive=False)[0]
    assert r1.verdict == "holds"
    r2 = check_conjectures(
        erf_fn, [claim("for x in [-2, 2], f(x) == erf(x)", route="probe")],
        extensive=False)[0]
    assert r2.verdict == "holds"


def test_recognized_function_names_are_reserved_as_bare_variables():
    for name in ("sin", "sqrt", "abs", "factorial", "gamma", "erf"):
        assert is_reserved(name)
    assert not is_reserved("len")   # a _SAFE_FUNCS-only name, checked separately


def test_a_recognized_function_name_works_as_a_call_but_not_bare():
    result_call = check_conjectures(
        double, [claim("f(x) == sin(x)", route="probe")], extensive=False)[0]
    assert result_call.verdict == "falsified"   # evaluated (2x != sin x), not rejected
    result_bare = check_conjectures(
        double, [claim("f(x) == sin", route="probe")], extensive=False)[0]
    assert result_bare.verdict == "skipped:misspecified"
    assert "reserved" in result_bare.note
    assert "missing call" in result_bare.note


def test_safe_funcs_only_name_len_is_also_reserved_bare():
    # len has no symbolic equivalent, so grammar.is_reserved() alone
    # doesn't know about it, conjecture._find_bare_reserved_name ORs
    # in its own _SAFE_FUNCS membership check to cover this case too.
    result = check_conjectures(
        double, [claim("f(x) == len", route="probe")], extensive=False)[0]
    assert result.verdict == "skipped:misspecified"
    assert "reserved" in result.note


def test_let_override_of_a_reserved_name_still_works_as_a_call():
    def sin_user(x: float) -> float:
        import math
        return math.sin(x)

    cj = claim("let sin = math.sin, for x in [0, 3], f(x) == sin(x)", route="probe")
    assert cj.funcs == {"sin": "math.sin"}
    result = check_conjectures(sin_user, [cj], extensive=False)[0]
    assert result.verdict == "holds"


def test_real_parameter_named_like_a_reserved_word_is_not_misspecified():
    # a real bug this exact reservation work introduced and then fixed:
    # a function can have a parameter literally named `d` (an arithmetic
    # series' common difference, say); referencing it bare is correct
    # usage, not a missing call to the derivative operator, regardless
    # of `d` also being globally reserved.
    def arithmetic_term(a1: float, d: float, n: float) -> float:
        return a1 + (n - 1) * d

    cj = claim("f(a1, d, n) == a1 + (n-1)*d", route="derive")
    result = check_conjectures(arithmetic_term, [cj], extensive=False)[0]
    assert result.verdict == "proven"

    cj_probe = claim("f(a1, d, n) == a1 + (n-1)*d", route="probe")
    result_probe = check_conjectures(arithmetic_term, [cj_probe], extensive=False)[0]
    assert result_probe.verdict == "holds"


def test_misspecified_verdict_is_identical_regardless_of_route():
    probe_result = check_conjectures(
        double, [claim("f(x) == sin", route="probe")], extensive=False)[0]
    derive_result = check_conjectures(
        double, [claim("f(x) == sin", route="derive")], extensive=False)[0]
    assert probe_result.verdict == derive_result.verdict == "skipped:misspecified"
    assert probe_result.note == derive_result.note


def test_factorial_adjudicates_on_the_probe_route():
    # factorial evaluates as gamma(x + 1), the same continuous
    # extension derive reasons about, so a claim over an unliftable
    # function gets real numeric evidence instead of being skipped
    import math

    def whiley(x: float) -> float:
        total = x
        while abs(total) > 1.0:
            total = total / 2.0
        return total

    r = check_conjectures(whiley, [claim(
        "for x in [1, 5], f(x) <= factorial(x)", route="best")])[0]
    assert r.verdict == "holds", (r.verdict, r.note)
    r = check_conjectures(whiley, [claim(
        "for x in [3, 5], f(x) >= factorial(x)", route="best")])[0]
    assert r.verdict == "falsified", (r.verdict, r.note)

    def fact_like(x: float) -> float:
        return math.gamma(x + 1)

    r = check_conjectures(fact_like, [claim(
        "for x in [0.5, 4.5], f(x) == factorial(x)", route="probe")])[0]
    assert r.verdict == "holds", (r.verdict, r.note)


def test_postfix_factorial_spelling_normalizes():
    # the traditional postfix spelling folds to the call form; != is
    # never touched, and n!! (double factorial, a different function)
    # is left alone rather than misread
    from mathema.grammar import normalize
    assert normalize("f(n) == n!") == "f(n) == factorial(n)"
    assert normalize("f(n) <= (n-1)! + 5!") == \
        "f(n) <= factorial(n-1) + factorial(5)"
    assert normalize("f(x) == abs(x)!") == "f(x) == factorial(abs(x))"
    assert normalize("f(n) == g(n)!") == "f(n) == factorial(g(n))"
    assert normalize("Sum(k!, k, 0, n) >= n!") == \
        "Sum(factorial(k), k, 0, n) >= factorial(n)"
    assert normalize("f(x) != x") == "f(x) != x"
    assert normalize("f(n) == n!!") == "f(n) == n!!"
    # idempotent, like every normalize pass
    assert normalize(normalize("f(n) <= (n-1)!")) == \
        normalize("f(n) <= (n-1)!")


def test_postfix_factorial_adjudicates_on_both_routes(tmp_path):
    import sys
    import textwrap
    (tmp_path / "facmod.py").write_text(textwrap.dedent('''
        import math

        def fact_fn(n: int) -> float:
            return float(math.factorial(n))
        '''))
    sys.path.insert(0, str(tmp_path))
    try:
        import importlib
        mod = importlib.import_module("facmod")
        importlib.reload(mod)
        r = check_conjectures(mod.fact_fn, [claim(
            "for n in [1,5] subset Z, f(n) == n!", route="derive")])[0]
        assert r.verdict == "proven", (r.verdict, r.note)
        # the record renders the resolved call form explicitly
        assert r.statement == "for n in [1, 5]:int|missing, f(n) = factorial(n)"
    finally:
        sys.path.remove(str(tmp_path))
        del sys.modules["facmod"]
