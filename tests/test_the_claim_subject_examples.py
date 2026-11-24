# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The lexicon's claim-subject examples: a function, a method with its
state written out, a pipeline, a tool, a config file and a module, each
as a map from a stated domain to a codomain. A row that is adjudicated
today lands on its pinned verdict, the true claim and its false twin
both; a form that is not accepted yet is pinned to what mathema says of
it today, the exact refusal or the verdict, beside the verdict it is to
land on."""
import importlib.util
import inspect

import pytest

from mathema import lexicon
from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.lexicon import CLAIM_SUBJECT_ROWS, FORMS_NOT_YET_ACCEPTED

#: the rows over a record language, adjudicated only with
#: `mathema-language` installed
_LANGUAGE_ROWS = ("subject_config_record", "subject_config_record_trap")

#: the verdict every adjudicated row lands on, or
#: `(verdict, text the witness contains)`
PINNED: dict = {
    "subject_function": "proven",
    "subject_function_trap": ("falsified", "x = "),
    "subject_method_state": "holds",
    "subject_method_state_funded": "proven",
    "subject_method_state_refusal": "holds",
    "subject_method_state_trap": ("falsified", "raised ValueError"),
    "subject_pipeline": "proven",
    "subject_pipeline_trap": ("falsified", "percent = "),
    "subject_pipeline_pointwise": "proven",
    "subject_pipeline_pointwise_trap": ("falsified", "percent = "),
    "subject_config_record": "proven",
    "subject_config_record_trap": ("falsified", "'jobs': 5"),
}

_VERDICTS = ("proven", "holds", "falsified")


def _adjudicated(function: str, text: str):
    """The row for `text` checked against the example function named."""
    row = claim(text)
    (p,) = [q for q in check_conjectures(getattr(lexicon, function), [row])
            if q.name == row.name]
    return p


def test_every_adjudicated_row_is_pinned_and_every_true_claim_has_a_false_twin():
    assert set(PINNED) == set(CLAIM_SUBJECT_ROWS)
    traps = {key for key in CLAIM_SUBJECT_ROWS if key.endswith("_trap")}
    for key in traps:
        assert key[:-len("_trap")] in CLAIM_SUBJECT_ROWS, key
        assert PINNED[key][0] == "falsified", key
    for key in set(CLAIM_SUBJECT_ROWS) - traps:
        assert PINNED[key] in ("proven", "holds"), key
    for subject in ("function", "method_state", "pipeline", "config_record"):
        assert f"subject_{subject}_trap" in traps, subject


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("key", list(CLAIM_SUBJECT_ROWS))
def test_an_adjudicated_row_lands_on_its_pinned_verdict(key):
    if key in _LANGUAGE_ROWS:
        pytest.importorskip("mathema_language")
    function, text = CLAIM_SUBJECT_ROWS[key]
    want = PINNED[key]
    verdict, witness = (want, None) if isinstance(want, str) else want
    p = _adjudicated(function, text)
    assert p.verdict == verdict, (p.verdict, p.note)
    if witness is not None:
        assert witness in str(p.counterexample), p.counterexample


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("key", list(FORMS_NOT_YET_ACCEPTED))
def test_a_form_not_yet_accepted_is_pinned_to_what_mathema_says_today(key):
    form = FORMS_NOT_YET_ACCEPTED[key]
    kind, _, text = form.today.partition(": ")
    if kind == "refused":
        with pytest.raises(InvalidConjecture) as refusal:
            claim(form.wanted)
        assert str(refusal.value) == text
    else:
        assert kind in _VERDICTS, form.today
        p = _adjudicated(form.function, form.wanted)
        assert p.verdict == kind, (p.verdict, p.note)
        assert text in str(p.counterexample), p.counterexample


def test_a_form_not_yet_accepted_states_the_verdict_it_is_to_land_on():
    for key, form in FORMS_NOT_YET_ACCEPTED.items():
        assert form.expected in _VERDICTS, key
        assert hasattr(lexicon, form.function), key
        if key.endswith("_trap"):
            assert form.expected == "falsified" and form.witness, key
            assert key[:-len("_trap")] in FORMS_NOT_YET_ACCEPTED, key
        else:
            assert form.expected in ("proven", "holds"), key
            assert form.expected != form.today.partition(": ")[0], key


def test_every_line_of_the_two_tables_is_marked_draft():
    lines = inspect.getsource(lexicon).splitlines()
    for name in ("CLAIM_SUBJECT_ROWS", "FORMS_NOT_YET_ACCEPTED"):
        start = next(i for i, line in enumerate(lines)
                     if line.startswith(f"{name}: dict"))
        end = next(i for i in range(start, len(lines))
                   if lines[i].startswith("}"))
        unmarked = [line for line in lines[start:end + 1]
                    if not line.rstrip().endswith("# :draft")]
        assert not unmarked, (name, unmarked)


def test_the_tables_stay_out_of_the_lexicon_proper():
    held_apart = set(CLAIM_SUBJECT_ROWS) | set(FORMS_NOT_YET_ACCEPTED)
    assert not held_apart & set(lexicon.LEXICON)
    assert not set(CLAIM_SUBJECT_ROWS) & set(FORMS_NOT_YET_ACCEPTED)


# --- the example functions, and what the expected verdicts rest on --------

def test_clamp_holds_a_value_to_its_interval():
    assert lexicon.clamp(5.0, 0.0, 2.0) == 2.0
    assert lexicon.clamp(-5.0, 0.0, 2.0) == 0.0
    assert lexicon.clamp(1.5, 0.0, 2.0) == 1.5


def test_withdraw_gives_the_new_balance_or_refuses():
    assert lexicon.withdraw(100.0, 30.0) == 70.0
    assert lexicon.withdraw(30.0, 30.0) == 0.0
    with pytest.raises(ValueError, match="insufficient funds"):
        lexicon.withdraw(30.0, 30.5)


def test_the_pipeline_is_its_two_stages_composed():
    transform, load = lexicon.PIPELINE_STAGES
    for percent in (0.0, 5.0, 12.5, 100.0):
        assert lexicon.growth_factor_pipeline(percent) == load(transform(percent))
    assert lexicon.growth_factor_misread(5.0) == 6.0


def test_describe_over_each_named_collection_member_by_member():
    """The complete enumeration the two collection claims are to be
    decided by: every stage is described the same way, and `clamp` is
    the member of the wider collection that is not."""
    assert {lexicon.describe(fn) for fn in lexicon.PIPELINE_STAGES} == {
        "(float) -> float"}
    trap = FORMS_NOT_YET_ACCEPTED["subject_tool_collection_trap"]
    assert lexicon.describe(lexicon.clamp) == trap.witness
    assert lexicon.clamp in lexicon.SUBJECT_MAPS
    one = FORMS_NOT_YET_ACCEPTED["subject_tool_one_program"]
    assert lexicon.describe(lexicon.percent_to_fraction) in one.wanted


def test_the_build_config_schema_bounds_the_jobs_a_file_may_ask_for():
    jobs = lexicon.BUILD_CONFIG["properties"]["jobs"]
    assert (jobs["minimum"], jobs["maximum"]) == (1, 8)
    assert lexicon.build_jobs({"jobs": 5}) == 5


def _public_functions(module_name: str) -> list:
    module = importlib.import_module(module_name)
    return [fn for name, fn in vars(module).items()
            if not name.startswith("_") and inspect.isfunction(fn)
            and fn.__module__ == module_name]


def test_the_module_examples_one_public_function_at_a_time():
    """What the two module claims are to be decided by: `is_deterministic`
    on each public function, which mathema reads from the source."""
    row = claim("is_deterministic(f)")
    for fn in _public_functions("mathema._deprecation"):
        (p,) = check_conjectures(fn, [row])
        assert p.verdict == "proven", (fn.__name__, p.note)
    (p,) = check_conjectures(lexicon.noisy_quote, [row])
    trap = FORMS_NOT_YET_ACCEPTED["subject_module_public_trap"]
    assert p.verdict == "falsified" and trap.witness in str(p.counterexample)
    assert lexicon.noisy_quote in _public_functions("mathema.lexicon")
