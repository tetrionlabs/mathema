# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Centrality of a function within the project's own call graph.

A repo-level badge is not a flat mean of its functions: a core function,
one the rest of the codebase depends on, should count for more than a
leaf helper. Centrality here is PageRank over the caller-to-callee graph,
so importance accrues to a function from the (already important)
functions that depend on it, transitively. The weights are mean-
normalised to 1, so a repo with no internal dependencies (every function
a leaf) yields all-1 weights and the weighted mean collapses to the
ordinary mean.
"""
from __future__ import annotations

from .inventory import function_dependencies


def build_call_graph(functions: dict[str, object]) -> dict[str, set[str]]:
    """Intent:
        The forward call graph over one population of functions:
        `{caller_key: {callee_key, ...}}`, restricted to edges whose
        callee is itself in `functions` (a call out to the standard
        library or a third party is not an internal dependency). A
        self-recursive call is dropped, since a function does not make
        itself more central by calling itself.
    Notes:
        Keys are `module.qualname` on both sides (`function_dependencies`
        emits `f"{mod}.{qual}"`, `discover` keys methods
        `module.Class.method`), so they line up without translation.
    """
    keys = set(functions)
    edges: dict[str, set[str]] = {k: set() for k in keys}
    for key, fn in functions.items():
        for dep in function_dependencies(fn):
            callee = dep.get("key")
            if (dep.get("kind") == "function" and callee in keys
                    and callee != key):
                edges[key].add(callee)
    return edges


def reverse_graph(edges: dict[str, set[str]]) -> dict[str, set[str]]:
    """Intent:
        The dependents graph `{callee_key: {caller_key, ...}}`, the
        transpose of a caller-to-callee `edges` map: who depends on each
        function. Every node in `edges` is a key, so a function nothing
        depends on maps to an empty set. A general graph operation, the
        obvious reuse point for impact analysis ("change this, what
        breaks") independent of the badge scoring.
    """
    rev: dict[str, set[str]] = {k: set() for k in edges}
    for caller, callees in edges.items():
        for callee in callees:
            rev.setdefault(callee, set()).add(caller)
    return rev


def in_degree(edges: dict[str, set[str]]) -> dict[str, int]:
    """Intent:
        How many functions depend on each one, `{key: count}`: the
        first-order centrality (the size of each dependents set), an
        alternative to `pagerank` when transitivity is not wanted.
    """
    return {k: len(v) for k, v in reverse_graph(edges).items()}


def pagerank(edges: dict[str, set[str]], damping: float = 0.85,
             iterations: int = 100, tol: float = 1e-9) -> dict[str, float]:
    """Intent:
        PageRank over caller-to-callee `edges`: each function's rank is
        the stationary probability of a damped random walk that follows
        a dependency with probability `damping` and teleports uniformly
        otherwise. A function many (important) functions depend on ranks
        high. Ranks sum to 1. An empty graph returns `{}`.
    Notes:
        A node with no outgoing dependency (a leaf) is dangling; its
        mass is redistributed uniformly each iteration, the standard
        treatment that keeps the ranks a proper distribution. Cycles
        need no special handling, damping guarantees convergence.
    """
    nodes = list(edges)
    n = len(nodes)
    if n == 0:
        return {}
    rank = {k: 1.0 / n for k in nodes}
    out_degree = {k: len(edges[k]) for k in nodes}
    base = (1.0 - damping) / n
    for _ in range(iterations):
        dangling = sum(rank[k] for k in nodes if out_degree[k] == 0)
        new = {k: base + damping * dangling / n for k in nodes}
        for k in nodes:
            if out_degree[k]:
                share = damping * rank[k] / out_degree[k]
                for callee in edges[k]:
                    new[callee] += share
        delta = sum(abs(new[k] - rank[k]) for k in nodes)
        rank = new
        if delta < tol:
            break
    return rank


def centrality_weights(functions: dict[str, object]) -> dict[str, float]:
    """Intent:
        A per-function weight `{key: weight}` from PageRank over the
        population's call graph, mean-normalised to 1 (the average
        function weighs 1, a central one more, a leaf less). An
        empty population returns `{}`.
    Notes:
        Mean-normalisation is what makes an all-leaf repo (uniform
        rank) produce all-1 weights, so a centrality-weighted mean over
        such a repo equals the ordinary mean, no special-casing needed.
    """
    rank = pagerank(build_call_graph(functions))
    if not rank:
        return {}
    mean = sum(rank.values()) / len(rank)
    return {k: v / mean for k, v in rank.items()}
