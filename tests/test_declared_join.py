# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The declared-layer join: hand-written claim files (the highest-
precedence authoring surface) reach every function-object entry point
through the one explicit IO boundary, `retrieve()`. `check()` itself
stays IO-free; `write_spec()`, the CLI check verb, and the MCP
adjudicate_target tool compose the join. Pinned because the gate counts
declared claims: a payload that silently loads none reports
`passed: True` beside falsified rows."""
import os
import sys
import textwrap


def _project(tmp_path, wrong_rhs="3*x"):
    pkg = tmp_path / "jpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent('''
        def double(x: float) -> float:
            """Doubles.

            Claims:
                halved: for x in [0,5], f(x)/2 == x
            """
            return 2.0 * x
        '''))
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "c.claims.yaml").write_text(textwrap.dedent(f"""
        jpkg.mod.double:
          claims:
            - name: doubles
              statement: 'for x in [0,5], f(x) == 2*x'
              route: derive
            - name: wrong
              statement: 'for x in [1,5], f(x) == {wrong_rhs}'
              route: derive
        """))
    sys.path.insert(0, str(tmp_path))
    return tmp_path


def _cleanup(tmp_path):
    sys.path.remove(str(tmp_path))
    for m in [m for m in sys.modules if m.startswith("jpkg")]:
        del sys.modules[m]


def test_retrieve_joins_file_and_function_surfaces(tmp_path):
    _project(tmp_path)
    try:
        import mathema
        from jpkg.mod import double
        entry = mathema.retrieve(double, str(tmp_path))
        names = {c["name"] for c in entry["claims"]}
        # file claims AND the docstring claim, one merged entry
        assert {"doubles", "wrong", "halved"} <= names
        # the key spelling works too
        by_key = mathema.retrieve("jpkg.mod.double", str(tmp_path))
        assert {c["name"] for c in by_key["claims"]} == names
    finally:
        _cleanup(tmp_path)


def test_check_is_io_free_but_adjudicates_a_retrieved_entry(tmp_path, monkeypatch):
    _project(tmp_path)
    try:
        import mathema
        from jpkg.mod import double
        entry = mathema.retrieve(double, str(tmp_path))
        # run check from an unrelated empty directory: with declared=
        # passed, the file claims are adjudicated anyway; without it,
        # they are absent; check reads no filesystem store
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        rec = mathema.check(double, claims=[], declared=entry)
        verdicts = {p.name: p.verdict for p in rec.probes}
        assert verdicts.get("doubles") == "proven"
        assert verdicts.get("wrong") == "falsified"
        bare = mathema.check(double, claims=[])
        assert "doubles" not in {p.name for p in bare.probes}
        assert "halved" in {p.name for p in bare.probes}   # travels with fn
    finally:
        _cleanup(tmp_path)


def test_call_site_claims_still_win_per_name(tmp_path):
    _project(tmp_path)
    try:
        import mathema
        from jpkg.mod import double
        entry = mathema.retrieve(double, str(tmp_path))
        override = mathema.claim("for x in [0,5], f(x) >= 0",
                                 name="wrong", route="derive")
        rec = mathema.check(double, claims=[override], declared=entry)
        verdicts = {p.name: p.verdict for p in rec.probes}
        assert verdicts.get("wrong") == "proven"   # the call-site version
    finally:
        _cleanup(tmp_path)


def test_write_spec_records_the_joined_set(tmp_path, monkeypatch):
    _project(tmp_path)
    try:
        import mathema
        from jpkg.mod import double
        monkeypatch.chdir(tmp_path)
        rec = mathema.write_spec(double, claims=[], root=str(tmp_path))
        assert rec.spec_path and os.path.exists(rec.spec_path)
        body = open(rec.spec_path).read()
        assert "doubles" in body and "wrong" in body and "halved" in body
    finally:
        _cleanup(tmp_path)


def test_mcp_adjudicate_target_gates_on_file_claims(tmp_path):
    _project(tmp_path)
    try:
        from mathema.interfaces.mcp.tools import adjudicate_target
        out = adjudicate_target("jpkg.mod.double", claims=[],
                             root=str(tmp_path))
        rows = {c["claim"]: c["verdict"] for c in out["claims"]}
        assert rows.get("doubles") == "proven"
        assert rows.get("wrong") == "falsified"
        assert out["passed"] is False          # the join makes the gate real
        assert out["counts"]["refuted"] >= 1
    finally:
        _cleanup(tmp_path)


def test_cli_check_joins_and_fails_on_a_falsified_file_claim(tmp_path):
    import subprocess
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _project(tmp_path)
    _cleanup(tmp_path)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([repo, str(tmp_path)]))
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         "sys.exit(main(['check', 'jpkg.mod', '--root', '.']))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert "1 falsified" in r.stdout, r.stdout
    assert r.returncode == 1, r.stdout + r.stderr
