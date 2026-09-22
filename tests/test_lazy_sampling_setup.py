# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""check_conjectures()'s shared sampling setup (probing._prepare_sampling,
seeded RNG + critical-point search) must be computed lazily, at most
once per call, and only when some claim actually reaches a probe-needing
attempt (the generic probe loop or a family's probe:algorithmic route).
A batch of route="derive" claims never touches derive at all through
this setup, so paying for the critical-point search on their behalf was
pure waste."""
from mathema import conjecture
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim


def line(x: float) -> float:
    return 3.0 * x + 2.0


def clamp01(x: float) -> float:
    return max(0.0, min(x, 1.0))


def _counting_prepare_sampling(monkeypatch):
    calls = []
    real = conjecture._prepare_sampling

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(conjecture, "_prepare_sampling", counting)
    return calls


def test_all_derive_route_batch_never_prepares_sampling(monkeypatch):
    # both claims' proofs decide, so nothing ever falls back to probing
    # and the sampling setup is never paid for. An undecided derive
    # claim would now probe, deliberately, per the
    # unknown-superseded-by-evidence ruling, so only a fully-deciding
    # batch keeps this guarantee.
    calls = _counting_prepare_sampling(monkeypatch)
    facts = analyze_source(line)
    claims = [claim("f(x) == 3.0 * x + 2.0", route="derive"),
             claim("d(f(x), x) == 3.0", route="derive")]

    check_conjectures(line, claims, facts=facts)

    assert calls == []


def test_a_probe_claim_still_triggers_sampling_setup(monkeypatch):
    calls = _counting_prepare_sampling(monkeypatch)
    facts = analyze_source(line)
    claims = [claim("f(x) == 3.0 * x + 2.0", route="probe")]

    check_conjectures(line, claims, facts=facts)

    assert len(calls) == 1


def test_sampling_setup_computed_at_most_once_for_a_multi_claim_probe_batch(monkeypatch):
    calls = _counting_prepare_sampling(monkeypatch)
    facts = analyze_source(line)
    claims = [claim("f(x) == 3.0 * x + 2.0", route="probe"),
             claim("f(x) >= 0", route="probe"),
             claim("f(x) <= 1000", route="probe")]

    check_conjectures(line, claims, facts=facts)

    assert len(calls) == 1


def test_a_derive_ineligible_auto_claim_falling_to_probe_still_triggers_setup(monkeypatch):
    # route="best" whose derive attempt can't settle (the bound
    # function has a while loop, so its lift refuses) -> falls to the
    # generic probe path. The lazy setup must still fire here, not
    # only for an explicitly-declared route="probe" claim. (A range
    # loop no longer qualifies as ineligible either: a branch-free
    # scalar loop binding closes through the sum machinery now.)
    def loopy_twin(x: float) -> float:
        total = x
        while abs(total) > 1.0:
            total = total / 2.0
        return total

    calls = _counting_prepare_sampling(monkeypatch)
    facts = analyze_source(line)
    claims = [claim("f(x) == g(x)", route="best", funcs={"g": loopy_twin})]

    check_conjectures(line, claims, facts=facts)

    assert len(calls) == 1


def test_family_probe_algorithmic_only_batch_triggers_setup_once(monkeypatch):
    # monotonic_increasing[x] resolves via the monotonic_increasing
    # family's probe:algorithmic route (clamp01 doesn't lift cleanly
    # enough for derive to settle it); this path reads rng/trials from
    # the same lazy setup, not the generic loop, and must still trigger
    # it exactly once.
    calls = _counting_prepare_sampling(monkeypatch)
    facts = analyze_source(clamp01)
    claims = [claim("d(f(x), x) >= 0", name="monotonic_increasing[x]", route="best")]

    check_conjectures(clamp01, claims, facts=facts)

    assert len(calls) == 1


def test_mixed_derive_and_probe_batch_triggers_setup_only_once(monkeypatch):
    calls = _counting_prepare_sampling(monkeypatch)
    facts = analyze_source(line)
    claims = [claim("f(x) == 3.0 * x + 2.0", route="derive"),
             claim("f(x) >= 0", route="probe"),
             claim("f(x) <= 1000", route="probe")]

    check_conjectures(line, claims, facts=facts)

    assert len(calls) == 1
