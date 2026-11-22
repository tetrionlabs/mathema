# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A verdict that rests on a language's stated definition rests on the
language's `contains()` too, since the definition was checked against
it. Such a row carries the identity of the code behind that membership
(`mathema.language_memberships`), and verify reads the record as stale
once that code is edited, even when the stated definition is not. An
edit that leaves the code's meaning as written (a comment) keeps the
record fresh."""
import os
import subprocess
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language

ALL = [[0, 0x10FFFF]]
LOWER = {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
         "language": {"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 122]]},
                      "min": 1, "max": None}}


def _lower(s):
    return len(s) >= 1 and all("a" <= c <= "z" for c in s)


@pytest.fixture
def lowerdef():
    register_language("lowerdef", StringLanguage(
        "lowerdef", level="predicate", accepts=_lower, pool="abc",
        generate=lambda rng: "".join(rng.choice("abc") for _ in range(rng.randint(1, 4))),
        schema={"definition": LOWER}))
    try:
        yield
    finally:
        unregister_language("lowerdef")


def _same(s):
    return s


def test_a_row_resting_on_a_checked_definition_stamps_the_membership(lowerdef):
    pytest.importorskip("z3")
    (row,) = check_conjectures(_same, [claim("L[lowerdef] subset L[lowerdef]",
                                             route="derive")])
    assert row.verdict == "proven", (row.verdict, row.note)
    stamp = row.meta["mathema.language_memberships"]
    assert set(stamp) == {"L[lowerdef]"}
    assert stamp["L[lowerdef]"].startswith("cd:")


def test_a_row_that_assumed_no_definition_carries_no_membership_stamp(lowerdef):
    (row,) = check_conjectures(_same, [claim("for s in L[lowerdef], f(s) == s")])
    assert "mathema.language_memberships" not in (row.meta or {})


def _strict():
    def strict(s):
        return s == "a"
    return strict


def _strict_commented():
    def strict(s):
        # the same test, with a comment
        return s == "a"
    return strict


def test_the_membership_identity_follows_the_code_and_not_the_layout():
    from mathema._code_identity import membership_identity
    strict, strict_commented = _strict(), _strict_commented()

    def loose(s):
        return s in ("a", "b")

    def make(accepts):
        return StringLanguage("x", level="predicate", accepts=accepts, schema={"d": 1})
    assert membership_identity(make(strict)) == membership_identity(make(strict))
    assert membership_identity(make(strict)) != membership_identity(make(loose))
    assert membership_identity(make(strict)).startswith("cd:")
    assert (membership_identity(make(strict)) ==
            membership_identity(make(strict_commented)))


_WORDS = '''
import re

from mathema.languages import StringLanguage, register_language

ALL = [[0, 0x10FFFF]]
LOWER = {{"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
          "language": {{"op": "repeat", "arg": {{"op": "chars", "ranges": [[97, 122]]}},
                       "min": 1, "max": None}}}}
_PAT = re.compile(r"[a-z]+")


def _accepts(s):
    {comment}
    pass
    return {test}


register_language("lowerdef", StringLanguage(
    "lowerdef", level="predicate", accepts=_accepts, pool="abc",
    generate=lambda rng: "".join(rng.choice("abc") for _ in range(rng.randint(1, 4))),
    schema={{"definition": LOWER}}))
'''


def _project(root, test, comment="pass"):
    """Write the project; `comment` is a line put in the body of the
    membership test."""
    (root / "memwords.py").write_text(_WORDS.format(test=test, comment=comment))
    (root / "memmod.py").write_text(textwrap.dedent('''
        import memwords  # noqa: F401


        def same(s: str) -> str:
            """The text, unchanged."""
            return s
    '''))
    (root / "claims").mkdir(exist_ok=True)
    (root / "claims" / "memmod.claims.yaml").write_text(textwrap.dedent("""
        memmod.same:
          claims:
            - name: lower_in_itself
              statement: 'L[lowerdef] subset L[lowerdef]'
              route: derive
    """))


def _verify_in_a_new_process(root):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root), repo])}
    run = subprocess.run(
        [sys.executable, "-c", "import sys; from mathema.cli import main; "
                               "sys.argv[0] = 'mathema'; raise SystemExit(main())",
         "verify", "--root", str(root), "--lenient"],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=600)
    return run.stdout + run.stderr


def test_an_edited_contains_makes_the_record_stale_in_a_second_process(tmp_path):
    pytest.importorskip("z3")
    _project(tmp_path, "_PAT.fullmatch(s) is not None")
    first = _verify_in_a_new_process(tmp_path)
    assert "memmod.same: no baseline record" in first, first
    second = _verify_in_a_new_process(tmp_path)
    assert "1 unchanged since the last run" in second, second
    _project(tmp_path, "_PAT.fullmatch(s) is not None", comment="pass  # only a comment")
    commented = _verify_in_a_new_process(tmp_path)
    assert "1 unchanged since the last run" in commented, commented
    # the definition still states [a-z]+; only the membership is edited
    _project(tmp_path, "_PAT.fullmatch(s) is not None or s == '0'")
    edited = _verify_in_a_new_process(tmp_path)
    assert "memmod.same: the definition of L[lowerdef] moved" in edited, edited
