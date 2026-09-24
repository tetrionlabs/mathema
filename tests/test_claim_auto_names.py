# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim with no name is named from its statement, relation word
included, so `f(x) >= 0` and `f(x) <= 0` are two names. The name keys
pins, locks and verified rows, so it never depends on a claim's
position in a list: two distinct claims that would take the same name
are refused, asking for an explicit name."""
import textwrap

import pytest

import mathema
from mathema.conjecture import InvalidConjecture, claim


@pytest.mark.parametrize("law, name", [
    ("f(x) >= 0", "f_x_ge_0"),
    ("f(x) <= 0", "f_x_le_0"),
    ("f(x) > 0", "f_x_gt_0"),
    ("f(x) < 0", "f_x_lt_0"),
    ("f(x) == x", "f_x_eq_x"),
    ("f(x) = x", "f_x_eq_x"),
    ("f(x) != 0", "f_x_ne_0"),
    ("f(x) ~= x", "f_x_approx_x"),
    ("f =:= g", "f_equiv_g"),
    ("for x in [0, 1], 0 <= f(x) <= 1", "0_le_f_x_le_1"),
    ("for x in [0, 1], f(x) ≥ 0", "f_x_ge_0"),
    ("raises(f(x), ValueError)", "raises_f_x_valueerror"),
])
def test_an_auto_name_carries_the_relation_word(law, name):
    assert claim(law).name == name


def test_an_explicit_name_is_kept():
    assert claim("f(x) >= 0", name="nonneg").name == "nonneg"


def test_a_safety_predicate_keeps_its_bracketed_name():
    assert claim("is_pole_safe(x)").name == "is_pole_safe[x]"


def _ramp(tmp_path):
    p = tmp_path / "ramp.py"
    p.write_text(textwrap.dedent('''
        def f(mi: float) -> float:
            return max(0.0, min(1.0, mi))
    '''))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ramp", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.f


def test_two_claims_that_name_alike_are_refused(tmp_path):
    f = _ramp(tmp_path)
    with pytest.raises(InvalidConjecture, match="f_mi_ge_0") as err:
        mathema.check(f, claims=["for mi in [0,1], f(mi) >= 0",
                                 "for mi in [1,2], f(mi) >= 0"])
    assert "explicit name" in str(err.value)


def test_named_variants_are_all_kept(tmp_path):
    f = _ramp(tmp_path)
    rec = mathema.check(f, claims=[
        claim("for mi in [0,1], f(mi) >= 0", name="low"),
        claim("for mi in [1,2], f(mi) >= 0", name="high")])
    assert {p.name for p in rec.probes} >= {"low", "high"}


def test_an_exact_duplicate_is_one_claim(tmp_path):
    f = _ramp(tmp_path)
    rec = mathema.check(f, claims=["f(mi) >= 0", "f(mi) >= 0"])
    assert [p.name for p in rec.probes].count("f_mi_ge_0") == 1


def test_the_relation_keeps_two_bounds_apart(tmp_path):
    f = _ramp(tmp_path)
    rec = mathema.check(f, claims=["for mi in [0,1], f(mi) >= 0",
                                   "for mi in [0,1], f(mi) <= 1"])
    by = {p.name: p.verdict for p in rec.probes}
    assert by["f_mi_ge_0"] in ("proven", "holds")
    assert by["f_mi_le_1"] in ("proven", "holds")


def test_no_name_depends_on_its_position(tmp_path):
    f = _ramp(tmp_path)
    one = mathema.check(f, claims=["for mi in [0,1], f(mi) >= 0",
                                   "for mi in [0,1], f(mi) <= 1"])
    two = mathema.check(f, claims=["for mi in [0,1], f(mi) <= 1",
                                   "for mi in [0,1], f(mi) >= 0"])
    assert {p.name for p in one.probes} == {p.name for p in two.probes}
    assert not any("__" in p.name for p in one.probes)


def test_a_claims_file_refuses_two_unnamed_claims_that_name_alike(tmp_path):
    from mathema.spec import ClaimsFileError, validate_claims_file
    data = {"ramp.f": {"claims": [
        {"statement": "for mi in [0, 1], f(mi) >= 0"},
        {"statement": "for mi in [1, 2], f(mi) >= 0"}]}}
    with pytest.raises(ClaimsFileError, match="f_mi_ge_0"):
        validate_claims_file(data, "claims.yaml")
    data = {"ramp.f": {"claims": [
        {"statement": "for mi in [0, 1], f(mi) >= 0"},
        {"statement": "for mi in [0, 1], f(mi) <= 1"}]}}
    validate_claims_file(data, "claims.yaml")
