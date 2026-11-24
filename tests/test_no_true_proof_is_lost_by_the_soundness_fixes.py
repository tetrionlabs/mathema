# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Base against head for the soundness fixes of this release. Each row
of `TRUE` is a claim that is true of its function, with the verdict
the release before these fixes gave it: the verdict now is at least as
strong. Each row of `FALSE` is a false claim one step beside a true
one, and stays falsified.

Three rows were proven before the fixes, lost to the reading of a
`None` or nan argument, and are proven again. `for x in [0, 1],
f(x, nan) == 0`: the function never reads the parameter given nan, so
derive reads the rest of the claim. `for x in {1}, f(nan, 0.5) == 1`
and `for x in {1}, f(None, 0.5) == 1`: the call is run at that point
with the value passed as itself."""
import importlib

import pytest

from mathema.conjecture import check_conjectures, claim

_STRENGTH = ("falsified", "unknown", "holds", "proven")


def one_unless_y_is_a_number(x, y=0.0):
    if y != y:
        return 1.0
    return 0.0


#: module, function, claim, the verdict before the fixes
TRUE = [
    # test_a_call_passing_a_literal_none_is_decided_by_running_it
    ('test_a_call_passing_a_literal_none_is_decided_by_running_it',
     'one_at_none',
     'for x in {1}, f(None, 0.5) == 1', 'proven'),
    ('test_a_call_passing_a_literal_none_is_decided_by_running_it',
     'one_at_none',
     'for x in {1}, f(2, 0.5) == 0', 'proven'),
    # test_a_negation_is_never_proven_from_a_disproof_read_from_source
    ('test_a_negation_is_never_proven_from_a_disproof_read_from_source',
     'writes_past_a_half',
     'not is_state_safe(f)', 'proven'),
    ('test_a_negation_is_never_proven_from_a_disproof_read_from_source',
     'writes_past_ten',
     'not is_state_safe(f)', 'proven'),
    ('test_a_negation_is_never_proven_from_a_disproof_read_from_source',
     'writes_past_a_half',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    # test_is_defined_runs_every_listed_missing_value
    ('test_is_defined_runs_every_listed_missing_value',
     'doubled',
     'for x in {None}, not is_defined(f)', 'falsified'),
    ('test_is_defined_runs_every_listed_missing_value',
     'doubled',
     'for x in {1, None}, not is_defined(f)', 'falsified'),
    ('test_is_defined_runs_every_listed_missing_value',
     'doubled_or_zero',
     'for x in {1, None}, is_defined(f)', 'proven'),
    ('test_is_defined_runs_every_listed_missing_value',
     'doubled',
     'for x in [0, 1], is_defined(f)', 'proven'),
    # test_is_empty_safe_runs_every_empty_value_the_parameter_admits
    ('test_is_empty_safe_runs_every_empty_value_the_parameter_admits',
     'mean_or_zero',
     'is_empty_safe(xs)', 'proven'),
    ('test_is_empty_safe_runs_every_empty_value_the_parameter_admits',
     'log_of_head',
     'is_empty_safe(xs)', 'falsified'),
    # test_a_write_in_unreachable_code_leaves_the_function_state_safe
    ('test_a_write_in_unreachable_code_leaves_the_function_state_safe',
     'never_writes',
     'for x in [0, 1], is_state_safe(f)', 'falsified'),
    ('test_a_write_in_unreachable_code_leaves_the_function_state_safe',
     'never_writes',
     'is_state_safe(f)', 'falsified'),
    ('test_a_write_in_unreachable_code_leaves_the_function_state_safe',
     'writes_past_ten',
     'for x in [0, 1], is_state_safe(f)', 'falsified'),
    ('test_a_write_in_unreachable_code_leaves_the_function_state_safe',
     'never_writes',
     'for x in [0, 1], is_deterministic(f)', 'falsified'),
    # test_the_safety_gate_is_no_stronger_than_its_weakest_stated_row
    ('test_the_safety_gate_is_no_stronger_than_its_weakest_stated_row',
     'refuses_missing',
     'is_missing_safe(f)', 'proven'),
    # test_excluded_outside_domain_needs_mathemas_own_wrapper
    ('test_excluded_outside_domain_needs_mathemas_own_wrapper',
     'guarded_doubled',
     'for x in [0, 1], excluded_outside_domain(x)', 'proven'),
    # test_unreachable_code_is_read_only_from_a_parameter_against_a_literal
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'joined_by_and',
     'for x in [0, 1], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'joined_by_or',
     'for x in [0, 5], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'negated',
     'for x in [0, 1], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'after_a_live_branch',
     'for x in [0, 1], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'two_copies_under_the_same_test',
     'for x in [0, 1], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'rebound_before_the_test',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'never_writes',
     'for x in [0, 1], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'never_writes',
     'is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'never_writes',
     'for x in [0, 1], is_deterministic(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'never_writes_in_an_inner_function',
     'for x in [0, 1], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'past_ten',
     'for x in [0, 5], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'past_ten',
     'for x in [0, 5], is_deterministic(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'literal_on_the_left',
     'for x in [0, 5], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'below_a_negative_literal',
     'for x in [0, 5], is_state_safe(f)', 'falsified'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'always_writes',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'past_ten',
     'for x in [0, 20], not is_state_safe(f)', 'proven'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'past_ten',
     'not is_state_safe(f)', 'proven'),
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'else_a_nan_takes',
     'for x in [0, 5], not is_state_safe(f)', 'proven'),
    # test_verdicts_beside_the_false_proofs_fixed
    ('test_verdicts_beside_the_false_proofs_fixed',
     'one_at_nan',
     'for x in {1}, f(nan, 0.5) == 1', 'proven'),
    ('test_verdicts_beside_the_false_proofs_fixed',
     'one_at_nan',
     'for x in [0, 1], f(x, nan) == 0', 'proven'),
    ('test_verdicts_beside_the_false_proofs_fixed',
     'mean_union_guarded',
     'is_empty_safe(xs)', 'proven'),
    ('test_verdicts_beside_the_false_proofs_fixed',
     'mean_list',
     'is_empty_safe(xs)', 'proven'),
    ('test_verdicts_beside_the_false_proofs_fixed',
     'wide',
     'for x in [0, 100], excluded_outside_domain(x)', 'proven'),
    ('test_verdicts_beside_the_false_proofs_fixed',
     'wide',
     'for x in [0, 200], excluded_outside_domain(x)', 'proven'),
    ('test_verdicts_beside_the_false_proofs_fixed',
     'wide',
     'excluded_outside_domain(x)', 'proven'),
    ('test_verdicts_beside_the_false_proofs_fixed',
     'exact',
     'for x in [0, 1], excluded_outside_domain(x)', 'proven'),
    ('test_verdicts_beside_the_false_proofs_fixed',
     'guarded',
     'for x in {1, None}, y in {0.65}, is_defined(f)', 'proven'),
    # test_unreachable_code_is_read_only_from_a_parameter_against_a_literal
    ('test_unreachable_code_is_read_only_from_a_parameter_against_a_literal',
     'draws',
     'for x in [0, 1], not is_deterministic(f)', 'proven'),
    # test_a_witness_call_runs_in_a_child_process
    ('test_a_witness_call_runs_in_a_child_process',
     'always_writes',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    ('test_a_witness_call_runs_in_a_child_process',
     'counts',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    ('test_a_witness_call_runs_in_a_child_process',
     'draws',
     'for x in [0, 1], not is_deterministic(f)', 'proven'),
    ('test_a_witness_call_runs_in_a_child_process',
     'writes_past_a_half',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    # test_no_true_proof_is_lost_by_the_soundness_fixes
    ('test_no_true_proof_is_lost_by_the_soundness_fixes',
     'one_unless_y_is_a_number',
     'for x in [0, 1], f(x, nan) == 1', 'holds'),
]

#: module, function, claim: false, and falsified
FALSE = [
    ("test_verdicts_beside_the_false_proofs_fixed",
     "one_at_nan",
     "for x in {1}, f(nan, 0.5) == 0"),
    ("test_verdicts_beside_the_false_proofs_fixed",
     "one_at_nan",
     "for x in {1}, f(x=nan, y=0.5) == 0"),
    ("test_a_call_passing_a_literal_none_is_decided_by_running_it",
     "one_at_none",
     "for x in {1}, f(None, 0.5) == 0"),
    ("test_no_true_proof_is_lost_by_the_soundness_fixes",
     "one_unless_y_is_a_number",
     "for x in [0, 1], f(x, nan) == 0"),
    ("test_no_true_proof_is_lost_by_the_soundness_fixes",
     "one_unless_y_is_a_number",
     "for x in {1}, f(x, nan) == 0"),
]


def _strength(verdict: str) -> int:
    return _STRENGTH.index(verdict) if verdict in _STRENGTH else 1


def _row(module, function, text):
    fn = (globals()[function] if module == __name__.rpartition(".")[2]
          else getattr(importlib.import_module(module), function))
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


@pytest.mark.parametrize("module, function, text, before", TRUE)
def test_a_true_claim_is_no_weaker_than_before_the_fixes(module, function,
                                                         text, before):
    p = _row(module, function, text)
    assert _strength(p.verdict) >= _strength(before), \
        (p.verdict, before, p.route, p.sketch, p.note)


@pytest.mark.parametrize("module, function, text", FALSE)
def test_a_false_claim_beside_a_true_one_stays_falsified(module, function,
                                                         text):
    p = _row(module, function, text)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)


def test_the_proofs_a_none_or_nan_argument_lost_are_proven_again():
    p = _row("test_verdicts_beside_the_false_proofs_fixed", "one_at_nan",
             "for x in [0, 1], f(x, nan) == 0")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.route)
    p = _row("test_verdicts_beside_the_false_proofs_fixed", "one_at_nan",
             "for x in {1}, f(nan, 0.5) == 1")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), \
        (p.verdict, p.route)
    p = _row("test_a_call_passing_a_literal_none_is_decided_by_running_it",
             "one_at_none", "for x in {1}, f(None, 0.5) == 1")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), \
        (p.verdict, p.route)
