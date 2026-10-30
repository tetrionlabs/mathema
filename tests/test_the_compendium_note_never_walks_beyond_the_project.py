# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The note that a project's compendium files were not read looks for
the project above the function's module only as far as the directory
the module is imported from, or the project the current directory is
in when the module lies inside it. A function outside any project (a
standard-library function under a home directory that carries a
project marker) gets no note and no directory is walked; a project's
own tree is walked with a bound, skipping hidden directories and
virtual environments."""
import sys
import textwrap
import time

import pytest

from mathema import compendium
from mathema.compendium import uninstalled_project_note


def _write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _huge(directory, count=4000):
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (directory / f"f{i}.txt").write_text("")


_CLAIMS = """
    compendium: numpy
    versions: ">=2.0"
    numpy.std:
      claims:
        - name: definition
          statement: "for a in R^n, f(a) ~= std(a, ddof=0)"
"""


def _import(monkeypatch, where, name):
    monkeypatch.syspath_prepend(str(where))
    for loaded in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        sys.modules.pop(loaded, None)
    module = __import__(name, fromlist=["x"])
    return module


@pytest.fixture(autouse=True)
def _fresh_project_cache():
    compendium._PROJECT_FILES.clear()
    yield
    compendium._PROJECT_FILES.clear()


@pytest.fixture
def walks(monkeypatch):
    seen = []
    real = compendium.os.walk

    def counted(top, *args, **kwargs):
        seen.append(str(top))
        return real(top, *args, **kwargs)
    monkeypatch.setattr(compendium.os, "walk", counted)
    return seen


def test_a_function_outside_any_project_is_never_walked(tmp_path, monkeypatch, walks):
    home = tmp_path / "home"
    _write(home / ".mathema" / "config.yaml")
    _write(home / "claims" / "numpy.claims.yaml", _CLAIMS)
    _huge(home / "Documents")
    lib = home / ".local" / "python" / "lib"
    _write(lib / "stdlike.py", '''
        def mean(xs):
            return sum(xs) / len(xs)
    ''')
    work = tmp_path / "work"
    _write(work / "pyproject.toml", '[project]\nname = "work"\n')
    monkeypatch.chdir(work)
    mean = _import(monkeypatch, lib, "stdlike").mean
    start = time.monotonic()
    assert uninstalled_project_note(mean) is None
    assert time.monotonic() - start < 1.0
    assert walks == []


def test_a_package_s_project_above_its_import_root_is_not_searched(tmp_path, monkeypatch,
                                                                     walks):
    home = tmp_path / "home"
    _write(home / ".git" / "HEAD")
    _write(home / "claims" / "numpy.claims.yaml", _CLAIMS)
    _write(home / "apps" / "loose" / "lpkg" / "__init__.py")
    _write(home / "apps" / "loose" / "lpkg" / "mod.py", '''
        def spread(a):
            return max(a) - min(a)
    ''')
    monkeypatch.chdir(tmp_path)
    spread = _import(monkeypatch, home / "apps" / "loose", "lpkg.mod").spread
    assert uninstalled_project_note(spread) is None
    assert walks == []


def test_a_src_layout_project_is_found_from_its_own_directory(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    _write(project / "pyproject.toml", '[project]\nname = "srcpkg"\n')
    _write(project / "claims" / "numpy.claims.yaml", _CLAIMS)
    _write(project / "src" / "srcpkg" / "__init__.py")
    _write(project / "src" / "srcpkg" / "mod.py", '''
        def spread(a):
            return max(a) - min(a)
    ''')
    monkeypatch.chdir(project)
    spread = _import(monkeypatch, project / "src", "srcpkg.mod").spread
    note = uninstalled_project_note(spread)
    assert note == (f"project compendium files under {project} were not read; "
                    f"to use them, call: mathema.compendium.install({str(project)!r})")


def test_the_walk_of_a_project_skips_hidden_and_virtual_environments_and_is_bounded(
        tmp_path, monkeypatch):
    project = tmp_path / "big"
    _write(project / "pyproject.toml", '[project]\nname = "bigpkg"\n')
    _write(project / "bigpkg" / "__init__.py")
    _write(project / "bigpkg" / "mod.py", '''
        def spread(a):
            return max(a) - min(a)
    ''')
    _write(project / ".hidden" / "claims" / "numpy.claims.yaml", _CLAIMS)
    _write(project / "env" / "pyvenv.cfg", "home = /usr\n")
    _write(project / "env" / "claims" / "numpy.claims.yaml", _CLAIMS)
    deep = project
    for i in range(compendium._NOTE_WALK_DEPTH + 2):
        deep = deep / f"d{i}"
    _write(deep / "claims" / "numpy.claims.yaml", _CLAIMS)
    _huge(project / "data", compendium._NOTE_WALK_FILES + 10)
    monkeypatch.chdir(project)
    spread = _import(monkeypatch, project, "bigpkg.mod").spread
    start = time.monotonic()
    assert uninstalled_project_note(spread) is None
    assert time.monotonic() - start < 2.0
