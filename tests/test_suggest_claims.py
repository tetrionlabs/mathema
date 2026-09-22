# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema.suggest_claims(): a standalone, opt-in claim-suggestion
function. Declares candidate claims (monotonicity/affine/convexity per
real scalar parameter, is_reproducible/is_numerically_stable/bounded/
permutation_invariant/scale_equivariant/translation_equivariant/
commutative/associative/even/odd/idempotent where applicable, plus a
raises(...) claim per guarded parameter), never runs or verifies any of
them. Routing is structural for the liftability-gated claims (does fn
lift, not whether the claim would actually prove); route="best" for
claims adjudicated at check-time regardless of liftability."""
from typing import Annotated as _HintAnnotated

import mathema
from mathema.suggest import _raise_guard_types, suggest_claims
from mathema.spec import load_declared
from mathema.types import Probability as _HintProbability


def _load(tmp_path, name, source):
    fixture = tmp_path / f"{name}.py"
    fixture.write_text(source)
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        mod = __import__(name)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


def test_suggests_auto_route_for_monotonic_and_affine_regardless_of_liftability(tmp_path):
    # monotonic_increasing/decreasing/affine/convex/concave/
    # is_numerically_stable all use route="best" unconditionally now,
    # check_conjectures() decides derive vs. a registered family's own
    # fallback at adjudication time, not this function pre-guessing
    # from fn's own liftability at suggestion time. True for a directly
    # liftable function and a fold-lifted one alike.
    line_mod = _load(tmp_path, "line_fixture",
                     "def line(x: float) -> float:\n"
                     "    return 3.0 * x + 2.0\n")
    ema_mod = _load(tmp_path, "ema_suggest_fixture",
                    "def ema(x: list, alpha: float) -> float:\n"
                    "    y = x[0]\n"
                    "    for v in x[1:]:\n"
                    "        y = alpha * v + (1 - alpha) * y\n"
                    "    return y\n")
    line_by_name = {c.name: c for c in suggest_claims(line_mod.line)}
    ema_by_name = {c.name: c for c in suggest_claims(ema_mod.ema)}
    for name in ("monotonic_increasing[x]", "monotonic_decreasing[x]",
                "affine[x]", "convex[x]", "concave[x]"):
        assert line_by_name[name].route == "best"
    for name in ("monotonic_increasing[alpha]", "monotonic_decreasing[alpha]",
                "affine[alpha]", "convex[alpha]", "concave[alpha]"):
        assert ema_by_name[name].route == "best"
    assert ema_by_name["is_deterministic"].route == "best"
    assert ema_by_name["is_numerically_stable"].route == "best"


def test_liftable_functions_monotonic_claims_actually_adjudicate_via_derive(tmp_path):
    # route="best" is structural at suggestion time; this confirms the
    # real payoff still happens at adjudication time, a genuinely
    # liftable function's monotonic/affine claims resolve "proven" via
    # real derive, not just "holds" via the probe:algorithmic fallback.
    mod = _load(tmp_path, "line_adjudicate_fixture",
               "def line(x: float) -> float:\n"
               "    return 3.0 * x + 2.0\n")
    r = mathema.check(mod.line, claims=suggest_claims(mod.line))
    probes = {p.name: p for p in r.probes}
    assert probes["monotonic_increasing[x]"].verdict == "proven"
    assert probes["monotonic_increasing[x]"].route == "derive"
    assert probes["affine[x]"].verdict == "proven"
    assert probes["affine[x]"].route == "derive"


def test_extensive_does_not_change_suggestion_time_routing(tmp_path):
    mod = _load(tmp_path, "ema_extensive_fixture",
               "def ema(x: list, alpha: float) -> float:\n"
               "    y = x[0]\n"
               "    for v in x[1:]:\n"
               "        y = alpha * v + (1 - alpha) * y\n"
               "    return y\n")
    fast = {c.name: c for c in suggest_claims(mod.ema)}
    extensive = {c.name: c for c in suggest_claims(mod.ema, extensive=True)}
    # extensive= no longer changes anything suggest_claims() itself
    # returns; every claim's route is decided at adjudication time
    # now (check_conjectures()'s own extensive, passed separately when
    # a caller actually runs check()), not pre-guessed here.
    for name in ("monotonic_increasing[alpha]", "monotonic_decreasing[alpha]",
                "affine[alpha]", "convex[alpha]", "concave[alpha]",
                "is_deterministic", "is_numerically_stable"):
        assert fast[name].route == extensive[name].route == "best"


def test_suggests_a_raises_claim_for_a_guarded_parameter(tmp_path):
    mod = _load(tmp_path, "guarded_suggest_fixture",
               "def guarded(x: float) -> float:\n"
               "    if x == 0:\n"
               "        raise ValueError('x cannot be zero')\n"
               "    return 1.0 / x\n")
    suggestions = suggest_claims(mod.guarded)
    raises = next(c for c in suggestions if c.name == "raises[x]")
    assert raises.rhs == "ValueError"


def test_no_raises_suggestion_for_an_unrecognized_exception_type(tmp_path):
    mod = _load(tmp_path, "custom_exc_fixture",
               "class MyCustomError(Exception):\n"
               "    pass\n\n"
               "def f(x: float) -> float:\n"
               "    if x < 0:\n"
               "        raise MyCustomError('negative')\n"
               "    return x\n")
    suggestions = suggest_claims(mod.f)
    assert not [c for c in suggestions if "raises" in c.name]


def test_suggest_claims_returns_conjecture_objects_usable_directly_by_check(tmp_path):
    mod = _load(tmp_path, "usable_fixture",
               "def line(x: float) -> float:\n"
               "    return 3.0 * x + 2.0\n")
    suggestions = suggest_claims(mod.line)
    r = mathema.check(mod.line, claims=suggestions)
    names = {p.name for p in r.probes}
    assert "affine[x]" in names


def test_write_appends_to_the_claims_yaml_file_not_the_mathema_dir(tmp_path):
    mod = _load(tmp_path, "write_fixture",
               "def line(x: float) -> float:\n"
               "    return 3.0 * x + 2.0\n")
    suggest_claims(mod.line, write=True, key="line", root=str(tmp_path))
    path = tmp_path / "claims" / "line.claims.yaml"
    assert path.exists()
    assert not (tmp_path / ".mathema").exists()
    declared = load_declared(str(tmp_path))
    assert "line" in declared
    # 5 monotonic/affine/convex/concave + even/odd/idempotent
    # + is_deterministic + is_state_safe (the stateless cluster's
    # unconditional pair) + is_numerically_stable
    # + is_representation_safe[x] (x carries a float annotation, the
    # representation gate's structural signal); line has one scalar
    # param and a numeric return, so no commutative/associative
    # (needs two scalar params) or bounded/permutation_invariant/etc
    # (needs a sequence-first param); no is_reproducible (no
    # structural randomness).
    assert len(declared["line"]["entry"]["claims"]) == 12


def test_write_merges_rather_than_clobbers_existing_claims(tmp_path):
    mod = _load(tmp_path, "merge_fixture",
               "def line(x: float) -> float:\n"
               "    return 3.0 * x + 2.0\n")
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    (claims_dir / "line.claims.yaml").write_text(
        'line:\n  claims:\n    - name: "hand_authored"\n      statement: "f(x) == f(x)"\n      route: "probe"\n')
    suggest_claims(mod.line, write=True, key="line", root=str(tmp_path))
    declared = load_declared(str(tmp_path))
    names = {c["name"] for c in declared["line"]["entry"]["claims"]}
    assert "hand_authored" in names
    assert "affine[x]" in names


def test_raise_guard_types_first_wins_across_multiple_guards():
    import ast
    tree = ast.parse(
        "def f(x, y):\n"
        "    if x == 0:\n"
        "        raise ValueError('a')\n"
        "    if x == 1:\n"
        "        raise TypeError('b')\n"
        "    if y < 0:\n"
        "        raise KeyError('c')\n"
        "    return x\n")
    fdef = tree.body[0]
    guards = _raise_guard_types(fdef, ["x", "y"])
    assert guards["x"] == "ValueError"   # first guard mentioning x wins
    assert guards["y"] == "KeyError"


def test_sum_like_suggestions_are_gated_and_useful(tmp_path):
    """A plain accumulation earns the order-insensitive family
    (self-concatenation additivity, sorted-order invariance, and the
    numpy.sum comparison by dotted path); a decaying fold earns none
    of them, because its weights treat positions differently and the
    claims would be noise."""
    import textwrap

    p = tmp_path / "sums.py"
    p.write_text(textwrap.dedent('''
        def total(xs: list) -> float:
            """Sum of the sequence."""
            y = 0.0
            for v in xs:
                y = y + v
            return y


        def ema(x: list, alpha: float) -> float:
            """Exponentially weighted moving average."""
            y = x[0]
            for v in x[1:]:
                y = alpha * v + (1 - alpha) * y
            return y
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("sums", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    from mathema.suggest import suggest_claims

    names = {c.name for c in suggest_claims(m.total)}
    assert {"self_concat_additive", "order_invariant",
            "sum_like"} <= names
    decay = {c.name for c in suggest_claims(m.ema)}
    assert not ({"self_concat_additive", "order_invariant",
                 "sum_like"} & decay)


def test_a_well_known_series_suggests_its_closed_form(tmp_path):
    """The sum of the first n integers suggests, and PROVES,
    `f(n) == n*(n + 1)/2`; a function whose loop is not a pure sum
    suggests nothing of the kind."""
    import textwrap

    p = tmp_path / "series.py"
    p.write_text(textwrap.dedent('''
        def triangle(n: int) -> int:
            """Sum of the first n integers."""
            total = 0
            for k in range(n + 1):
                total = total + k
            return total
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("series", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    import mathema

    rec = mathema.check(m.triangle)
    (row,) = [pr for pr in rec.probes if pr.name == "closed_form"]
    assert row.verdict == "proven", (row.verdict, row.note)
    assert "n*(n + 1)/2" in row.statement


def test_return_marker_suggests_the_output_bound_as_a_full_chain(tmp_path):
    # a marked return states the output bound directly: the value/bound
    # family authors write by hand, which the shape battery never
    # proposed. A two-sided marker renders as the full chain, not its
    # first link; a one-sided marker as a single inequality.
    mod = _load(tmp_path, "bound_fixture",
                "from typing import Annotated\n"
                "from mathema.types import Probability, Positive, UnitBall\n"
                "def prob(x: float) -> Annotated[float, Probability]:\n"
                "    return 0.5\n"
                "def pos(x: float) -> Positive:\n"
                "    return abs(x) + 1.0\n"
                "def corr(x: float) -> UnitBall:\n"
                "    return 0.0\n")
    from mathema.records import claim_statement
    prob_by = {c.name: c for c in suggest_claims(mod.prob)}
    assert "returns_in_range" in prob_by
    assert claim_statement(prob_by["returns_in_range"]) == "0 <= f(x) <= 1"
    assert len(prob_by["returns_in_range"].links) == 2      # a real chain

    corr_by = {c.name: c for c in suggest_claims(mod.corr)}
    assert claim_statement(corr_by["returns_in_range"]) == "-1 <= f(x) <= 1"

    pos_by = {c.name: c for c in suggest_claims(mod.pos)}
    assert claim_statement(pos_by["returns_in_range"]) == "f(x) > 0"

    # an unmarked return earns no bound suggestion
    plain = _load(tmp_path, "plain_bound_fixture",
                  "def f(x: float) -> float:\n    return x\n")
    assert "returns_in_range" not in {c.name for c in suggest_claims(plain.f)}


def test_square_matrix_return_suggests_is_symmetric(tmp_path):
    import pytest
    pytest.importorskip("numpy")
    mod = _load(tmp_path, "sym_fixture",
                "import numpy as np\n"
                "from mathema.types import Mat\n"
                "def gram(A: Mat('n', 'n')) -> Mat('n', 'n'):\n"
                "    B = np.asarray(A, dtype=float)\n"
                "    return B @ B.T\n"
                "def scale(A: Mat('m', 'n'), c: float) -> Mat('m', 'n'):\n"
                "    return c * np.asarray(A, dtype=float)\n")
    from mathema.records import claim_statement
    gram_by = {c.name: c for c in suggest_claims(mod.gram)}
    assert "is_symmetric" in gram_by
    assert claim_statement(gram_by["is_symmetric"]) == "is_symmetric(f(A))"
    # a non-square return earns no structure suggestion
    assert "is_symmetric" not in {c.name for c in suggest_claims(mod.scale)}


def test_single_delegate_suggests_function_equivalence(tmp_path):
    # a wrapper whose whole body is `return core(<its own params>)` is
    # pinned to that core via the function-equivalence relation the
    # lexicon already carries, not an ad-hoc pointwise equality.
    import sys
    pkg = tmp_path / "delegpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text("def sq(x: float) -> float:\n    return x * x\n")
    (pkg / "wrap.py").write_text(
        "from delegpkg.core import sq\n"
        "def square(x: float) -> float:\n"
        "    return sq(x)\n"
        "def plus(x: float) -> float:\n"
        "    return sq(x) + 1.0\n")
    sys.path.insert(0, str(tmp_path))
    try:
        from delegpkg import wrap
        from mathema.records import claim_statement
        by = {c.name: c for c in suggest_claims(wrap.square)}
        assert "equivalent_to_core" in by
        assert claim_statement(by["equivalent_to_core"]) == \
            "let g = delegpkg.core.sq, f =:= g"
        # a body that does more than the single delegating call is not it
        assert "equivalent_to_core" not in {c.name for c in suggest_claims(wrap.plus)}
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("delegpkg")]:
            del sys.modules[m]


def _hint_clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _hint_annotated(x: float) -> _HintAnnotated[float, _HintProbability]:
    return min(1.0, max(0.0, x))


def _hint_plain(x: float) -> float:
    return x * 2


def test_bound_annotation_hint_steers_to_a_marker_not_a_prose_bound():
    # a structurally bounded but unannotated return earns a nudge to
    # annotate (so returns_in_range can fire), never a bound mathema
    # invents; an already-annotated or non-clamp return earns nothing.
    # Module-level fixtures (not a tmp module) keep the source stable so
    # the best-effort hint reads it under any suite ordering/load.
    from mathema.suggest import bound_annotation_hint
    hint = bound_annotation_hint(_hint_clamp01)
    assert hint is not None
    assert "InRange(0, 1)" in hint and "clamped to [0, 1]" in hint
    assert bound_annotation_hint(_hint_annotated) is None   # already marked
    assert bound_annotation_hint(_hint_plain) is None       # not bounded


def test_suggest_claims_tool_carries_the_bound_hint(tmp_path):
    import sys
    from mathema.interfaces.mcp import tools
    pkg = tmp_path / "hintpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "def clamp01(x: float) -> float:\n"
        "    return min(1.0, max(0.0, x))\n")
    sys.path.insert(0, str(tmp_path))
    try:
        out = tools.suggest_claims("hintpkg.mod:clamp01", root=str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("hintpkg")]:
            del sys.modules[m]
    assert out.get("hints")
    assert "InRange(0, 1)" in out["hints"][0]


def test_roundtrip_suggests_the_inverse_composition(tmp_path):
    # a function with an inverse sibling (encode/decode) earns the
    # round-trip composition g(f(x)) == x; a function without one does not.
    import sys
    pkg = tmp_path / "rtpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "codec.py").write_text(
        "def encode(x: int) -> int:\n"
        "    return x + 1\n"
        "def decode(y: int) -> int:\n"
        "    return y - 1\n"
        "def lonely(x: int) -> int:\n"
        "    return x * 2\n")
    sys.path.insert(0, str(tmp_path))
    try:
        from rtpkg import codec
        from mathema.records import claim_statement
        by = {c.name: c for c in suggest_claims(codec.encode)}
        assert "roundtrips_with" in by
        assert claim_statement(by["roundtrips_with"]) == \
            "let g = rtpkg.codec.decode, g(f(x)) == x"
        # no inverse sibling -> no round-trip suggestion
        assert "roundtrips_with" not in {c.name for c in suggest_claims(codec.lonely)}
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("rtpkg")]:
            del sys.modules[m]
