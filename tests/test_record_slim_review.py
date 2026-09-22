# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The slimmed verified record (null/derivable fields omitted, stable
order, no re-verify churn), the single-key `verify`, the `init` git
scaffold, and the claim-level `review` delta."""
import os
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DOUBLE = """
def double(x: float) -> float:
    \"\"\"Doubles.\"\"\"
    return 2.0 * x
"""

_CLAIMS = """
spkg.mod.double:
  claims:
    - name: doubles
      statement: 'for x in [0,5], f(x) == 2*x'
      route: derive
    - name: nonneg
      statement: 'for x in [0,5], f(x) >= 0'
      route: derive
"""


def _project(tmp_path):
    pkg = tmp_path / "spkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_DOUBLE))
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "c.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), env=env, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=str(tmp_path), env=env,
                   check=True)
    return env


def _mathema(tmp_path, env, *args):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main([*{list(args)!r}, '--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _record(tmp_path):
    return (tmp_path / ".mathema" / "verified"
            / "spkg.mod.double.yaml").read_text()


def test_record_omits_null_and_derivable_fields(tmp_path):
    env = _project(tmp_path)
    _mathema(tmp_path, env, "verify")
    body = _record(tmp_path)
    # null/empty placeholders are gone
    assert "n: null" not in body and "counterexample: null" not in body
    assert 'note: ""' not in body and "tolerance: null" not in body
    # per-row grammar is dropped when it equals the record grammar
    assert body.count('grammar: "mathema"') == 1   # only the record header
    # rows are name-sorted (dependencies_current < doubles < nonneg)
    order = [ln.split('name: "')[1].split('"')[0]
             for ln in body.splitlines() if ln.strip().startswith('- name:')]
    assert order == sorted(order)


def test_reverify_leaves_record_byte_identical(tmp_path):
    env = _project(tmp_path)
    _mathema(tmp_path, env, "verify")
    first = _record(tmp_path)
    _mathema(tmp_path, env, "verify")
    assert _record(tmp_path) == first          # no lineage churn


def test_verify_single_key(tmp_path):
    env = _project(tmp_path)
    r = _mathema(tmp_path, env, "verify", "spkg.mod.double")
    assert r.returncode == 0 and "spkg.mod.double" in r.stdout
    # an unknown key is a clear error, not "nothing declared"
    r2 = _mathema(tmp_path, env, "verify", "spkg.mod.nope")
    assert r2.returncode == 2 and "no such key" in r2.stdout


def test_init_scaffolds_git_files(tmp_path):
    env = _project(tmp_path)
    r = _mathema(tmp_path, env, "init")
    assert r.returncode == 0
    assert (tmp_path / ".gitattributes").exists()
    assert "linguist-generated" in (tmp_path / ".gitattributes").read_text()
    gi = (tmp_path / ".mathema" / ".gitignore").read_text()
    assert "/declared/" in gi and "/issues/" in gi
    # idempotent
    r2 = _mathema(tmp_path, env, "init")
    assert "already in place" in r2.stdout


def test_review_reports_claim_deltas(tmp_path):
    env = _project(tmp_path)
    _mathema(tmp_path, env, "verify")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), env=env, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "baseline"], cwd=str(tmp_path), env=env,
                   check=True)
    # add a claim that falsifies, then re-verify
    (tmp_path / "claims" / "c.claims.yaml").write_text(textwrap.dedent(_CLAIMS)
        + "    - name: triples\n"
          "      statement: 'for x in [1,5], f(x) == 3*x'\n"
          "      route: best\n")
    _mathema(tmp_path, env, "verify")
    r = _mathema(tmp_path, env, "review", "HEAD")
    assert r.returncode == 0
    assert "triples" in r.stdout and "1 added" in r.stdout
    assert "newly falsified" in r.stdout
