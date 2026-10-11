# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What one `repo_badges` run costs as the population grows: the stores,
the claims files and the library claims are read once per run, a shared
callee's docstring is measured once, each function's steps stop at the
wall-clock cap, progress is reported per function, and each
`StateDependenceWarning` is shown once per function."""
import collections
import io
import os
import sys
import warnings

import pytest

from mathema import _timeout
from mathema import badges as badges_mod
from mathema.badges import repo_badges


def _package(tmp_path, name: str, n: int) -> list:
    """A package `name` of `n` documented functions, each calling one
    shared helper, with a verified record and a claims-file entry for
    each; returns the function keys."""
    from mathema.spec import verified_dir, write_yaml
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    lines = ["SCALE = 2.0\n",
             "def helper(x: float) -> float:\n",
             "    '''Intent:\n        Twice x.\n    '''\n",
             "    return x + x\n"]
    for i in range(n):
        lines += [f"def f{i}(x: float) -> float:\n",
                  f"    '''Intent:\n        Twice x plus {i}.\n    '''\n",
                  f"    return helper(x) + {i}\n"]
    (pkg / "mod.py").write_text("".join(lines))
    keys = [f"{name}.mod.helper"] + [f"{name}.mod.f{i}" for i in range(n)]
    os.makedirs(verified_dir(str(tmp_path)), exist_ok=True)
    claims = {}
    for key in keys:
        short = key.rsplit(".", 1)[-1]
        write_yaml(os.path.join(verified_dir(str(tmp_path)), f"{key}.yaml"),
                   {key: {"name": short, "claims": [
                       {"name": "doubles", "statement": f"{short}(1.0) > 1.0",
                        "verdict": "proven", "route": "derive"}]}})
        claims[key] = {"claims": [{"name": "doubles",
                                   "statement": f"{short}(1.0) > 1.0"}]}
    (tmp_path / "claims").mkdir()
    write_yaml(str(tmp_path / "claims" / f"{name}.claims.yaml"), claims)
    return keys


@pytest.fixture
def importable(tmp_path):
    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    sys.path.remove(str(tmp_path))
    for m in [m for m in sys.modules if m.startswith("bsc")]:
        del sys.modules[m]


def _counting(monkeypatch, targets: dict) -> collections.Counter:
    calls: collections.Counter = collections.Counter()
    for (module, name) in targets:
        original = getattr(module, name)

        def wrapper(*a, _original=original, _name=name, **k):
            calls[_name] += 1
            return _original(*a, **k)
        monkeypatch.setattr(module, name, wrapper)
    return calls


def _reads(monkeypatch) -> collections.Counter:
    from mathema import compendium, spec
    return _counting(monkeypatch, {(spec, "read_verified_file"): 1,
                                   (spec, "read_claims_file"): 1,
                                   (spec, "load_declared"): 1,
                                   (spec, "load_verified"): 1,
                                   (compendium, "_read_library_claims"): 1})


@pytest.mark.parametrize("implementation", [False, True],
                         ids=["without-coverage", "with-coverage"])
def test_a_badges_run_reads_each_store_once_whatever_the_population(
        importable, monkeypatch, implementation):
    tmp_path = importable
    counts = []
    for name, n in (("bsc_small", 2), ("bsc_large", 6)):
        root = tmp_path / name / "root"
        root.mkdir(parents=True)
        keys = _package(root, name, n)
        sys.path.insert(0, str(root))
        calls = _reads(monkeypatch)
        try:
            scores = repo_badges([name], root=str(root),
                                 implementation=implementation)
        finally:
            sys.path.remove(str(root))
            monkeypatch.undo()
        assert set(scores.per_function) == set(keys)
        counts.append((len(keys), dict(calls)))
    (small_n, small), (large_n, large) = counts
    # every record file is read once, so the count follows the store
    assert small["read_verified_file"] == small_n
    assert large["read_verified_file"] == large_n
    # the claims files and library claims cost the same at any size
    for name in ("read_claims_file", "_read_library_claims"):
        assert small.get(name, 0) == large.get(name, 0), name
    assert large["load_verified"] == 1 and large["load_declared"] == 1


def test_a_shared_callees_docstring_is_measured_once(importable,
                                                     monkeypatch):
    from mathema import docstring
    keys = _package(importable, "bsc_shared", 5)
    shallow: collections.Counter = collections.Counter()
    original = docstring.docstring_sync

    def counting(fn, *a, **k):
        if k.get("_shallow"):
            shallow[fn.__qualname__] += 1
        return original(fn, *a, **k)
    monkeypatch.setattr(docstring, "docstring_sync", counting)
    repo_badges(["bsc_shared"], root=str(importable), implementation=False)
    assert len(keys) == 6
    assert shallow == {"helper": 1}


def test_a_step_stopped_by_the_cap_is_named_and_left_out(importable,
                                                         monkeypatch):
    from mathema import docstring, impl_coverage
    _package(importable, "bsc_capped", 2)
    real_sync = docstring.docstring_sync
    real_cov = impl_coverage.function_coverage

    def sync(fn, *a, **k):
        if fn.__name__ == "f0" and not k.get("_shallow"):
            raise _timeout._WallClockExpired("cap")
        return real_sync(fn, *a, **k)

    def coverage(fn, *a, **k):
        if fn.__name__ == "f1":
            raise _timeout._WallClockExpired("cap")
        return real_cov(fn, *a, **k)
    monkeypatch.setattr(docstring, "docstring_sync", sync)
    monkeypatch.setattr(impl_coverage, "function_coverage", coverage)
    scores = repo_badges(["bsc_capped"], root=str(importable))
    assert scores.capped == {"bsc_capped.mod.f0": ("intent",),
                             "bsc_capped.mod.f1": ("implementation",)}
    f0 = scores.per_function["bsc_capped.mod.f0"]
    f1 = scores.per_function["bsc_capped.mod.f1"]
    assert f0["intent"] is None and f0["implementation"] is not None
    # no test report: a capped coverage step counts no line covered
    assert f1["implementation"] == 0 and f1["intent"] is not None


def test_the_cap_is_the_badges_step_cap(monkeypatch):
    seen = []

    def fake(step, seconds):
        seen.append(seconds)
        return step()
    monkeypatch.setattr(_timeout, "_with_timeout", fake)
    assert badges_mod._capped(lambda: 7) == 7
    assert seen == [_timeout.BADGES_STEP_TIMEOUT_SECONDS]


def test_the_badges_step_cap_is_sixty_seconds_unless_the_env_sets_it(
        monkeypatch):
    import importlib
    monkeypatch.delenv("MATHEMA_BADGES_STEP_TIMEOUT", raising=False)
    try:
        assert importlib.reload(_timeout).BADGES_STEP_TIMEOUT_SECONDS == 60
        monkeypatch.setenv("MATHEMA_BADGES_STEP_TIMEOUT", "90")
        assert importlib.reload(_timeout).BADGES_STEP_TIMEOUT_SECONDS == 90
        monkeypatch.setenv("MATHEMA_BADGES_STEP_TIMEOUT", "not a number")
        assert importlib.reload(_timeout).BADGES_STEP_TIMEOUT_SECONDS == 60
    finally:
        monkeypatch.undo()
        importlib.reload(_timeout)


def test_the_snapshot_lists_capped_functions_only_when_there_are_some():
    from mathema.badges import BadgeScores, ci_snapshot
    plain = BadgeScores(implementation=50, intent=40, clarity=30, overall=7,
                        per_function={"m.f": {"implementation": 50,
                                              "intent": 40, "clarity": 30}})
    assert "capped" not in ci_snapshot(plain)
    capped = BadgeScores(implementation=50, intent=40, clarity=30, overall=7,
                         per_function=plain.per_function,
                         capped={"m.g": ("implementation", "clarity"),
                                 "m.f": ("intent",)})
    assert ci_snapshot(capped)["capped"] == [
        ["m.f", ["intent"]], ["m.g", ["implementation", "clarity"]]]


def test_progress_is_reported_after_every_function(importable):
    _package(importable, "bsc_progress", 3)
    seen = []
    repo_badges(["bsc_progress"], root=str(importable), implementation=False,
                progress=lambda done, total: seen.append((done, total)))
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]


class _Terminal(io.StringIO):
    def isatty(self):
        return True


def test_the_cli_prints_progress_on_a_terminal_only():
    from mathema.cli import _badges_progress
    assert _badges_progress(io.StringIO()) is None
    stream = _Terminal()
    report = _badges_progress(stream, every=2)
    for done in range(1, 6):
        report(done, 5)
    lines = stream.getvalue().splitlines()
    assert [line.split(",")[0] for line in lines] == [
        "badges: 2/5 functions", "badges: 4/5 functions",
        "badges: 5/5 functions"]
    assert all(line.endswith("s") for line in lines)


def test_a_state_dependence_warning_is_shown_once_per_function(importable):
    _package(importable, "bsc_state", 1)
    mod = importable / "bsc_state" / "mod.py"
    mod.write_text(mod.read_text() + (
        "def scaled(x: float) -> float:\n"
        "    '''Intent:\n        x times SCALE.\n    '''\n"
        "    return x * SCALE\n"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        repo_badges(["bsc_state"], root=str(importable))
    from mathema.analysis import StateDependenceWarning
    texts = [str(w.message) for w in caught
             if issubclass(w.category, StateDependenceWarning)]
    assert any("scaled" in t for t in texts)
    assert len(texts) == len(set(texts))


def test_the_mcp_badges_tool_takes_its_targets_as_optional(tmp_path):
    from mathema.interfaces.mcp import tools
    out = tools.badges(root=str(tmp_path))
    assert out["rows"] == [] and out["capped"] == []
