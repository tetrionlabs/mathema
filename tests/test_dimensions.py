# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Dimensional analysis in the claim grammar: `dim(x, axis)` is the
canonical spelling, `len`/`rows`/`cols` are sugar folding to it (with
their own pinned axes), all four share one identity, and a dimension
premise over sequences is drawn to hold by construction rather than
rejection-sampled. The mechanism is axis-general; 1-D is what the
sampler synthesises today."""
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.grammar import normalize
from mathema.spec import fingerprint_text


def test_the_sugar_folds_to_dim_with_the_right_axis():
    assert normalize("len(x) == 5") == "dim(x, 0) == 5"
    assert normalize("rows(A) >= 2") == "dim(A, 0) >= 2"
    assert normalize("cols(A) == cols(B)") == "dim(A, 1) == dim(B, 1)"
    # canonical form is left untouched
    assert normalize("dim(A, 1) == 3") == "dim(A, 1) == 3"


def test_all_four_spellings_share_one_identity():
    ref = fingerprint_text(claim(
        "assuming dim(x, 0) == dim(y, 0), f(x, y) == f(y, x)"))
    for spelling in ("assuming len(x) == len(y), f(x, y) == f(y, x)",
                     "assuming rows(x) == rows(y), f(x, y) == f(y, x)"):
        assert fingerprint_text(claim(spelling)) == ref, spelling


@pytest.fixture(scope="module")
def strict_dot(tmp_path_factory):
    p = tmp_path_factory.mktemp("dims") / "d.py"
    p.write_text(textwrap.dedent('''
        def strict_dot(x: list, y: list) -> float:
            """Product sum; raises when lengths differ."""
            if len(x) != len(y):
                raise ValueError("length mismatch")
            return sum(a * b for a, b in zip(x, y))
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("d", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.strict_dot


def test_an_equal_length_premise_holds_by_construction(strict_dot):
    # without the premise the free 2..8 draws mismatch and hit the
    # raise, a genuine out-of-contract falsification
    (bare,) = check_conjectures(strict_dot,
                                [claim("f(x, y) == f(y, x)", route="probe")])
    assert bare.verdict == "falsified"

    # with it, lengths are drawn equal, so the raise region is never
    # touched and the symmetry holds, in every spelling
    for spelling in ("assuming len(x) == len(y), f(x, y) == f(y, x)",
                     "assuming dim(x, 0) == dim(y, 0), f(x, y) == f(y, x)",
                     "assuming rows(x) == rows(y), f(x, y) == f(y, x)"):
        (p,) = check_conjectures(strict_dot, [claim(spelling, route="probe")])
        assert p.verdict == "holds", (spelling, p.note)


def test_a_bounded_length_premise_constrains_the_draw(strict_dot):
    # equal-and-at-least-4: still holds, and the plan never draws
    # below the floor (a raise on a too-short input would falsify)
    (p,) = check_conjectures(strict_dot, [claim(
        "assuming dim(x, 0) == dim(y, 0) and dim(x, 0) >= 4, "
        "f(x, y) == f(y, x)", route="probe")])
    assert p.verdict == "holds", p.note


def test_dim_in_a_law_evaluates_at_runtime(strict_dot):
    # dim(x, 0) is a real quantity in a law, not only a premise
    (p,) = check_conjectures(strict_dot, [claim(
        "assuming len(x) == len(y), dim(x, 0) == dim(y, 0)",
        route="probe")])
    assert p.verdict == "holds", p.note


def test_axis_one_on_a_sequence_is_an_honest_error(strict_dot):
    # a 1-D sequence has no axis 1; a law asking for it is unliftable,
    # not silently wrong
    (p,) = check_conjectures(strict_dot, [claim(
        "assuming len(x) == len(y), dim(x, 1) == dim(y, 1)",
        route="probe")])
    assert p.verdict in ("skipped", "unknown", "falsified")


def test_enforce_dimensions_guards_the_premise_at_runtime():
    """`@enforce_dimensions` is the shape analogue of
    `@enforce_domain`: it makes the function reject inputs that violate
    a declared dimension premise, so `assuming <premise>, <law>` and a
    runtime guard for `<premise>` are one precondition stated once."""
    from mathema.authoring import claims as claims_decorator
    from mathema.authoring import enforce_dimensions

    @enforce_dimensions()
    @claims_decorator("assuming len(x) == len(y), f(x, y) == f(y, x)")
    def dot(x: list, y: list) -> float:
        """Dot product."""
        return sum(a * b for a, b in zip(x, y))

    assert dot([1.0, 2.0], [3.0, 4.0]) == 11.0
    with pytest.raises(ValueError, match="dim.x, 0.=2"):
        dot([1.0, 2.0], [3.0])


def test_enforce_dimensions_honours_a_bound_against_a_constant():
    from mathema.authoring import claims as claims_decorator
    from mathema.authoring import enforce_dimensions

    @enforce_dimensions()
    @claims_decorator("assuming dim(x, 0) >= 3, f(x) == f(x)")
    def head(x: list) -> float:
        """First three summed."""
        return x[0] + x[1] + x[2]

    assert head([1.0, 2.0, 3.0]) == 6.0
    with pytest.raises(ValueError, match=">= 3"):
        head([1.0, 2.0])


@pytest.fixture(scope="module")
def matrices(tmp_path_factory):
    p = tmp_path_factory.mktemp("mtx") / "m.py"
    p.write_text(textwrap.dedent('''
        from typing import Annotated

        from mathema.types import Shape


        def row_sums(a: Annotated[list, Shape("m", "n")]) -> Annotated[list, Shape("m")]:
            """Sum each row of an m x n matrix."""
            return [sum(row) for row in a]


        def matvec(a: Annotated[list, Shape("m", "n")],
                   x: Annotated[list, Shape("n")]) -> Annotated[list, Shape("m")]:
            """Matrix times vector; needs cols(a) == len(x)."""
            return [sum(a[i][j] * x[j] for j in range(len(x)))
                    for i in range(len(a))]
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("m", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_marked_matrix_parameter_synthesises_nested(matrices):
    # a Shape("m","n") parameter is drawn as a nested list; a law over
    # dim(a, 0)/dim(a, 1) and the marker names holds because the real
    # shapes match what the resolver bound
    (p,) = check_conjectures(matrices.row_sums, [claim(
        "assuming m >= 2, dim(f(a), 0) == dim(a, 0)", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_marker_dims_are_first_class_symbols(matrices):
    (p,) = check_conjectures(matrices.row_sums, [claim(
        "assuming n >= 3, dim(a, 1) == n", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_shared_marker_dim_makes_arguments_conformable(matrices):
    # a's columns and x's length share the marker n, so they agree
    # every trial and the product is always well-defined
    (p,) = check_conjectures(matrices.matvec, [claim(
        "assuming m >= 1 and n >= 1, dim(f(a, x), 0) == dim(a, 0)",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_an_unmarked_nested_parameter_stays_one_dimensional():
    # the L8 boundary honoured: with no Shape marker, a nested-list
    # parameter is a plain 1-D sequence, never silently given a 2nd axis
    from mathema.analysis import analyze_source
    from mathema.dimensions import resolve
    from mathema.types import shapes_from_signature

    def flat(m: list) -> float:
        """First leaf."""
        return m[0][0]

    r = resolve(analyze_source(flat), shapes_from_signature(flat))
    assert r.shapes["m"].axes == (None,)


# --- the space form: R^n / [0,1]^n / R^(m*n), and its round trip ----

@pytest.mark.parametrize("spelling,dims", [
    ("v in R^n", ("n",)),
    ("v in R^k", ("k",)),
    ("A in R^(m*n)", ("m", "n")),
    ("A in R^(m×n)", ("m", "n")),
    ("xs in [0, 1]^n", ("n",)),
    ("xs in [0, 1]^k \\ {0}", ("k",)),
    ("v in Z^n", ("n",)),
    ("v in Rⁿ", ("n",)),
    ("A in Rᵐˣⁿ", ("m", "n")),
    ("xs in [0, 1]ⁿ", ("n",)),
])
def test_space_forms_parse_and_carry_their_dims(spelling, dims):
    from mathema.domain import parse_binding
    name, bound = parse_binding(spelling)
    assert getattr(bound, "dims", ()) == dims, (spelling, bound)


@pytest.mark.parametrize("spelling", [
    "v in R^n", "A in R^(m*n)", "xs in [0, 1]^n", "v in Z^k",
    "w in [0, 1]^n \\ {0}", "v in Rⁿ", "A in Rᵐˣⁿ",
])
def test_space_forms_are_fixed_points_in_both_modes(spelling):
    from mathema.domain import parse_binding, render_domain
    _, bound = parse_binding(spelling)
    for mode in (False, True):
        first = render_domain(bound, ascii_mode=mode)
        _, again = parse_binding(f"z in {first}")
        second = render_domain(again, ascii_mode=mode)
        assert first == second, (spelling, mode, first, second)
        assert getattr(again, "dims", ()) == getattr(bound, "dims", ())


def test_the_missing_clause_trails_the_space():
    from mathema.domain import parse_binding, render_domain
    _, bound = parse_binding("A in R^(m*n)")
    assert render_domain(bound, ascii_mode=False) == "ℝᵐˣⁿ ∪ {∅}"


def test_unicode_renders_the_exponent_as_a_superscript():
    from mathema.domain import parse_binding, render_domain
    _, v = parse_binding("v in R^n")
    assert render_domain(v, ascii_mode=False) == "ℝⁿ ∪ {∅}"
    _, a = parse_binding("A in R^(m*n)")
    assert render_domain(a, ascii_mode=False) == "ℝᵐˣⁿ ∪ {∅}"


def test_a_shared_space_dimension_draws_equal_lengths(strict_dot):
    # `R^n` on both parameters names one dimension, so they are drawn
    # equal every trial, premise or not, the space form IS the
    # constraint
    (shared,) = check_conjectures(strict_dot, [claim(
        "for x in R^n, y in R^n, f(x, y) == f(y, x)", route="probe")])
    assert shared.verdict == "holds", (shared.verdict, shared.note)
    # distinct dimension names are free to differ, so the strict
    # function's own length guard falsifies
    (distinct,) = check_conjectures(strict_dot, [claim(
        "for x in R^n, y in R^m, f(x, y) == f(y, x)", route="probe")])
    assert distinct.verdict == "falsified"


def test_a_space_endpoint_power_is_not_the_dimension():
    # `10**6` inside an interval is an endpoint, never mistaken for the
    # space power; only a top-level caret binds a dimension
    from mathema.domain import parse_binding
    name, bound = parse_binding("M in [1, 10**6]")
    assert getattr(bound, "dims", ()) == ()


@pytest.mark.parametrize("spelling", [
    "v in R^", "v in R^^n", "v in R^(m,n)", "v in R^()", "v in R^(m",
    "v in R^-1", "v in R^n^", "v in [0,1]^n^m", "x in R**n**2",
])
def test_malformed_space_forms_reject_cleanly(spelling):
    # every adversarial spelling either rejects (None) or raises a
    # clean InvalidConjecture, never a crash or a silently wrong parse
    from mathema.conjecture import InvalidConjecture, claim
    from mathema.domain import parse_binding
    assert parse_binding(spelling) is None
    with pytest.raises(InvalidConjecture):
        claim(f"for {spelling}, f(v) >= 0")


def test_a_top_level_power_over_an_interval_with_an_endpoint_power():
    # both a genuine dimension power and an endpoint power in one
    # binding: the endpoint stays inside the interval, the dimension
    # binds the whole space
    from mathema.domain import parse_binding
    name, bound = parse_binding("v in [1, 10**6]^n")
    assert getattr(bound, "dims", ()) == ("n",)
    (piece,) = bound.pieces
    assert piece[1] == 1000000.0


def test_a_fixed_numeric_dimension_synthesises_that_length(tmp_path):
    p = tmp_path / "pair.py"
    p.write_text(textwrap.dedent('''
        def pair_sum(v: list) -> float:
            """Sum of a 2-vector; indexes both slots."""
            return v[0] + v[1]
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("pair", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    (pr,) = check_conjectures(m.pair_sum, [claim(
        "for v in R^2, f(v) == v[0] + v[1]", route="probe")])
    assert pr.verdict == "holds", (pr.verdict, pr.note)


def test_vec_and_mat_are_shorthand_for_the_shape_marker():
    import typing

    from mathema.types import Mat, Shape, Vec, shapes_from_signature

    assert Vec("n") == typing.Annotated[list, Shape("n")]
    assert Mat("m", "n") == typing.Annotated[list, Shape("m", "n")]
    assert Mat is Vec

    def matvec(a: Mat("m", "n"), x: Vec("n")) -> Vec("m"):
        """Matrix-vector product."""
        return [sum(a[i][j] * x[j] for j in range(len(x)))
                for i in range(len(a))]

    read = {k: v.dims for k, v in shapes_from_signature(matvec).items()}
    assert read == {"a": ("m", "n"), "x": ("n",), "return": ("m",)}


@pytest.fixture(scope="module")
def scale_rows(tmp_path_factory):
    p = tmp_path_factory.mktemp("cf") / "s.py"
    p.write_text(textwrap.dedent('''
        from mathema.types import Mat


        def scale_rows(a: Mat("m", "n"), c: float) -> Mat("m", "n"):
            """Scale every entry."""
            return [[c * x for x in row] for row in a]
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("s", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.scale_rows


def test_a_claim_dim_name_aliases_the_marker_name(scale_rows):
    # the claim names the axes p, q; the marker names them m, n. They
    # are the SAME dimensions (per axis), so the claim holds with p/q
    # bound from the real shape, no conflict
    (p,) = check_conjectures(scale_rows, [claim(
        "assuming p >= 2 and q >= 2, for a in R^(p*q), c in R, "
        "dim(f(a, c), 1) == q", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_rank_mismatch_is_a_dimension_conflict(scale_rows):
    # the claim calls a 1-D but the marker declares it 2-D: a real
    # contradiction, skipped with the reason, never adjudicated
    (p,) = check_conjectures(scale_rows, [claim(
        "for a in R^n, c in R, dim(f(a, c), 0) == dim(a, 0)",
        route="probe")])
    assert p.verdict == "skipped"
    assert p.meta.get("mathema.premise") == "dimension-conflict"
    assert "authoritative" in (p.note or "")


def test_a_structure_marker_narrows_synthesis(tmp_path):
    # a PositiveDefinite-marked matrix is sampled positive-definite, so
    # a claim true only on PD matrices (positive diagonal) holds rather
    # than falsifying on a random nested list
    p = tmp_path / "pd.py"
    p.write_text(textwrap.dedent('''
        from mathema.types import Mat, PositiveDefinite


        def diag_sum(a: Mat("n", "n", PositiveDefinite)) -> float:
            """Sum of the diagonal."""
            return sum(a[i][i] for i in range(len(a)))
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("pd", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    (pr,) = check_conjectures(m.diag_sum,
                              [claim("for a in R^(n*n), f(a) > 0", route="probe")])
    assert pr.verdict == "holds", (pr.verdict, pr.note)


def test_assuming_structure_narrows_synthesis(tmp_path):
    # `assuming a is positive definite` samples PD matrices, so a claim
    # true only on PD input (positive diagonal) holds; the same claim
    # without the premise falsifies on a random matrix
    p = tmp_path / "asm.py"
    p.write_text(textwrap.dedent('''
        def diag_sum(a: list) -> float:
            """Sum of the diagonal."""
            return sum(a[i][i] for i in range(len(a)))
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("asm", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    (held,) = check_conjectures(m.diag_sum, [claim(
        "assuming a is positive definite, for a in R^(n*n), f(a) > 0",
        route="probe")])
    assert held.verdict == "holds", (held.verdict, held.note)
    (bare,) = check_conjectures(m.diag_sum, [claim(
        "for a in R^(n*n), f(a) > 0", route="probe")])
    assert bare.verdict == "falsified"


# --- the same premise, on the derive route ----------------------------------

_REPEAT = '''\
def repeat_total(xs: list, s: float) -> float:
    """Add s once per element of xs."""
    t = 0.0
    for i in range(len(xs)):
        t = t + s
    return t
'''


def _repeat(tmp_path, monkeypatch):
    (tmp_path / "premmod.py").write_text(_REPEAT)
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    import sys
    sys.modules.pop("premmod", None)
    importlib.invalidate_caches()
    return __import__("premmod").repeat_total


def test_a_premise_reaches_the_sequence_derive_route(tmp_path, monkeypatch):
    """A premise narrows the region the claim is made over, so the
    derive route has to see it. The sequence families are reached
    through a separate cascade from the scalar one, and a premise that
    never arrives there adjudicates the claim over a region its author
    excluded: here `f(xs, s) >= 0` is false for negative `s` and true
    once `s >= 0` is assumed."""
    import mathema
    fn = _repeat(tmp_path, monkeypatch)
    (bare,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("f(xs, s) >= 0", route="derive")])
    (premised,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("assuming s >= 0, f(xs, s) >= 0", route="derive")])
    assert bare.verdict == "falsified", bare.sketch
    assert premised.verdict == "proven", premised.sketch


def test_the_premise_arrives_as_triples(tmp_path, monkeypatch):
    import mathema
    from mathema.symbolic import _dot, _fold, _seq_common, _sum
    seen = []
    original = _seq_common.try_prove_seq

    def spy(*args, **kwargs):
        seen.append(kwargs.get("assumption"))
        return original(*args, **kwargs)

    for mod in (_seq_common, _sum, _fold, _dot):
        monkeypatch.setattr(mod, "try_prove_seq", spy)
    fn = _repeat(tmp_path, monkeypatch)
    mathema.claims.check_conjectures(
        fn, [mathema.claim("assuming s >= 0, f(xs, s) >= 0", route="derive")])
    assert seen and seen[0] == [("s", ">=", "0")], seen


def test_a_route_predating_the_premise_keyword_still_works():
    """`routes()` is a published seam, so a family written before the
    `assumption` keyword existed keeps receiving exactly the arguments
    it declares."""
    from mathema import families
    calls = []

    def old_style_route(fn, facts, lhs_src, rhs_src, relation,
                        domain=None, tolerance=None):
        calls.append(sorted(locals()))
        return "ok"

    assert families.call_route(old_style_route, None, None, "f(x)", "0", ">=",
                               domain=None, tolerance=None,
                               assumption=[("s", ">=", "0")]) == "ok"

    def new_style_route(fn, facts, lhs_src, rhs_src, relation,
                        domain=None, tolerance=None, assumption=None):
        return assumption

    assert families.call_route(new_style_route, None, None, "f(x)", "0", ">=",
                               assumption=[("s", ">=", "0")]) == [("s", ">=", "0")]

    def kwargs_route(fn, facts, lhs_src, rhs_src, relation, **kw):
        return kw["assumption"]

    assert families.call_route(kwargs_route, None, None, "f(x)", "0", ">=",
                               assumption=["p"]) == ["p"]


_SPREAD = '''\
def spread(xs: list, lo: float, hi: float) -> float:
    """Accumulate the gap once per element."""
    t = 0.0
    for i in range(len(xs)):
        t = t + (hi - lo)
    return t
'''


def test_a_premise_relating_two_parameters_reaches_the_sequence_route(
        tmp_path, monkeypatch):
    """`assuming hi >= lo` is not a box, so box-tightening cannot carry
    it; it reaches the prover as an assumption predicate instead. The
    claim is false for `hi < lo` and true once the premise holds."""
    import mathema
    (tmp_path / "spreadmod.py").write_text(_SPREAD)
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    import sys
    sys.modules.pop("spreadmod", None)
    importlib.invalidate_caches()
    fn = __import__("spreadmod").spread
    (bare,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("f(xs, lo, hi) >= 0", route="derive")])
    (premised,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("assuming hi >= lo, f(xs, lo, hi) >= 0",
                           route="derive")])
    assert bare.verdict == "falsified", bare.sketch
    assert premised.verdict == "proven", premised.sketch


# --- a dimension premise pins the derive route's own length symbol ----------

def test_length_pins_resolve_independently_of_premise_order():
    import sympy

    from mathema.symbolic._seq_common import _length_pins
    Lx, Ly, Lz = (sympy.Symbol(n, integer=True, nonnegative=True)
                  for n in ("L_x", "L_y", "L_z"))
    lengths = {Lx, Ly, Lz}
    i = sympy.Integer

    assert _length_pins([(Lx, i(2))], lengths) == {Lx: i(2)}
    assert _length_pins([(i(2), Lx)], lengths) == {Lx: i(2)}
    # an alias makes the two sums share one symbol
    assert _length_pins([(Lx, Ly)], lengths) == {Ly: Lx}
    # a chain pins every member, whichever order it was written in
    chain = {Lx: i(3), Ly: i(3)}
    assert _length_pins([(Lx, Ly), (Ly, i(3))], lengths) == chain
    assert _length_pins([(Ly, i(3)), (Lx, Ly)], lengths) == chain
    # an empty region says nothing rather than proving everything
    assert _length_pins([(Lx, i(2)), (Lx, i(3))], lengths) == {}
    # a length is a count, so a negative literal describes no sequence
    assert _length_pins([(Lx, i(-1))], lengths) == {}
    # an equality that is not about a length is left to the predicates
    assert _length_pins([(sympy.Symbol("s"), i(2))], lengths) == {}


_SUMSQ = '''\
def sumsq(x: list) -> float:
    """Sum of squares."""
    t = 0.0
    for i in range(len(x)):
        t = t + x[i] * x[i]
    return t
'''


def test_a_fixed_dimension_premise_proves_on_derive(tmp_path, monkeypatch):
    """The corpus's first vector-space finding: `f(x) == x[0]**2 +
    x[1]**2` came back falsified with a witness at `L_x=0`, because the
    lift's length symbol was never pinned. It is a substitution, not an
    assumption: sympy cannot expand a `Sum` from `Q.zero(L_x - 2)`, but
    it can once the limit is a number."""
    import mathema
    (tmp_path / "sqmod.py").write_text(_SUMSQ)
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    import sys
    sys.modules.pop("sqmod", None)
    importlib.invalidate_caches()
    fn = __import__("sqmod").sumsq

    def verdict(law):
        (p,) = mathema.claims.check_conjectures(
            fn, [mathema.claim(law, route="derive")])
        return p.verdict, p.sketch

    # without the premise the claim really is false for other lengths
    bare, _ = verdict("f(x) == x[0]**2 + x[1]**2")
    assert bare == "falsified", bare
    for spelling in ("assuming len(x) == 2, f(x) == x[0]**2 + x[1]**2",
                     "assuming dim(x, 0) == 2, f(x) == x[0]**2 + x[1]**2"):
        v, sketch = verdict(spelling)
        assert v == "proven", (spelling, v, sketch)


_DOT = '''\
def dot(x: list, y: list) -> float:
    """Dot product."""
    t = 0.0
    for i in range(len(x)):
        t = t + x[i] * y[i]
    return t
'''


def test_a_shared_dimension_premise_ties_two_lengths_on_derive(
        tmp_path, monkeypatch):
    """The other half: two parameters sharing a dimension were not
    forced to the same length on derive, so `len(x) == len(y)` was
    falsified outright. The premise now maps one length symbol onto the
    other, which is what the probe route's resolver does by drawing one
    length."""
    import mathema
    (tmp_path / "dotmod.py").write_text(_DOT)
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    import sys
    sys.modules.pop("dotmod", None)
    importlib.invalidate_caches()
    fn = __import__("dotmod").dot

    (bare,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("len(x) == len(y)", route="derive")])
    assert bare.verdict == "falsified", bare.verdict
    (premised,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("assuming len(x) == len(y), len(x) == len(y)",
                           route="derive")])
    assert premised.verdict == "proven", (premised.verdict, premised.sketch)
