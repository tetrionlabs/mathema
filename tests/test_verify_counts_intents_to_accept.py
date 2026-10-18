# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema verify` ends with one line counting the stated intents that
wait on a person, by level, and the command that walks them. The line
is information: it never changes the exit code."""
import pytest

from tests.test_accept_intent_walks_every_stated_intent import (
    _accept, _forget, make_project)


@pytest.fixture(autouse=True)
def _own_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def project(tmp_path, monkeypatch, request):
    tag = "v" + "".join(ch for ch in request.node.name if ch.isalnum())[-10:]
    names = make_project(tmp_path, monkeypatch, tag)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        f"{names['t']}.mod.price:\n"
        "  claims:\n"
        "    - name: doubles\n"
        "      statement: 'for x in [0,5], f(x) == 2*x'\n")
    yield names
    _forget([names["t"], names["r"]])


def _verify(root, capsys):
    from mathema.cli import main
    code = main(["verify", "--root", root])
    return code, capsys.readouterr().out


_LINE = ("6 intents to accept (1 codebase, 2 packages, 1 module, "
         "2 functions): mathema accept --intent")


def test_verify_counts_the_intents_to_accept(project, capsys):
    code, out = _verify(project["root"], capsys)
    assert code == 0, out
    assert out.rstrip().splitlines()[-1] == _LINE


def test_the_line_goes_once_every_intent_is_accepted(project, monkeypatch,
                                                     capsys):
    _accept(["--intent", "--yes", "--root", project["root"]], "",
            monkeypatch, capsys)
    code, out = _verify(project["root"], capsys)
    assert code == 0, out
    assert "to accept" not in out


def test_the_line_never_changes_the_exit_code(project, capsys):
    import os
    claims = os.path.join(project["root"], "claims", "c.claims.yaml")
    with open(claims, "a") as fh:
        fh.write("    - name: wrong\n"
                 "      statement: 'for x in [0,5], f(x) == 3*x'\n")
    code, out = _verify(project["root"], capsys)
    assert code == 1, out
    assert out.rstrip().splitlines()[-1] == _LINE


def test_one_intent_reads_in_the_singular(tmp_path, monkeypatch, capsys):
    import mathema
    pkg = tmp_path / "vsingle"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text(
        'def f(x: float) -> float:\n    """Returns x."""\n    return x\n')
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "vsingle.m.f:\n  claims:\n"
        "    - name: same\n      statement: 'for x in [0,5], f(x) == x'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    _forget(["vsingle"])
    import importlib
    mathema.write_spec(importlib.import_module("vsingle.m").f,
                       root=str(tmp_path))
    try:
        code, out = _verify(str(tmp_path), capsys)
    finally:
        _forget(["vsingle"])
    assert code == 0, out
    assert out.rstrip().splitlines()[-1] == (
        "1 intent to accept (1 function): mathema accept --intent")
