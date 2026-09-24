# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exit-code contract, command by command: 0 ok, 1 claims failed or
refused, 2 a bad argument or a target that does not resolve (one clean
line on stderr, no traceback, nothing written), 130 interrupted."""
import pytest

from mathema.cli import main

_SOURCE = "def sq(x):\n    return x * x\n"
_CLAIMS = ("exitfix.sq:\n  claims:\n    - name: nonneg\n"
           '      statement: "for x in [0, 1], sq(x) >= 0"\n')


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "exitfix.py").write_text(_SOURCE)
    (tmp_path / "exitfix.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _bad(capsys, argv, *words):
    try:
        rc = main(argv)
    except SystemExit as e:
        rc = e.code
    captured = capsys.readouterr()
    assert rc == 2, captured.out + captured.err
    lines = captured.err.strip().splitlines()
    assert len(lines) == 1, captured.err
    assert "Traceback" not in captured.err
    for w in words:
        assert w in lines[0], lines[0]
    return captured


def _listing(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if "__pycache__" not in p.parts)


@pytest.mark.parametrize("verb", [["verify"], ["coverage"],
                                  ["check", "exitfix.py"]])
def test_a_root_that_does_not_exist_is_a_bad_argument(project, capsys,
                                                      verb):
    _bad(capsys, [*verb, "--root", str(project / "nowhere")], "--root",
         "nowhere")


def test_compendium_export_of_an_unknown_library_writes_nothing(project,
                                                                 capsys):
    main(["verify", "--root", str(project)])
    capsys.readouterr()
    before = _listing(project)
    _bad(capsys, ["compendium", "export", "nope", "--root", str(project)],
         "nope")
    assert _listing(project) == before


def test_init_with_an_unresolvable_target_writes_nothing(project, capsys):
    before = _listing(project)
    _bad(capsys, ["init", "nope.mod", "--root", str(project)], "nope.mod")
    assert _listing(project) == before


def test_badges_to_an_unwritable_dir_prints_no_badge(project, capsys):
    blocker = project / "blocker"
    blocker.write_text("a file, so no directory can be made under it")
    captured = _bad(capsys, ["badges", "--out", str(blocker / "out"),
                             "--root", str(project)], "blocker")
    assert captured.out == ""


def test_verify_of_a_recorded_key_that_no_longer_resolves(project, capsys):
    main(["verify", "--root", str(project)])
    capsys.readouterr()
    (project / "exitfix.claims.yaml").unlink()
    (project / "exitfix.py").write_text("def other(x):\n    return x\n")
    import sys
    sys.modules.pop("exitfix", None)
    rc = main(["verify", "exitfix.sq", "--root", str(project)])
    assert rc == 2, capsys.readouterr()


@pytest.mark.parametrize("scale", ["0", "-1", "nan"])
def test_trials_scale_outside_its_range_is_refused(project, capsys, scale):
    _bad(capsys, ["check", "exitfix.py", "--trials-scale", scale],
         "--trials-scale")


def test_describe_depth_below_zero_is_refused(project, capsys):
    _bad(capsys, ["describe", "exitfix.sq", "--depth", "-1"], "--depth")


@pytest.mark.parametrize("argv", [["verify", "--bogus"],
                                  ["check"],
                                  ["nosuchverb"]])
def test_an_argparse_error_is_one_line(project, capsys, argv):
    _bad(capsys, argv, "mathema")


@pytest.mark.parametrize("spec,word", [("x=nan:1", "NaN"),
                                       ("x=1:nan", "NaN"),
                                       ("x=5:1", "inverted"),
                                       ("y=0:1", "y")])
def test_a_bad_domain_is_refused(project, capsys, spec, word):
    _bad(capsys, ["check", "exitfix.py", "--domain", spec], word)


def test_a_good_domain_still_checks(project, capsys):
    assert main(["check", "exitfix.py", "--domain", "x=0:1"]) == 0


def test_an_interrupt_exits_130(project, capsys, monkeypatch):
    import mathema.verify as verify_mod

    def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(verify_mod, "verify_project", interrupted)
    assert main(["verify", "--root", str(project)]) == 130
