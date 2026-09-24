# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Interval evaluation never returns a hull it did not really compute.

Interval evaluation is a scalar technique: it bounds an expression by
substituting a real interval for each real quantity. A sequence is not
a real quantity. Boxing one used to produce a hull of exactly `0`, and
a zero hull reads downstream as "this difference is identically zero",
which proves a claim AND its negation at once. That is the one failure
mode the method exists to prevent, so these tests assert the property
directly rather than only pinning the fixtures that exposed it.

The mechanism, for anyone reading this after a sympy upgrade: a
sequence's base label reaches `free_symbols` as a plain `Symbol`
(`IndexedBase("a").free_symbols == {Symbol("a")}`), so a fallback that
boxes every free symbol boxes the base too. Two different sequences
then become the same object and `a[i] - b[i]` cancels to a literal 0.
`Sum(0, ...)` answers `is_number` and `is_comparable` with True and
evaluates to 0, so the old exit guard let it through.

There is no backstop below this for a wrong proof: the corroboration
gate only re-checks disproofs, and `_stability_gate` is off by default.
"""
import sympy

from mathema.symbolic._proof_support import (_interval_bounds, _interval_hull,
                                             _prove_relation)


def _two_sequences():
    a, b = sympy.IndexedBase("a"), sympy.IndexedBase("b")
    i = sympy.Symbol("i", integer=True)
    L = sympy.Symbol("L", integer=True, nonnegative=True)
    return (sympy.Sum(a[i], (i, 0, L - 1)),
            sympy.Sum(b[i], (i, 0, L - 1)))


# --- the hull itself --------------------------------------------------------

def test_interval_bounds_declines_on_a_sum_rather_than_inventing_a_hull():
    sa, sb = _two_sequences()
    assert _interval_bounds(sa - sb, {}, {}) is None


def test_interval_bounds_declines_on_a_bare_indexed_element():
    a = sympy.IndexedBase("a")
    i = sympy.Symbol("i", integer=True)
    assert _interval_bounds(a[i] + 1, {}, {}) is None


def test_a_scalar_hull_is_still_computed():
    # the guard must not be satisfiable by refusing everything
    x = sympy.Symbol("x", real=True)
    assert _interval_bounds(x ** 2 + 1, {}, {}) is not None


def test_interval_hull_rejects_a_corrupted_result_that_answers_is_number():
    # the exact shape the old exit guard admitted: it answers is_number
    # and is_comparable, and evaluates to the maximally wrong hull
    i = sympy.Symbol("i", integer=True)
    corrupt = sympy.Sum(0, (i, 0, sympy.AccumBounds(0, 9)))
    assert corrupt.is_number and corrupt.is_comparable    # the trap
    assert corrupt.doit() == 0
    x = sympy.Symbol("x", real=True)
    box = {x: sympy.AccumBounds(-sympy.oo, sympy.oo)}
    # routed through the hull, a result of this shape must not survive
    assert _interval_hull(corrupt, box) is None


# --- the property that actually failed --------------------------------------

def test_a_relation_and_its_negation_are_never_both_proven():
    """The invariant, asserted directly. Before the fix all four of
    these resolved: `<=` and `>=` both proven, `<` and `>` both
    disproven, on the same expression pair."""
    sa, sb = _two_sequences()
    statuses = {rel: getattr(_prove_relation(sa, sb, rel, {}, None, {}),
                             "status", None)
                for rel in ("<=", ">=", "<", ">")}
    assert not (statuses["<="] == "proven" and statuses[">="] == "proven"), \
        f"a claim and its negation both proven: {statuses}"
    assert not (statuses["<"] == "disproven" and statuses[">"] == "disproven"), \
        f"a claim and its negation both disproven: {statuses}"


# --- end to end, on the corpus's own smoking gun ----------------------------

_MANHATTAN = '''\
def manhattan(x: list, y: list) -> float:
    """Manhattan distance between two vectors."""
    t = 0.0
    for i in range(len(x)):
        t = t + abs(x[i] - y[i])
    return t
'''


def _manhattan(tmp_path, monkeypatch):
    (tmp_path / "sgfix.py").write_text(_MANHATTAN)
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    import sys
    sys.modules.pop("sgfix", None)
    importlib.invalidate_caches()
    return __import__("sgfix").manhattan


def test_a_false_bound_on_an_unbounded_sum_is_not_proven(tmp_path, monkeypatch):
    # the corpus's single-loop smoking gun: one accumulator pass, both
    # vectors read in the same summand. `<= 5` is false over an
    # unbounded domain and used to come back proven.
    import mathema
    fn = _manhattan(tmp_path, monkeypatch)
    (p,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("f(x, y) <= 5", route="derive")])
    assert p.verdict != "proven", p.sketch


def test_the_true_claim_on_the_same_function_still_proves(tmp_path, monkeypatch):
    # capability check: the fix must cost nothing real. This proves via
    # the termwise route, where each element carries its own bounded
    # symbol, which is the sound way to decide a sequence claim.
    import mathema
    fn = _manhattan(tmp_path, monkeypatch)
    (p,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("f(x, y) >= 0", route="derive")])
    assert p.verdict == "proven", p.sketch


_CAUCHY_SCHWARZ = '''\
def cs_margin(x: list, y: list) -> float:
    """Cauchy-Schwarz margin: dot(x, y)**2 - sumsq(x) * sumsq(y)."""
    d = 0.0
    for i in range(len(x)):
        d = d + x[i] * y[i]
    sx = 0.0
    for i in range(len(x)):
        sx = sx + x[i] * x[i]
    sy = 0.0
    for i in range(len(x)):
        sy = sy + y[i] * y[i]
    return d * d - sx * sy
'''


def test_the_cauchy_schwarz_trio_resolves_the_way_the_algebra_does(
        tmp_path, monkeypatch):
    """The corpus's headline case. `dot(x,y)**2 <= sumsq(x)*sumsq(y)` is
    true, `<= -1` and `>= 1` are false, and all three used to come back
    `proven` at once. The true one may hold or prove, but must not be
    falsified; neither false one may be proven."""
    import mathema
    (tmp_path / "csfix.py").write_text(_CAUCHY_SCHWARZ)
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    import sys
    sys.modules.pop("csfix", None)
    importlib.invalidate_caches()
    fn = __import__("csfix").cs_margin

    def verdict(law, route):
        (p,) = mathema.claims.check_conjectures(
            fn, [mathema.claim(f"assuming len(x) == len(y), {law}",
                               route=route)])
        return p.verdict, p.note

    for route in ("derive", "probe"):
        true_v, note = verdict("f(x, y) <= 0", route)
        assert true_v in ("proven", "holds"), (route, true_v, note)
        for false_law in ("f(x, y) <= -1", "f(x, y) >= 1"):
            v, note = verdict(false_law, route)
            assert v != "proven", (route, false_law, v, note)
