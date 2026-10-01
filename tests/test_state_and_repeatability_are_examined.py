# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_state_safe, is_deterministic, is_reproducible and is_repeatable
are decided by examining the function's source, never by running it.
A write outside the call (through an alias, a local import, a helper,
an in-place method, `out=`, `print`, a draw from a shared generator)
falsifies is_state_safe with the site as the witness; a hidden input
(the environment, the clock, a shared generator) falsifies
is_deterministic; anything the examination cannot read leaves the row
unknown with the reason; a threaded reduction leaves determinism
unknown; and a body with none of these is proven."""
import os
import sys

import pytest

from mathema import check
from mathema.conjecture import check_conjectures, claim

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))
import examined_functions as ex  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _imports_made():
    # a first check imports what the engine needs; an import that sets an
    # environment variable is not the examined function's doing
    check_conjectures(ex.pure, [claim("f(x) >= -1e300")])


def _row(fn, statement):
    (p,) = check_conjectures(fn, [claim(statement)])
    return p


@pytest.mark.parametrize("fn, site", [
    (ex.alias_append, "changes its argument xs (ys.append(1.0))"),
    (ex.env_alias, "changes os.environ"),
    (ex.iadd, "changes its argument xs in place (xs += [1])"),
    (ex.local_import, "changes os.environ"),
    (ex.path_alias, "changes sys.path"),
    (ex.sorts, "changes its argument xs (xs.sort())"),
    (ex.helper_writes, "_bump changes the module-level _COUNT"),
    (ex.ufunc_out, "writes its result into its argument b (out=)"),
    (ex.chdir, "calls os.chdir"),
    (ex.prints, "calls print()"),
    (ex.npdraw, "advances the shared random generator"),
    (ex.rand_alias, "advances the shared random generator"),
    (ex.shuffles, "changes its argument xs"),
    (ex.dead_branch, "changes os.environ"),
])
def test_a_write_outside_the_call_falsifies_with_its_site(fn, site):
    cwd, env = os.getcwd(), dict(os.environ)
    p = _row(fn, "is_state_safe(f)")
    assert (p.verdict, p.route) == ("falsified", "examine"), (
        fn.__name__, p.verdict, p.route, p.note)
    assert site in str(p.counterexample), p.counterexample
    assert os.getcwd() == cwd and dict(os.environ) == env   # never run


@pytest.mark.parametrize("fn", [ex.pure, ex.sorted_copy, ex.recursive,
                                ex.logs, ex.gen, ex.explodes])
def test_a_body_with_no_write_is_proven_without_running_it(fn):
    p = _row(fn, "is_state_safe(f)")
    assert (p.verdict, p.route) == ("proven", "examine"), (
        fn.__name__, p.verdict, p.note)


@pytest.mark.parametrize("fn, reason", [
    (ex.dyn, "calls getattr"),
    (ex.table, "reads the module-level _TABLE"),
    (ex.hostname, "socket.gethostname"),
])
def test_what_cannot_be_read_is_unknown_with_the_reason(fn, reason):
    p = _row(fn, "is_state_safe(f)")
    assert p.verdict == "unknown", (fn.__name__, p.verdict, p.note)
    assert reason in (p.note or ""), p.note


@pytest.mark.parametrize("fn, site", [
    (ex.clock, "calls time.time"),
    (ex.env_read, "reads os.environ"),
    (ex.npdraw, "draws from the shared random generator"),
])
def test_a_hidden_input_falsifies_determinism(fn, site):
    p = _row(fn, "is_deterministic(f)")
    assert (p.verdict, p.route) == ("falsified", "examine"), (
        fn.__name__, p.verdict, p.note)
    assert site in str(p.counterexample), p.counterexample


@pytest.mark.parametrize("fn", [ex.dotted, ex.nplin])
def test_a_threaded_reduction_leaves_determinism_unknown(fn):
    p = _row(fn, "is_deterministic(f)")
    assert p.verdict == "unknown", (fn.__name__, p.verdict, p.note)
    assert "threaded reduction" in (p.note or ""), p.note


def test_a_pure_body_is_deterministic_and_repeatable():
    assert _row(ex.pure, "is_deterministic(f)").verdict == "proven"
    assert _row(ex.pure, "is_repeatable(f)").verdict == "proven"


def test_randomness_through_the_generator_parameter_is_reproducible():
    assert _row(ex.gen, "is_reproducible(f)").verdict == "proven"
    p = _row(ex.rand_alias, "is_reproducible(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_write_falsifies_repeatable():
    p = _row(ex.env_alias, "is_repeatable(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_named_claim_is_examined_too():
    (p,) = check_conjectures(ex.clock, [claim("f(x) == f(x)",
                                              name="is_deterministic")])
    assert (p.verdict, p.route) == ("falsified", "examine"), (p.verdict, p.note)


def test_check_reports_the_examined_row(monkeypatch):
    # other rows of check() run the function; the state row is examined
    monkeypatch.chdir(os.getcwd())
    rows = {p.name: p for p in check(ex.chdir).probes}
    assert (rows["is_state_safe"].verdict,
            rows["is_state_safe"].route) == ("falsified", "examine")


def test_brute_force_never_trusts_a_body_whose_helper_writes_state():
    (p,) = check_conjectures(ex.counted, [claim(
        "for n in [1, 5] subset Z, f(n) >= 1")])
    assert p.route != "derive:brute_force", (p.verdict, p.route)


def test_a_write_in_a_branch_the_domain_never_reaches_still_falsifies():
    p = _row(ex.dead_branch, "for x in [0, 5], is_state_safe(f)")
    assert (p.verdict, p.route) == ("falsified", "examine"), (p.verdict, p.note)
    assert "changes os.environ" in p.counterexample
    assert ("the branch it sits in cannot run over the domain "
            "(x > 10 never holds there)") in p.counterexample, p.counterexample


def test_a_write_in_a_branch_the_domain_reaches_carries_no_dead_branch_note():
    p = _row(ex.dead_branch, "for x in [0, 50], is_state_safe(f)")
    assert p.verdict == "falsified"
    assert "cannot run" not in p.counterexample, p.counterexample


def test_the_else_of_a_branch_the_domain_always_takes_is_named_as_dead():
    p = _row(ex.dead_else, "for x in [0, 5], is_state_safe(f)")
    assert p.verdict == "falsified"
    assert "not (x < 10) never holds there" in p.counterexample, \
        p.counterexample


def test_a_helper_filling_a_list_the_call_made_is_no_write():
    p = _row(ex.fresh_buffer, "is_state_safe(f)")
    assert (p.verdict, p.route) == ("proven", "examine"), (p.verdict, p.note)


@pytest.mark.parametrize("fn, site", [
    (ex.passes_param, "passes its argument xs to _fill, and _fill changes "
                      "its argument buf"),
    (ex.asarray_sort, "changes its argument xs (b.sort())"),
    (ex.branch_rebind, "changes its argument xs (xs.append(1.0))"),
    (ex.np_copyto, "changes its argument xs (np.copyto(xs, 0.0))"),
    (ex.median_overwrite, "reorder its argument xs (overwrite_input=True)"),
    (ex.frame_fill, "changes its argument df in place (inplace=True)"),
])
def test_a_write_through_a_helper_an_alias_or_a_library_writer(fn, site):
    p = _row(fn, "is_state_safe(f)")
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    assert site in p.counterexample, (fn.__name__, p.counterexample)


def test_the_sort_function_returns_a_copy_and_writes_nothing():
    p = _row(ex.np_sort, "is_state_safe(f)")
    assert (p.verdict, p.route) == ("proven", "examine"), (p.verdict, p.note)


def test_a_draw_without_a_seed_is_never_proven_deterministic():
    p = _row(ex.frame_sample, "is_deterministic(f)")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "with no seed" in p.note, p.note
    p = _row(ex.random_rank, "is_deterministic(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ranks ties at random with no seed" in p.counterexample
    p = _row(ex.frame_sample_seeded, "is_deterministic(f)")
    assert (p.verdict, p.route) == ("proven", "examine"), (p.verdict, p.note)
