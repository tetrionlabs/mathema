# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Clarity's domain entropy per parameter comes from the domain the
checks complete for it, the one source: a parameter with no annotation
costs the most, a type alone less, a bounded range or a finite set
less again, and an exhaustive proof over a finite set clears it. An
Optional parameter adds an absence source, cleared by an absent row.
The algorithm version moves with the scale."""
import textwrap

from mathema.badges import (CLARITY_ALGO, _clarity_profile, _clarity_sources,
                            clarity_bits, clarity_score)


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_BODY = '''
    from typing import Literal, Optional

    def bare(s):
        """The text in capitals."""
        return s.upper()

    def typed(s: str) -> str:
        """The text in capitals."""
        return s.upper()

    def finite(s: Literal["a", "b"]) -> str:
        """The text in capitals."""
        return s.upper()

    def optional(s: Optional[str]) -> str:
        """The text in capitals."""
        return "" if s is None else s.upper()

    def wide(x: float) -> float:
        """Twice x."""
        return 2.0 * x
'''


def _domain_bits(fn) -> dict:
    """The bits each unguarded parameter's inputs cost, by name."""
    return {d.name: d.bits for d in _clarity_profile(fn).domains}


def test_the_algorithm_version_moved_with_the_scale():
    assert CLARITY_ALGO == "entropy-dimensions@1.3"


def test_less_is_known_about_an_unannotated_parameter(tmp_path):
    mod = _load(tmp_path, _BODY, "clarity_domains")
    assert _domain_bits(mod.bare)["s"] == 1.5
    assert _domain_bits(mod.typed)["s"] == 1.0
    assert _domain_bits(mod.finite)["s"] == 0.1
    assert _domain_bits(mod.wide)["x"] == 1.0


def test_an_optional_parameter_adds_an_absence_source(tmp_path):
    mod = _load(tmp_path, _BODY, "clarity_optional")
    sources = _clarity_sources(_clarity_profile(mod.optional))
    assert ("domain", 0.5, "absence:s") in sources
    assert not any(reducer == "absence:s"
                   for _dim, _bits, reducer in _clarity_sources(_clarity_profile(mod.typed)))
    with_row = [{"name": "absent[s]", "statement": "absent(f, s) drops",
                 "verdict": "holds", "route": "probe:counterfactual",
                 "meta": {"mathema.policy": {"kind": "absent", "parameter": "s"}}}]
    assert clarity_score(mod.optional, verified_claims=with_row) > \
        clarity_score(mod.optional, verified_claims=[])


def test_an_exhaustive_proof_clears_a_finite_set(tmp_path):
    mod = _load(tmp_path, _BODY, "clarity_finite")
    swept = [{"name": "upper", "statement": 'f(s) == f(s)',
              "verdict": "proven", "route": "derive:brute_force"}]
    _h0, rem_swept = clarity_bits(mod.finite, verified_claims=swept)
    _h0, rem_plain = clarity_bits(mod.finite, verified_claims=[])
    assert rem_swept < rem_plain


def test_a_claim_binding_a_narrower_domain_lowers_the_parameter_s_bits(tmp_path):
    mod = _load(tmp_path, _BODY, "clarity_bound")
    narrow = [{"name": "small", "statement": "for x in [0, 1], f(x) <= 2",
               "verdict": "holds", "route": "probe"}]
    whole = [{"name": "small", "statement": "f(x) <= 2",
              "verdict": "holds", "route": "probe"}]
    assert clarity_score(mod.wide, verified_claims=narrow) > \
        clarity_score(mod.wide, verified_claims=whole)
