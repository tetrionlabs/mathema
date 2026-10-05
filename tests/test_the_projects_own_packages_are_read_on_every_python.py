# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The packages a project's pyproject.toml declares are read on every
supported Python.

`tomllib` is in the standard library from Python 3.11. On 3.10 mathema
reads the file with `tomli` when it is installed, and otherwise with its
own reader of the few tables it needs (the project name, setuptools',
poetry's and hatch's package lists). A pyproject.toml that none of them
can read is said, never taken silently as a project with no packages.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from mathema._claim_reach import declared_packages

_PYPROJECT = textwrap.dedent("""\
    # a comment
    [project]
    name = "my-proj"   # trailing comment
    version = "0.1"
    dependencies = ["numpy>=2", 'pandas']

    [tool.setuptools]
    packages = ["alpha", "beta.sub"]

    [tool.poetry]
    packages = [{ include = "gamma" }, {include = "delta", from = "src"}]

    [tool.hatch.build.targets.wheel]
    packages = ["src/epsilon"]
    """)


@pytest.fixture(params=["tomllib", "tomli", "neither"])
def reader(request, monkeypatch):
    if request.param in ("tomli", "neither"):
        monkeypatch.setitem(sys.modules, "tomllib", None)
    if request.param == "tomli":
        pytest.importorskip("tomli")
    if request.param == "neither":
        monkeypatch.setitem(sys.modules, "tomli", None)
    if request.param == "tomllib" and sys.version_info < (3, 11):
        pytest.skip("tomllib is in the standard library from 3.11")
    return request.param


def test_every_declared_package_is_read(tmp_path, reader):
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT)
    assert declared_packages(str(tmp_path)) == frozenset(
        {"my_proj", "alpha", "beta", "gamma", "delta", "epsilon"})


def test_an_unreadable_pyproject_is_said(tmp_path, reader):
    (tmp_path / "pyproject.toml").write_text("[project\nname = \n")
    with pytest.warns(UserWarning, match="pyproject.toml"):
        assert declared_packages(str(tmp_path)) == frozenset()
