# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What the examine route reads, held against a second set of attacks:
writes through the elements of a copy, ndarray rows, methods of an
object the call made, property setters and in-place operators, a
writer handed a caller's file; hidden inputs from a generator seeded
with None and from the order of a set of strings however it was
built; a counter read after the call changes it; a slice of a list is
a copy. A write is never proven state-safe, a hidden input is never
proven deterministic, and a pure function is never falsified."""

import pytest

pytest.importorskip("numpy")

import inspect  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))
import examine_attacks2 as A  # noqa: E402
import examine_closures as C  # noqa: E402
import examine_counter as N  # noqa: E402
import examine_wrappers as W  # noqa: E402

#: decided outside what the examine route reads: threads, coroutines
#: and the result an lru_cache shares between callers
_ELSEWHERE = {"w_thread", "w_asyncio", "r_thread_race", "r_lru_shared",
              "w_class_decorated"}


def _row(fn, statement):
    (p,) = check_conjectures(fn, [claim(statement)])
    return p


def _named(prefix):
    out = []
    for module in (A, C, N, W):
        for name, fn in sorted(vars(module).items()):
            if callable(fn) and name.startswith(prefix) \
                    and name not in _ELSEWHERE and not inspect.isclass(fn):
                out.append(pytest.param(fn, id=f"{module.__name__}.{name}"))
    return out


@pytest.mark.parametrize("fn", _named("w_"))
def test_a_write_is_never_proven_state_safe(fn):
    p = _row(fn, "is_state_safe(f)")
    assert p.verdict != "proven", (p.sketch,)


@pytest.mark.parametrize("fn", _named("r_"))
def test_a_hidden_input_is_never_proven_deterministic(fn):
    p = _row(fn, "is_deterministic(f)")
    assert p.verdict != "proven", (p.sketch,)


@pytest.mark.parametrize("fn", _named("p_"))
def test_a_pure_function_is_never_falsified(fn):
    for statement in ("is_state_safe(f)", "is_deterministic(f)"):
        p = _row(fn, statement)
        assert p.verdict != "falsified", (statement, p.counterexample)


@pytest.mark.parametrize("fn", [N.w_global_counter, C.w_counter],
                         ids=lambda f: f.__name__)
def test_a_counter_the_call_changes_and_reads_falsifies_determinism(fn):
    p = _row(fn, "is_deterministic(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "which the call also changes" in p.counterexample, p.counterexample


@pytest.mark.parametrize("fn, site", [
    (A.w_list_copy_elem, "changes an element of its argument xs"),
    (A.w_shallow_copy_elem, "changes an element of its argument xs"),
    (A.w_sorted_elem, "changes an element of its argument xs"),
    (A.w_dict_values_list, "changes an element of its argument d"),
    (A.w_row_iadd, "changes an element of its argument a"),
    (A.w_fresh_method_global, "leak changes the module-level LOG"),
    (A.w_fresh_method_argwrite, "passes its argument xs to absorb"),
    (A.w_property_setter, "changes the module-level LOG"),
    (A.w_iadd_fresh, "changes the module-level LOG"),
    (A.w_json_dump, "its argument fp"),
    (W.w_cache_writer, "changes the module-level _LOG"),
])
def test_a_write_it_follows_falsifies_with_the_site(fn, site):
    p = _row(fn, "is_state_safe(f)")
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    assert site in p.counterexample, (fn.__name__, p.counterexample)


@pytest.mark.parametrize("fn", [A.r_random_none, A.r_default_rng_none,
                                A.r_default_rng_none_pos],
                         ids=lambda f: f.__name__)
def test_a_generator_seeded_with_none_reads_fresh_entropy(fn):
    p = _row(fn, "is_deterministic(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "with no seed" in p.counterexample, p.counterexample


@pytest.mark.parametrize("fn", [A.r_set_from_list, A.r_set_from_list_for,
                                A.r_str_of_set, A.r_fstring_set,
                                A.r_set_union, C.r_split_set],
                         ids=lambda f: f.__name__)
def test_the_order_of_any_set_of_strings_leaves_determinism_unknown(fn):
    p = _row(fn, "is_deterministic(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch)
    assert "set of strings" in p.note, p.note


@pytest.mark.parametrize("fn", [A.p_slice_copy_append, A.p_copy_slice_extend],
                         ids=lambda f: f.__name__)
def test_a_slice_of_a_list_is_a_copy(fn):
    p = _row(fn, "is_state_safe(f)")
    assert (p.verdict, p.route) == ("proven", "examine"), (p.verdict, p.note)
