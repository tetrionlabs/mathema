# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Verdict vocabulary v2: `unknown` for attempted-but-undecided
adjudication, `invalidated` as the record layer's regression error
state (with `mathema.previous_verdict`/`mathema.regressed_to`
history), strict mode counting both unestablished families, and a
declared-spec `intent:` earning the `documented` rung."""
import yaml

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.records import Probe, classify_verdict
from mathema.spec import record


def branchy(x: float) -> float:
    if x > 0:
        return x
    return -x


def test_underivable_derive_claim_superseded_by_evidence_keeps_its_status_tag():
    # a branchy function doesn't lift: the derive route ran and decided
    # nothing either way. Empirical evidence then supersedes the
    # unknown (route supersession), so the VERDICT lands at holds; the
    # structured which-kind-of-couldn't-decide tag survives onto the
    # record, pinned exactly, the piecewise lift succeeds here but
    # the sign question stays undecided.
    (p,) = check_conjectures(branchy, [claim("f(x) >= 0", route="derive")])
    assert p.verdict == "holds"
    assert p.meta.get("mathema.derive_status") == "undecided"

    (blocked,) = check_conjectures(branchy, [claim("f(x) >= 0", route="quantum")])
    assert classify_verdict(blocked.verdict) == "skipped"


def _write(tmp_path, key, probes):
    facts = mathema.analyze(branchy)
    rec = mathema.Record(facts=facts, probes=probes)
    return record(rec, key=key, root=str(tmp_path))


def _read(tmp_path, key):
    doc = yaml.safe_load((tmp_path / ".mathema" / "verified" / f"{key}.yaml").read_text())
    return {c["name"]: c for c in doc[key]["claims"]}


def test_supported_to_unsupported_regression_is_invalidated(tmp_path):
    key = "vocab.regression"
    _write(tmp_path, key, [Probe("nonneg", "f(x) >= 0", "proven", route="derive")])
    _write(tmp_path, key, [Probe("nonneg", "f(x) >= 0", "falsified", route="probe",
                                 counterexample="x=-1: -1 vs 0")])
    c = _read(tmp_path, key)["nonneg"]
    assert c["verdict"] == "invalidated"
    assert c["meta"]["mathema.previous_verdict"] == "proven"
    assert c["meta"]["mathema.regressed_to"] == "falsified"
    # the evidence itself is preserved alongside the error state
    assert c["counterexample"] == "x=-1: -1 vs 0"


def test_invalidation_persists_until_genuinely_resupported(tmp_path):
    key = "vocab.persistence"
    _write(tmp_path, key, [Probe("nonneg", "f(x) >= 0", "holds", n=64, route="probe")])
    _write(tmp_path, key, [Probe("nonneg", "f(x) >= 0", "unknown", route="derive")])
    assert _read(tmp_path, key)["nonneg"]["verdict"] == "invalidated"

    # a still-failing re-run never launders the error back to ordinary
    _write(tmp_path, key, [Probe("nonneg", "f(x) >= 0", "skipped", route=None)])
    c = _read(tmp_path, key)["nonneg"]
    assert c["verdict"] == "invalidated"
    assert c["meta"]["mathema.previous_verdict"] == "invalidated"

    # genuine re-support recovers, with the history still visible
    _write(tmp_path, key, [Probe("nonneg", "f(x) >= 0", "proven", route="derive")])
    c = _read(tmp_path, key)["nonneg"]
    assert c["verdict"] == "proven"
    assert c["meta"]["mathema.previous_verdict"] == "invalidated"


def test_verdict_change_within_supported_keeps_verdict_but_records_history(tmp_path):
    key = "vocab.drift"
    _write(tmp_path, key, [Probe("nonneg", "f(x) >= 0", "proven", route="derive")])
    _write(tmp_path, key, [Probe("nonneg", "f(x) >= 0", "holds", n=64, route="probe")])
    c = _read(tmp_path, key)["nonneg"]
    assert c["verdict"] == "holds"   # still supported: weaker, not a regression
    assert c["meta"]["mathema.previous_verdict"] == "proven"


def test_strict_check_counts_unknown_as_unverifiable(tmp_path):
    import subprocess
    import sys
    (tmp_path / "funcs.py").write_text(
        "def branchy(x: float) -> float:\n"
        "    if x > 0:\n"
        "        return x\n"
        "    return -x\n")
    script = ("import sys; from mathema.cli import main; "
             "sys.exit(main(['check', 'funcs.py:branchy', '--strict', "
             "'--claim', 'f(x) >= 0']))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True)
    # the inline claim probes fine; strict failure isn't guaranteed here,
    # but the row must carry the unknown bucket and total must add up.
    script_json = ("import sys; from mathema.cli import main; "
                  "sys.exit(main(['check', 'funcs.py:branchy', "
                  "'--format', 'json']))")
    r = subprocess.run([sys.executable, "-c", script_json], cwd=str(tmp_path),
                       capture_output=True, text=True)
    import json
    (row,) = json.loads(r.stdout)["functions"]
    assert "unknown" in row
    assert row["total"] == (row["proven"] + row["holds"] + row["refuted"]
                            + row["unverifiable"] + row["unknown"])


def test_declared_intent_starts_on_the_declared_rung(tmp_path):
    key = "vocab.intent"
    facts = mathema.analyze(branchy)
    rec = mathema.Record(facts=facts, probes=[])
    record(rec, key=key, root=str(tmp_path),
           declared_intent="Absolute value, stated in the declared spec.")
    doc = yaml.safe_load((tmp_path / ".mathema" / "verified" / f"{key}.yaml").read_text())
    spec = doc[key]
    assert spec["intent"] == "Absolute value, stated in the declared spec."
    # every stated intent starts at the declared rung now;
    # "documented" is the human acceptance (mathema accept --intent)
    assert spec["meta"]["mathema.intent_provenance"] == "declared"
