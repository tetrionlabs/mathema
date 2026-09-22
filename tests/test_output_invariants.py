# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Output-contract invariants: cheap structural checks on a function's
output, the property-based-testing "some things never change" family.
Relations (preserves_length, is_permutation_of_input, preserves_type)
adjudicate on the probe route; the suggestion gate fires for a sequence-
returning function whose first argument is a sequence."""
import textwrap


def _load(tmp_path, body, name="m"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _v(fn, law):
    from mathema.conjecture import check_conjectures, claim
    (pr,) = check_conjectures(fn, [claim(law)])
    return pr.verdict


def test_preserves_length_holds_and_falsifies(tmp_path):
    mod = _load(tmp_path, '''
        def rev(xs: list) -> list:
            """Reverse."""
            return xs[::-1]
        def dup(xs: list) -> list:
            """Double."""
            return xs + xs
    ''')
    assert _v(mod.rev, "len(f(xs)) == len(xs)") == "holds"
    assert _v(mod.dup, "len(f(xs)) == len(xs)") == "falsified"


def test_is_permutation_of_input_holds_for_a_reordering(tmp_path):
    mod = _load(tmp_path, '''
        def rev(xs: list) -> list:
            """A reordering."""
            return xs[::-1]
        def squares(xs: list) -> list:
            """Not a permutation of the input."""
            return [x * x for x in xs]
    ''')
    assert _v(mod.rev, "sorted(f(xs)) == sorted(xs)") == "holds"
    assert _v(mod.squares, "sorted(f(xs)) == sorted(xs)") == "falsified"


def test_preserves_type_holds_and_falsifies(tmp_path):
    mod = _load(tmp_path, '''
        def rev(xs: list) -> list:
            """list -> list."""
            return xs[::-1]
        def joined(xs: list) -> str:
            """list -> str, type not preserved."""
            return ",".join(str(x) for x in xs)
    ''')
    assert _v(mod.rev, "type(f(xs)) == type(xs)") == "holds"
    assert _v(mod.joined, "type(f(xs)) == type(xs)") == "falsified"


def test_invariants_suggested_only_for_a_sequence_return(tmp_path):
    from mathema.suggest import suggest_claims
    mod = _load(tmp_path, '''
        def rev(xs: list) -> list:
            """Sequence in and out."""
            return xs[::-1]
        def total(xs: list) -> float:
            """Sequence in, scalar out."""
            return float(sum(xs))
    ''')
    seq_names = {c.name for c in suggest_claims(mod.rev)}
    assert {"preserves_length", "is_permutation_of_input",
            "preserves_type"} <= seq_names
    scalar_names = {c.name for c in suggest_claims(mod.total)}
    assert "preserves_length" not in scalar_names


def test_is_sorted_output_predicate_holds_and_falsifies(tmp_path):
    from mathema.conjecture import check_conjectures, claim
    mod = _load(tmp_path, '''
        def do_sort(xs: list) -> list:
            """Returns sorted."""
            return sorted(xs)
        def rev(xs: list) -> list:
            """Reverse, not sorted."""
            return xs[::-1]
    ''')
    (a,) = check_conjectures(mod.do_sort, [claim("is_sorted_output(f(xs))", route="best")])
    assert a.verdict == "holds"
    (b,) = check_conjectures(mod.rev, [claim("is_sorted_output(f(xs))", route="best")])
    assert b.verdict == "falsified"


def test_output_never_none_predicate_holds_and_falsifies(tmp_path):
    from mathema.conjecture import check_conjectures, claim
    mod = _load(tmp_path, '''
        def maybe(x: float) -> float:
            """None on a branch."""
            if x < 0:
                return None
            return x
        def always(x: float) -> float:
            """Always a value."""
            return x * 2.0
    ''')
    (a,) = check_conjectures(mod.maybe, [claim("output_never_none(f(x))", route="best")])
    assert a.verdict == "falsified"
    (b,) = check_conjectures(mod.always, [claim("output_never_none(f(x))", route="best")])
    assert b.verdict == "holds"


def test_output_predicates_gated_precisely(tmp_path):
    from mathema.suggest import suggest_claims
    mod = _load(tmp_path, '''
        def do_sort(xs: list) -> list:
            """Sequence return."""
            return sorted(xs)
        def find(xs: list, k: float):
            """Has a None-returning path."""
            for x in xs:
                if x == k:
                    return x
            return None
    ''')
    sort_names = {c.name for c in suggest_claims(mod.do_sort)}
    assert "is_sorted_output" in sort_names
    assert "output_never_none" not in sort_names   # no None path
    find_names = {c.name for c in suggest_claims(mod.find)}
    assert "output_never_none" in find_names        # has return None
