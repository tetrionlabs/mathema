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


def _snapshot(scores) -> str:
    import json

    from mathema.badges import ci_snapshot
    return json.dumps(ci_snapshot(scores), sort_keys=True)


def _traces(monkeypatch) -> list:
    from mathema import impl_coverage
    traced: list = []
    original = impl_coverage._trace_check

    def counting(fn, *a, **k):
        traced.append(fn.__name__)
        return original(fn, *a, **k)
    monkeypatch.setattr(impl_coverage, "_trace_check", counting)
    return traced


def test_a_second_run_on_an_unchanged_project_reads_every_result_from_the_cache(
        importable, monkeypatch):
    _package(importable, "bsc_cache", 3)
    traced = _traces(monkeypatch)
    first = repo_badges(["bsc_cache"], root=str(importable))
    assert sorted(traced) == ["f0", "f1", "f2", "helper"]
    traced.clear()
    from mathema import centrality
    graphs = _counting(monkeypatch, {(centrality, "build_call_graph"): 1})
    second = repo_badges(["bsc_cache"], root=str(importable))
    assert traced == []
    assert graphs == {}
    assert _snapshot(second) == _snapshot(first)
    uncached = repo_badges(["bsc_cache"], root=str(importable), cache=False)
    assert sorted(traced) == ["f0", "f1", "f2", "helper"]
    assert _snapshot(uncached) == _snapshot(first)
    cache_dir = importable / ".mathema" / "cache" / "badges"
    assert (cache_dir / ".gitignore").read_text() == "*\n"
    # one entry per function and one for the centrality weights
    assert len(list(cache_dir.glob("*/*.json"))) == 5


def _fresh_import(name: str) -> None:
    for m in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        del sys.modules[m]


_GRAPH_SOURCE = '''\
def helper(x: float) -> float:
    """Intent:
        Twice x.
    """
    return x + x
def f0(x: float) -> float:
    """Intent:
        Twice x plus 0.
    """
    return helper(x) + 0
def f1(x: float) -> float:
    """Intent:
        Twice x plus 1.
    """
    return helper(x) + 1
def lone(x: float) -> float:
    """Intent:
        x plus 3.
    """
    return x + 3
'''


def _graph_package(root, name: str) -> None:
    """`helper`, two callers of it (`f0`, `f1`), and `lone`, which calls
    nothing; each with a verified record and a claims-file entry."""
    from mathema.spec import verified_dir, write_yaml
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(_GRAPH_SOURCE)
    os.makedirs(verified_dir(str(root)), exist_ok=True)
    claims = {}
    for short in ("helper", "f0", "f1", "lone"):
        key = f"{name}.mod.{short}"
        write_yaml(os.path.join(verified_dir(str(root)), f"{key}.yaml"),
                   {key: {"name": short, "claims": [
                       {"name": "grows", "statement": f"{short}(1.0) > 1.0",
                        "verdict": "proven", "route": "derive"}]}})
        claims[key] = {"claims": [{"name": "grows",
                                   "statement": f"{short}(1.0) > 1.0"}]}
    (root / "claims").mkdir()
    write_yaml(str(root / "claims" / f"{name}.claims.yaml"), claims)


