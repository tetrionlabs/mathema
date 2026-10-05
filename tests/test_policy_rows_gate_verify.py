# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A policy row mathema writes that the code contradicts, and a raise no
claim accounts for, are falsified claims: they fail `verify` and `check`
in every mode and are counted as falsified. The author's ways out are
the usual ones: change the word, change the code, or accept the row as
a discovery (with the corrected row, where there is a word to correct
to)."""
import textwrap

import pytest

from mathema.cli import main

_MOD = textwrap.dedent('''
    # SPDX-License-Identifier: BUSL-1.1
    # Copyright 2026 Tetrion Ltd
    import math
    from typing import Optional


    def clamp01(x: float) -> float:
        """Claims:
            unit: for x in R, 0 <= f(x) <= 1
        """
        return max(0.0, min(1.0, x))


    def root_opt(x: Optional[float]) -> float:
        """Claims:
            nonneg: for x in [0, 4], f(x) >= 0
        """
        return math.sqrt(x)
''')


@pytest.fixture()
def project(tmp_path, monkeypatch):
    (tmp_path / "pv.py").write_text(_MOD)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    import mathema
    import pv
    for fn in (pv.clamp01, pv.root_opt):
        mathema.write_spec(fn, root=str(tmp_path))
    return tmp_path


def _line(capsys, key):
    out = capsys.readouterr().out
    return next(ln for ln in out.splitlines() if f" {key}:" in ln)


def test_a_contradicted_default_fails_verify_and_is_counted(project, capsys):
    assert main(["verify", "--root", str(project), "pv.clamp01"]) == 1
    line = _line(capsys, "pv.clamp01")
    assert line.startswith("FAIL pv.clamp01:")
    assert "1 falsified" in line
    assert ("1 policy row to settle: missing[x], f drops a missing x (nan in, 1.0 out) "
            "where mathema's default says propagates") in line


def test_an_unaccounted_raise_fails_verify_in_lenient_mode_too(project, capsys):
    assert main(["verify", "--root", str(project), "--lenient", "pv.root_opt"]) == 1
    line = _line(capsys, "pv.root_opt")
    assert line.startswith("FAIL pv.root_opt:") and "1 falsified" in line


def test_the_remedy_names_the_discovery_route(project):
    import mathema
    import pv
    rec = mathema.check(pv.clamp01)
    (row,) = [p for p in rec.probes if p.name == "missing[x]"]
    assert row.meta["mathema.policy"]["next"].endswith(
        '(iii) to accept it as a discovery, run: mathema accept pv.clamp01 missing[x] --as '
        'discovery --corrected "missing(f, x) drops"')


def test_accepting_a_contradicted_default_as_a_discovery_settles_it(project, capsys):
    main(["verify", "--root", str(project), "pv.clamp01"])
    capsys.readouterr()
    assert main(["accept", "pv.clamp01", "missing[x]", "--as", "discovery",
                 "--corrected", "missing(f, x) drops", "--yes",
                 "--root", str(project)]) == 0
    capsys.readouterr()
    assert main(["verify", "--root", str(project), "pv.clamp01"]) == 0
    assert _line(capsys, "pv.clamp01").startswith("ok   pv.clamp01:")


def test_accepting_an_unaccounted_raise_as_a_discovery_retires_it(project, capsys):
    main(["verify", "--root", str(project), "pv.root_opt"])
    capsys.readouterr()
    assert main(["accept", "pv.root_opt", "absent[x]", "--as", "discovery", "--yes",
                 "--root", str(project)]) == 0
    capsys.readouterr()
    assert main(["verify", "--root", str(project), "pv.root_opt"]) == 0
    assert _line(capsys, "pv.root_opt").startswith("ok   pv.root_opt:")



def test_verify_after_write_names_the_contradicted_row(tmp_path, monkeypatch, capsys):
    (tmp_path / "pw.py").write_text(textwrap.dedent('''
        # SPDX-License-Identifier: BUSL-1.1
        # Copyright 2026 Tetrion Ltd


        def clamp(x: float) -> float:
            return max(0.0, min(1.0, x))
    '''))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "pw.claims.yaml").write_text(
        'pw.clamp:\n  claims:\n    - name: unit\n'
        '      statement: "for x in R, 0 <= f(x) <= 1"\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    assert main(["claims", "pw.clamp", "--write", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["verify", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    note = next(ln for ln in out.splitlines() if ln.startswith("note pw.clamp:"))
    assert note.startswith("note pw.clamp: missing[x] falsified on first adjudication; "
                           "f drops a missing x (nan in, 1.0 out)")
