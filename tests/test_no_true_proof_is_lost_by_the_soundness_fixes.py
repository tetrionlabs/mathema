# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Base against head for the soundness fixes of this release. Each row
of `TRUE` is a claim that is true of its function, with the verdict
the release before these fixes gave it: the verdict now is at least as
strong. Each row of `FALSE` is a false claim one step beside a true
one, and stays falsified. Each row of `NOT_PROVEN` is a false claim one
step beside a proof (the write never runs over the domain, or the
statement changes nothing), and is not proven. Each row of `EXCEPTIONS`
is a true claim that was proven before and is unknown now, with the
reason the row gives: the function cannot be run contained, the run
did not finish within its budget, the function opens a file for
writing and file writers are not run, what it writes is not something
a child process's witness watches, the value it changes is larger than
the comparison's budget, is an object whose class defines how its
attributes are read, or keeps state the comparison cannot read (a
generator, a numpy array of objects), or the witness search reached its budget of
points before the member that writes.

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


_log: list = []
_HERE = "test_no_true_proof_is_lost_by_the_soundness_fixes"
_SOURCE = "test_a_write_every_call_makes_is_read_from_the_source"
_NUMBERS = "test_a_parameter_the_claim_binds_to_numbers_is_drawn_as_a_number"
_LET = "test_a_let_bound_function_passed_as_an_argument_is_itself"
_CHILD = "test_a_witness_call_runs_in_a_child_process"
_SHOWN = "test_a_witness_names_what_changed_and_shows_no_value"
_ENDS = "test_an_enforced_domain_inside_the_claims_is_read_with_exact_ends"
_EMPTY = "test_is_empty_safe_runs_every_empty_value_the_parameter_admits"
_STATE = "test_is_state_safe_sees_process_state"
_HOLD = "test_a_witness_reads_values_by_what_they_hold"
_ST = "for x in [0, 1], not is_state_safe(f)"
_ND = "for x in [0, 1], not is_deterministic(f)"
_MEMBERS = "{" + ", ".join(str(k) for k in range(5000)) + "}"
_OVER_BUDGET = ("the comparison's budget of 1000000 values was reached "
                "before all of it was read")
_POINTS_BUDGET = ("the budget of 24 points was reached before the search "
                  "was done, and 24 of the 5000 members of the claim's set "
                  "were tried")
_READS_ITSELF = ("could not be compared before and after the call (an "
                 "object has a class that defines how its attributes are "
                 "read)")
_FILE = ("a file is opened for writing; whether it is changed is not decided "
         "without running, and file writers are not run")
_LOCAL_REASON = ("f cannot be run contained (it is defined inside another "
                 "function")
_UNWATCHED = ("the positive claim is falsified only from the source, and "
              "that line was not executed, so its negation is not proven")


def one_unless_y_is_a_number(x, y=0.0):
    if y != y:
        return 1.0
    return 0.0


def _local_functions() -> dict:
    def appends_past_a_half(x):
        if x > 0.5:
            _log.append(x)
        return x * 2.0

    def appends_where_the_square_is_large(x):
        if x * x > 100.0:
            _log.append(x)
        return x * 2.0

    def draws_locally(x):
        import random
        return x + random.random()

    def sets_the_environment_locally(x):
        import os
        os.environ["MATHEMA_TEST_NO_PROOF_LOST_NOT_RUN"] = "1"
        return x * 2.0

    return {fn.__name__: fn for fn in (
        appends_past_a_half, appends_where_the_square_is_large,
        draws_locally, sets_the_environment_locally)}


