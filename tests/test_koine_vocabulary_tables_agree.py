# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The vocabulary tables agree with each other and with the helpers
that realise them: every operator and function has an implementation,
a rendering and a signature, and every `__koine__` path is a term."""
from mathema.koine import vocabulary as V
from mathema.koine._render import CALLS
from mathema.koine.aliases import alias_of, aliases, path_of
from mathema.koine.functions import HELPER_FUNCTIONS, IMPLEMENTATIONS, helpers


def test_every_operator_and_function_is_implemented():
    ops = set(V.UNARY + V.ARITHMETIC + V.DIVISION + V.REMAINDER)
    assert ops | set(V.FUNCTIONS) <= set(IMPLEMENTATIONS)
    assert set(IMPLEMENTATIONS) <= set(V.EXPRESSIONS)


def test_every_call_rendering_names_a_known_term():
    assert set(CALLS) <= set(V.EXPRESSIONS)


def test_every_alias_names_a_term_and_every_helper_has_an_alias():
    assert set(aliases().values()) <= set(V.EXPRESSIONS)
    bound = helpers()
    assert {fn.__koine__ for fn in HELPER_FUNCTIONS} == {fn.__koine__ for fn in bound.values()}
    for alias, fn in bound.items():
        assert path_of(alias) == fn.__koine__
        assert IMPLEMENTATIONS[fn.__koine__] is fn


def test_an_alias_reads_both_ways():
    assert path_of("div_trunc") == "operator::binary::division::truncation"
    assert alias_of("function::rounding::ties_up") == "round_ties_up"
    assert path_of("no_such_alias") is None
    assert alias_of("operator::binary::addition") is None


def test_the_tree_is_rooted():
    roots = {"statement", "operator", "function", "value", "constant", "call", "failure",
             "nonvalue", "as", "kind", "representation"}
    for head in V.ALL_HEADS:
        if "::" in head:
            assert head.split("::")[0] in roots, head
    assert all(h.startswith("nonvalue::") and h.count("::") == 2 for h in V.NONVALUES)


def test_the_families_pair_up():
    quotients = {h.rpartition("::")[2] for h in V.DIVISION} - {"real"}
    remainders = {h.rpartition("::")[2] for h in V.REMAINDER}
    assert quotients == remainders == {"truncation", "floor", "euclidean"}
    ties = {h for h in V.FUNCTIONS if h.startswith("function::rounding::ties_")}
    assert ties == {"function::rounding::ties_even", "function::rounding::ties_away",
                    "function::rounding::ties_up"}


def test_the_subsets_name_real_terms():
    assert V.UPDATE_OPS <= set(V.EXPRESSIONS)
    assert V.DOMAIN_FUNCTIONS <= set(V.FUNCTIONS)
    assert V.SINGULAR_AT_ZERO_DIVISOR <= set(V.EXPRESSIONS)


def test_the_alias_table_ships_with_the_package():
    import glob
    import os
    import pathlib
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib
    root = pathlib.Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text())
    patterns = data["tool"]["setuptools"]["package-data"].get("mathema.koine", [])
    pkg = root / "mathema" / "koine"
    declared = {os.path.normpath(p) for pattern in patterns
                for p in glob.glob(os.path.join(glob.escape(str(pkg)), pattern))}
    assert os.path.normpath(str(pkg / "data" / "aliases.yaml")) in declared
