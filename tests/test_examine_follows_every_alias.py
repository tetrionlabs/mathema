# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The examine route never proves what it cannot follow. A write
through an alias it tracks (a container holding the argument,
unpacking, a loop target, an assignment expression, a conditional
expression, a helper that returns its argument) falsifies, or leaves
the row unknown with the reason where the object only may be the
argument; a write it cannot attribute (a
`functools.partial` of a writer) is unknown. A class attribute is
module-level state, a decorator's own body is examined with the
function, a generator built with no seed reads fresh entropy, and the
iteration order of a set of strings changes from one process to the
next. A pure function is never falsified."""
import inspect
import os
import sys

import pytest

from mathema.conjecture import check_conjectures, claim

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))
import examine_attacks as A  # noqa: E402


def _row(fn, statement):
    (p,) = check_conjectures(fn, [claim(statement)])
    return p


def _named(prefix):
    return [fn for name, fn in sorted(vars(A).items())
            if inspect.isfunction(fn) and name.startswith(prefix)
            and fn.__module__ == A.__name__]


@pytest.mark.parametrize("fn", _named("w_"), ids=lambda f: f.__name__)
def test_a_write_is_never_proven_state_safe(fn):
    p = _row(fn, "is_state_safe(f)")
    assert p.verdict != "proven", (fn.__name__, p.sketch)
    assert p.route == "examine"


@pytest.mark.parametrize("fn", _named("r_"), ids=lambda f: f.__name__)
def test_a_hidden_input_is_never_proven_deterministic(fn):
    p = _row(fn, "is_deterministic(f)")
    assert p.verdict != "proven", (fn.__name__, p.sketch)


@pytest.mark.parametrize("fn", _named("p_"), ids=lambda f: f.__name__)
def test_a_pure_function_is_never_falsified(fn):
    for statement in ("is_state_safe(f)", "is_deterministic(f)"):
        p = _row(fn, statement)
        assert p.verdict != "falsified", (fn.__name__, statement,
                                          p.counterexample)


@pytest.mark.parametrize("fn, site", [
    (A.w_tuple_unpack, "changes its argument xs (a.append(1.0))"),
    (A.w_walrus, "changes its argument xs"),
    (A.w_cond_alias, "changes its argument xs (y.append(1.0))"),
    (A.w_dict_alias, "changes its argument xs (d['k'].append(1.0))"),
    (A.w_for_alias, "changes its argument xs (y.append(1.0))"),
    (A.w_return_alias, "changes its argument xs (y.append(1.0))"),
    (A.w_element_of_argument, "changes an element of its argument rows"),
    (A.w_class_attr, "changes the class Counter (Counter.n += 1)"),
    (A.w_decorated, "changes the module-level _COUNT"),
    (A.w_np_ravel, "changes its argument a (np.ravel(a)[0] = ...)"),
])
def test_a_write_it_follows_falsifies_with_the_site(fn, site):
    p = _row(fn, "is_state_safe(f)")
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    assert site in p.counterexample, (fn.__name__, p.counterexample)


@pytest.mark.parametrize("fn, reason", [
    (A.w_partial, "calls p, an object mathema cannot follow"),
])
def test_a_write_it_cannot_attribute_is_unknown_with_the_reason(fn, reason):
    p = _row(fn, "is_state_safe(f)")
    assert p.verdict == "unknown", (fn.__name__, p.verdict,
                                    p.counterexample)
    assert reason in p.note, (fn.__name__, p.note)


@pytest.mark.parametrize("fn, site", [
    (A.r_unseeded_random_instance, "random.Random() with no seed"),
    (A.r_unseeded_rng, "numpy.random.default_rng() with no seed"),
    (A.r_secrets, "secrets.randbelow"),
    (A.r_system_random, "random.SystemRandom"),
])
def test_a_generator_built_without_a_seed_falsifies_determinism(fn, site):
    p = _row(fn, "is_deterministic(f)")
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    assert site in p.counterexample, (fn.__name__, p.counterexample)


def test_hash_of_a_string_is_unknown_across_processes():
    p = _row(A.r_str_hash, "is_deterministic(f)")
    assert p.verdict == "unknown", p.verdict
    assert "calls hash(), whose value for a string, bytes or an object " \
        "varies across processes" in p.note, p.note
    assert _row(A.r_str_hash, "is_state_safe(f)").verdict == "proven"


def test_a_written_mutable_default_is_state_every_call_shares():
    p = _row(A.w_default_mutable, "is_state_safe(f)")
    assert p.verdict == "falsified"
    assert ("changes its argument cache, whose default every call that "
            "leaves it out shares") in p.counterexample, p.counterexample


@pytest.mark.parametrize("fn", [A.r_set_order, A.r_frozenset_order,
                                A.r_set_loop], ids=lambda f: f.__name__)
def test_iterating_a_set_of_strings_leaves_determinism_unknown(fn):
    p = _row(fn, "is_deterministic(f)")
    assert p.verdict == "unknown", (fn.__name__, p.verdict)
    assert "iteration order of a set of strings varies across processes" \
        in p.note, p.note


@pytest.mark.parametrize("fn", [A.p_int_set_order, A.p_sorted_string_set,
                                A.p_nonlocal, A.p_seeded_rng],
                         ids=lambda f: f.__name__)
def test_what_is_the_same_in_every_process_is_proven(fn):
    for statement in ("is_state_safe(f)", "is_deterministic(f)"):
        p = _row(fn, statement)
        assert (p.verdict, p.route) == ("proven", "examine"), (
            fn.__name__, statement, p.verdict, p.note)


def test_a_proof_over_numpy_says_it_assumes_the_default_error_state():
    p = _row(A.p_sum_vector, "is_deterministic(f)")
    assert p.verdict == "proven"
    assert "it assumes numpy's default error state" in p.sketch, p.sketch
    p = _row(A.p_local_list, "is_deterministic(f)")
    assert "error state" not in p.sketch, p.sketch
