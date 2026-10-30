# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Badges worker processes score a package that is importable only
through the run's `root`, not through the caller's `sys.path`: the
workers find the population the parent finds, nothing is printed to
stderr, and no function falls back to being scored in the parent."""
import sys

import pytest

from mathema import badges
from tests.test_badges_sweep_cost import _package


@pytest.fixture
def rooted(tmp_path, monkeypatch):
    scored_in_parent: list = []
    real = badges._score_one

    def parent_score(key, fn, ctx):
        scored_in_parent.append(key)
        return real(key, fn, ctx)
    monkeypatch.setattr(badges, "_score_one", parent_score)
    yield tmp_path, scored_in_parent
    for m in [m for m in sys.modules if m.startswith("bwr_")]:
        del sys.modules[m]


def test_workers_score_a_package_the_parent_imported_through_root(
        rooted, capfd):
    from mathema.targets import _root_on_path
    root, scored_in_parent = rooted
    keys = _package(root, "bwr_seen", 3)
    with _root_on_path(str(root)):
        __import__("bwr_seen.mod")
    assert str(root) not in sys.path
    scores = badges.repo_badges(["bwr_seen"], root=str(root),
                                implementation=False, cache=False, jobs=2)
    assert sorted(scores.per_function) == sorted(keys)
    assert scored_in_parent == []
    assert capfd.readouterr().err == ""


def test_workers_score_a_package_reachable_only_through_root(rooted, capfd):
    root, scored_in_parent = rooted
    keys = _package(root, "bwr_fresh", 3)
    assert str(root) not in sys.path
    scores = badges.repo_badges(["bwr_fresh"], root=str(root),
                                implementation=False, cache=False, jobs=2)
    assert sorted(scores.per_function) == sorted(keys)
    assert scored_in_parent == []
    assert capfd.readouterr().err == ""
