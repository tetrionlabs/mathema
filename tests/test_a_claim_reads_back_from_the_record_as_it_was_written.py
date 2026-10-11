# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim written to the verified store reads back as the same claim.

`verify` writes each claim's canonical text into its record, and every
later run reads that text back: to decide whether the author changed
the claim (its identity against the authored text) and, when the
author did, to check the recorded version in its place. So a stored
statement has to read back to the same canonical text, the same
identity as the claim it records, and the same verdict.

A `let` binding is where this is easiest to lose. `let c be [a, b]`
binds a constant, which has no hole, and `let axis be 1` binds a
single value. A record written by mathema 0.6.0 spelled a constant
with its type and the hole class (`let rho be [0.01, 0.99]:float|missing`),
which today reads as a constant admitting a hole: a misspecified claim
that the author never wrote, checked in place of the one they did."""
import os
import re
import subprocess
import sys
import textwrap

import pytest
import yaml

import mathema
from mathema import sync
from mathema.conjecture import claim
from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON
from mathema.spec import (_declared_conjecture, canonical_claim_text, declare,
                          entry_claims, load_verified, record,
                          save_verified_entry)
from mathema.types import Mat

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MOD = '''
import math


def linfoot(mi: float) -> float:
    """Linfoot's informational coefficient of correlation."""
    if mi <= 0:
        return 0.0
    return math.sqrt(1.0 - math.exp(-2.0 * mi))


def scale(x: float, axis: int) -> float:
    """x scaled by an integer factor."""
    return x * axis
