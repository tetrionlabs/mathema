# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/diagnostics.py's diagnostic_report(): the opt-in bundle,
never computed by default, covering both the lifting and non-lifting
paths."""
import math

import sympy

import mathema
from mathema.analysis import analyze_source
from mathema.diagnostics import diagnostic_report


def clamped_ratio(x: float, lo: float, hi: float) -> float:
    return max(lo, min(x, hi)) / 2


def calls_unmapped(x: float) -> float:
    return math.hypot(x, x)


def npv_shaped(c1: float, r: float) -> float:
    return c1 / (1 + r)


def test_liftable_function_gets_the_full_bundle():
    facts = analyze_source(clamped_ratio)
    result = diagnostic_report(clamped_ratio, facts)
    assert result["liftable"] is True
    assert result["diagnostic_scheme"] == 3
    # scheme 3: no fingerprint fields at all; similarity is not
    # core's concern, and nothing here ever read them
    assert "failure_dedup_fingerprint" not in result
    assert "ast_fingerprint" not in result
    assert {m["motif"] for m in result["motifs"]} == {"clamp"}
    assert isinstance(result["operations_of_interest"], dict)
    assert result["domain_hazards"] == []
    assert "source" not in result
    assert "similar_claims" not in result
    assert result["sympy_version"] == sympy.__version__
    assert result["mathema_version"] == mathema.__version__


def test_non_liftable_function_gets_error_code_and_constructs():
    facts = analyze_source(calls_unmapped)
    result = diagnostic_report(calls_unmapped, facts)
    assert result["liftable"] is False
    assert result["diagnostic_scheme"] == 3
    assert result["error_code"] == "unsupported-construct"
    assert result["error_category"] == "unsupported-call"
    assert "error_line" not in result
    assert result["sympy_version"] == sympy.__version__
    assert result["mathema_version"] == mathema.__version__
    assert "failure_dedup_fingerprint" not in result
    assert "ast_fingerprint" not in result
    assert "source" not in result


def test_no_similarity_fingerprint_on_either_branch():
    # the excision, pinned from both sides: core ships no shingle,
    # signature, or locality hash for any function, liftable or not
    for fn in (clamped_ratio, calls_unmapped):
        result = diagnostic_report(fn, analyze_source(fn))
        assert not any("fingerprint" in k or "signature" in k
                       or "locality" in k for k in result), result.keys()


def test_no_source_of_any_kind_is_ever_included():
    # source text/line/column live one layer up, in
    # reason_codes.build_issue_record()'s own gated "source" section;
    # diagnostic_report() never carries them, opted in or not.
    facts = analyze_source(clamped_ratio)
    result = diagnostic_report(clamped_ratio, facts)
    assert "source" not in result
    assert "line" not in result
    assert "column" not in result


def test_domain_hazards_found_for_a_real_pole_shaped_function():
    facts = analyze_source(npv_shaped)
    result = diagnostic_report(npv_shaped, facts)
    assert len(result["domain_hazards"]) == 1
    assert result["domain_hazards"][0]["at"] == "-1"
    assert result["domain_hazards"][0]["domain"] == "assumed (-inf, inf), not declared"


def test_diagnostic_report_never_matches_a_corpus_that_belongs_in_pro():
    # core computes this one function's own raw facts and stops there,
    # no corpus/similar-claims matching lives here (that's an
    # accumulate-shaped, cross-function concern, deliberately kept out
    # of core, see the module's own docstring).
    facts = analyze_source(clamped_ratio)
    result = diagnostic_report(clamped_ratio, facts)
    assert "similar_claims" not in result
    assert "corpus" not in diagnostic_report.__kwdefaults__


def test_motifs_reach_functions_that_do_not_lift(tmp_path):
    # the motif library is AST-based precisely so it still says
    # something about a function that FAILS to lift, which is the
    # case failure telemetry most needs. It used to be emitted only on
    # the liftable branch, so those functions never carried it.
    import importlib.util
    import sys
    src = tmp_path / "motif_fixture.py"
    src.write_text(
        "import math\n"
        "def clamped_but_unliftable(xs: list, lo: float) -> float:\n"
        "    total = 0.0\n"
        "    for v in xs:\n"
        "        total = total * v + math.hypot(v, lo)\n"
        "    return max(total, lo)\n")
    spec = importlib.util.spec_from_file_location("motif_fixture", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["motif_fixture"] = mod
    try:
        spec.loader.exec_module(mod)
        fn = mod.clamped_but_unliftable
        result = diagnostic_report(fn, analyze_source(fn))
    finally:
        sys.modules.pop("motif_fixture", None)
    assert result["liftable"] is False
    assert "clamp" in {m["motif"] for m in result["motifs"]}
    # and the fields that genuinely don't apply are typed empties,
    # never absent and never null
    assert result["operations_of_interest"] == {}
    assert result["domain_hazards"] == []
