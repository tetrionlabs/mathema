# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Implementation coverage that cannot be measured is unknown, never
full. A function with no Python source to read (defined by `exec`) has
no statement lines to count, so `mathema coverage` shows it as `no
source` rather than `100%`, the project figure counts only the lines
it can read, and the implementation badge leaves the function out
instead of scoring it 100; with no line read anywhere the badge says
`unknown`."""
import io
import sys
import textwrap
from contextlib import redirect_stdout

import pytest

MODULE = '''
    _NS: dict = {"__name__": __name__}
    exec(compile("def area(r):\\n    return 3.0 * r * r\\n", "<generated>", "exec"), _NS)
    area = _NS["area"]
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "nosrc_cov_mod.py").write_text(textwrap.dedent(MODULE))
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'p'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("nosrc_cov_mod", None)
    yield tmp_path
    sys.modules.pop("nosrc_cov_mod", None)


def test_the_coverage_pass_shows_no_source_rather_than_full(project):
    from mathema import cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.main(["coverage", "nosrc_cov_mod", "--root", str(project)])
    out = buf.getvalue()
    row = next(line for line in out.splitlines() if "nosrc_cov_mod.area" in line)
    assert "100%" not in row and "no source" in row, out
    assert "implementation coverage: 100%" not in out, out


def test_the_badge_leaves_an_unmeasured_function_out(project):
    from mathema.badges import repo_badges
    scores = repo_badges(["nosrc_cov_mod"], root=str(project), implementation=True)
    assert scores.per_function["nosrc_cov_mod.area"]["implementation"] is None, \
        scores.per_function
    assert scores.implementation is None, scores.implementation
    from mathema.badges import render_triangle, shields_payloads
    assert "IMPL unknown" in render_triangle(scores.implementation, scores.intent,
                                             scores.clarity)
    assert shields_payloads(scores)["implementation"]["message"] == "unknown"