'''

_CLAIMS = """
rpkg.mod.linfoot:
  claims:
    - name: gaussian_calibration
      statement: "let rho be [0.01, 0.99], f(-log(1 - rho^2)/2) == rho"
rpkg.mod.scale:
  claims:
    - name: axis_one
      statement: "let axis be 1, for x in [0, 1], f(x, axis) >= 0"
"""

#: what mathema 0.6.0 wrote for each claim above
_WRITTEN_BY_0_6_0 = {
    ("rpkg.mod.linfoot", "gaussian_calibration"):
        "let rho be [0.01, 0.99]:float|missing, f(-log(1 - rho^2)/2) = rho",
    ("rpkg.mod.scale", "axis_one"):
        "let axis be [1.0, 1.0]:float|missing, "
        "for x in [0.0, 1.0]:float|missing, f(x, axis) >= 0",
}


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


def _verify(tmp_path, env):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _rows(tmp_path, key):
    path = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    entry = yaml.safe_load(path.read_text())[key]
    return {c.get("name"): c for c in entry["claims"]}


def _as_written_by_0_6_0(tmp_path):
    """Rewrite each record's authored rows (and their float companions)
    to the statement 0.6.0 wrote, restamping the integrity checksum, so
    the store is what a 0.6.0 run left behind."""
    for (key, name), statement in _WRITTEN_BY_0_6_0.items():
        path = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
        entry = yaml.safe_load(path.read_text())[key]
        for row in entry["claims"]:
            if row.get("name") in (name, f"{name}[float]"):
                row["statement"] = statement
        save_verified_entry(key, entry, root=str(tmp_path))


@pytest.mark.needs_full_proof_budget
def test_a_let_constant_recorded_by_0_6_0_reads_back_as_the_claim_written(tmp_path):
    env = _project(tmp_path)
    first = _verify(tmp_path, env)
    assert first.returncode == 0, first.stdout + first.stderr
    _as_written_by_0_6_0(tmp_path)
    for _ in range(2):
        run = _verify(tmp_path, env)
        assert run.returncode == 0, run.stdout + run.stderr
        assert "re-authored" not in run.stdout
    for key, name in _WRITTEN_BY_0_6_0:
        row = _rows(tmp_path, key)[name]
        assert row["verdict"] in ("proven", "holds"), row
        assert "mathema.pending_supersession" not in (row.get("meta") or {})


def scale(x: float, axis: int) -> float:
    """x scaled by an integer factor."""
    return x * axis


def test_a_let_constant_is_written_as_its_value():
    cj = claim("let axis be 1, for x in [0, 1], f(x, axis) >= 0")
    assert canonical_claim_text(cj).startswith("let axis be 1, ")
    assert canonical_claim_text(claim("let k be 2.5, f(k) >= 0")) \
        == "let k be 2.5, f(k) >= 0"


def test_a_point_constant_recorded_by_0_6_1_keeps_its_identity():
    """0.6.1 wrote `let axis be 1` as the interval `[1.0, 1.0]`, which
    holds the one value 1: it is the same claim, not a re-authored one."""
    authored = {"name": "axis_one",
                "statement": "let axis be 1, for x in [0, 1], f(x, axis) >= 0"}
    row = {"name": "axis_one", "verdict": "holds",
           "statement": "let axis be [1.0, 1.0], for x in [0.0, 1.0] : float|missing, "
                        "f(x, axis) >= 0"}
    assert sync._claim_identity(authored, scale) == sync._row_identity(row, scale)



@pytest.mark.parametrize("law", ["let b be R^n, f(b) >= 0",
                                 "let c be [0, 1]|absent, f(c) >= 0",
                                 "let c be [0, 1]^n, f(c) >= 0"])
def test_a_constant_admits_no_hole_it_was_not_written_with(law):
    """`check` passes a claim through its declared form; a vector
    constant, or one that admits only absence, comes back without a hole."""
    original = claim(law)
    (restored,) = entry_claims({"claims": [declare(original)]})
    assert canonical_claim_text(restored) == canonical_claim_text(original)
    assert "missing" not in canonical_claim_text(restored)


def square(A: Mat("n", "n")):
    """The matrix itself."""
    return A


@pytest.mark.needs_full_proof_budget
def test_a_vector_constant_is_checked_as_written():
    law = "let b be R^n, assuming det(A) != 0, A @ solve(A, b) ~= b"
    rec = mathema.check(square, claims=[claim(law, name="solves")])
    (p,) = [p for p in rec.probes if p.name == "solves"]
    assert p.verdict == "proven", p.note

# --- every lexicon row and docs claim through the store --------------------

def _store_round_trip(fn, key, laws, root):
    """Intent:
        Adjudicate `laws` (name -> claim text) against `fn`, write the
        record the way `verify` does, read it back from disk, and return
        `[(name, problem)]` for each claim whose stored statement does
        not read back to the same canonical text, the same identity or
        the same verdict.
    """
    authored = [{"name": n, "statement": t} for n, t in laws.items()]
    rec = mathema.check(fn, claims=[claim(t, name=n) for n, t in laws.items()])
    first = {p.name: p.verdict for p in rec.probes}
    record(rec, key=key, root=root, claims=authored, fn=fn)
    entry = load_verified(root)[key]["entry"]
    rows = {r.get("name"): r for r in entry["claims"]}
    problems = []
    for a in authored:
        row = rows.get(a["name"])
        if row is None or not row.get("statement"):
            continue
        stored = row["statement"]
        again = canonical_claim_text(sync._completed(_declared_conjecture(
            {"statement": stored, "domain": row.get("domain")}), fn))
        want = canonical_claim_text(sync._completed(claim(a["statement"]), fn))
        if again != want:
            problems.append((a["name"], f"text {stored!r} reads back as {again!r}, "
                                        f"not {want!r}"))
        if sync._claim_identity(a, fn) != sync._row_identity(row, fn):
            problems.append((a["name"], f"identity: authored {a['statement']!r} "
                                        f"is not the stored {stored!r}"))
    conflicts = [c for c in sync.claim_conflicts(fn, {"claims": authored}, entry)
                 if c["kind"] == "supersession"]
    # the recorded version of every claim, as `verify` checks it in place
    # of a re-authored one
    rebuilt = sync.apply_verified_wins(
        [dict(a) for a in authored],
        [{"kind": "supersession", "claim": a["name"]} for a in authored], entry)
    again = mathema.check(fn, claims=[_declared_conjecture(r) for r in rebuilt])
    for p in again.probes:
        if p.name in laws and p.verdict != first[p.name]:
            problems.append((p.name, f"verdict {first[p.name]} -> {p.verdict} "
                                     f"read back from {rows[p.name]['statement']!r}"))
    problems += [(c["claim"], f"read back as re-authored: {c['verified']!r}")
                 for c in conflicts]
    return problems


def _uses_let(law):
    return re.search(r"\blet\b", law) is not None


@pytest.mark.needs_full_proof_budget
def test_every_lexicon_let_row_reads_back_from_the_store(tmp_path):
    problems = []
    for fn_name, (fn, keys) in EXAMPLE_FUNCTIONS.items():
        laws = {k: LEXICON[k] for k in keys if _uses_let(LEXICON[k])}
        if laws:
            problems += _store_round_trip(fn, f"lexicon.{fn_name}", laws,
                                          str(tmp_path))
    assert not problems, "\n".join(f"{k}: {why}" for k, why in problems)


def test_every_lexicon_row_reads_back_from_the_store_as_written(tmp_path):
    """Every row, its statement written as the record writes it (completed
    by its example function when it has one) and read back from disk."""
    example = {k: fn for fn, keys in EXAMPLE_FUNCTIONS.values() for k in keys}
    rows = [{"name": key, "verdict": "holds",
             "statement": canonical_claim_text(
                 sync._completed(claim(law), example.get(key)))}
            for key, law in LEXICON.items()]
    save_verified_entry("lexicon.rows", {"claims": rows}, root=str(tmp_path))
    stored = load_verified(str(tmp_path))["lexicon.rows"]["entry"]["claims"]
    problems = []
    for row in stored:
        fn = example.get(row["name"])
        again = canonical_claim_text(sync._completed(claim(row["statement"]), fn))
        if again != row["statement"]:
            problems.append(f"{row['name']}: {row['statement']!r} reads back as {again!r}")
        if sync._claim_identity({"statement": LEXICON[row["name"]]}, fn) \
                != sync._row_identity(row, fn):
            problems.append(f"{row['name']}: identity of {row['statement']!r} moved")
    assert not problems, "\n".join(problems)


def _docs_let_verdicts():
    """Every `verdicts` example in the docs with a claim that uses
    `let`, as (id, example, part index)."""
    sys.path.insert(0, os.path.join(REPO, "tests"))
    from test_docs_outputs import _all_examples
    out = []
    for ident, ex in _all_examples():
        for i, part in enumerate(ex["parts"]):
            if part["role"] == "verdicts" and re.search(r"\blet\b", part["body"]):
                out.append(pytest.param(ex, i, id=f"{ident}#{i}"))
    return out


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("example,index", _docs_let_verdicts())
def test_every_docs_let_claim_reads_back_from_the_store(example, index, tmp_path,
                                                        monkeypatch):
    from test_docs_outputs import _Driver
    for name in ("XDG_CONFIG_HOME", "MATHEMA_FAST_TIMEOUT",
                 "MATHEMA_EXTENSIVE_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    driver = _Driver(str(tmp_path))
    for part in example["parts"][:index]:
        if part["role"] in ("file", "run"):
            driver.run_part(part, silent=True)
    part = example["parts"][index]
    fn = driver._target(part["options"]["fn"])
    laws = {}
    for i, ln in enumerate(part["body"].splitlines()):
        text = ln.partition("  #")[0].strip()
        if text and re.search(r"\blet\b", text):
            laws[f"docs_{i}"] = text
    problems = _store_round_trip(fn, "docs.example", laws, str(tmp_path))
    assert not problems, "\n".join(f"{laws[k]}: {why}" for k, why in problems)