def _edit(path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def test_editing_one_function_computes_it_and_its_callers_again(
        importable, monkeypatch):
    _graph_package(importable, "bsc_graph")
    traced = _traces(monkeypatch)
    repo_badges(["bsc_graph"], root=str(importable))
    assert sorted(traced) == ["f0", "f1", "helper", "lone"]
    mod = importable / "bsc_graph" / "mod.py"
    _edit(mod, "return helper(x) + 0", "return helper(x) + 70")
    _fresh_import("bsc_graph")
    traced.clear()
    repo_badges(["bsc_graph"], root=str(importable))
    assert traced == ["f0"]
    _edit(mod, "return x + x", "return x + x + 0.0")
    _fresh_import("bsc_graph")
    traced.clear()
    cached = repo_badges(["bsc_graph"], root=str(importable))
    assert sorted(traced) == ["f0", "f1", "helper"]
    uncached = repo_badges(["bsc_graph"], root=str(importable), cache=False)
    assert _snapshot(cached) == _snapshot(uncached)


def test_a_changed_record_computes_that_function_and_its_callers_again(
        importable, monkeypatch):
    import pathlib

    from mathema.spec import verified_dir
    _graph_package(importable, "bsc_record")
    traced = _traces(monkeypatch)
    repo_badges(["bsc_record"], root=str(importable))
    store = pathlib.Path(verified_dir(str(importable)))
    _edit(store / "bsc_record.mod.lone.yaml", "lone(1.0) > 1.0",
          "lone(2.0) > 1.0")
    traced.clear()
    repo_badges(["bsc_record"], root=str(importable))
    assert traced == ["lone"]
    _edit(store / "bsc_record.mod.helper.yaml", "helper(1.0) > 1.0",
          "helper(2.0) > 1.0")
    traced.clear()
    repo_badges(["bsc_record"], root=str(importable))
    assert sorted(traced) == ["f0", "f1", "helper"]


def test_a_new_unrelated_file_computes_nothing_again(importable,
                                                     monkeypatch):
    _graph_package(importable, "bsc_unrelated")
    traced = _traces(monkeypatch)
    repo_badges(["bsc_unrelated"], root=str(importable))
    (importable / "bsc_unrelated" / "extra.py").write_text("LIMIT = 3\n")
    traced.clear()
    repo_badges(["bsc_unrelated"], root=str(importable))
    assert traced == []


def test_a_function_its_record_lists_as_a_dependency_counts_as_reached(
        importable, monkeypatch):
    from mathema.spec import verified_dir, write_yaml
    _graph_package(importable, "bsc_listed")
    key = "bsc_listed.mod.lone"
    write_yaml(os.path.join(verified_dir(str(importable)), f"{key}.yaml"),
               {key: {"name": "lone", "claims": [
                   {"name": "grows", "statement": "lone(1.0) > 1.0",
                    "verdict": "proven", "route": "derive"}],
                   "dependencies": [{"name": "helper", "kind": "function",
                                     "key": "bsc_listed.mod.helper"}]}})
    traced = _traces(monkeypatch)
    repo_badges(["bsc_listed"], root=str(importable))
    _edit(importable / "bsc_listed" / "mod.py", "return x + x",
          "return x + x + 0.0")
    _fresh_import("bsc_listed")
    traced.clear()
    repo_badges(["bsc_listed"], root=str(importable))
    assert sorted(traced) == ["f0", "f1", "helper", "lone"]


def test_refresh_computes_every_function_again_and_rewrites_the_cache(
        importable, monkeypatch):
    import json
    _graph_package(importable, "bsc_refresh")
    traced = _traces(monkeypatch)
    first = repo_badges(["bsc_refresh"], root=str(importable))
    cache_dir = importable / ".mathema" / "cache" / "badges"
    for path in cache_dir.glob("*/*.json"):
        entry = json.loads(path.read_text())
        if "intent" in entry:
            entry["intent"] = 3
            path.write_text(json.dumps(entry))
    traced.clear()
    stale = repo_badges(["bsc_refresh"], root=str(importable))
    assert traced == [] and _snapshot(stale) != _snapshot(first)
    refreshed = repo_badges(["bsc_refresh"], root=str(importable),
                            cache="refresh")
    assert sorted(traced) == ["f0", "f1", "helper", "lone"]
    assert _snapshot(refreshed) == _snapshot(first)
    traced.clear()
    again = repo_badges(["bsc_refresh"], root=str(importable))
    assert traced == []
    assert _snapshot(again) == _snapshot(first)


def test_the_cli_passes_refresh_to_the_run(tmp_path, monkeypatch, capsys):
    from mathema import badges
    from mathema.cli import main
    seen = []
    real = badges.repo_badges

    def recording(*a, **k):
        seen.append(k.get("cache"))
        return real(*a, **k)
    monkeypatch.setattr(badges, "repo_badges", recording)
    main(["badges", "--root", str(tmp_path), "--refresh"])
    main(["badges", "--root", str(tmp_path)])
    assert seen == ["refresh", True]


def test_a_result_with_a_capped_step_is_never_cached(importable,
                                                     monkeypatch):
    from mathema import impl_coverage
    _package(importable, "bsc_nocache", 1)
    real = impl_coverage.function_coverage

    def coverage(fn, *a, **k):
        if fn.__name__ == "f0":
            raise _timeout._WallClockExpired("cap")
        return real(fn, *a, **k)
    monkeypatch.setattr(impl_coverage, "function_coverage", coverage)
    first = repo_badges(["bsc_nocache"], root=str(importable))
    assert first.capped == {"bsc_nocache.mod.f0": ("implementation",)}
    monkeypatch.setattr(impl_coverage, "function_coverage", real)
    traced = _traces(monkeypatch)
    second = repo_badges(["bsc_nocache"], root=str(importable))
    assert traced == ["f0"]
    assert second.capped == {}


def test_worker_processes_give_the_same_snapshot_as_one_process(importable):
    _package(importable, "bsc_jobs", 4)
    alone = repo_badges(["bsc_jobs"], root=str(importable), cache=False)
    seen = []
    pooled = repo_badges(["bsc_jobs"], root=str(importable), cache=False,
                         jobs=2, progress=lambda d, n: seen.append((d, n)))
    assert _snapshot(pooled) == _snapshot(alone)
    assert seen == [(d, 5) for d in range(1, 6)]


def test_the_cli_takes_a_jobs_count():
    from mathema import badges as badges_module
    assert 1 <= badges_module.default_jobs() <= 4


def _cached_keys(root) -> set:
    import json
    cache_dir = root / ".mathema" / "cache" / "badges"
    out = set()
    for path in cache_dir.glob("*/*.json"):
        entry = json.loads(path.read_text())
        if "intent" in entry:
            out.add(entry["key"])
    return out


def test_a_proof_cap_recorded_in_check_leaves_that_function_uncached(
        importable, monkeypatch):
    from mathema import impl_coverage
    from mathema.records import Probe
    _package(importable, "bsc_proofcap", 2)
    original = impl_coverage._trace_check

    def recording(fn, *a, **k):
        statements, executed, record = original(fn, *a, **k)
        if fn.__name__ == "f0" and record is not None:
            record.probes.append(Probe(
                name="capped", statement="f0(1.0) > 1.0", verdict="unknown",
                route="derive", meta={"mathema.timeout": "fast"}))
        return statements, executed, record
    monkeypatch.setattr(impl_coverage, "_trace_check", recording)
    scores = repo_badges(["bsc_proofcap"], root=str(importable))
    assert scores.capped == {}
    assert _cached_keys(importable) == {"bsc_proofcap.mod.helper",
                                        "bsc_proofcap.mod.f1"}
    monkeypatch.setattr(impl_coverage, "_trace_check", original)
    traced = _traces(monkeypatch)
    repo_badges(["bsc_proofcap"], root=str(importable))
    assert traced == ["f0"]


def test_a_cap_fired_anywhere_while_scoring_leaves_that_function_uncached(
        importable, monkeypatch):
    import time

    from mathema import docstring
    _package(importable, "bsc_anycap", 2)
    original = docstring.docstring_sync

    def slow_once(fn, *a, **k):
        if fn.__name__ == "f1" and not k.get("_shallow"):
            try:
                _timeout._with_timeout(lambda: time.sleep(5), 1)
            except TimeoutError:
                pass
        return original(fn, *a, **k)
    monkeypatch.setattr(docstring, "docstring_sync", slow_once)
    scores = repo_badges(["bsc_anycap"], root=str(importable))
    assert scores.capped == {}
    assert _cached_keys(importable) == {"bsc_anycap.mod.helper",
                                        "bsc_anycap.mod.f0"}
