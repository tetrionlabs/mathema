# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The MCP `pending_decisions` queue lists a stated intent that no one
has accepted yet, at every level, as an `intent-acceptance-new` row
beside the `intent-acceptance-stale` rows for a function whose accepted
intent moved on. The rows only report: accepting stays a person's act
in the CLI."""
import pytest

from tests.test_accept_intent_walks_every_stated_intent import (
    _accept, _forget, make_project)


@pytest.fixture(autouse=True)
def _own_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def project(tmp_path, monkeypatch, request):
    tag = "m" + "".join(ch for ch in request.node.name if ch.isalnum())[-10:]
    names = make_project(tmp_path, monkeypatch, tag)
    yield names
    _forget([names["t"], names["r"]])


def _intent_rows(root):
    from mathema.interfaces.mcp.tools import pending_decisions
    out = pending_decisions(root=root)
    assert out["cols"] == ["key", "claim", "kind", "detail"]
    return [r for r in out["rows"] if r[2].startswith("intent-")]


def test_new_intents_are_listed_at_every_level(project):
    rows = _intent_rows(project["root"])
    assert [r[0] for r in rows] == [
        "__project__", project["r"], project["t"], f"{project['t']}.mod",
        f"{project['r']}.core.half", f"{project['t']}.mod.price"]
    assert {r[2] for r in rows} == {"intent-acceptance-new"}
    assert all(r[1] is None for r in rows)
    price = rows[-1]
    assert price[3] == ("function intent stated, never accepted; a human "
                        f"runs `mathema accept {project['t']}.mod.price "
                        "--intent`, or `mathema accept --intent` for all")


def test_accepted_intents_leave_the_queue(project, monkeypatch, capsys):
    _accept(["--intent", "--yes", "--root", project["root"]], "",
            monkeypatch, capsys)
    assert _intent_rows(project["root"]) == []


def test_a_stale_function_intent_keeps_its_own_row(project, monkeypatch,
                                                   capsys):
    import importlib
    import os

    import mathema
    _accept(["--intent", "--yes", "--root", project["root"]], "",
            monkeypatch, capsys)
    path = os.path.join(project["root"], project["t"], "mod.py")
    with open(path) as fh:
        text = fh.read()
    with open(path, "w") as fh:
        fh.write(text.replace("ValueError", "ArithmeticError"))
    _forget([f"{project['t']}.mod"])
    mod = importlib.import_module(f"{project['t']}.mod")
    mathema.write_spec(mod.price, root=project["root"])
    rows = _intent_rows(project["root"])
    assert rows == [[f"{project['t']}.mod.price", None,
                     "intent-acceptance-stale",
                     "re-accept with `mathema accept --intent`"]]