_LOCAL = _local_functions()


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
    # a write read from the source where no call is run
    (_SOURCE, 'sets_the_environment',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SOURCE, 'imports_then_sets_the_environment',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SOURCE, 'sets_past_a_half',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SOURCE, 'sets_past_a_half',
     'not is_state_safe(f)', 'proven'),
    (_SOURCE, 'sets_in_the_else',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SOURCE, 'sets_in_a_band',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SOURCE, 'sets_after_a_division',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SOURCE, 'sets_after_an_early_return',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_CHILD, 'sets_the_environment',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    # a write before a raise, integer points, every member of a set
    (_SHOWN, 'writes_then_raises',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SHOWN, 'always_writes',
     'for x in Z, not is_state_safe(f)', 'proven'),
    (_SHOWN, 'always_writes',
     'for x in N, not is_state_safe(f)', 'proven'),
    (_SHOWN, 'writes_past_three_tenths',
     'for x in Z, not is_state_safe(f)', 'proven'),
    (_SHOWN, 'writes_past_three_tenths',
     'for x in {0, 1}, not is_state_safe(f)', 'proven'),
    (_SHOWN, 'writes_past_two',
     'for x in {0, 1, 2, 3}, not is_state_safe(f)', 'proven'),
    (_SHOWN, 'writes_below_a_half_chained',
     'for x in (0, 1], not is_state_safe(f)', 'proven'),
    # process state the child has its own copy of
    (_SHOWN, 'draws_and_drops',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SHOWN, 'prints_a_line',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SHOWN, 'sets_a_module_entry',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    # an object whose state changed, compared by what it holds
    (_SHOWN, 'moves_the_point',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    (_SHOWN, 'a_later_point_after_reading_the_clock',
     'for x in [0, 1], not is_deterministic(f)', 'proven'),
    # an enforced domain inside the claim's, ends read exactly
    (_ENDS, 'two_points',
     'for x in [0, 1], excluded_outside_domain(x)', 'proven'),
    (_ENDS, 'two_points',
     'for x in [0, 100], excluded_outside_domain(x)', 'proven'),
    (_ENDS, 'two_points',
     'for x in {0, 1}, excluded_outside_domain(x)', 'proven'),
    (_ENDS, 'opened',
     'for x in [0, 1], excluded_outside_domain(x)', 'proven'),
    (_ENDS, 'open_above',
     'for x in [0, 1], excluded_outside_domain(x)', 'proven'),
    (_ENDS, 'closed',
     'for x in [0, 1], excluded_outside_domain(x)', 'proven'),
    # every empty value of a union handled
    (_EMPTY, 'size_ratio_or_zero_text', 'is_empty_safe(xs)', 'proven'),
    (_EMPTY, 'size_ratio_or_zero_many', 'is_empty_safe(xs)', 'proven'),
    (_HERE, 'appends_past_a_half',
     'for x in [0, 1], not is_state_safe(f)', 'proven'),
    # a marked parameter the claim binds to numbers
    (_NUMBERS, 'plus_one_finite',
     'for x in [0, 5], f(x) == x + 1', 'falsified'),
    (_NUMBERS, 'plus_one_finite',
     'for x in {0, 1, 2.5}, f(x) == x + 1', 'falsified'),
    (_NUMBERS, 'plus_one_finite',
     'for x in R, f(x) == x + 1', 'falsified'),
    # a let-bound function passed as an argument
    (_LET, 'describe',
     f'let stage = {_LET}.halve, describe(stage) == "(float) -> float"',
     'falsified'),
    (_LET, 'halve',
     f'let g = {_LET}.also_halve, for x in [0, 1], f(x) == g(x)', 'proven'),
    # a type named at run time, said as an object
    (_HOLD, 'rebinds_to_a_type_named_at_run_time', _ST, 'proven'),
    (_HOLD, 'rebinds_to_a_qualname_set_at_run_time', _ST, 'proven'),
    (_HOLD, 'rebinds_to_a_name_set_at_run_time', _ST, 'proven'),
    (_HOLD, 'rebinds_to_a_module_set_at_run_time', _ST, 'proven'),
    (_HOLD, 'appends_a_named_object', _ST, 'proven'),
    (_HOLD, 'enters_a_named_object', _ST, 'proven'),
    (_HOLD, 'returns_a_named_object_with_a_draw', _ND, 'proven'),
    # standard-library values, read by their contents
    (_HOLD, 'appends_to_a_deque', _ST, 'proven'),
    (_HOLD, 'sets_an_ordered_entry', _ST, 'proven'),
    (_HOLD, 'moves_an_ordered_entry_to_the_end', _ST, 'unknown'),
    (_HOLD, 'binds_a_decimal', _ST, 'proven'),
    (_HOLD, 'binds_a_date', _ST, 'proven'),
    (_HOLD, 'appends_to_an_array', _ST, 'proven'),
    (_HOLD, 'binds_a_pattern', _ST, 'proven'),
    (_HOLD, 'appends_to_a_large_list', _ST, 'proven'),
    (_HOLD, 'appends_to_a_list_that_holds_itself', _ST, 'proven'),
    (_HOLD, 'makes_a_list_hold_itself', _ST, 'proven'),
    (_HOLD, 'rebinds_to_a_stateless_named_object', _ST, 'proven'),
    (_HOLD, 'returns_a_deque_of_a_draw', _ND, 'proven'),
    (_HOLD, 'returns_a_list_of_a_draw_that_holds_itself', _ND, 'proven'),
    # a write at a member a guard names, over a large set
    (_HOLD, 'writes_at_the_last_member',
     f'for x in {_MEMBERS}, not is_state_safe(f)', 'proven'),
    (_HOLD, 'writes_past_a_late_member',
     f'for x in {_MEMBERS}, not is_state_safe(f)', 'proven'),
    (_HOLD, 'writes_at_a_middle_member',
     f'for x in {_MEMBERS}, not is_state_safe(f)', 'proven'),
    # a named set enforced, read as the claims read it
    (_ENDS, 'over_the_reals', 'for x in R, excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_reals', 'for x in (-oo, oo), excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_integers', 'for x in Z, excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_integers', 'for x in R, excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_integers',
     'for x in (-oo, oo), excluded_outside_domain(x)', 'proven'),
    (_ENDS, 'over_the_naturals', 'for x in N, excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_naturals', 'for x in Z, excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_naturals', 'for x in R, excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_naturals', 'for x in [0, oo), excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_naturals', 'for x in [0, inf), excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_naturals', 'for x in [0, inf], excluded_outside_domain(x)',
     'proven'),
    (_ENDS, 'over_the_naturals',
     'for x in (-oo, oo), excluded_outside_domain(x)', 'proven'),
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
    (_SOURCE, "sets_past_a_half",
     "for x in [0, 0.25], not is_state_safe(f)"),
    (_NUMBERS, "plus_one_finite", "for x in [0, 5], f(x) == x + 2"),
    (_NUMBERS, "plus_one_finite", "for x in {0, inf}, f(x) == x + 1"),
    (_NUMBERS, "plus_one_finite", "for x in [0, oo], f(x) == x + 1"),
    (_LET, "describe",
     f'let stage = {_LET}.halve, describe(stage) == "(int) -> int"'),
    # the empty value of a union member that the guard does not catch
    (_EMPTY, "size_ratio_text", "is_empty_safe(xs)"),
    (_EMPTY, "size_ratio_dict", "is_empty_safe(xs)"),
    (_EMPTY, "size_ratio_set", "is_empty_safe(xs)"),
    (_EMPTY, "size_ratio_bytes", "is_empty_safe(xs)"),
    (_EMPTY, "size_ratio_bar", "is_empty_safe(xs)"),
    (_EMPTY, "size_ratio_optional", "is_empty_safe(xs)"),
]

#: module, function, claim: false (no call changes anything over the
#: domain), and not proven
NOT_PROVEN = [
    (_SOURCE, "sets_under_arithmetic",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SOURCE, "opens_under_arithmetic",
     "for x in [0, 1], not is_state_safe(f)"),
    # a file opened in a mode or at a path that changes nothing
    (_SOURCE, "opens_to_update",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SOURCE, "opens_what_exists_exclusively",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SOURCE, "opens_in_a_missing_directory",
     "for x in [0, 1], not is_state_safe(f)"),
    # a value written back as it was, an equal object returned twice
    (_SHOWN, "writes_the_point_back",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SHOWN, "writes_the_slot_back",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SHOWN, "binds_a_fresh_nan_list",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SHOWN, "an_equal_point_after_reading_the_clock",
     "for x in [0, 1], not is_deterministic(f)"),
    (_SHOWN, "raises_before_the_write",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SHOWN, "prints_nothing",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SHOWN, "writes_a_module_entry_back",
     "for x in [0, 1], not is_state_safe(f)"),
    (_SHOWN, "writes_past_two",
     "for x in {0, 1, 2}, not is_state_safe(f)"),
    # the wrapper accepts an end the claim's domain leaves out
    (_ENDS, "closed", "for x in (0, 1), excluded_outside_domain(x)"),
    (_ENDS, "closed", "for x in [0, 1), excluded_outside_domain(x)"),
    (_ENDS, "closed", "for x in (0, 1], excluded_outside_domain(x)"),
    (_ENDS, "open_above", "for x in (0, 1), excluded_outside_domain(x)"),
    (_ENDS, "open_below", "for x in (0, 1), excluded_outside_domain(x)"),
    (_SOURCE, "sets_after_a_rebinding",
     "for x in [0, 1], not is_state_safe(f)"),
    (_HERE, "appends_where_the_square_is_large",
     "for x in [0, 1], not is_state_safe(f)"),
    # a standard-library value left as it was
    (_HOLD, "extends_a_deque_by_nothing", _ST),
    (_HOLD, "moves_both_ordered_entries_back", _ST),
    (_HOLD, "writes_a_list_that_holds_itself_back", _ST),
    (_HOLD, "writes_the_box_back", _ST),
    # an object whose class decides how it is read, written as it was
    (_HOLD, "writes_an_attribute_back_beside_a_dict_property", _ST),
    (_HOLD, "writes_a_slot_beside_a_property_shadowing_it", _ST),
    (_HOLD, "returns_an_object_that_reads_itself", _ND),
    # a write at no member of a large set
    (_HOLD, "writes_at_no_member",
     f"for x in {_MEMBERS}, not is_state_safe(f)"),
    # the wrapper admits inf, which the claim's domain leaves out
    (_ENDS, "up_to_infinity", "for x in [0, oo), excluded_outside_domain(x)"),
    (_ENDS, "up_to_infinity", "for x in [0, inf), excluded_outside_domain(x)"),
    (_ENDS, "up_to_infinity",
     "for x in (-oo, oo), excluded_outside_domain(x)"),
    # a named set enforced that admits what the claim's leaves out
    (_ENDS, "over_the_reals", "for x in Z, excluded_outside_domain(x)"),
    (_ENDS, "over_the_integers", "for x in N, excluded_outside_domain(x)"),
]

#: module, function, claim, the verdict before the fixes, the reason
#: the row gives now
EXCEPTIONS = [
    (_HERE, "draws_locally",
     "for x in [0, 1], not is_deterministic(f)", "proven", _LOCAL_REASON),
    # reading alone does not show that an environment item assigned
    # differs from what the variable holds, and no child can import f
    (_HERE, "sets_the_environment_locally",
     "for x in [0, 1], not is_state_safe(f)", "proven", _LOCAL_REASON),
    # a file opened for writing: never run, and the source does not
    # show that the path can be written
    (_SOURCE, "opens_to_write",
     "for x in [0, 1], not is_state_safe(f)", "proven", _FILE),
    (_SOURCE, "opens_to_append",
     "for x in [0, 1], not is_state_safe(f)", "proven", _FILE),
    (_SOURCE, "opens_past_a_half",
     "for x in [0, 1], not is_state_safe(f)", "proven", _FILE),
    (_SOURCE, "opens_past_a_half",
     "not is_state_safe(f)", "proven", _FILE),
    (_SOURCE, "opens_in_the_else",
     "for x in [0, 1], not is_state_safe(f)", "proven", _FILE),
    (_SOURCE, "opens_in_the_else",
     "for x in [0, 0.25], not is_state_safe(f)", "proven", _FILE),
    (_SOURCE, "opens_in_a_band",
     "for x in [0, 1], not is_state_safe(f)", "proven", _FILE),
    (_SOURCE, "opens_after_a_division",
     "for x in [0, 1], not is_state_safe(f)", "proven", _FILE),
    (_SOURCE, "opens_after_an_early_return",
     "for x in [0, 1], not is_state_safe(f)", "proven", _FILE),
    (_CHILD, "writes_a_file",
     "for x in [0, 1], not is_state_safe(f)", "proven", _FILE),
    # process state no witness watches, and a write beside something
    # the examination cannot read: the function is not run
    (_STATE, "change_dir",
     "for x in [0, 1], not is_state_safe(f)", "proven", _UNWATCHED),
    (_STATE, "extend_path",
     "for x in [0, 1], not is_state_safe(f)", "proven", _UNWATCHED),
    (_STATE, "reseed",
     "for x in [0, 1], not is_state_safe(f)", "proven", _UNWATCHED),
    (_STATE, "put_env",
     "for x in [0, 1], not is_state_safe(f)", "proven", _UNWATCHED),
    (_SHOWN, "appends_after_an_exec",
     "for x in [0, 1], not is_state_safe(f)", "proven", _UNWATCHED),
    (_CHILD, "writes_then_never_returns",
     "for x in [0, 1], not is_state_safe(f)", "proven",
     "the run did not finish within its budget"),
    # a value larger than the comparison's budget
    (_HOLD, "appends_to_a_list_over_the_budget", _ST, "proven", _OVER_BUDGET),
    # a write at a member no guard names, past the budget of points
    (_HOLD, "writes_where_arithmetic_picks_a_member",
     f"for x in {_MEMBERS}, not is_state_safe(f)", "proven", _POINTS_BUDGET),
    # an object whose class decides how its attributes are read
    (_HOLD, "rebinds_to_an_object_that_reads_itself", _ST, "proven",
     _READS_ITSELF),
    # state the comparison cannot read: a generator, an array of objects
    (_HOLD, "rebinds_to_a_generator", _ST, "proven",
     "(a generator object keeps state the comparison cannot read)"),
    (_HOLD, "writes_into_an_array_of_objects", _ST, "proven",
     "(it is a numpy array of objects)"),
]


def _strength(verdict: str) -> int:
    return _STRENGTH.index(verdict) if verdict in _STRENGTH else 1


def _row(module, function, text):
    if module == _HERE:
        fn = _LOCAL.get(function) or globals()[function]
    else:
        fn = getattr(importlib.import_module(module), function)
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


@pytest.mark.parametrize("module, function, text", NOT_PROVEN)
def test_a_claim_beside_a_proof_is_not_proven(
        module, function, text):
    p = _row(module, function, text)
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch, p.note)


@pytest.mark.parametrize("module, function, text, before, reason", EXCEPTIONS)
def test_a_recorded_exception_is_unknown_with_its_reason(
        module, function, text, before, reason, monkeypatch):
    from mathema import _contained
    monkeypatch.setattr(_contained, "FAILSAFE_WALL_CLOCK_SECONDS", 4)
    p = _row(module, function, text)
    assert before == "proven"
    assert p.verdict == "unknown", (p.verdict, p.route, p.sketch, p.note)
    assert reason in (p.note or ""), p.note


def test_a_marked_parameter_bound_to_numbers_is_proven_as_the_unmarked_is():
    marked = _row(_NUMBERS, "plus_one_finite", "for x in [0, 5], f(x) == x + 1")
    unmarked = _row(_NUMBERS, "plus_one", "for x in [0, 5], f(x) == x + 1")
    assert (marked.verdict, marked.route) == (unmarked.verdict, unmarked.route) \
        == ("proven", "derive"), (marked.verdict, marked.route, marked.note)


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
