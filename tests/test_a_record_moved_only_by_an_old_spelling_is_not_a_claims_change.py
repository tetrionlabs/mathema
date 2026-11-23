# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record re-recorded only because an earlier release spelled its
stored text another way is not a change to the claims.

The run's note says nothing the author wrote changed; the key's row
gives mathema's claim rules as the reason it was checked again, and the
record does not name `claims` among what invalidated it.
"""
import importlib
import subprocess
import sys
import textwrap

import pytest
import yaml

KEY = "spkg.mod.outside"

_MOD = '''
def outside(x: float, lo: float, hi: float) -> bool:
    """Whether x lies outside the open interval (lo, hi)."""
    return not (lo < x and x < hi)
'''

_CLAIM = ("for x in [0, 10], lo in [0, 3], hi in [7, 10], "
          "f(x, lo, hi) == (not (lo < x and x < hi))")


def _forget():
    for name in [m for m in sys.modules if m == "spkg" or m.startswith("spkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / "spkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "s.claims.yaml").write_text(yaml.safe_dump(
        {KEY: {"claims": [{"name": "outside", "statement": _CLAIM}]}}))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def test_an_old_negation_spelling_is_a_rules_change(project):
    from mathema._scan import legacy_not_parentheses
    from mathema.verify import verify_project
    with legacy_not_parentheses():
        verify_project(root=str(project))
    out = verify_project(root=str(project))
    assert any("negated relation is rewritten" in ln for ln in out.lines), out.lines
    assert {r["key"]: r["why"] for r in out.keys}[KEY] == "mathema's claim rules changed"
    entry = yaml.safe_load((project / ".mathema" / "verified"
                            / f"{KEY}.yaml").read_text())[KEY]
    assert "claims" not in (entry.get("meta") or {}).get("mathema.invalidated_by", [])
