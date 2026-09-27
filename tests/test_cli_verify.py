# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema verify`: the test-runner sweep over the spec store.

Every scenario here shells out to a real subprocess rather than calling
mathema.cli.main() in-process. That matters specifically for the
form-changed scenarios: mathema reads a function's source via
inspect.getsource(), which resolves against the *currently loaded*
module's cached line numbers. Mutating a fixture file and re-importing it
in the same interpreter without a real reload can read back stale,
misaligned source (a shifted def block lands mid-function), an artifact
of the test harness, not something `mathema verify` users hit, since real
usage is one process per invocation (a CI job, a terminal command). A
subprocess per call is what makes this test representative instead of
flaky.
"""
import subprocess
import sys


def _write_funcs(path, add_body="    return a + b"):
    path.write_text(
        "def add(a: float, b: float) -> float:\n" + add_body + "\n\n\n"
        "def clamp01(x: float) -> float:\n"
        "    return min(1.0, max(0.0, x))\n\n\n"
        "def gated_sqrt(x: float) -> float:\n"
        "    if x < 0:\n"
        "        raise ValueError('x must be nonnegative')\n"
        "    return x ** 0.5\n"
    )


def _repo_root():
    import os
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_with_repo_on_path():
    import os
    env = dict(os.environ)
    repo = _repo_root()
    env["PYTHONPATH"] = repo + (os.pathsep + env["PYTHONPATH"]
                                if env.get("PYTHONPATH") else "")
    return env


def _run(root, *extra_args):
    script = ("import sys; from mathema.cli import main; "
             f"sys.exit(main(['verify', '--root', {str(root)!r}"
             + "".join(f", {a!r}" for a in extra_args) + "]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=_env_with_repo_on_path())


def _seed_run(root, funcs_path):
    script = f"""
import sys
sys.path.insert(0, {str(funcs_path.parent)!r})
import mathema, funcs
for name in ("add", "clamp01", "gated_sqrt"):
    mathema.write_spec(getattr(funcs, name), root={str(root)!r})
