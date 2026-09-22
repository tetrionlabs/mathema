# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The agent-facing claim row: a closed `stance` beside the open
verdict, the authoring-surface `source`, the `gates` population flag,
and the envelope rule (counterexample present iff refuted, blocked_by
iff blocked). Pinned so "seven falsified suggestions, zero declared
claims" is self-evident from a payload instead of a contradiction."""
import sys
import textwrap

from mathema.records import claim_row, row_source, stance


def test_stance_folds_the_open_verdict_vocabulary():
    assert stance("proven") == "supported"
    assert stance("holds") == "supported"
    assert stance("falsified") == "refuted"
    # a subroute example only: no adjudication path produces this string
    # (an uncorroborated disproof downgrades to "unknown"); it pins that
    # ANY falsified:* subroute folds to refuted
    assert stance("falsified:uncorroborated") == "refuted"
    assert stance("invalidated") == "refuted"
    assert stance("unknown") == "undecided"
    assert stance("declared") == "undecided"
    assert stance("skipped:misspecified") == "blocked"
    assert stance("skipped:unknown_but_accepted") == "blocked"
    # open vocabulary: an unrecognized verdict is undecided, never a crash
    assert stance("probe:algorithmic") == "undecided"


def test_row_source_folds_the_historical_sentinels():
    assert row_source({"mathema.surface": "mathema"}) == "suggested"
    assert row_source({"mathema.surface": "docstring"}) == "docstring"
    assert row_source({"mathema.surface": "decorator"}) == "decorator"
    assert row_source({"mathema.surface": "declared"}) == "declared"
    # the pre-rename spellings still read from an older store
    assert row_source({"mathema.surface": "author"}) == "decorator"
    assert row_source({"mathema.surface": "the author"}) == "declared"
    assert row_source({"mathema.surface": "builtin"}) == "builtin"
    assert row_source({"mathema.surface": "types"}) == "types"
    assert row_source({"mathema.surface": "user"}) == "ad_hoc"
    # provenance that is absent or unrecognized is stated, loudly, as
    # its own answer, never silently filed under the call-site bucket
    import pytest as _pytest
    with _pytest.warns(UserWarning, match="no surface"):
        assert row_source({}) == "unknown"
    with _pytest.warns(UserWarning, match="unrecognized surface"):
        assert row_source({"mathema.surface": "a-typo"}) == "unknown"
    assert row_source(None, "conjectured by mathema; ...") == "suggested"


def test_envelope_rule_keys_present_iff_meaningful():
    refuted = claim_row({"name": "w", "statement": "f(x) == 3*x",
                         "verdict": "falsified", "route": "derive",
                         "counterexample": "x=1", "n": 0,
                         "meta": {"mathema.surface": "the author"}})
    assert refuted["stance"] == "refuted" and refuted["counterexample"] == "x=1"
    assert "blocked_by" not in refuted
    assert refuted["gates"] is True and refuted["source"] == "declared"

    supported = claim_row({"name": "d", "statement": "f(x) == 2*x",
                           "verdict": "proven", "route": "derive"})
    assert "counterexample" not in supported and "blocked_by" not in supported

    blocked = claim_row({"name": "b", "statement": "f(x) >= 0",
                         "verdict": "skipped:misspecified", "route": "derive"})
    assert blocked["stance"] == "blocked"
    assert blocked["blocked_by"] == "misspecified"

    suggestion = claim_row({"name": "s", "statement": "f(x) >= 0",
                            "verdict": "falsified", "route": "probe",
                            "meta": {"mathema.surface": "mathema"}})
    assert suggestion["gates"] is False and suggestion["source"] == "suggested"


def test_check_stamps_battery_and_suggestion_surfaces(tmp_path):
    import importlib

    import mathema
    (tmp_path / "rowpkg.py").write_text(textwrap.dedent('''
        def double(x: float) -> float:
            """Doubles."""
            return 2.0 * x

        def noisy(x: float) -> float:
            """Prints."""
            print(x)
            return x
        '''))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module("rowpkg")
        importlib.reload(mod)
        # the suggestion battery (claims=None) is labeled suggested
        rec = mathema.check(mod.double)
        sources = {p.name: row_source(p.meta, p.note or "")
                   for p in rec.probes}
        assert sources.get("affine[x]") == "suggested"
        # a structural gap row from probe() itself is labeled builtin
        rec = mathema.check(mod.noisy, claims=[])
        sources = {p.name: row_source(p.meta, p.note or "")
                   for p in rec.probes}
        assert sources.get("purity") == "builtin"
    finally:
        sys.path.remove(str(tmp_path))
        del sys.modules["rowpkg"]


def test_mixed_payload_is_self_evident(tmp_path):
    """A falsified declared claim and a falsified suggestion in one
    payload: passed is False because of the first, and the rows say so
    through gates/source rather than leaving a contradiction."""
    pkg = tmp_path / "mpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "def weird(x: float) -> float:\n"
        "    return -abs(x)\n")
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "c.claims.yaml").write_text(textwrap.dedent("""
        mpkg.mod.weird:
          claims:
            - name: wrong_sign
              statement: 'for x in [1,5], f(x) >= 0'
              route: derive
        """))
    sys.path.insert(0, str(tmp_path))
    try:
        from mathema.interfaces.mcp.tools import adjudicate_target
        out = adjudicate_target("mpkg.mod.weird", root=str(tmp_path))
        rows = {c["claim"]: c for c in out["claims"]}
        assert rows["wrong_sign"]["stance"] == "refuted"
        assert rows["wrong_sign"]["source"] == "declared"
        assert rows["wrong_sign"]["gates"] is True
        assert out["passed"] is False
        # any falsified suggestion in the same payload is marked non-gating
        for c in out["claims"]:
            if c["source"] == "suggested":
                assert c["gates"] is False
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("mpkg")]:
            del sys.modules[m]
