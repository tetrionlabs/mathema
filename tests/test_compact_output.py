# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The column-oriented agent output: audit's `{prefix, cols, rows}`
shape (CLI --compact/--cols and the MCP audit tool alike) and check's
`--format compact` adjudication rows. Column names appear once, the
shared key prefix is factored out, values are raw data with null for
missing, and the resolved column selection is always echoed back."""
import json
import os
import subprocess
import sys
import textwrap

import pytest

from mathema.audit import COMPACT_DEFAULT_COLS, compact_audit


def _rows():
    return [
        {"key": "arbital.measures.linfoot", "span": "185:193p",
         "claimed": True, "n_claims": 7, "claim_floor": 3, "pure": True, "unconditional": True, "derivable": True,
         "purity_reason": None, "blocked_report": None,
         "complexity": {"cyclomatic": 1},
         "typing": {"params_typed": 1, "params_total": 1,
                    "return_typed": True, "finite_domains": {}},
         "global_vars": [], "unresolved": [], "test_covered": "yes",
         "_scope_excluded": False,
         "docs": {"score": 3, "applicable": 4}, "concepts": []},
        {"key": "arbital.geometry.angular_layout", "span": "20:44p",
         "claimed": False, "n_claims": 0, "claim_floor": None,
         "pure": None, "unconditional": None, "derivable": None,
         "purity_reason": "branch", "blocked_report": None,
         "complexity": None, "typing": None,
         "global_vars": [], "unresolved": [], "test_covered": None,
         "_scope_excluded": True,
         "docs": None, "concepts": []},
    ]


def test_compact_factors_prefix_and_echoes_cols():
    out = compact_audit(_rows(), ["key", "span", "claims", "typed"])
    assert out["prefix"] == "arbital."
    assert out["cols"] == ["key", "span", "claims", "typed"]
    # typed is an [n, m] pair now, never an "n/m" string to parse
    assert out["rows"][0] == ["measures.linfoot", "185:193p", 7, [2, 2]]
    # null strictly means NOT COMPUTED (the analysis was excluded)
    assert out["rows"][1] == ["geometry.angular_layout", "20:44p", 0, None]


def test_null_policy_and_blocker_split():
    # null = not computed; typed empty values = computed-and-empty;
    # the blocker column is a bare CODE_TABLE key with decorations
    # split into their own columns
    computed, excluded = _rows()
    out = compact_audit([computed],
                        ["key", "derivable", "blocker", "blocker_params",
                         "blocker_more", "concepts", "global_vars",
                         "tested"])
    assert out["rows"][0] == ["linfoot", True, "", [], 0,
                              0, [], "yes"]
    out = compact_audit([excluded],
                        ["key", "derivable", "blocker", "blocker_params",
                         "blocker_more", "global_vars", "tested"])
    assert out["rows"][0] == ["angular_layout", None, None,
                              None, None, None, None]


def test_compact_default_cols_and_unknown_col_error():
    out = compact_audit(_rows())
    assert out["cols"] == list(COMPACT_DEFAULT_COLS)
    with pytest.raises(ValueError) as e:
        compact_audit(_rows(), ["key", "nope"])
    assert "nope" in str(e.value) and "key" in str(e.value)


def test_compact_round_trip_reassembles_the_full_key():
    out = compact_audit(_rows(), ["key", "claims"])
    keys = [out["prefix"] + r[0] for r in out["rows"]]
    assert keys == [r["key"] for r in _rows()]


def _project(tmp_path):
    pkg = tmp_path / "cpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent("""
        def double(x: float) -> float:
            return 2.0 * x

        def branchy(x: float) -> float:
            if x < 0:
                return -x
            return x
        """))
    return dict(os.environ, PYTHONPATH=os.pathsep.join(
        [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
         str(tmp_path)]))


def test_cli_audit_compact_flag(tmp_path):
    env = _project(tmp_path)
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         "sys.exit(main(['audit', 'cpkg', '--root', '.', "
         "'--cols', 'key,span,claims,blocker,blocker_params']))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout.splitlines()[-1])
    assert out["cols"] == ["key", "span", "claims", "blocker",
                           "blocker_params"]
    assert out["prefix"] == "cpkg.mod."
    by_key = {r0[0]: r0 for r0 in out["rows"]}
    # a bare CODE_TABLE key, its parameters split into their own cell
    assert by_key["branchy"][3] == "branch:needs-domain"
    assert by_key["branchy"][4] == ["x"]
    assert by_key["double"][3] == ""             # computed, no blocker
    assert by_key["double"][1].endswith("p")     # sed-ready lines


def test_cli_audit_unknown_col_names_the_vocabulary(tmp_path):
    env = _project(tmp_path)
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         "sys.exit(main(['audit', 'cpkg', '--root', '.', "
         "'--cols', 'nope']))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode != 0
    assert "nope" in r.stderr and "choose from" in r.stderr


def test_cli_check_format_compact_rows(tmp_path):
    env = _project(tmp_path)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(textwrap.dedent("""
        cpkg.mod.double:
          claims:
            - name: doubles
              statement: 'for x in [0,5], f(x) == 2*x'
              route: derive
            - name: wrong
              statement: 'for x in [1,5], f(x) == 3*x'
              route: derive
        """))
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         "sys.exit(main(['check', 'cpkg.mod:double', '--root', '.', "
         "'--format', 'compact']))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode == 1, r.stdout + r.stderr   # the falsified file claim
    (entry,) = json.loads(r.stdout)
    assert entry["passed"] is False
    rows = {c["claim"]: c for c in entry["claims"]}
    assert rows["doubles"]["stance"] == "supported"
    assert "counterexample" not in rows["doubles"]   # envelope rule
    assert rows["wrong"]["stance"] == "refuted"
    assert "counterexample" in rows["wrong"]
    assert rows["wrong"]["source"] == "declared"
    assert rows["wrong"]["gates"] is True


def test_column_selection_skips_unneeded_analyses():
    # the speed half: a triage call must not compute what its columns
    # never show
    from mathema.audit import AUDIT_ANALYSES, exclude_for_cols
    assert exclude_for_cols(["key", "span", "claims"]) == AUDIT_ANALYSES
    assert exclude_for_cols(["key", "derivable", "blocker"]) == \
        AUDIT_ANALYSES - {"derivable"}
    assert "typing" not in exclude_for_cols(["key", "typed"])
    assert exclude_for_cols(["key", "cx", "doc_quality"]) == \
        AUDIT_ANALYSES - {"complexity", "docs"}


def test_audit_filter_is_explicit_and_composes(tmp_path):
    # the derive_unlock/claim-status filter: right for a lifting pass,
    # wrong for a claims pass, so it is an explicit parameter, never
    # a default
    import pytest as _pytest

    from mathema.audit import filter_rows
    rows = [
        {"key": "a.one", "claimed": True, "pure": True, "unconditional": True, "derivable": True,
         "blocked_report": None},
        {"key": "a.two", "claimed": False, "pure": False, "unconditional": False, "derivable": False,
         "blocked_report": {"liftable": False, "blocker": "loop",
                            "constructs": [], "line": 1,
                            "code": "loop:not-a-fold"}},
    ]
    # filter by claim status
    assert [r["key"] for r in filter_rows(rows, "claimed")] == ["a.one"]
    assert [r["key"] for r in filter_rows(rows, "unclaimed")] == ["a.two"]
    # by derivability
    assert [r["key"] for r in filter_rows(rows, "derivable")] == ["a.one"]
    # terms AND together
    assert filter_rows(rows, "claimed, underivable") == []
    with _pytest.raises(ValueError) as e:
        filter_rows(rows, "nope")
    assert "choose from" in str(e.value)


def test_mcp_audit_filter(tmp_path):
    import sys

    from mathema.interfaces.mcp import tools
    env_dir = tmp_path
    pkg = env_dir / "fpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent("""
        def clean(x: float) -> float:
            return 2.0 * x

        def loopy(xs: list) -> float:
            out = []
            for v in xs:
                out.append(v)
            return len(out) * 1.0
        """))
    sys.path.insert(0, str(env_dir))
    try:
        out = tools.audit_targets(["fpkg"], root=str(env_dir),
                                  cols=["key", "blocker"],
                                  filter="limitation")
        keys = [r[0] for r in out["rows"]]
        assert any("loopy" in k for k in keys)
        assert not any("clean" in k for k in keys)
        bad = tools.audit_targets(["fpkg"], root=str(env_dir),
                                  filter="wrong-term")
        assert "error" in bad and "known_filters" in bad
    finally:
        sys.path.remove(str(env_dir))
        for m in [m for m in sys.modules if m.startswith("fpkg")]:
            del sys.modules[m]


def test_filter_columnar_matching_scoped_and_any_column():
    from mathema.audit import filter_rows
    rows = [
        {"key": "a.mutual_info", "span": "1:9p", "claimed": True,
         "n_claims": 2, "pure": False, "unconditional": False, "derivable": False, "purity_reason": "branch",
         "blocked_report": None, "complexity": None, "typing": None,
         "global_vars": [], "unresolved": [], "test_covered": None,
         "docs": None, "concepts": []},
        {"key": "a.pearson", "span": "10:19p", "claimed": False,
         "n_claims": 0, "pure": True, "unconditional": True, "derivable": True, "purity_reason": None,
         "blocked_report": None, "complexity": None, "typing": None,
         "global_vars": [], "unresolved": [], "test_covered": None,
         "docs": None, "concepts": []},
    ]
    # scoped to one column
    assert [r["key"] for r in filter_rows(rows, "key~mutual")] == \
        ["a.mutual_info"]
    # any column
    assert [r["key"] for r in filter_rows(rows, "~pearson")] == \
        ["a.pearson"]
    # mixes with semantic terms (AND)
    assert filter_rows(rows, "claimed, key~pearson") == []
    # unknown column named loudly
    import pytest as _pytest
    with _pytest.raises(ValueError) as e:
        filter_rows(rows, "nope~x")
    assert "col~text" in str(e.value)


def test_filter_same_dimension_terms_or_together():
    # "actionable,limitation" means EITHER; a pure AND would make
    # every same-dimension pair a guaranteed-empty query that reads
    # like a confident answer; it is also how "everything except N/A"
    # is spelled, the exact query a claims pass wants
    from mathema.audit import filter_rows
    rows = [
        {"key": "a.one", "claimed": True, "pure": True, "unconditional": True, "derivable": True,
         "blocked_report": None},
        {"key": "a.two", "claimed": False, "pure": False, "unconditional": False, "derivable": False,
         "blocked_report": {"liftable": False, "blocker": "loop",
                            "constructs": [], "line": 1,
                            "code": "loop:not-a-fold"}},
    ]
    both = filter_rows(rows, "claimed,unclaimed")
    assert [r["key"] for r in both] == ["a.one", "a.two"]
    either = filter_rows(rows, "derivable,underivable")
    assert [r["key"] for r in either] == ["a.one", "a.two"]
    # dimensions still AND across
    assert [r["key"] for r in filter_rows(rows, "claimed,underivable,derivable")] \
        == ["a.one"]


def test_filter_empty_match_text_errors():
    # a truncated "~" or "col~" must never read as a successful
    # keep-everything query
    import pytest as _pytest

    from mathema.audit import filter_rows
    rows = [{"key": "a.one", "claimed": True, "pure": True, "unconditional": True, "derivable": True,
             "blocked_report": None}]
    for bad in ("~", "blocker~"):
        with _pytest.raises(ValueError) as e:
            filter_rows(rows, bad)
        assert "empty match text" in str(e.value)


def test_filter_references_pull_in_their_analyses():
    # an empty result must mean "nothing matched", never "never
    # looked": a columnar filter term forces its column's analysis to
    # be computed even when no output column shows it, and a bare
    # ~text term (any column) forces everything
    from mathema.audit import AUDIT_ANALYSES, exclude_for_cols
    only_key = exclude_for_cols(["key"])
    assert only_key == AUDIT_ANALYSES
    assert "complexity" not in exclude_for_cols(["key"], filters="cx~24")
    assert "scope" not in exclude_for_cols(["key"],
                                           filters="global_vars~R_CLIP")
    assert "docs" not in exclude_for_cols(["key"], filters="doc_quality~18")
    # a semantic term reads derivability facts
    assert "derivable" not in exclude_for_cols(["key"], filters="actionable")
    # ~text matches ANY column: nothing can be skipped
    assert exclude_for_cols(["key"], filters="~measures") == frozenset()


def test_every_compact_column_reaches_its_own_analysis():
    # the docsync regression: selecting a column must never exclude
    # the analysis that produces it, null for a column the caller
    # explicitly asked for is the sharpest possible violation of the
    # null rule
    from mathema.audit import COMPACT_COLUMNS, exclude_for_cols, _COL_ANALYSES
    for col, analysis in _COL_ANALYSES.items():
        assert col in COMPACT_COLUMNS, col
        assert analysis not in exclude_for_cols(["key", col]), col


def test_blocker_hint_carries_the_remedy_in_the_row():
    # reason_code was never called by an agent that had read a skill
    # telling it to: the code arrives inside a payload already being
    # read, and a second call to decode it loses the thread. The hint
    # rides along when asked for, never by default.
    from mathema.audit import COMPACT_DEFAULT_COLS, audit_rows, compact_audit

    assert "blocker_hint" not in COMPACT_DEFAULT_COLS
    assert "blocker_unlock" not in COMPACT_DEFAULT_COLS

    rows = audit_rows(["mathema.identity"], root=".")
    out = compact_audit(rows, ["key", "blocker", "blocker_hint",
                               "blocker_unlock"])
    blocked = [r for r in out["rows"] if r[1]]
    assert blocked, "the fixture module has underivable functions"
    for _key, code, hint, unlock in blocked:
        assert hint, f"{code} carries no hint"
        assert unlock in ("actionable", "limitation", "N/A")
    # a derivable row is computed-and-empty, never null
    from mathema.reason_codes import CODE_TABLE
    assert any(r[1] in CODE_TABLE or ":" in r[1] for r in blocked)


def test_claims_vs_floor_and_the_underclaimed_filter():
    # an aggregate can look healthy while the functions carrying the
    # risk are the unevidenced ones; this is the view that shows it
    from mathema.audit import audit_rows, compact_audit, filter_rows

    rows = audit_rows(["mathema.identity"], root=".")
    out = compact_audit(rows, ["key", "claims_vs_floor"])
    for _key, pair in out["rows"]:
        assert isinstance(pair, list) and len(pair) == 2
        actual, floor = pair
        assert actual <= floor or actual > floor   # both numbers present

    under = filter_rows(rows, "underclaimed")
    assert all(r["n_claims"] < r["claim_floor"] for r in under)
    # a function that meets its floor is not underclaimed
    for r in rows:
        if r["claim_floor"] and r["n_claims"] >= r["claim_floor"]:
            assert r not in under


def test_the_span_column_is_named_for_what_it_is():
    # `lines` read like a line count or a display range; it is a
    # ready-made sed address. It also collided with verify's own
    # `lines`, which is report prose, same name, adjacent tools,
    # unrelated meanings. Clean break: `span` here, `report` there.
    import re

    import pytest as _pytest

    from mathema.audit import (COMPACT_COLUMNS, COMPACT_DEFAULT_COLS,
                               audit_rows, compact_audit)
    assert "span" in COMPACT_DEFAULT_COLS and "lines" not in COMPACT_DEFAULT_COLS
    assert "lines" not in COMPACT_COLUMNS

    rows = audit_rows(["mathema.identity"], root=".",
                      exclude=frozenset({"derivable", "complexity", "typing",
                                         "scope", "tested", "docs", "docsync"}))
    out = compact_audit(rows, ["key", "span"])
    for _key, span in out["rows"]:
        assert re.fullmatch(r"\d+:\d+p", span), span

    # the old name is gone, not aliased; asking for it is an error
    with _pytest.raises(ValueError, match="unknown column"):
        compact_audit(rows, ["key", "lines"])
