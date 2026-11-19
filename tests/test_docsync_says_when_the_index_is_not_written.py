# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A failure to write the index is visible: the docsync report carries
the error's type and message, `mathema docsync` prints it and exits
non-zero, and every declared entry materialized before it is kept."""
import importlib
import sys
import textwrap

import pytest

_MOD = '''
def double(x: float) -> float:
    """Doubles the input.

    Claims:
        doubles: for x in [0, 9], f(x) == 2*x
    """
    return 2.0 * x
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    sys.modules.pop("idxpkg", None)
    importlib.invalidate_caches()
    (tmp_path / "idxpkg.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "idxpkg.double:\n"
        "  claims:\n"
        "    - name: doubles\n"
        "      statement: 'for x in [0, 9], f(x) == 2*x'\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    def write_index(targets, root="."):
        raise PermissionError("index.yaml is read only")
    import mathema.audit
    monkeypatch.setattr(mathema.audit, "write_index", write_index)
    yield tmp_path
    sys.modules.pop("idxpkg", None)


def test_the_report_carries_the_index_error(project):
    from mathema.sync import sync
    report = sync([], root=str(project))
    assert report.index_path is None
    assert report.index_error == "PermissionError: index.yaml is read only"
    assert report.materialized == ["idxpkg.double"]
    assert (project / ".mathema" / "declared").is_dir()


def test_docsync_prints_the_error_and_exits_non_zero(project, capsys):
    from mathema.cli import main
    code = main(["docsync", "--root", str(project), "--yes"])
    text = capsys.readouterr()
    assert code != 0
    assert ("index not written: PermissionError: index.yaml is read only"
            in text.out + text.err)
    assert "materialized 1 declared entry" in text.out
