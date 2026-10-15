# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The accept command printed under a falsified computation line names
that line, `<claim>[float]`, and running it as printed records the
discovery. The proven claim it belongs to is its own acceptance, so a
command naming the claim would be refused."""
import shlex

import pytest

pytest.importorskip("numpy")

import mathema  # noqa: E402

_MOD = ("def running_total(xs: list, y0: float) -> float:\n"
        "    total = y0\n"
        "    for v in xs:\n"
        "        total = v + total\n"
        "    return total\n")
_CLAIMS = ("ledger.running_total:\n  claims:\n    - name: shift\n"
           "      statement: \"for xs in [-1e16, 1e16]^2 \\\\ {missing}, y0 in {1}, "
           "f(xs, y0) == f(xs, 0) + y0\"\n")


def _project(tmp_path, monkeypatch):
    (tmp_path / "ledger.py").write_text(_MOD)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "ledger.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _accept_command(text: str) -> list:
    """The argv of the one `mathema accept ... --as discovery` command
    in `text`, the command being the last thing on its line."""
    commands = [line.split("run: ", 1)[1].strip() for line in text.splitlines()
                if "run: mathema accept" in line and "--as discovery" in line]
    assert len(commands) == 1, text
    return shlex.split(commands[0])


def test_verify_prints_an_accept_command_that_is_accepted(
        tmp_path, monkeypatch, capsys):
    from mathema.cli import main
    _project(tmp_path, monkeypatch)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    assert "shift[float] initially falsified" in printed, printed
    argv = _accept_command(printed)
    assert argv[:4] == ["mathema", "accept", "ledger.running_total",
                        "shift[float]"], argv
    assert main(argv[1:] + ["--yes", "--root", str(tmp_path)]) == 0, argv
    assert main(["verify", "--root", str(tmp_path)]) == 0, \
        capsys.readouterr().out


def test_the_record_prints_an_accept_command_that_is_accepted(
        tmp_path, monkeypatch, capsys):
    from mathema.cli import main
    _project(tmp_path, monkeypatch)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    capsys.readouterr()
    import ledger
    rec = mathema.check(ledger.running_total, claims=[mathema.claim(
        "for xs in [-1e16, 1e16]^2 \\ {missing}, y0 in {1}, "
        "f(xs, y0) == f(xs, 0) + y0",
        name="shift")])
    argv = _accept_command(repr(rec))
    assert argv[3] == "shift[float]", argv
    assert main(argv[1:] + ["--yes", "--root", str(tmp_path)]) == 0, argv
