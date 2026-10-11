# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language may declare how a function refuses a value outside it
(`Refusal`) and what counts as answering a member (`DefinedAnswer`).
`excluded_outside_domain` then checks each outside draw is refused that
way, and `is_language_defined` checks each member gets that answer; the
witness names the declaration and what the call did instead. A
language declaring neither keeps the checks as they were: any raise
refuses, and only an unguarded accidental crash is undefined."""
import argparse
import dataclasses
import random
import sys

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import (DefinedAnswer, HazardValue, Problem, Refusal, StringLanguage,
                               language_problems, register_language,
                               unregister_language)


@dataclasses.dataclass(frozen=True)
class Argv:
    """The argument lists a parser taking one optional `--n INT` admits:
    `[]` and `["--n", <an int>]`."""

    name: str = "argv"
    refusal: "Refusal | None" = None
    defined_answer: "DefinedAnswer | None" = None
    kind = "sequence"
    level = "predicate"

    def contains(self, value):
        if value == []:
            return True
        if not (isinstance(value, list) and len(value) == 2 and value[0] == "--n"):
            return False
        try:
            int(value[1])
        except (TypeError, ValueError):
            return False
        return True

    def explain(self, value):
        return None if self.contains(value) else [Problem("", "--n INT", value)]

    def sample(self, rng):
        return ["--n", str(rng.randint(-9, 9))]

    def members(self, limit):
        return None

    def hazards(self):
        return (HazardValue("empty", [], "no arguments"),
                HazardValue("extremity", ["--n", "-1"], "a negative count"),
                HazardValue("extremity", ["--n", "7"], "a count past five"))

    def outside(self, rng):
        return rng.choice([["--n", "x"], ["--bogus"], ["--n"], ["n", "1"]])

    def shrink(self, value):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return f"L[{self.name}]"

    def to_json(self):
        return {"type": "array", "items": {"type": "string"}}


CLI = Argv("cli_argv", refusal=Refusal.exit(2), defined_answer=DefinedAnswer.exit(0, 1))
PLAIN = Argv("plain_argv")


def setup_module(module):
    register_language("cli_argv", CLI)
    register_language("plain_argv", PLAIN)


def teardown_module(module):
    unregister_language("cli_argv")
    unregister_language("plain_argv")


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="best")])
    return p


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool")
    parser.add_argument("--n", type=int)
    return parser


def parse(argv: list) -> dict:
    """The options the command line sets."""
    return vars(_parser().parse_args(argv))


def parse_by_hand(argv: list) -> dict:
    """The options the command line sets, read without a parser."""
    return {"n": int(argv[argv.index("--n") + 1]) if argv else None}


def run(argv: list) -> None:
    """Exit 0 for a non-negative `--n`, else 1."""
    n = parse(argv)["n"] or 0
    sys.exit(0 if n >= 0 else 1)


def run_past_five(argv: list) -> None:
    """Exit 0, or 3 when `--n` is past five."""
    n = parse(argv)["n"] or 0
    sys.exit(3 if n > 5 else 0)


def test_an_argparse_parse_is_refused_the_way_the_language_declares(capsys):
    p = _one(parse, "for argv in L[cli_argv], excluded_outside_domain(argv)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_a_parse_that_tracebacks_falsifies_naming_the_refusal_and_the_raise():
    p = _one(parse_by_hand, "for argv in L[cli_argv], excluded_outside_domain(argv)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "outside L[cli_argv]" in p.counterexample, p.counterexample
    assert ("was not refused the way the language declares "
            "(SystemExit (exit code 2)): the call raised ") in p.counterexample, \
        p.counterexample
    assert "Error" in p.counterexample.rsplit("raised ", 1)[1], p.counterexample


def test_a_return_outside_the_language_falsifies_naming_what_was_returned():
    def accept(argv: list) -> int:
        """How many arguments there are."""
        return len(argv)

    p = _one(accept, "for argv in L[cli_argv], excluded_outside_domain(argv)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "(SystemExit (exit code 2)): the call returned " in p.counterexample, \
        p.counterexample


def test_with_no_refusal_declared_any_raise_still_refuses():
    p = _one(parse_by_hand, "for argv in L[plain_argv], excluded_outside_domain(argv)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_a_refusal_declared_by_a_returned_value_is_read():
    register_language("sentinel_argv", Argv(
        "sentinel_argv", refusal=Refusal("a return of None", returns=lambda v: v is None)))
    try:
        def lenient(argv: list):
            """The options, or None when the line does not parse."""
            try:
                return parse_by_hand(argv)
            except (IndexError, ValueError):
                return None

        p = _one(lenient, "for argv in L[sentinel_argv], excluded_outside_domain(argv)")
        q = _one(parse_by_hand, "for argv in L[sentinel_argv], excluded_outside_domain(argv)")
    finally:
        unregister_language("sentinel_argv")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert q.verdict == "falsified", (q.verdict, q.note)
    assert "(a return of None): the call raised" in q.counterexample, q.counterexample


def test_exits_0_or_1_are_the_defined_answer():
    p = _one(run, "for argv in L[cli_argv], is_language_defined(argv)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_an_exit_3_on_a_member_falsifies_naming_the_answer_declared():
    p = _one(run_past_five, "for argv in L[cli_argv], is_language_defined(argv)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "(inside L[cli_argv]) raised SystemExit (exit code 3), not the defined " \
           "answer the language declares (a return, or SystemExit (exit code 0 or 1))" \
        in p.counterexample, p.counterexample


def test_with_no_answer_declared_an_exit_is_not_a_crash():
    p = _one(run_past_five, "for argv in L[plain_argv], is_language_defined(argv)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_a_refinement_keeps_the_declarations_of_its_base():
    from mathema.languages import RefinedLanguage
    refined = RefinedLanguage(CLI, "len", [0, 2], measure=len)
    assert (refined.refusal, refined.defined_answer) == (CLI.refusal, CLI.defined_answer)


def test_a_string_language_carries_the_declarations():
    words = StringLanguage("words", char_ok=str.isalpha, refusal=Refusal.exit(2))
    assert words.refusal.matches_raise(SystemExit(2))
    assert not words.refusal.matches_raise(SystemExit(1))
    assert words.defined_answer is None
    assert not language_problems(words)


@pytest.mark.parametrize("code, status", [(None, 0), (0, 0), (2, 2), ("bad usage", 1)])
def test_the_exit_status_is_read_as_the_interpreter_reads_it(code, status):
    answer = DefinedAnswer.exit(status)
    assert answer.matches_raise(SystemExit(code))
    assert answer.matches_return(object())


def test_a_declaration_of_the_wrong_kind_is_a_protocol_problem():
    bad = dataclasses.replace(PLAIN, refusal="SystemExit 2")
    assert any("'refusal' must be a Refusal" in p for p in language_problems(bad))
    with pytest.raises(ValueError, match="refusal"):
        register_language("bad_argv", bad)


def test_a_draw_from_the_test_language_is_a_member():
    rng = random.Random(0)
    assert all(CLI.contains(CLI.sample(rng)) for _ in range(20))
    assert not any(CLI.contains(CLI.outside(rng)) for _ in range(20))