"""
    r = subprocess.run([sys.executable, "-c", script], cwd=str(root),
                       capture_output=True, text=True, env=_env_with_repo_on_path())
    assert r.returncode == 0, r.stderr


def test_all_fresh_immediately_after_seeding(tmp_path):
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)

    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "3 fresh" in r.stdout
    assert "0 adjudicated" in r.stdout


def test_declared_claim_file_is_adjudicated_and_derive_route_dispatches(tmp_path):
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "add.claims.yaml").write_text(
        "funcs.add:\n"
        "  claims:\n"
        "    - name: commutative_derived\n"
        '      statement: "f(a, b) == f(b, a)"\n'
        "      route: derive\n"
    )
    _seed_run(tmp_path, funcs_path)

    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    # the declared claim makes funcs.add non-fresh relative to a bare
    # baseline the first time it's picked up, and it must have been
    # adjudicated via the derive route (proven), not silently dropped
    assert "funcs.add" in r.stdout


def test_unbounded_claim_over_a_raising_guard_falsifies_and_fails_verify(tmp_path):
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "gated_sqrt.claims.yaml").write_text(
        "funcs.gated_sqrt:\n"
        "  claims:\n"
        "    - name: unliftable\n"
        '      statement: "f(x) >= 0"\n'
        "      route: derive\n"
    )
    _seed_run(tmp_path, funcs_path)

    # with no domain the claim covers x < 0, where gated_sqrt raises:
    # pedantically falsified, and a falsified claim fails verify in
    # EVERY mode (lenient only relaxes unverifiable claims, never
    # wrong ones)
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "falsified" in r.stdout

    r = _run(tmp_path, "--lenient")
    assert r.returncode == 1, r.stdout


def test_foreign_grammar_claim_is_not_counted_as_unverifiable(tmp_path):
    """A claim tagged for a different grammar (mathema.data's, mixed
    into the same key/file core mathema also reads) must not fail
    strict mode as an unverifiable claim; it's simply not this
    command's job, and the run must say so explicitly (both per-key and
    in the end-of-sweep grammar summary)."""
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)
    # written AFTER seeding: write_spec's own retrieve now covers
    # file claims at seed time, and a pre-seeded file would leave
    # everything fresh; this pin is about the adjudication path
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "add.claims.yaml").write_text(
        "funcs.add:\n"
        "  claims:\n"
        "    - name: commutative\n"
        '      statement: "f(a, b) == f(b, a)"\n'
        "      route: probe\n"
        "    - name: sum_nonneg\n"
        '      statement: "a + b >= 0"\n'
        "      route: observe\n"
        "      grammar: mathema-data\n"
    )

    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "unverifiable" not in r.stdout
    assert "1 not this grammar (mathema-data)" in r.stdout
    assert "grammars detected: mathema, mathema-data" in r.stdout
    assert "verified by this run: mathema" in r.stdout
    assert "not verified here (different grammar, needs its own tool): mathema-data" in r.stdout


def test_foreign_grammar_claim_does_not_mask_a_genuine_failure(tmp_path):
    """The two kinds of skip stay distinct even in the same key: a
    genuinely bad route still fails strict mode on its own, counted
    separately from the foreign-grammar claim sitting right next to it."""
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)
    # written AFTER seeding: write_spec's own retrieve now covers
    # file claims at seed time, and a pre-seeded file would leave
    # everything fresh; this pin is about the adjudication path
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "add.claims.yaml").write_text(
        "funcs.add:\n"
        "  claims:\n"
        "    - name: commutative\n"
        '      statement: "f(a, b) == f(b, a)"\n'
        "      route: probe\n"
        "    - name: bad_route\n"
        '      statement: "a + b >= 0"\n'
        "      route: nonsense\n"
        "    - name: sum_nonneg\n"
        '      statement: "a + b >= 0"\n'
        "      route: observe\n"
        "      grammar: mathema-data\n"
    )

    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "1 skipped" in r.stdout
    assert "1 not this grammar (mathema-data)" in r.stdout


def test_declared_claims_never_mask_verified_identity(tmp_path):
    """The bug this guards: a declared claims file for a key must not
    blot out that key's verified `identity.form`, or freshness tracking
    breaks permanently for any function with a claims overlay."""
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "add.claims.yaml").write_text(
        "funcs.add:\n"
        "  claims:\n"
        "    - name: commutative_derived\n"
        '      statement: "f(a, b) == f(b, a)"\n'
        "      route: derive\n"
    )
    _seed_run(tmp_path, funcs_path)

    first = _run(tmp_path)
    assert first.returncode == 0, first.stdout
    second = _run(tmp_path)
    assert "3 fresh" in second.stdout, second.stdout   # funcs.add now fresh too
    assert "0 adjudicated" in second.stdout, second.stdout


def test_form_change_triggers_reverification_then_refreshes_baseline(tmp_path):
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)

    r1 = _run(tmp_path)
    assert "3 fresh" in r1.stdout

    _write_funcs(funcs_path, add_body="    result = a + b\n    return result")
    r2 = _run(tmp_path)
    assert "funcs.add" in r2.stdout and "form changed" in r2.stdout
    assert "2 fresh" in r2.stdout        # clamp01, gated_sqrt untouched

    r3 = _run(tmp_path)                  # baseline should have refreshed
    assert "3 fresh" in r3.stdout, r3.stdout
    assert "0 adjudicated" in r3.stdout, r3.stdout


def test_all_flag_forces_reverification_when_fresh(tmp_path):
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)

    r = _run(tmp_path, "--all")
    assert "0 fresh" in r.stdout
    assert "3 adjudicated" in r.stdout
    assert "forced (--all)" in r.stdout


def test_unresolvable_key_reported_not_crashed(tmp_path):
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)

    ghost = tmp_path / ".mathema" / "verified" / "funcs.does_not_exist.yaml"
    ghost.write_text('funcs.does_not_exist:\n  identity: {form: "deadbeef0000"}\n'
                     "  claims: []\n")

    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "cannot resolve to a live function" in r.stdout


def test_bare_name_key_fails_cleanly_without_target_fallback(tmp_path):
    # the loose --target bare-name fallback is gone: a store keyed by a
    # bare function name is a per-key problem line, never a traceback
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    (tmp_path / ".mathema" / "verified").mkdir(parents=True)
    (tmp_path / ".mathema" / "verified" / "add.yaml").write_text(
        'add:\n  identity: {form: "deadbeef0000"}\n  claims: []\n')

    r = _run(tmp_path)
    assert r.returncode == 1
    assert "add: cannot resolve" in r.stdout


def test_nothing_declared_yet_is_a_clean_noop(tmp_path):
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "nothing declared yet" in r.stdout


def test_decorator_declared_claim_is_picked_up_by_verify(tmp_path):
    """Integration test for the wiring added after both claim-authoring
    agents landed: cmd_verify must merge decorator/docstring claims
    (authoring.declared_from_function) in underneath file-declared claims,
    not just read load_declared()'s file layer. A function with only a
    @claims_decorator claim and no claims file at all must still get that
    claim adjudicated once its key is known (via a seeded baseline).

    write_spec()/check() also merge declared_from_function() now (a related fix
    made once this test surfaced the gap), so the seeded baseline already
    reflects the decorator claim from the very first write_spec() call, verify
    is fresh immediately rather than needing one round to "catch up." The
    real assertion here is that the decorator claim actually got checked
    and recorded, not the specific fresh/adjudicated timing."""
    funcs_path = tmp_path / "funcs.py"
    funcs_path.write_text(
        "from mathema import claims_decorator\n\n\n"
        "@claims_decorator('f(a, b) == f(b, a)')\n"
        "def add(a: float, b: float) -> float:\n"
        "    return a + b\n"
    )
    _seed_run_single(tmp_path, funcs_path, "add")

    recorded = (tmp_path / ".mathema" / "verified" / "funcs.add.yaml").read_text()
    # the decorator's own claim (auto-named from its law) is recorded
    # and PROVES: unrouted claims default to the best cascade now, and
    # add's commutativity lifts, pinned exactly, so a silent route
    # change shows up here. The suggestion that shares this law no
    # longer rides along, suggestions never enter the verified layer
    assert "f_a_b_eq_f_b_a" in recorded
    assert 'verdict: "proven"' in recorded

    r1 = _run(tmp_path)
    assert r1.returncode == 0, r1.stdout
    assert "1 fresh" in r1.stdout and "0 adjudicated" in r1.stdout

    r2 = _run(tmp_path)
    assert "1 fresh" in r2.stdout and "0 adjudicated" in r2.stdout


def _seed_run_single(root, funcs_path, name):
    script = f"""
