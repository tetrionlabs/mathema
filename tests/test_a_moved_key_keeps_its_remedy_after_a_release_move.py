# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An orphan record whose function moved names the move and its rename
remedy when a key the same sweep adjudicates before it holds a claim
whose stored text an earlier release wrote (a release move)."""
import importlib
import shutil
import sys
import textwrap

import pytest
import yaml

OLD = "mvpkg.mod.double"
NEW = "mvpkg.other.double"

_DOUBLE = '''
def double(x: float) -> float:
    """Doubles.

    Claims:
        nonneg_on_unit [probe]: for x in [0, 5], f(x) >= 0
    """
    return 2.0 * x
'''

_ALPHA = '''
def alpha(n: int, a: str = "", b: str = "") -> int:
    return 2 * n
'''

_ALPHA_CLAIMS = {"mvpkg.aaa.alpha": {"claims": [
    {"name": "twice",
     "statement": "for n in [0, 10] subset Z, f(n, '}\"', 's') == n + n"}]}}


def _forget_package():
    for name in [m for m in sys.modules if m == "mvpkg" or m.startswith("mvpkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget_package()
    pkg = tmp_path / "mvpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_DOUBLE))
    (pkg / "aaa.py").write_text(textwrap.dedent(_ALPHA))
    (tmp_path / "claims").mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget_package()


def test_the_moved_remedy_survives_an_earlier_release_move(project):
    from mathema._scan import legacy_quoting
    from mathema.verify import verify_project
    claims = project / "claims" / "c.claims.yaml"
    claims.write_text(yaml.safe_dump({**_ALPHA_CLAIMS, OLD: {"claims": []}}))
    with legacy_quoting():
        first = verify_project(root=str(project))
    assert not first.problems, first.problems
    stored = yaml.safe_load((project / ".mathema" / "verified"
                             / "mvpkg.aaa.alpha.yaml").read_text())
    rows = {r["name"]: r for r in stored["mvpkg.aaa.alpha"]["claims"]}
    assert rows["twice"]["statement"] == "for n in [0, 10] : int, f(n, '}\"\", \"s') = 2*n"
    claims.write_text(yaml.safe_dump(_ALPHA_CLAIMS))
    (project / "mvpkg" / "mod.py").write_text("")
    (project / "mvpkg" / "other.py").write_text(textwrap.dedent(_DOUBLE))
    shutil.rmtree(project / "mvpkg" / "__pycache__", ignore_errors=True)
    _forget_package()
    out = verify_project(root=str(project), all=True)
    rows = {row["key"]: row for row in out.keys}
    assert not any("re-authored" in p for p in out.problems), out.problems
    assert rows[OLD]["why"] == "unresolvable"
    assert rows[OLD].get("moved_to") == [NEW], rows[OLD]
    remedy = f"mathema accept {NEW} --as reconciled --from {OLD}"
    assert any(remedy in line for line in out.lines), out.lines
