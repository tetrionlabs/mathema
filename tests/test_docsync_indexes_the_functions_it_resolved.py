# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""docsync's index lists the functions its targets resolved to: a
file-path target writes an index of that file's functions, and a
dotted-name target writes the same index `write_index` gives for that
name."""
import importlib
import sys
import textwrap

import pytest
import yaml

_MOD = '''
def documented(x: float) -> float:
    """Documented.

    Intent:
        States itself.
    """
    return x


def bare(x: float) -> float:
    return x
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    sys.modules.pop("idxfuncs", None)
    importlib.invalidate_caches()
    (tmp_path / "idxfuncs.py").write_text(textwrap.dedent(_MOD))
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    sys.modules.pop("idxfuncs", None)


def _index(root):
    return yaml.safe_load((root / ".mathema" / "index.yaml").read_text())["index"]


def _keys(index):
    return sorted(f["key"] for m in index["modules"] for f in m["functions"])


def test_a_file_path_target_writes_an_index_of_its_functions(project):
    from mathema.sync import sync
    report = sync(["idxfuncs.py"], root=str(project))
    assert report.index_error is None, report.index_error
    assert report.index_path is not None
    assert _keys(_index(project)) == ["idxfuncs.bare", "idxfuncs.documented"]


def test_a_dotted_target_writes_the_index_write_index_gives(project):
    from mathema.audit import write_index
    from mathema.sync import sync
    report = sync(["idxfuncs"], root=str(project))
    assert report.index_error is None, report.index_error
    from_sync = _index(project)
    write_index(["idxfuncs"], root=str(project))
    assert from_sync == _index(project)
