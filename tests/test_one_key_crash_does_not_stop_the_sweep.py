# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An unexpected exception while one key is adjudicated or written is
a failure of that key alone: the sweep reports it as a problem naming
the key and the exception, leaves that key's record exactly as it was,
goes on to every other key, and exits non-zero. An interrupt or the
wall-clock alarm still stops the whole run."""
import importlib
import sys

import pytest

import mathema
from mathema import _timeout

_BODY = '''\
def alpha(n: int) -> int:
    return 2 * n


def boom(n: int) -> int:
    return 3 * n


def gamma(n: int) -> int:
    return 4 * n
'''

_CLAIMS = '''\
crashpkg.alpha:
  claims:
    - name: twice
      statement: "for n in [0, 10] subset Z, f(n) == n + n"
crashpkg.boom:
  claims:
    - name: thrice
      statement: "for n in [0, 10] subset Z, f(n) == n + n + n"
crashpkg.gamma:
  claims:
    - name: four
      statement: "for n in [0, 10] subset Z, f(n) == 4 * n"
'''

KEYS = ("crashpkg.alpha", "crashpkg.boom", "crashpkg.gamma")


@pytest.fixture
def project(tmp_path, monkeypatch):
    sys.modules.pop("crashpkg", None)
    importlib.invalidate_caches()
    (tmp_path / "crashpkg.py").write_text(_BODY)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    sys.modules.pop("crashpkg", None)


def _record(root, key):
    return root / ".mathema" / "verified" / f"{key}.yaml"


def _raising_check(monkeypatch, exc):
    real = mathema.check

    def check(fn, *args, **kwargs):
        if getattr(fn, "__name__", "") == "boom":
            raise exc
        return real(fn, *args, **kwargs)
    monkeypatch.setattr(mathema, "check", check)


def _first_sweep(root):
    from mathema.verify import verify_project
    out = verify_project(root=str(root))
    assert not out.problems, out.problems
    before = _record(root, "crashpkg.boom").read_bytes()
    for key in ("crashpkg.alpha", "crashpkg.gamma"):
        _record(root, key).unlink()
    return before


def test_a_crashing_key_is_reported_and_its_neighbours_are_written(
        project, monkeypatch):
    from mathema.verify import verify_project
    before = _first_sweep(project)
    _raising_check(monkeypatch, RecursionError("maximum recursion depth exceeded"))
    out = verify_project(root=str(project), all=True)
    for key in ("crashpkg.alpha", "crashpkg.gamma"):
        assert _record(project, key).exists(), key
    assert _record(project, "crashpkg.boom").read_bytes() == before
    rows = {row["key"]: row for row in out.keys}
    assert rows["crashpkg.alpha"]["passed"] and rows["crashpkg.gamma"]["passed"]
    assert not rows["crashpkg.boom"]["passed"]
    (problem,) = [p for p in out.problems if "crashpkg.boom" in p]
    assert "RecursionError" in problem
    assert "maximum recursion depth exceeded" in problem
    assert any(line.startswith("FAIL crashpkg.boom") and "RecursionError" in line
               for line in out.lines), out.lines


def test_a_crashing_key_with_no_record_gets_none(project, monkeypatch):
    from mathema.verify import verify_project
    _raising_check(monkeypatch, ValueError("cannot be written"))
    out = verify_project(root=str(project))
    assert not _record(project, "crashpkg.boom").exists()
    assert _record(project, "crashpkg.alpha").exists()
    assert _record(project, "crashpkg.gamma").exists()
    assert any("crashpkg.boom" in p and "ValueError" in p for p in out.problems)


def test_the_cli_exits_non_zero_naming_the_crash(project, monkeypatch, capsys):
    from mathema.cli import main
    _raising_check(monkeypatch, RuntimeError("checker fell over"))
    code = main(["verify", "--root", str(project)])
    text = capsys.readouterr()
    assert code != 0
    assert "crashpkg.boom" in text.out + text.err
    assert "RuntimeError: checker fell over" in text.out + text.err


@pytest.mark.parametrize("exc", [KeyboardInterrupt(),
                                 _timeout._WallClockExpired()])
def test_an_interrupt_still_stops_the_sweep(project, monkeypatch, exc):
    from mathema.verify import verify_project
    _raising_check(monkeypatch, exc)
    with pytest.raises(type(exc)):
        verify_project(root=str(project))
