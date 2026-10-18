# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema accept --intent` with no key walks every stated intent that
waits on a person: the codebase README, each package (its `__init__.py`
docstring, else its README.md), each module, and each function with a
record, top down. Each one is shown and answered y/n/e/q; `--yes`
prints the whole list and then accepts every item on it. Every write
still passes the human check and records who accepted it.
"""
import importlib
import io
import sys
import textwrap

import pytest
import yaml

from mathema import auth

_README = "# demo\n\n## Intent\n\nA toy pricing project.\n"

_INIT = '''"""Pricing helpers.

Intent:
    Prices things for the toy project.
"""
'''

_MOD = '''"""Price rules.

Intent:
    Doubles a price.
"""


def price(x: float) -> float:
    """Prices the thing.

    Intent:
        Twice x, always.
    """
    if x < 0:
        raise ValueError("negative")
    return 2.0 * x
'''

_CORE = '''def half(x: float) -> float:
    """Halves x."""
    return x / 2.0
'''


@pytest.fixture(autouse=True)
def _own_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _forget(prefixes):
    for name in [m for m in sys.modules
                 if any(m == p or m.startswith(p + ".") for p in prefixes)]:
        del sys.modules[name]


def make_project(tmp_path, monkeypatch, tag: str) -> dict:
    """A README with an Intent section, a package stating its intent in
    `__init__.py` (with a module and a function stating theirs), and a
    package stating its intent only in a README.md (with a function whose
    summary line is its intent). Both functions have a record."""
    import mathema
    t, r = f"t{tag}", f"r{tag}"
    (tmp_path / "README.md").write_text(_README)
    (tmp_path / t).mkdir()
    (tmp_path / t / "__init__.py").write_text(_INIT)
    (tmp_path / t / "mod.py").write_text(_MOD)
    (tmp_path / r).mkdir()
    (tmp_path / r / "__init__.py").write_text("")
    (tmp_path / r / "README.md").write_text(
        f"# {r}\n\nIntent:\n    Rounds things.\n")
    (tmp_path / r / "core.py").write_text(_CORE)
    monkeypatch.syspath_prepend(str(tmp_path))
    _forget([t, r])
    mod = importlib.import_module(f"{t}.mod")
    core = importlib.import_module(f"{r}.core")
    mathema.write_spec(mod.price, root=str(tmp_path))
    mathema.write_spec(core.half, root=str(tmp_path))
    return {"t": t, "r": r, "root": str(tmp_path)}


@pytest.fixture
def project(tmp_path, monkeypatch, request):
    tag = "".join(ch for ch in request.node.name if ch.isalnum())[-12:]
    names = make_project(tmp_path, monkeypatch, tag)
    yield names
    _forget([names["t"], names["r"]])


def _accept(argv, stdin: str, monkeypatch, capsys):
    from mathema.cli import main
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = main(["accept", *argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def _scope_meta(root) -> dict:
    import os
    path = os.path.join(root, ".mathema", "meta", "intent.yaml")
    if not os.path.exists(path):
        return {}
    return yaml.safe_load(open(path)) or {}


def _record(root, key) -> dict:
    import os
    path = os.path.join(root, ".mathema", "verified", f"{key}.yaml")
    return yaml.safe_load(open(path))[key]


def _keys(p):
    return ["__project__", p["r"], p["t"], f"{p['t']}.mod",
            f"{p['r']}.core.half", f"{p['t']}.mod.price"]


def test_every_stated_intent_is_listed_top_down(project):
    from mathema.acceptance import pending_intents
    items = pending_intents(project["root"])
    assert [i["key"] for i in items] == _keys(project)
    assert [i["level"] for i in items] == [
        "codebase", "package", "package", "module", "function", "function"]
    assert all(i["status"] == "new" for i in items)
    by_key = {i["key"]: i for i in items}
    assert by_key["__project__"]["text"] == "A toy pricing project."
    price = by_key[f"{project['t']}.mod.price"]
    assert price["text"] == "Twice x, always."
    assert price["signature"] == "(x: float) -> float"
    assert price["raises"] == ["ValueError"]


def test_a_package_states_its_intent_in_init_or_in_its_readme(project):
    from mathema.acceptance import pending_intents
    by_key = {i["key"]: i for i in pending_intents(project["root"])}
    from_init = by_key[project["t"]]
    assert from_init["text"] == "Prices things for the toy project."
    assert from_init["file"].endswith("__init__.py")
    from_readme = by_key[project["r"]]
    assert from_readme["text"] == "Rounds things."
    assert from_readme["file"].endswith("README.md")
    # a module with no docstring of its own is not listed again under
    # its package's README text
    assert f"{project['r']}.core" not in by_key


def test_answering_yes_writes_each_acceptance_and_who(project, monkeypatch,
                                                      capsys):
    code, out, err = _accept(
        ["--intent", "--by", "lovelace", "--root", project["root"]],
        "y\n" * 6, monkeypatch, capsys)
    assert code == 0, out + err
    meta = _scope_meta(project["root"])
    for key in ("__project__", project["r"], project["t"],
                f"{project['t']}.mod"):
        assert meta[key]["accepted"]["by"] == "lovelace", key
    for key in (f"{project['r']}.core.half", f"{project['t']}.mod.price"):
        entry = _record(project["root"], key)
        assert entry["intent_accepted"]["by"] == "lovelace", key
        assert entry["meta"]["mathema.intent_provenance"] == "documented"
    # what was shown before each answer
    assert "A toy pricing project." in out
    assert "signature: (x: float) -> float" in out
    assert "raises: ValueError" in out
    from mathema.acceptance import pending_intents
    assert pending_intents(project["root"]) == []


def test_no_skips_an_intent_and_quit_stops_the_walk(project, monkeypatch,
                                                    capsys):
    code, out, err = _accept(
        ["--intent", "--by", "lovelace", "--root", project["root"]],
        "n\ny\nq\n", monkeypatch, capsys)
    assert code == 0, out + err
    meta = _scope_meta(project["root"])
    assert list(meta) == [project["r"]]
    for key in (f"{project['r']}.core.half", f"{project['t']}.mod.price"):
        assert "intent_accepted" not in _record(project["root"], key)
    from mathema.acceptance import pending_intents
    left = [i["key"] for i in pending_intents(project["root"])]
    assert left == [k for k in _keys(project) if k != project["r"]]


def test_yes_flag_prints_the_list_then_accepts_each(project, monkeypatch,
                                                    capsys):
    code, out, err = _accept(
        ["--intent", "--yes", "--by", "lovelace", "--root",
         project["root"]], "", monkeypatch, capsys)
    assert code == 0, out + err
    # the whole list is printed before the first write
    listed = out.index(f"{project['t']}.mod.price")
    assert listed < out.index("written")
    assert out.count("written") == 6
    meta = _scope_meta(project["root"])
    assert set(meta) == {"__project__", project["r"], project["t"],
                         f"{project['t']}.mod"}
    entry = _record(project["root"], f"{project['t']}.mod.price")
    assert entry["intent_accepted"]["by"] == "lovelace"


def test_a_stale_function_intent_shows_what_changed(project, monkeypatch,
                                                    capsys):
    import mathema
    key = f"{project['t']}.mod.price"
    _accept(["--intent", "--yes", "--by", "lovelace", "--root",
             project["root"]], "", monkeypatch, capsys)
    src = textwrap.dedent('''
        def price(x: float) -> float:
            """Prices the thing.

            Intent:
                Twice x, always.
            """
            if x < 0:
                raise ArithmeticError("negative")
            return 2.0 * x
        ''')
    import os
    path = os.path.join(project["root"], project["t"], "mod.py")
    with open(path, "w") as fh:
        fh.write(_MOD.split("\n\n\ndef")[0] + "\n\n" + src)
    _forget([f"{project['t']}.mod"])
    mod = importlib.import_module(f"{project['t']}.mod")
    mathema.write_spec(mod.price, root=project["root"])
    assert _record(project["root"], key)["intent_accepted"]["stale"] is True

    from mathema.acceptance import pending_intents
    (item,) = pending_intents(project["root"])
    assert item["key"] == key and item["status"] == "stale"
    assert item["changed"] == ["raised exceptions"]

    code, out, err = _accept(
        ["--intent", "--by", "babbage", "--root", project["root"]],
        "y\n", monkeypatch, capsys)
    assert code == 0, out + err
    assert "stale" in out and "raised exceptions" in out
    assert "raises: ArithmeticError" in out
    entry = _record(project["root"], key)
    assert not entry["intent_accepted"].get("stale")
    assert entry["intent_accepted"]["by"] == "babbage"
    assert entry["intent_accepted"]["raises"] == ["ArithmeticError"]


def test_json_lists_pending_intents_without_writing(project, monkeypatch,
                                                    capsys):
    import json
    for argv in (["--intent"], ["--intent", "--yes"]):
        code, out, err = _accept(
            [*argv, "--format", "json", "--root", project["root"]], "",
            monkeypatch, capsys)
        assert code == 0, out + err
        body = json.loads(out)
        assert [i["key"] for i in body["intents"]] == _keys(project)
        assert body["applied"] is False
    assert _scope_meta(project["root"]) == {}
    assert "intent_accepted" not in _record(
        project["root"], f"{project['t']}.mod.price")


def test_nothing_is_written_without_the_human_check(project, monkeypatch,
                                                    capsys):
    auth.set_pin("4321")
    monkeypatch.setattr(auth, "_tty_available", lambda: False)
    for argv, stdin in ((["--intent", "--yes"], ""),
                        (["--intent"], "y\n" * 6)):
        code, out, err = _accept([*argv, "--root", project["root"]], stdin,
                                 monkeypatch, capsys)
        assert code == 1, out + err
        assert "human verification" in err
    assert _scope_meta(project["root"]) == {}
    for key in (f"{project['r']}.core.half", f"{project['t']}.mod.price"):
        assert "intent_accepted" not in _record(project["root"], key)


def test_the_pin_is_asked_for_each_acceptance(project, monkeypatch, capsys):
    import getpass
    info = auth.set_pin("4321")
    codes = ["4321"] * 6
    monkeypatch.setattr(auth, "_tty_available", lambda: True)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": codes.pop(0))
    code, out, err = _accept(
        ["--intent", "--yes", "--by", "lovelace", "--root",
         project["root"]], "", monkeypatch, capsys)
    assert code == 0, out + err
    assert codes == []
    meta = _scope_meta(project["root"])
    assert meta["__project__"]["accepted"]["verified_by"]["key"] == info["key"]
    entry = _record(project["root"], f"{project['t']}.mod.price")
    assert entry["intent_accepted"]["verified_by"]["key"] == info["key"]


def test_edit_opens_the_intent_and_reads_it_again(project, monkeypatch,
                                                  capsys, tmp_path):
    import os
    editor = tmp_path / "fake_editor.py"
    editor.write_text(textwrap.dedent('''
        import sys
        line, path = sys.argv[1], sys.argv[2]
        with open(sys.argv[3], "w") as log:
            log.write(line + " " + path)
        text = open(path).read()
        open(path, "w").write(text.replace("A toy pricing project.",
                                           "A small pricing project."))
        '''))
    log = tmp_path / "editor.log"
    monkeypatch.setenv("EDITOR", f"{sys.executable} {editor}")
    # the fake editor takes `+LINE PATH`, then a log path the test appends
    from mathema import cli
    real = cli._editor_command

    def with_log(path, line):
        return real(path, line) + [str(log)]
    monkeypatch.setattr(cli, "_editor_command", with_log)
    code, out, err = _accept(
        ["--intent", "--by", "lovelace", "--root", project["root"]],
        "e\ny\nq\n", monkeypatch, capsys)
    assert code == 0, out + err
    opened = log.read_text()
    assert opened == f"+3 {os.path.join(project['root'], 'README.md')}"
    meta = _scope_meta(project["root"])
    assert list(meta) == ["__project__"]
    assert meta["__project__"]["text"] == "A small pricing project."
    assert "A small pricing project." in out


def test_edit_without_an_editor_prints_where_the_intent_is(project,
                                                           monkeypatch,
                                                           capsys):
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    code, out, err = _accept(
        ["--intent", "--root", project["root"]], "n\nn\ne\nq\n",
        monkeypatch, capsys)
    assert code == 0, out + err
    assert f"{project['t']}/__init__.py:3; edit it there" in out
    assert _scope_meta(project["root"]) == {}


def test_nothing_pending_says_so(tmp_path, monkeypatch, capsys):
    code, out, err = _accept(["--intent", "--root", str(tmp_path)], "",
                             monkeypatch, capsys)
    assert code == 0, out + err
    assert "no intents to accept" in out
