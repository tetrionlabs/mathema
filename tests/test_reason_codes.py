# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema.reason_codes: the public reason-code registries and
build_issue_record()/issue(), built directly on top of
derivability_report()/diagnostic_report()/check_conjectures(), no
new analysis, just a stable, named shape for what they already
compute, on top of the real CDD spec record (spec.to_spec())."""
import json
import math
import os
import socket

from mathema.claims import claim
from mathema.inventory import derivability_report
from mathema.reason_codes import (
    Category, ClaimReasonCode, ReasonCode, build_issue_record, claim_reason_code, issue,
)


def calls_unmapped(x: float) -> float:
    return math.hypot(x, x)


def has_a_loop(xs: list) -> float:
    total = 0.0
    for v in xs:
        total = total * v
    return total


def linear_fn(x: float) -> float:
    return 2.0 * x + 1.0


def clock_hour(hour: float) -> float:
    return hour % 12


def test_reason_code_values_match_derivability_report_exactly():
    report = derivability_report(calls_unmapped)
    assert report["blocker"] == ReasonCode.UNSUPPORTED_CONSTRUCT
    assert report["category"] == Category.UNSUPPORTED_CALL


def test_reason_code_all_lists_every_blocker_derivability_report_can_return():
    assert set(ReasonCode.ALL) == {
        "stateful", "loop", "branch", "recursion", "no-parameters",
        "non-scalar-parameters", "internal-error", "unsupported-construct",
    }


def test_build_issue_record_for_an_unliftable_function():
    record = build_issue_record(calls_unmapped)
    assert record is not None
    diag = record["meta"]["mathema.diagnostic_report"]
    assert diag["liftable"] is False
    assert diag["error_code"] == ReasonCode.UNSUPPORTED_CONSTRUCT
    assert diag["error_category"] == Category.UNSUPPORTED_CALL
    assert diag["diagnostic_scheme"] == 3
    assert "mathema_version" in diag
    assert "sympy_version" in diag
    assert "source" not in record["meta"]["mathema.issue"]


def test_build_issue_record_omitted_claims_uses_suggest_claims():
    # lenient (default) has nothing to report, linear_fn's falsified
    # claims (monotonic_decreasing/even/odd/idempotent, all real,
    # expected outcomes for a strictly increasing, non-symmetric,
    # non-idempotent linear function) are pending discoveries, not
    # failures, until diagnosed. include_falsified=True is what makes them count,
    # confirming suggest_claims()'s now-fuller battery (monotonicity/
    # affine/convexity plus symmetry/idempotence/determinism/stability,
    # all migrated onto claims this session) is really what's driving
    # the record.
    assert build_issue_record(linear_fn) is None
    record = build_issue_record(linear_fn, include_falsified=True)
    names = {c["name"] for c in record["claims"]}
    assert names == {"monotonic_increasing[x]", "monotonic_decreasing[x]",
                     "affine[x]", "convex[x]", "concave[x]",
                     "even", "odd", "idempotent", "is_deterministic",
                     "is_state_safe", "is_numerically_stable",
                     "is_representation_safe[x]"}
    assert set(record["meta"]["mathema.issue"]["failing_claims"]) == \
        {"monotonic_decreasing[x]", "even", "odd", "idempotent"}


def test_build_issue_record_explicit_empty_list_means_no_claims_at_all():
    # distinct from omitting claims entirely (which falls back to
    # suggest_claims); claims=[] is how a caller says "check nothing".
    assert build_issue_record(linear_fn, []) is None


def test_build_issue_record_explicit_claims_override_suggest_claims():
    # falsified only counts as a failing claim under include_falsified=True (see
    # test_build_issue_record_omitted_claims_uses_suggest_claims);
    # lenient here has nothing to report even though clock_wraps is
    # genuinely falsified.
    cj = claim("for hour in [0, 15], f(hour) == hour", route="derive", name="clock_wraps")
    assert build_issue_record(clock_hour, [cj]) is None
    record = build_issue_record(clock_hour, [cj], include_falsified=True)
    assert [c["name"] for c in record["claims"]] == ["clock_wraps"]
    assert record["claims"][0]["verdict"] == "falsified"
    assert record["meta"]["mathema.issue"]["failing_claims"] == ["clock_wraps"]


def test_build_issue_record_never_treats_a_falsified_suggested_claim_as_failing_by_default():
    # even/odd/idempotent/is_reproducible/is_numerically_stable are no
    # longer a separate, bypassed "built-in battery"; they're
    # suggest_claims()'s own claims now, migrated onto the same
    # adaptive derive/probe pipeline as everything else. What actually
    # keeps an ordinary function's expected falsifications (a linear
    # function is not even, not odd, not idempotent, by design) from
    # being a reportable anomaly is the lenient/strict distinction, not
    # which battery a claim came from.
    assert build_issue_record(linear_fn) is None
    record = build_issue_record(linear_fn, include_falsified=True)
    names = {c["name"] for c in record["claims"]}
    assert names & {"even", "odd", "idempotent", "is_deterministic", "is_numerically_stable",
                     "is_representation_safe[x]"}
    assert record["meta"]["mathema.issue"]["failing_claims"]


def test_build_issue_record_multiple_failure_nodes():
    # clock_wraps is falsified (only counts under strict); stays_small
    # stays genuinely unknown on BOTH routes (sympy can't close the
    # Sum-of-Mod bound, and the probe route can't evaluate a Sum(...)
    # law at all); an open unknown always counts, lenient or strict,
    # so lenient here already reports one failing node, and strict is
    # what makes it two at once.
    cj1 = claim("for hour in [0, 15], f(hour) == hour", route="derive", name="clock_wraps")
    cj2 = claim("for hour in [0, 100], Sum(f(hour), k, 1, 3) <= 32",
                route="derive", name="stays_small")
    # stays_small now FALSIFIES through the lifted-numeric fallback
    # (3*Mod(hour,12) reaches 33 > 32, an executed witness on the
    # resolved intermediate), so no OPEN unknown remains and the
    # lenient record is empty; strict reports both falsifications
    lenient = build_issue_record(clock_hour, [cj1, cj2])
    assert lenient is None
    record = build_issue_record(clock_hour, [cj1, cj2], include_falsified=True)
    failing = set(record["meta"]["mathema.issue"]["failing_claims"])
    assert failing == {"clock_wraps", "stays_small"}


def test_build_issue_record_returns_none_for_a_fully_clean_function():
    def identity(x: float) -> float:
        return x

    cj = claim("f(x) == x", route="derive")
    assert build_issue_record(identity, [cj]) is None


def test_build_issue_record_source_section_present_only_when_requested():
    without = build_issue_record(calls_unmapped)
    assert "source" not in without["meta"]["mathema.issue"]

    with_source = build_issue_record(calls_unmapped, include_source=True)
    section = with_source["meta"]["mathema.issue"]["source"]
    assert "math.hypot" in section["text"]
    assert section["line"] == 2
    assert "dependencies" in section
    assert set(section["dependencies"]) == {"global_vars", "global_funcs", "unresolved"}


def test_reasoning_narrates_a_skipped_claim():
    # has_a_loop is not liftable (a loop with no recognized fold/dot/sum
    # shape), so a derive claim against it comes back skipped rather
    # than falsified, the case reasoning_chain()'s "gap" branch exists
    # for.
    cj = claim("Sum(f(xs), k, 1, 3) >= 0", route="derive", name="nonneg")
    record = build_issue_record(has_a_loop, [cj])
    assert record["claims"][0]["verdict"] == "unknown"
    gaps = [step for step in record["reasoning"]
           if step["step"] == "gap" and step["claim"] == "Sum(f(xs), k, 1, 3) >= 0"]
    assert len(gaps) == 1
    assert "not derivable" in gaps[0]["basis"]


def test_claim_reason_code_recognizes_every_skip_shape():
    # hand-built Probes, not a live proof attempt, claim_reason_code()
    # is recognition logic over what check_conjectures() already wrote,
    # and testing it this way stays correct regardless of how sympy's
    # own decidability changes over time (several of these exact skip
    # shapes were found and fixed this same session).
    from mathema.probing import Probe

    cases = [
        (Probe("c", "s", "skipped", meta={"mathema.foreign_grammar": "other"}),
         ClaimReasonCode.FOREIGN_GRAMMAR),
        (Probe("c", "s", "skipped", meta={"mathema.derive_status": "undecided"}),
         ClaimReasonCode.DERIVE_UNDECIDED),
        (Probe("c", "s", "skipped", meta={"mathema.derive_status": "unliftable"}),
         ClaimReasonCode.DERIVE_UNLIFTABLE),
        (Probe("c", "s", "skipped",
              meta={"mathema.derive_status": "undecided", "mathema.timeout": "fast"}),
         ClaimReasonCode.DERIVE_TIMEOUT),
        (Probe("c", "s", "skipped",
              note="...; derive route does not yet lift multi-function or != claims"),
         ClaimReasonCode.UNSUPPORTED_MULTI_FUNCTION),
        (Probe("c", "s", "skipped", note="unknown route 'bogus'"), ClaimReasonCode.UNKNOWN_ROUTE),
        (Probe("c", "s", "skipped", note="unknown relation '==='"),
         ClaimReasonCode.UNKNOWN_RELATION),
        (Probe("c", "s", "skipped", note="unknown exception type 'Bogus'"),
         ClaimReasonCode.UNKNOWN_EXCEPTION_TYPE),
        (Probe("c", "s", "skipped", note="...; no evaluable inputs"),
         ClaimReasonCode.NO_EVALUABLE_INPUTS),
        (Probe("c", "s", "skipped", note="name 'q' is not allowed",
               meta={"mathema.invalid_conjecture": True}),
         ClaimReasonCode.INVALID_CONJECTURE),
    ]
    for probe, expected in cases:
        assert claim_reason_code(probe) == expected, probe


def test_claim_reason_code_only_meaningful_for_skipped():
    from mathema.probing import Probe

    assert claim_reason_code(Probe("c", "s", "proven")) is None
    assert claim_reason_code(Probe("c", "s", "holds")) is None
    assert claim_reason_code(Probe("c", "s", "falsified")) is None


def test_claim_reason_code_all_lists_every_value():
    assert set(ClaimReasonCode.ALL) == {
        "foreign-grammar", "unsupported-multi-function", "derive-undecided",
        "derive-unliftable", "derive-timeout", "unknown-route", "unknown-relation",
        "unknown-exception-type", "invalid-conjecture", "no-evaluable-inputs",
        "derive-gap-empirical",
        # a conditional claim whose premise could not be discharged:
        # the claim was never attempted, so these say what the premise
        # did, not what the claim did
        "missing-prerequisite", "unmet-prerequisite",
        "ambiguous-reference", "dependency-cycle",
    }


def test_derive_timeout_tag_appears_on_a_real_timed_out_claim(monkeypatch):
    # confirms the actual code path, not just claim_reason_code()'s own
    # recognition of it: a real wall-clock cutoff inside _prove_relation
    # must carry mathema.timeout through to the claim's own Probe.meta.
    import time

    import sympy

    def _slow_simplify(expr, *args, **kwargs):
        time.sleep(4)
        return expr

    monkeypatch.setattr(sympy, "simplify", _slow_simplify)

    def identity(x: float) -> float:
        return math.lgamma(x)

    # a d(...) law keeps the probe route out (it can't evaluate a
    # derivative), and polygamma has no plain-math lambdify mapping so
    # the lifted-numeric fallback declines too, the timed-out derive
    # attempt is the whole story
    cj = claim("for x in [2, 10], d(f(x), x) >= 0", route="derive")
    record = build_issue_record(identity, [cj])
    probe = record["claims"][0]
    assert probe["verdict"] == "unknown"
    assert probe["meta"]["mathema.timeout"] == "fast"
    assert claim_reason_code_probe(probe) == ClaimReasonCode.DERIVE_TIMEOUT


def claim_reason_code_probe(probe_dict):
    """`claim_reason_code()` takes a real `Probe` object; a spec dict's
    own claim entry has the same fields under different access (`[k]`
    not `.k`); this adapts one to the other for this one test rather
    than giving `claim_reason_code()` a second calling convention."""
    from mathema.probing import Probe
    return claim_reason_code(Probe(probe_dict["name"], probe_dict["statement"],
                                   probe_dict["verdict"], meta=probe_dict["meta"] or {},
                                   note=probe_dict["note"]))


def test_to_json_payload_round_trips_through_real_json():
    record = build_issue_record(calls_unmapped)
    reparsed = json.loads(json.dumps(record, default=str))
    assert reparsed["meta"]["mathema.diagnostic_report"]["error_code"] == "unsupported-construct"
    assert reparsed["meta"]["mathema.diagnostic_report"]["diagnostic_scheme"] == 3


def test_issue_makes_no_network_call(tmp_path, monkeypatch):
    # a direct assertion, not "it seemed fine": any attempt to open a
    # socket at all fails the test immediately.
    def _refuse(*args, **kwargs):
        raise AssertionError("mathema issue must never touch the network")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    path = issue(calls_unmapped, root=str(tmp_path), confirm=lambda _: True)
    assert path is not None
    assert os.path.exists(path)


def test_issue_prints_the_payload_and_writes_only_on_confirmation(tmp_path, capsys):
    declined = issue(calls_unmapped, root=str(tmp_path), confirm=lambda _: False)
    assert declined is None
    out = capsys.readouterr().out
    assert '"error_code": "unsupported-construct"' in out
    assert not os.path.exists(os.path.join(str(tmp_path), ".mathema", "issues"))

    written = issue(calls_unmapped, root=str(tmp_path), confirm=lambda _: True)
    assert written is not None
    assert written.endswith(".json")
    with open(written) as f:
        payload = json.load(f)
    assert payload["meta"]["mathema.diagnostic_report"]["error_code"] == "unsupported-construct"


def test_issue_returns_none_for_a_clean_function_without_prompting():
    def identity(x: float) -> float:
        return x

    prompted = []
    cj = claim("f(x) == x", route="derive")
    result = issue(identity, [cj], confirm=lambda _: prompted.append(1) or True)
    assert result is None
    assert not prompted


def test_issue_source_only_included_when_explicitly_requested(tmp_path):
    without = issue(calls_unmapped, root=str(tmp_path), confirm=lambda _: True)
    with open(without) as f:
        payload_without = json.load(f)
    assert "source" not in payload_without["meta"]["mathema.issue"]

    with_source = issue(calls_unmapped, root=str(tmp_path), include_source=True,
                        confirm=lambda _: True)
    with open(with_source) as f:
        payload_with = json.load(f)
    assert "math.hypot" in payload_with["meta"]["mathema.issue"]["source"]["text"]


def test_diagnostic_report_known_key_set_guard(tmp_path):
    # if this breaks, diagnostic_report()'s own field layout changed,
    # bump diagnostics.DIAGNOSTIC_SCHEME and update this test's
    # expected key set deliberately, don't just patch it to pass.
    # Scheme 3 dropped ast_fingerprint/failure_dedup_fingerprint:
    # similarity fingerprinting left core entirely.
    from mathema.analysis import analyze_source
    from mathema.diagnostics import diagnostic_report

    expected = {
        "diagnostic_scheme", "liftable", "wraps",
        "error_code", "error_category", "blocked", "constructs",
        "motifs", "operations_of_interest", "domain_hazards",
        "sympy_version", "mathema_version",
    }
    # ONE stable key set on both branches: a consumer reads any field
    # without branching on `liftable` first, and an empty list means
    # "computed, nothing found", never "never looked"
    liftable = diagnostic_report(linear_fn, analyze_source(linear_fn))
    assert set(liftable) == expected
    assert liftable["diagnostic_scheme"] == 3
    assert liftable["error_code"] is None and liftable["constructs"] == []
    not_liftable = diagnostic_report(calls_unmapped, analyze_source(calls_unmapped))
    assert set(not_liftable) - {"liftable_note"} == expected
    assert not_liftable["operations_of_interest"] == {}
    assert not_liftable["domain_hazards"] == []