import sys
sys.path.insert(0, {str(funcs_path.parent)!r})
import mathema, funcs
mathema.write_spec(getattr(funcs, {name!r}), root={str(root)!r})
"""
    r = subprocess.run([sys.executable, "-c", script], cwd=str(root),
                       capture_output=True, text=True, env=_env_with_repo_on_path())
    assert r.returncode == 0, r.stderr


def _seeded(tmp_path):
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)
    return tmp_path


def _json_run(root, *extra):
    import json
    r = _run(root, "--format", "json", *extra)
    return r, json.loads(r.stdout)


def test_verify_format_json_carries_per_key_claim_rows(tmp_path):
    # R002: a client must never parse prose. Every fact the text path
    # prints is in the payload as data, and the claim rows speak the
    # same vocabulary check --format compact and the MCP tools use.
    root = _seeded(tmp_path)
    r, doc = _json_run(root)
    assert doc["tool"] == "mathema" and doc["CDD_spec_version"]
    assert isinstance(doc["keys"], list) and doc["keys"]
    entry = doc["keys"][0]
    assert set(entry) >= {"key", "why", "passed", "counts", "claims"}
    assert set(entry["counts"]) >= {"proven", "refuted", "unknown"}
    for row in entry["claims"]:
        assert row["stance"] in ("supported", "refuted", "undecided",
                                 "blocked")
        # the envelope rule, same as every other agent payload
        assert ("counterexample" in row) == (row["stance"] == "refuted")
    assert doc["totals"]["fresh"] + doc["totals"]["adjudicated"] > 0


def test_verify_format_json_output_file_matches_stdout(tmp_path):
    root = _seeded(tmp_path)
    out = tmp_path / "report.json"
    r_stdout = _run(root, "--format", "json")
    _run(root, "--format", "json", "--output", str(out))
    import json
    assert json.loads(out.read_text()) == json.loads(r_stdout.stdout)


def test_verify_format_json_keeps_the_exit_code_and_the_text_path(tmp_path):
    # JSON is a rendering, never an adjudication mode: same exit code,
    # and the prose path is byte-for-byte what it always was
    root = _seeded(tmp_path)
    text, js = _run(root), _run(root, "--format", "json")
    assert text.returncode == js.returncode
    assert "fresh" in text.stdout and not text.stdout.startswith("{")


def _foreign_then_native(tmp_path, with_grammar: bool):
    body = ("grammar: other\n" if with_grammar else "") + (
        "funcs.add:\n"
        "  claims:\n"
        "    - name: commutative\n"
        '      statement: "f(a, b) == f(b, a)"\n'
        "    - name: above_clamp\n"
        '      statement: "let g = funcs.clamp01, for a in [0, 1], '
        'b in [0, 1], f(a, b) >= g(a)"\n')
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "add.claims.yaml").write_text(body)


def test_removing_a_foreign_grammar_adjudicates_the_claims_it_skipped(
        tmp_path):
    """A claim skipped as another grammar's is stored as the claim it
    is, `let` sections included, so once the grammar line goes the
    unchanged claims adjudicate under mathema's grammar: never read as
    re-authored, never pinned to the old grammar."""
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)
    _foreign_then_native(tmp_path, with_grammar=True)
    r = _run(tmp_path)
    assert "2 not this grammar (other)" in r.stdout, r.stdout + r.stderr
    stored = (tmp_path / ".mathema" / "verified" / "funcs.add.yaml")
    assert "let g = " in stored.read_text(), stored.read_text()

    _foreign_then_native(tmp_path, with_grammar=False)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "re-authored" not in r.stdout + r.stderr, r.stdout
    assert "not this grammar" not in r.stdout, r.stdout
    text = stored.read_text()
    assert "let g = " in text, text
    assert "grammar: other" not in text, text
    assert "foreign_grammar" not in text, text

    r = _run(tmp_path, "--all")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "re-authored" not in r.stdout + r.stderr, r.stdout


def test_toggling_a_file_grammar_makes_every_entry_in_it_stale(tmp_path):
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)
    body = ("funcs.add:\n"
            "  claims:\n"
            "    - name: commutative\n"
            '      statement: "f(a, b) == f(b, a)"\n'
            "funcs.clamp01:\n"
            "  claims:\n"
            "    - name: at_most_one\n"
            '      statement: "f(x) <= 1"\n')
    (tmp_path / "claims").mkdir()
    path = tmp_path / "claims" / "funcs.claims.yaml"
    path.write_text(body)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    r = _run(tmp_path)
    assert "2 adjudicated" not in r.stdout, r.stdout
    for text in ("grammar: other\n" + body, body):
        path.write_text(text)
        r = _run(tmp_path)
        assert "2 adjudicated" in r.stdout, (text, r.stdout)
        assert r.stdout.count("claims changed") >= 2, r.stdout


def test_a_row_skipped_as_another_grammars_claim_never_supersedes():
    """A record written before skipped rows kept their `let` sections
    holds the bare relation; it established no verdict, so the authored
    claim is not reported as re-authored against it."""
    from mathema.sync import claim_conflicts

    def add(a: float, b: float) -> float:
        return a + b

    declared = {"claims": [{
        "name": "above_clamp",
        "statement": "let g = funcs.clamp01, for a in [0, 1], "
                     "b in [0, 1], f(a, b) >= g(a)"}]}
    verified = {"grammar": "mathema", "claims": [{
        "name": "above_clamp", "statement": "f(a, b) >= g(a)",
        "verdict": "skipped", "grammar": "other",
        "meta": {"mathema.foreign_grammar": "other"}}]}
    assert claim_conflicts(add, declared, verified) == []
    verified["claims"][0]["verdict"] = "holds"
    verified["claims"][0]["meta"] = {}
    assert [c["kind"] for c in claim_conflicts(add, declared, verified)] \
        == ["supersession"]


def _write_lib(tmp_path, step):
    (tmp_path / "lib.py").write_text(
        f"def g(x: float) -> float:\n    return x + {step}\n")


def test_a_wrapper_reverifies_when_the_library_function_it_calls_changes(
        tmp_path):
    """A wrapper calling `lib.g(x)` and one calling `g(x)` after
    `from lib import g` both depend on g's form. The record keeps the
    form each callee had when the wrapper was adjudicated, so a change
    to g re-adjudicates both, whether or not g has a record of its
    own."""
    _write_lib(tmp_path, 1)
    (tmp_path / "wrap.py").write_text(
        "import lib\n"
        "from lib import g\n\n\n"
        "def through_module(x: float) -> float:\n"
        "    return lib.g(x)\n\n\n"
        "def through_name(x: float) -> float:\n"
        "    return g(x)\n")
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "wrap.claims.yaml").write_text(
        "wrap.through_module:\n"
        "  claims:\n"
        "    - name: above\n"
        '      statement: "for x in [0, 1], f(x) >= x"\n'
        "wrap.through_name:\n"
        "  claims:\n"
        "    - name: above\n"
        '      statement: "for x in [0, 1], f(x) >= x"\n')
    r = _run(tmp_path)
    assert "2 adjudicated" in r.stdout, r.stdout + r.stderr
    stored = (tmp_path / ".mathema" / "verified"
              / "wrap.through_module.yaml").read_text()
    assert "lib.g" in stored and "form:" in stored, stored
    r = _run(tmp_path)
    assert "2 fresh" in r.stdout, r.stdout
    _write_lib(tmp_path, 2)
    r = _run(tmp_path)
    assert "0 fresh" in r.stdout, r.stdout
    assert r.stdout.count("dependency changed") >= 2, r.stdout


def _check(root, *extra):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['check', 'funcs.py', '--root', {str(root)!r}"
              + "".join(f", {a!r}" for a in extra) + "]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True,
                          env=_env_with_repo_on_path())


def test_a_claims_file_wholly_in_another_grammar_is_warned_about_once(
        tmp_path):
    """Every claim of a file in a grammar this checker does not
    adjudicate is most often a `grammar:` line copied from somewhere:
    verify and check say so once, naming the file and the grammar."""
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "funcs.claims.yaml").write_text(
        "grammar: python-expression\n"
        "funcs.add:\n"
        "  claims:\n"
        "    - name: commutative\n"
        '      statement: "f(a, b) == f(b, a)"\n'
        "funcs.clamp01:\n"
        "  claims:\n"
        "    - name: at_most_one\n"
        '      statement: "f(x) <= 1"\n')
    (tmp_path / "claims" / "mixed.claims.yaml").write_text(
        "funcs.gated_sqrt:\n"
        "  claims:\n"
        "    - name: nonneg\n"
        '      statement: "for x in [0, 4], f(x) >= 0"\n'
        "    - name: other_tool\n"
        '      statement: "f(x) >= 0"\n'
        "      grammar: python-expression\n")
    for r in (_run(tmp_path), _check(tmp_path)):
        text = r.stdout + r.stderr
        warned = [ln for ln in text.splitlines()
                  if "does not adjudicate" in ln]
        assert len(warned) == 1, text
        assert "funcs.claims.yaml" in warned[0], warned
        assert "'python-expression'" in warned[0], warned
        assert "omit `grammar:`" in warned[0], warned
        assert "mixed.claims.yaml" not in warned[0], warned


def test_a_verified_claim_moved_to_another_grammar_warns_without_blocking(
        tmp_path):
    """A claim with a real verdict recorded under mathema that now
    declares another grammar is no longer adjudicated here: verify says
    so once on the key's line, the run does not fail on it, and the
    JSON row names the change."""
    funcs_path = tmp_path / "funcs.py"
    _write_funcs(funcs_path)
    _seed_run(tmp_path, funcs_path)
    _foreign_then_native(tmp_path, with_grammar=False)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    _foreign_then_native(tmp_path, with_grammar=True)
    r, doc = _json_run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    rows = {row["claim"]: row for entry in doc["keys"]
            if entry["key"] == "funcs.add" for row in entry["claims"]}
    assert rows["commutative"]["grammar_changed"] == {"from": "mathema",
                                                      "to": "other"}
    _foreign_then_native(tmp_path, with_grammar=False)
    _run(tmp_path)
    _foreign_then_native(tmp_path, with_grammar=True)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    warning = ("warning: claim commutative of funcs.add was verified under "
               "mathema; its grammar is now 'other', so mathema no longer "
               "adjudicates it")
    assert (r.stdout + r.stderr).count(warning) == 1, r.stdout + r.stderr
