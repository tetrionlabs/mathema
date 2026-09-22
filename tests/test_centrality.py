# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Centrality over the project call graph: PageRank (importance accrues
to a function from those that depend on it) plus the general graph
primitives (transpose/dependents, in-degree). Reusable beyond badges."""
from mathema.centrality import (build_call_graph, centrality_weights,
                                in_degree, pagerank, reverse_graph)


def test_pagerank_ranks_a_depended_on_core_above_leaves():
    edges = {"a": {"core"}, "b": {"core"}, "c": {"core"},
             "core": set(), "leaf": set()}
    pr = pagerank(edges)
    assert pr["core"] == max(pr.values())
    assert pr["core"] > pr["leaf"]
    assert abs(sum(pr.values()) - 1.0) < 1e-9        # a proper distribution


def test_pagerank_handles_cycles_and_dangling_nodes():
    cyc = {"x": {"y"}, "y": {"z"}, "z": {"x"}, "d": {"x"}, "leaf": set()}
    pr = pagerank(cyc)
    assert abs(sum(pr.values()) - 1.0) < 1e-9
    assert pr["x"] == max(pr.values())               # d and the cycle feed x
    assert pagerank({}) == {}


def test_reverse_graph_and_in_degree():
    edges = {"a": {"core"}, "b": {"core"}, "core": set()}
    assert reverse_graph(edges)["core"] == {"a", "b"}
    assert reverse_graph(edges)["a"] == set()
    assert in_degree(edges) == {"a": 0, "b": 0, "core": 2}


def test_weights_mean_normalise_to_one_and_all_leaf_is_uniform():
    # an all-leaf population (no internal deps) weighs every function 1,
    # so a weighted mean collapses to the ordinary mean.
    leaves = {"p": set(), "q": set(), "r": set()}
    pr = pagerank(leaves)
    mean = sum(pr.values()) / len(pr)
    assert all(abs(v / mean - 1.0) < 1e-9 for v in pr.values())


def test_build_call_graph_restricts_to_the_population(tmp_path):
    import sys
    pkg = tmp_path / "cgpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text("def sq(x):\n    return x * x\n")
    (pkg / "wrap.py").write_text(
        "import math\n"
        "from cgpkg.core import sq\n"
        "def outer(x):\n"
        "    return sq(x) + math.sqrt(x)\n")   # sqrt is out of population
    sys.path.insert(0, str(tmp_path))
    try:
        from cgpkg import core, wrap
        functions = {"cgpkg.core.sq": core.sq, "cgpkg.wrap.outer": wrap.outer}
        edges = build_call_graph(functions)
        # the internal call is an edge; the stdlib call is not
        assert edges["cgpkg.wrap.outer"] == {"cgpkg.core.sq"}
        assert edges["cgpkg.core.sq"] == set()
        w = centrality_weights(functions)
        assert w["cgpkg.core.sq"] > w["cgpkg.wrap.outer"]   # core is depended on
        assert abs(sum(w.values()) / len(w) - 1.0) < 1e-9   # mean weight 1
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("cgpkg")]:
            del sys.modules[m]
