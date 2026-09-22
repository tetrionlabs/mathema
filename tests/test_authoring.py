# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Tests for the decorator and docstring claim-authoring surfaces
(mathema/authoring.py): declared-schema.md names both as legitimate ways to
author a claim, alongside a hand-written claims.yaml file.

Fixture functions for the decorator tests are written to a real file on
disk and imported from there, not defined inline: `inspect.getsource()` (used
elsewhere in mathema's pipeline, e.g. analyze_source()) fails on functions
defined inline via exec()/inline `def` in a test body, since there is no
real source file behind them to read back.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from typing import Annotated

import pytest

import mathema
from mathema.authoring import (declared_from_function, materialize_declared,
                               parse_docstring_claims, resolve_declared)
from mathema.grammar import Interval, normalize, split_quantifier
from mathema.types import Probability


def _load_fixture_module(tmp_path, name, source):
    """Write `source` to a real .py file under tmp_path and import it as a
    top-level module, so functions defined in it are genuinely file-backed
    (inspect.getsource()/getsourcelines() work, matching how a real project
    module behaves)."""
    path = tmp_path / f"{name}.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    _LOADED_FIXTURE_MODULES.append(name)
    spec.loader.exec_module(mod)
    return mod


_LOADED_FIXTURE_MODULES: list = []


@pytest.fixture(autouse=True)
def _unload_fixture_modules():
    # fixture modules registered in sys.modules must not outlive their
    # test: inspect.getsource resolves against currently-loaded module
    # state, so a leaked name is cross-test contamination waiting to
    # collide
    yield
    while _LOADED_FIXTURE_MODULES:
        sys.modules.pop(_LOADED_FIXTURE_MODULES.pop(), None)



_FIXTURE_SOURCE = '''\
import mathema


@mathema.claims_decorator("f(-x) == -f(x)", "f(x) >= 0")
def cube_odd(x: float) -> float:
    return x ** 3


def only_docstring(x: float) -> float:
    """Identity-ish function with only docstring claims.

    Claims:
        odd: f(-x) == -f(x)
        nonneg [derive]: f(x) >= 0
        bounded: for x in [0, 1], f(x) <= 1
    """
    return x


def no_claims_here(x: float) -> float:
    """A plain docstring with no Claims: section at all."""
    return x


@mathema.claims_decorator(mathema.claim("f(-x) == -f(x)", name="odd", route="probe"))
def both_surfaces(x: float) -> float:
    """Has a claim named "odd" on both surfaces, plus a docstring-only one.

    Claims:
        odd: f(-x) == -f(x)
        nonneg: f(x) >= 0
    """
    return x
'''


@pytest.fixture()
def fixture_mod(tmp_path):
    return _load_fixture_module(tmp_path, "authoring_fixture_mod", _FIXTURE_SOURCE)


def _key(fn):
    mod = fn.__module__
    qual = fn.__qualname__
    return qual if mod in ("", "__main__") else f"{mod}.{qual}"


# ---- the decorator ----------------------------------------------------

def test_decorator_stamps_declared_shape_and_returns_fn_unchanged(fixture_mod):
    fn = fixture_mod.cube_odd
    assert callable(fn)
    declared = fn.__mathema_claims__
    assert len(declared) == 2
    for c in declared:
        assert set(c) >= {"name", "statement", "route", "grammar", "authored"}
        assert c["route"] == "best"
        assert c["grammar"] == "mathema"
        # authored is the record schema's object: surface always,
        # plus the line-level origin reference this tool can compute
        assert c["authored"]["surface"] == "decorator"
        assert ":decorator:L" in c["authored"]["ref"]
        assert c["authored"]["ref"].startswith(_key(fn))


def test_decorator_accepts_prebuilt_conjecture(fixture_mod):
    fn = fixture_mod.both_surfaces
    declared = fn.__mathema_claims__
    assert len(declared) == 1
    assert declared[0]["name"] == "odd"
    assert declared[0]["statement"] == "f(-x) == -f(x)"


# ---- the docstring parser ----------------------------------------------

def test_parse_docstring_claims_no_section_returns_empty():
    doc = "Just a summary line.\n\nNo claims section anywhere."
    assert parse_docstring_claims(doc) == []
    assert parse_docstring_claims("") == []
    assert parse_docstring_claims(None) == []


def test_parse_docstring_claims_multiple_with_route_and_domain():
    doc = (
        "One-line summary.\n\n"
        "Claims:\n"
        "    odd: f(-x) == -f(x)\n"
        "    nonneg [derive]: f(x) >= 0\n"
        "    bounded: for x in [0, 1], f(x) <= 1\n"
    )
    claims = parse_docstring_claims(doc)
    by_name = {c["name"]: c for c in claims}
    assert set(by_name) == {"odd", "nonneg", "bounded"}

    assert by_name["odd"]["statement"] == "f(-x) == -f(x)"
    # untagged docstring claims default to "best" (derive when it
    # can, probe otherwise); probe-only needs an explicit [probe]
    assert by_name["odd"]["route"] == "best"

    assert by_name["nonneg"]["route"] == "derive"
    assert by_name["nonneg"]["statement"] == "f(x) >= 0"

    assert by_name["bounded"]["statement"] == "f(x) <= 1"
    # declare()'s own self-describing interval shape, not the old
    # positional [lo, hi] list, see grammar.domain_bound_to_json.
    assert by_name["bounded"]["domain"] == {
        "x": {"lo": 0.0, "hi": 1.0, "closed_lo": True, "closed_hi": True}}


def test_parse_docstring_claims_on_fixture_function(fixture_mod):
    doc_claims = parse_docstring_claims(fixture_mod.only_docstring.__doc__)
    assert {c["name"] for c in doc_claims} == {"odd", "nonneg", "bounded"}

    assert parse_docstring_claims(fixture_mod.no_claims_here.__doc__) == []


def test_parse_docstring_claims_with_no_summary_line():
    # regression: ast.get_docstring()/inspect.getdoc() dedent by the
    # shallowest margin present across the WHOLE docstring, when
    # Claims: is the only content (no summary line above it to anchor a
    # shallower margin), the header and its body collapse to the exact
    # same column. Building `doc` as a hand-indented string literal (like
    # the tests above) never exercises this, since it bypasses cleandoc
    # entirely; this test goes through the real ast.get_docstring()
    # path a live function docstring actually takes.
    import ast

    src = (
        "def f(x):\n"
        "    \"\"\"Claims:\n"
        "        odd: f(-x) == -f(x)\n"
        "        nonneg [derive]: f(x) >= 0\n"
        "    \"\"\"\n"
        "    return x\n"
    )
    fdef = ast.parse(src).body[0]
    doc = ast.get_docstring(fdef)
    assert doc == "Claims:\nodd: f(-x) == -f(x)\nnonneg [derive]: f(x) >= 0"
    claims = parse_docstring_claims(doc)
    assert {c["name"] for c in claims} == {"odd", "nonneg"}


# ---- declared_from_function(): decorator vs docstring merge ------------

def test_declared_from_function_docstring_only(fixture_mod):
    declared = declared_from_function(fixture_mod.only_docstring)
    names = {c["name"] for c in declared}
    assert names == {"odd", "nonneg", "bounded"}
    for c in declared:
        assert c["authored"]["surface"] == "docstring"
        assert ":docstring" in c["authored"]["ref"]


def test_declared_from_function_decorator_wins_on_name_collision(fixture_mod):
    fn = fixture_mod.both_surfaces
    declared = declared_from_function(fn)
    by_name = {c["name"]: c for c in declared}
    # "odd" is declared on both surfaces; the decorator's copy must win
    assert by_name["odd"]["statement"] == "f(-x) == -f(x)"
    assert ":decorator:" in by_name["odd"]["authored"]["ref"]
    # "nonneg" only exists in the docstring, and must still come through
    assert "nonneg" in by_name
    assert ":docstring" in by_name["nonneg"]["authored"]["ref"]


# ---- resolve_declared(): file layer overrides the function layer -------

def test_resolve_declared_file_overrides_function(tmp_path, fixture_mod):
    fn = fixture_mod.cube_odd
    key = _key(fn)

    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    claim_name = fn.__mathema_claims__[0]["name"]  # override this one
    (claims_dir / "override.yaml").write_text(
        f'{key}:\n'
        f'  claims:\n'
        f'    - name: {claim_name}\n'
        f'      statement: "f(x) == f(x)"\n'
        f'      route: derive\n'
    )

    resolved = resolve_declared(fn, key, root=str(tmp_path))
    by_name = {c["name"]: c for c in resolved["claims"]}

    # the file's version wins for the overridden name
    assert by_name[claim_name]["statement"] == "f(x) == f(x)"
    assert by_name[claim_name]["route"] == "derive"
    # the other decorator claim (not mentioned in the file) survives untouched
    other_names = {c["name"] for c in fn.__mathema_claims__} - {claim_name}
    assert other_names <= set(by_name)

    # ready for entry_claims(): should parse into Conjectures without error
    from mathema.spec import entry_claims
    cjs = entry_claims(resolved)
    assert {cj.name for cj in cjs} == set(by_name)


def test_resolve_declared_no_file_layer_falls_back_to_function(tmp_path, fixture_mod):
    fn = fixture_mod.only_docstring
    key = _key(fn)
    resolved = resolve_declared(fn, key, root=str(tmp_path))
    assert {c["name"] for c in resolved["claims"]} == {"odd", "nonneg", "bounded"}


# ---- materialize_declared() ---------------------------------------------

def test_materialize_declared_writes_expected_shape(tmp_path, fixture_mod):
    fn = fixture_mod.cube_odd
    key = _key(fn)
    path = materialize_declared(fn, key, root=str(tmp_path))

    out_path = tmp_path / ".mathema" / "declared" / f"{key}.yaml"
    assert str(out_path) == path
    assert out_path.exists()

    text = out_path.read_text()
    assert text.startswith("#")
    assert "not meant for hand-editing" in text or "regenerated" in text

    import yaml
    data = yaml.safe_load(text)
    assert key in data
    claim_names = {c["name"] for c in data[key]["claims"]}
    assert claim_names == {c["name"] for c in fn.__mathema_claims__}


# ---- enforce_domain() ------------------------------------------------------

def test_enforce_domain_passes_through_an_in_domain_call():
    @mathema.enforce_domain({"alpha": (0, 1)})
    def ema(x: list, alpha: float) -> float:
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    assert ema([1.0, 2.0], 0.5) == ema.__wrapped__([1.0, 2.0], 0.5)


def test_enforce_domain_raises_on_an_out_of_interval_value():
    @mathema.enforce_domain({"alpha": (0, 1)})
    def ema(x: list, alpha: float) -> float:
        return alpha

    with pytest.raises(ValueError, match="alpha=1.5"):
        ema([1.0], 1.5)


def test_enforce_domain_raises_on_a_non_integer_for_z():
    @mathema.enforce_domain({"n": "Z"})
    def f(n) -> int:
        return n

    with pytest.raises(ValueError, match="n=1.5"):
        f(1.5)
    assert f(3) == 3


def test_enforce_domain_allows_missing_for_a_bare_named_type_by_default():
    # a bare "Z"/"N" string bypasses grammar parsing entirely, but is
    # just as much a stated type as an explicit ⊂ Z clause, stating a
    # type never excludes missing by default, regardless of spelling; a
    # claim's own domain text doesn't get to assert that true just by
    # naming a type, only an explicit exclusion clause does.
    @mathema.enforce_domain({"n": "Z"})
    def f(n):
        return n

    assert math.isnan(f(float("nan")))   # passes through, not rejected


def test_enforce_domain_raises_on_a_negative_for_n():
    @mathema.enforce_domain({"n": "N"})
    def f(n) -> int:
        return n

    with pytest.raises(ValueError, match="n=-1"):
        f(-1)
    assert f(0) == 0


def test_enforce_domain_raises_outside_an_explicit_set():
    @mathema.enforce_domain({"scale": frozenset({"linear", "log"})})
    def f(scale) -> str:
        return scale

    with pytest.raises(ValueError, match="scale='quadratic'"):
        f("quadratic")
    assert f("log") == "log"


def test_inline_note_comment_feeds_facts_doc_notes(tmp_path):
    from mathema.analysis import analyze_source
    from mathema.spec import to_spec

    mod = _load_fixture_module(tmp_path, "inline_note_fixture", '''\
def half(x: float) -> float:
    # Note: only tested for finite inputs.
    # NaN handling is unspecified.
    return x / 2
''')
    facts = analyze_source(mod.half)
    assert facts.doc_notes == "only tested for finite inputs. NaN handling is unspecified."

    ex = mathema.Record(facts=facts, probes=[])
    out = to_spec(ex)
    assert out["meta"]["notes"] == facts.doc_notes


def test_reject_missing_rejects_a_missing_scalar_or_sequence_element():
    @mathema.reject_missing("xs", "alpha")
    def f(xs, alpha):
        return sum(xs) + alpha

    assert f([1.0, 2.0], 0.5) == 3.5
    with pytest.raises(ValueError, match="alpha=nan"):
        f([1.0, 2.0], float("nan"))
    with pytest.raises(ValueError, match=r"element 1 \(nan\)"):
        f([1.0, float("nan")], 0.5)


def test_reject_missing_places_no_bound_on_ordinary_values():
    @mathema.reject_missing("x")
    def f(x):
        return x

    assert f(-1e9) == -1e9
    assert f(1e9) == 1e9


def test_enforce_domain_leaves_undeclared_parameters_unchecked():
    @mathema.enforce_domain({"alpha": (0, 1)})
    def f(alpha, beta) -> float:
        return alpha + beta

    assert f(0.5, 999) == 999.5


def _dom(text: str):
    domain, _ = split_quantifier(normalize(text))
    return domain["x"]


def test_enforce_domain_respects_open_bounds_not_just_closed():
    # closed_lo/closed_hi were previously ignored; an open bound was
    # enforced identically to a closed one, fixed as a byproduct of
    # routing every consumer through the shared domain_contains().
    @mathema.enforce_domain({"x": Interval(0.0, 1.0, closed_lo=False)})
    def f(x) -> float:
        return x

    with pytest.raises(ValueError, match="x=0.0"):
        f(0.0)
    assert f(0.5) == 0.5


def test_enforce_domain_checks_every_sequence_element_against_its_domain():
    @mathema.enforce_domain({"xs": (0, 100)})
    def total(xs: list) -> float:
        return sum(xs)

    assert total([1.0, 50.0, 100.0]) == 151.0
    with pytest.raises(ValueError, match=r"element 1 \(150.0\)"):
        total([1.0, 150.0])


def test_enforce_domain_allows_a_missing_element_when_domain_is_explicit_type():
    # stating a type alone (⊂ Z) never excludes missing by default,
    # regardless of spelling, only an explicit exclusion clause does
    # (see test_enforce_domain_rejects_a_missing_element_when_explicitly_excluded).
    @mathema.enforce_domain({"xs": _dom("for x in [0, 100] \\subset Z, True")})
    def total(xs: list) -> float:
        return sum(v for v in xs if v == v)

    assert total([1, 2, 3]) == 6
    assert total([1, float("nan"), 3]) == 4


def test_enforce_domain_rejects_a_missing_element_when_explicitly_excluded():
    @mathema.enforce_domain({"xs": _dom("for x in [0, 100] \\subset Z \\ {missing}, True")})
    def total(xs: list) -> float:
        return sum(xs)

    assert total([1, 2, 3]) == 6
    with pytest.raises(ValueError, match=r"element 1 \(nan\)"):
        total([1, float("nan"), 3])


def test_enforce_domain_allows_a_missing_element_when_domain_is_implicit_type():
    @mathema.enforce_domain({"xs": _dom("for x in [0, 100], True")})
    def total(xs: list) -> float:
        return sum(v for v in xs if v == v)

    assert total([1.0, float("nan"), 3.0]) == 4.0


def test_enforce_domain_merges_with_type_marker_inferred_domain():
    @mathema.enforce_domain()
    def f(p: Annotated[float, Probability]) -> float:
        return p

    with pytest.raises(ValueError, match="p=1.5"):
        f(1.5)
    assert f(0.5) == 0.5


def test_enforce_domain_explicit_wins_over_inferred():
    @mathema.enforce_domain({"p": (0.0, 0.9)})
    def f(p: Annotated[float, Probability]) -> float:
        return p

    with pytest.raises(ValueError, match="p=0.95"):
        f(0.95)


def test_enforce_domain_picks_up_a_declared_claims_own_domain():
    @mathema.enforce_domain()
    @mathema.claims_decorator("for alpha in [0, 1], f(x, alpha) <= max(x)")
    def ema(x, alpha) -> float:
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    with pytest.raises(ValueError, match="alpha=1.5"):
        ema([1.0, 2.0], 1.5)
    assert ema([1.0, 2.0], 0.5) is not None


def test_enforce_domain_raises_when_declared_claims_disagree():
    @mathema.claims_decorator(
        mathema.claim("for alpha in [0, 1], f(x, alpha) <= max(x)", name="a"),
        mathema.claim("for alpha in [0, 2], f(x, alpha) >= min(x)", name="b"))
    def ema(x, alpha) -> float:
        return alpha

    with pytest.raises(ValueError, match="disagree"):
        mathema.enforce_domain()(ema)


def test_enforce_domain_raises_when_explicit_domain_conflicts_with_declared():
    @mathema.claims_decorator("for alpha in [0, 1], f(x, alpha) <= max(x)")
    def ema(x, alpha) -> float:
        return alpha

    with pytest.raises(ValueError, match="conflicts"):
        mathema.enforce_domain({"alpha": (0, 2)})(ema)


def test_enforce_domain_explicit_agreeing_with_declared_is_fine():
    @mathema.claims_decorator("for alpha in [0, 1], f(x, alpha) <= max(x)")
    def ema(x, alpha) -> float:
        return alpha

    wrapped = mathema.enforce_domain({"alpha": (0, 1)})(ema)
    with pytest.raises(ValueError, match="alpha=1.5"):
        wrapped([1.0], 1.5)


def test_a_suggestion_never_outranks_a_same_named_declared_claim():
    # regression: the suggestion battery merged as an OVERLAY over the
    # declared entry, so a suggested claim sharing a name with a
    # human's declared one won, the declared claim came back
    # source "suggested" with gates False, and its verdict silently
    # stopped counting toward the gate. A suggestion is the LEAST
    # deliberate surface and must always lose that tie.
    import mathema
    from mathema.records import claim_row

    def midpoint(a: float, b: float) -> float:
        return (a + b) / 2.0

    declared = {"claims": [{"name": "commutative",
                            "statement": "f(a, b) == f(b, a)",
                            "route": "derive"}]}
    rec = mathema.check(midpoint, declared=declared)      # battery runs
    row = next(r for r in (claim_row(p) for p in rec.probes)
               if r["claim"] == "commutative")
    assert row["source"] == "declared"
    assert row["gates"] is True

    # and a genuine CALL-SITE claim still wins the same tie, because
    # it is the most deliberate surface
    rec = mathema.check(midpoint, claims=["f(a, b) == 999"],
                        declared=declared)
    names = {r["claim"]: r for r in (claim_row(p) for p in rec.probes)}
    assert "999" in names["f_a_b_999"]["statement"]
