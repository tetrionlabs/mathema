# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The distribution metadata is part of the product.

A wheel's metadata is the first thing anyone sees on PyPI and the last
thing anyone checks, which is how a literal `TODO(human)` placeholder
reached built metadata and stayed there. These tests read
`pyproject.toml` directly, so they fail in the working tree rather
than after a publish.
"""
import pathlib
import tomllib

import mathema

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    with open(_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def test_the_package_ships_its_typing_marker():
    """PEP 561: without this file a type checker ignores every
    annotation in the installed package and resolves imported names to
    Any, however carefully the source is typed."""
    assert (_ROOT / "mathema" / "py.typed").is_file()
    data = _pyproject()["tool"]["setuptools"]["package-data"]
    assert "py.typed" in data.get("mathema", [])


def test_no_project_url_is_a_placeholder():
    urls = _pyproject()["project"].get("urls", {})
    assert urls, "the project declares no URLs at all"
    for name, value in urls.items():
        assert "TODO" not in value, f"{name} is still a placeholder: {value}"
        assert value.startswith("https://"), f"{name} is not an https URL"


def test_the_declared_python_range_is_covered_by_classifiers():
    project = _pyproject()["project"]
    classifiers = project.get("classifiers", [])
    assert classifiers, "no classifiers: PyPI cannot categorise the project"
    versions = {c.rsplit(" :: ", 1)[1] for c in classifiers
                if c.startswith("Programming Language :: Python :: ")
                and c.rsplit(" :: ", 1)[1][0].isdigit()}
    # every version the CI matrix tests must be advertised
    assert {"3.10", "3.11", "3.12", "3.13"} <= versions, versions
    assert "Typing :: Typed" in classifiers


def test_the_version_is_single_sourced_from_the_package():
    project = _pyproject()["project"]
    assert "version" in project.get("dynamic", []), \
        "a literal version in pyproject can drift from mathema.__version__"
    attr = _pyproject()["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "mathema.__version__"
    assert mathema.__version__


def test_repo_tooling_stays_out_of_the_distribution():
    """`_devtools` shells out to `git ls-files`; it is meaningless in
    an installed wheel."""
    find = _pyproject()["tool"]["setuptools"]["packages"]["find"]
    assert any("_devtools" in pattern for pattern in find.get("exclude", []))
