# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An orphan record whose function moved names the move and its
rename remedy whatever other keys the same sweep adjudicates before
it."""
import importlib
import shutil
import sys
import textwrap

import pytest

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
def alpha(n: int) -> int:
    return 2 * n
'''

_ALPHA_CLAIMS = ("mvpkg.aaa.alpha:\n"
                 "  claims:\n"
                 "    - name: twice\n"
                 "      statement: 'for n in [0, 10] subset Z, f(n) == n + n'\n")


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


def test_the_moved_remedy_survives_an_earlier_adjudicated_key(project):
    from mathema.verify import verify_project
    claims = project / "claims" / "c.claims.yaml"
    claims.write_text(_ALPHA_CLAIMS + f"{OLD}:\n  claims: []\n")
    first = verify_project(root=str(project))
    assert not first.problems, first.problems
    claims.write_text(_ALPHA_CLAIMS)
    (project / "mvpkg" / "mod.py").write_text("")
    (project / "mvpkg" / "other.py").write_text(textwrap.dedent(_DOUBLE))
    shutil.rmtree(project / "mvpkg" / "__pycache__", ignore_errors=True)
    _forget_package()
    out = verify_project(root=str(project), all=True)
    rows = {row["key"]: row for row in out.keys}
    assert rows["mvpkg.aaa.alpha"]["why"] != "fresh"
    assert rows[OLD]["why"] == "unresolvable"
    assert rows[OLD].get("moved_to") == [NEW], rows[OLD]
    remedy = f"mathema accept {NEW} --as reconciled --from {OLD}"
    assert any(remedy in line for line in out.lines), out.lines
