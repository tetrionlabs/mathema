# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""End to end: what mathema writes to the verified store, mathema must
read back. Every persisted claim statement is a law the claim grammar
parses (machine diagnostics carry no statement at all), the record
states the default tolerance in force, a re-verify of a store holding
machine rows neither crashes nor churns bytes, and a record this
version cannot parse fails per key with a named remedy while the sweep
continues."""
import os
import subprocess
import sys
import textwrap

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MOD = '''
_COUNT = 0


def double(x: float) -> float:
    """Doubles."""
    return 2.0 * x


def impure(x: float) -> float:
    """Count the call, then echo."""
    global _COUNT
    _COUNT = _COUNT + 1
    return float(x)
'''

_CLAIMS = """
rpkg.mod.double:
  claims:
    - name: doubles
      statement: 'for x in [0,5], f(x) == 2*x'
      route: derive
rpkg.mod.impure:
  claims:
    - name: echoes
      statement: 'for x in [0,5], f(x) == x'
      route: probe
"""


def _project(tmp_path):
    pkg = tmp_path / "rpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "r.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    return env


def _verify(tmp_path, env, *extra):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['verify', *{list(extra)!r}, "
         f"'--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _records(tmp_path):
    vdir = tmp_path / ".mathema" / "verified"
    out = {}
    for p in sorted(vdir.glob("*.yaml")):
        for key, entry in (yaml.safe_load(p.read_text()) or {}).items():
            out[key] = (p, entry)
    return out


def test_every_persisted_statement_is_a_law_or_absent(tmp_path):
    env = _project(tmp_path)
    _verify(tmp_path, env, "--lenient")
    from mathema.conjecture import claim
    recs = _records(tmp_path)
    assert recs, "verify wrote no records"
    for key, (_, entry) in recs.items():
        for row in entry.get("claims") or []:
            statement = row.get("statement") or ""
            if not statement or row.get("grammar", "mathema") != "mathema":
                continue
            # must round-trip through the claim grammar, loudly
            claim(statement, name=row.get("name"))


def test_record_states_the_default_tolerance(tmp_path):
    env = _project(tmp_path)
    _verify(tmp_path, env, "--lenient")
    for key, (_, entry) in _records(tmp_path).items():
        assert entry.get("tolerance") == 1e-9, key


def test_skip_reason_rides_note_not_statement(tmp_path):
    env = _project(tmp_path)
    _verify(tmp_path, env, "--lenient")
    _, entry = _records(tmp_path)["rpkg.mod.impure"]
    purity = next(r for r in entry["claims"] if r["name"] == "purity")
    assert not purity.get("statement")
    assert "algebraic probing" in (purity.get("note") or "")


def test_reverify_all_is_crash_free_and_byte_stable(tmp_path):
    env = _project(tmp_path)
    _verify(tmp_path, env, "--lenient")
    r2 = _verify(tmp_path, env, "--all", "--lenient")
    assert "Traceback" not in r2.stderr, r2.stderr
    snap = {k: p.read_text() for k, (p, _) in _records(tmp_path).items()}
    r3 = _verify(tmp_path, env, "--all", "--lenient")
    assert "Traceback" not in r3.stderr, r3.stderr
    for k, (p, _) in _records(tmp_path).items():
        assert p.read_text() == snap[k], f"{k} churned bytes on re-verify"


def test_unreadable_record_diagnoses_per_key_and_continues(tmp_path):
    env = _project(tmp_path)
    _verify(tmp_path, env, "--lenient")
    recs = _records(tmp_path)
    path, _ = recs["rpkg.mod.double"]
    doc = yaml.safe_load(path.read_text())
    doc["rpkg.mod.double"]["claims"].append(
        {"name": "mystery", "statement": "this is not a law",
         "verdict": "holds"})
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    r = _verify(tmp_path, env, "--all", "--lenient")
    assert "Traceback" not in r.stderr, r.stderr
    assert r.returncode == 1, (r.returncode, r.stdout)
    # the diagnosis names the key and the remedy, per key
    assert "rpkg.mod.double" in r.stdout and "rebuild" in r.stdout.lower()
    # and the sweep continued to the other key
    assert "rpkg.mod.impure" in r.stdout


def test_sweep_is_quiet_about_state_dependence(tmp_path):
    # analyze()'s state-outside warning is real signal on a single
    # function; a sweep prints it per stateful key (twice, even: the
    # freshness analyze and the battery's own) and drowns the report,
    # whose rows and gate lines already carry the same fact. verify
    # silences the category; a direct analyze still warns.
    pkg = tmp_path / "qpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "_SCALE = 2.0\n\n\n"
        "def scaled(x: float) -> float:\n"
        '    """Scale by the module constant."""\n'
        "    return x * _SCALE\n")
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "q.claims.yaml").write_text(
        "qpkg.mod.scaled:\n  claims:\n"
        "    - name: doubles\n"
        "      statement: 'for x in [0,5], f(x) == 2*x'\n"
        "      route: probe\n")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    r = _verify(tmp_path, env, "--lenient")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "state outside" not in r.stderr, r.stderr[:400]

    import pytest

    import mathema

    def leans_on_module_state(x: float) -> float:
        return x + _NOT_DEFINED_HERE          # noqa: F821

    with pytest.warns(UserWarning, match="state outside"):
        mathema.analyze(leans_on_module_state)


def test_targeted_verify_re_adjudicates_and_restamps(tmp_path):
    # the checksum warning told users to re-run `mathema verify <key>`,
    # but freshness short-circuited on an unchanged form hash, so the
    # remedy did nothing and the warning persisted; the only flag that
    # worked (--all) was never named, leaving `--as reconciled` (which
    # vouches without checking) as the apparent way out. A NAMED key
    # now always re-adjudicates.
    env = _project(tmp_path)
    _verify(tmp_path, env, "--lenient")
    path, entry = _records(tmp_path)["rpkg.mod.double"]
    doc = yaml.safe_load(path.read_text())
    doc["rpkg.mod.double"]["claims"].append(
        {"name": "planted", "statement": "for x in [0,5], f(x) >= 0",
         "verdict": "holds"})
    path.write_text(yaml.safe_dump(doc, sort_keys=False))

    r = _verify(tmp_path, env, "rpkg.mod.double", "--lenient")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "checksum no longer matches" in r.stdout
    # the remedy must not steer at reconciled, which vouches unchecked
    assert "reconciled" not in r.stdout
    # and it must actually adjudicate, not skip as fresh
    assert "0 adjudicated" not in r.stdout

    # having re-stamped, a second run is clean
    r2 = _verify(tmp_path, env, "rpkg.mod.double", "--lenient")
    assert "checksum no longer matches" not in r2.stdout, r2.stdout


def _mini(tmp_path, statement):
    pkg = tmp_path / "fpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "def keep(x: float) -> float:\n"
        '    """Absolute value."""\n'
        "    return abs(x)\n")
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "f.claims.yaml").write_text(
        "fpkg.mod.keep:\n  claims:\n"
        f"    - name: cand\n      statement: '{statement}'\n"
        "      route: probe\n")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    return env


def test_born_falsified_claim_teaches_the_cheap_experiment(tmp_path):
    # a claim that falsifies on its FIRST adjudication is a failed
    # authoring experiment, and it is permanent until a human signs it
    # off (membership never silently shrinks, by design). Nothing
    # taught the cheap path, so the report now names it once.
    env = _mini(tmp_path, "for x in [-5, 5], f(x) == x")
    r = _verify(tmp_path, env, "--lenient")
    assert "mathema check" in r.stdout, r.stdout
    assert "writes nothing" in r.stdout
    # and it names the exits a human actually has
    assert "--as discovery" in r.stdout

    # a SECOND run: the claim is no longer new, so the teaching line
    # does not repeat (that is a regression, not an experiment)
    r2 = _verify(tmp_path, env, "--all", "--lenient")
    assert "writes nothing" not in r2.stdout, r2.stdout


def test_root_is_found_upward_instead_of_scattering_a_second_store(tmp_path):
    # --root defaulted to ".", so running from a subdirectory created a
    # whole second .mathema/ there (a stray src/.mathema/index.yaml was
    # found in a real checkout). The root is now discovered upward.
    env = _project(tmp_path)
    _verify(tmp_path, env, "--lenient")
    assert (tmp_path / ".mathema").is_dir()
    sub = tmp_path / "rpkg"
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         "sys.exit(main(['verify', '--lenient']))"],
        cwd=str(sub), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (sub / ".mathema").exists(), "scattered a second store"
    assert "using project root" in r.stdout      # says which root it chose
    assert "rpkg.mod.double" in r.stdout         # and actually found it


def test_root_discovery_stays_inside_the_repository(tmp_path, monkeypatch):
    # a `.mathema/` ABOVE the enclosing git repository belongs to something
    # else (a parent project, a per-user config directory); the root is
    # this repository, never an ancestor outside it
    from mathema.cli import _resolve_root
    outer = tmp_path / "outer"
    (outer / ".mathema").mkdir(parents=True)
    repo = outer / "repo"
    (repo / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.chdir(repo / "src")
    assert os.path.realpath(_resolve_root(None)) == os.path.realpath(repo)


def test_root_discovery_never_takes_the_home_directory(tmp_path, monkeypatch):
    # outside any repository, the home directory's `.mathema/` is per-user
    # configuration, not a project store
    from mathema.cli import _resolve_root
    home = tmp_path / "home"
    (home / ".mathema").mkdir(parents=True)
    work = home / "work"
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert os.path.realpath(_resolve_root(None)) == os.path.realpath(work)


def test_explicit_root_is_taken_verbatim(tmp_path):
    # an explicit --root is an instruction, never second-guessed: it
    # still creates a store where the user pointed
    (tmp_path / "pkg").mkdir()
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         "sys.exit(main(['init', '--root', '.']))"],
        cwd=str(tmp_path / "pkg"), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "pkg" / ".mathema").exists()
    assert "using project root" not in r.stdout
