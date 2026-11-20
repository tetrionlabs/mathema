# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The second review of the canonical statement text and crash
isolation records work, each reproduction as a test with its outcome.

- A moved key keeps its rename remedy after an earlier key's release
  move.
- Stored text an earlier release wrote for two claims is reported as
  ambiguous in one direction and checked again in the other; no verdict
  carries across unchecked.
- A record keeping a row mathema could not rewrite stays stale.
- After a crashed key's record is put back, whatever stopped the run,
  a read of the store in the same run scope matches the disk.
- A claim mathema cannot store fails its key.
- Over a seeded sample of claim texts, no edited claim whose old stored
  text an earlier release could have written is taken as a release move.
"""
import contextlib
import importlib
import itertools
import json
import random
import shutil
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema import _run_scope, _timeout, spec
from mathema import verify as _verify

_PACKAGE = "revpkg"

_MOD = '''
def tag(s: str, a: str = "", b: str = "") -> int:
    """One when b is "s"."""
    return int(b == "s")


def stored(x: str, body: str = "", t: str = "") -> int:
    """The length of t."""
    return len(t)
'''

_DOUBLE = '''
def double(x: float) -> float:
    """Doubles.

    Claims:
        nonneg_on_unit [probe]: for x in [0, 5], f(x) >= 0
    """
    return 2.0 * x
'''

TWO = "for s in {\"a\"}, f(s, '}\"', 's') == 1"
ONE = "for s in {\"a\"}, f(s, '}\"\", \"s') == 1"
STORED = "for s in {\"a\"}, f(s, '}\"\", \"s') = 1"
UNSTORABLE = "for x in {\"a\"}, f(x, '}\"', t='s') == 1"


def _forget():
    for name in [m for m in sys.modules
                 if m == _PACKAGE or m.startswith(_PACKAGE + ".")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / _PACKAGE
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def _claims(root, by_key):
    (root / "claims" / "r.claims.yaml").write_text(yaml.safe_dump(
        {k: {"claims": [{"name": n, "statement": s} for n, s in v.items()]}
         for k, v in by_key.items()}))


def _row(root, key, name):
    entry = yaml.safe_load((root / ".mathema" / "verified"
                            / f"{key}.yaml").read_text())[key]
    return {r["name"]: r for r in entry["claims"]}[name]


def _why(out):
    return {r["key"]: r["why"] for r in out.keys}


def _legacy(root):
    from mathema._scan import legacy_quoting
    from mathema.verify import verify_project
    with legacy_quoting():
        return verify_project(root=str(root))


TAG = f"{_PACKAGE}.mod.tag"
STORED_KEY = f"{_PACKAGE}.mod.stored"


def test_a_moved_key_keeps_its_remedy_after_a_release_move(project):
    from mathema.verify import verify_project
    old, new = f"{_PACKAGE}.old.double", f"{_PACKAGE}.other.double"
    (project / _PACKAGE / "old.py").write_text(textwrap.dedent(_DOUBLE))
    _claims(project, {TAG: {"c": TWO}, old: {}})
    _legacy(project)
    _claims(project, {TAG: {"c": TWO}})
    (project / _PACKAGE / "old.py").write_text("")
    (project / _PACKAGE / "other.py").write_text(textwrap.dedent(_DOUBLE))
    shutil.rmtree(project / _PACKAGE / "__pycache__", ignore_errors=True)
    _forget()
    out = verify_project(root=str(project), all=True)
    assert {r["key"]: r for r in out.keys}[old].get("moved_to") == [new]
    assert any(f"mathema accept {new} --as reconciled --from {old}" in ln
               for ln in out.lines), out.lines


def test_an_edit_to_the_other_reading_is_ambiguous(project):
    from mathema.verify import verify_project
    _claims(project, {TAG: {"c": ONE}})
    _legacy(project)
    assert _row(project, TAG, "c")["statement"] == STORED
    _claims(project, {TAG: {"c": TWO}})
    out = verify_project(root=str(project))
    assert any("ambiguous" in ln and STORED in ln for ln in out.lines), out.lines
    assert _row(project, TAG, "c")["verdict"] == "proven"


def test_an_edit_onto_the_stored_reading_is_checked_again(project):
    from mathema.verify import verify_project
    _claims(project, {TAG: {"c": TWO}})
    _legacy(project)
    assert _row(project, TAG, "c")["verdict"] == "proven"
    _claims(project, {TAG: {"c": ONE}})
    out = verify_project(root=str(project))
    assert _why(out)[TAG] != "fresh"
    assert _row(project, TAG, "c")["verdict"] == "falsified"


def test_a_kept_row_stays_stale(project, monkeypatch):
    from mathema import grammar
    from mathema.verify import verify_project
    _claims(project, {STORED_KEY: {"two_literals": UNSTORABLE,
                                   "plain": 'for x in {"a"}, f(x, t="ab") == 2'}})
    verify_project(root=str(project))
    monkeypatch.setattr(grammar, "_double_quoted", grammar._legacy_double_quoted)
    verify_project(root=str(project), all=True)
    assert _why(verify_project(root=str(project)))[STORED_KEY] != "fresh"


def test_an_unstorable_claim_fails_its_key(project, monkeypatch):
    from mathema import grammar
    from mathema.verify import verify_project
    _claims(project, {STORED_KEY: {"two_literals": UNSTORABLE}})
    verify_project(root=str(project))
    monkeypatch.setattr(grammar, "_double_quoted", grammar._legacy_double_quoted)
    out = verify_project(root=str(project), all=True)
    row = {r["key"]: r for r in out.keys}[STORED_KEY]
    assert row["passed"] is False
    assert {c["claim"]: c for c in row["claims"]}["two_literals"]["verdict"] \
        == "unchecked"


@pytest.mark.parametrize("exc", [RuntimeError("injected"), MemoryError(),
                                 KeyboardInterrupt(),
                                 _timeout._WallClockExpired()])
def test_the_store_matches_the_disk_after_a_restore(project, monkeypatch, exc):
    from mathema.verify import verify_project
    _claims(project, {TAG: {"c": TWO}})
    verify_project(root=str(project))
    path = project / ".mathema" / "verified" / f"{TAG}.yaml"
    before = path.read_bytes()
    _claims(project, {TAG: {"c": TWO, "d": "for s in {\"a\"}, f(s) >= 0"}})
    real = _verify._carry_recorded_verdicts

    def carry(probes, written, key):
        real(probes, written, key)
        spec.load_verified(str(project))
        raise exc
    monkeypatch.setattr(_verify, "_carry_recorded_verdicts", carry)
    with _run_scope.run_scope():
        if isinstance(exc, RuntimeError):
            verify_project(root=str(project))
        else:
            with pytest.raises(type(exc)):
                verify_project(root=str(project))
        kept = spec.load_verified(str(project))[TAG]["entry"]
        assert kept == spec.read_verified_file(str(path))[0][TAG]
    assert path.read_bytes() == before


_VALUES = ["a", "s", 'a"b', "a'b", '}"', '}"", "s', "a\\b", "\t", '"', "'",
           "x, y", "-->"]


def _spellings(value):
    out = {repr(value), json.dumps(value)}
    if "'" not in value and "\\" not in value:
        out.add("'" + value + "'")
    if '"' not in value and "\\" not in value:
        out.add('"' + value + '"')
    return sorted(out)


def _sample(count, seed=20261120):
    literals = sorted({s for v in _VALUES for s in _spellings(v)})
    texts = [f"f(s, {a}, {b}) == 1" for a, b in itertools.product(literals, repeat=2)]
    texts += [f"f(s, {a}) == 1" for a in literals]
    picked = random.Random(seed).sample(texts, count)
    return sorted(set(picked) | {"f(s, '}\"', 's') == 1", "f(s, '}\"\", \"s') == 1"})


def _measure(s, a="", b=""):
    """Toy."""
    return 1


def test_no_edited_claim_is_taken_as_a_release_move():
    from mathema.conjecture import claim
    from mathema.sync import _legacy_renderings, claim_conflicts
    renderings = _legacy_renderings()
    canonical, written_as = {}, {}
    for text in _sample(60):
        try:
            canonical[text] = spec.fingerprint_text(claim(text))
        except Exception:
            continue
        for size in range(1, len(renderings) + 1):
            for chosen in itertools.combinations(sorted(renderings), size):
                with contextlib.ExitStack() as stack:
                    for name in chosen:
                        stack.enter_context(renderings[name]())
                    try:
                        stored = spec.canonical_claim_text(claim(text))
                    except Exception:
                        continue
                written_as.setdefault(stored, set()).add(text)
    adopted = []
    for recorded, identity in canonical.items():
        stored = spec.canonical_claim_text(claim(recorded))
        for edited in written_as.get(stored, ()):
            if canonical.get(edited) in (None, identity):
                continue
            row = {"name": "c", "statement": stored, "verdict": "proven",
                   "route": "probe"}
            kinds = [c["kind"] for c in claim_conflicts(
                _measure, {"claims": [{"name": "c", "statement": edited}]},
                {"claims": [row], "lineage": {"generated_by": "mathema 0.6.6.1"}})]
            if kinds == ["release-move"]:
                adopted.append((recorded, edited))
    assert adopted == [], adopted[:5]
