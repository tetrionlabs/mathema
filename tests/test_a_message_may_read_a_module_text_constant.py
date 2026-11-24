# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A refusing validator's exception message may read, inside an
f-string, a name the function's globals bind to an object of exact type
`str`: formatting a text cannot raise, so the message cannot change
what the function raises. A method call on the constant, a format
specification, or a constant of another type is not read. The record
of a claim read this way goes stale when the constant changes."""
import os
import subprocess
import sys
import textwrap

import pytest

import _message_validators as M
import _text_validators as T
from mathema._validators import read_validator

pytest.importorskip("z3")


@pytest.fixture
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


@pytest.mark.parametrize("fn", [M.check_name, M.check_name_own_error])
def test_a_message_reading_a_module_text_constant_is_read(fn):
    read = read_validator(fn)
    assert not isinstance(read, str), read
    assert read.constants == ("SETTING",)


@pytest.mark.parametrize("fn", [M.check_name_calling, M.check_name_formatting,
                                M.check_name_not_text])
def test_a_method_call_a_format_specification_or_another_type_declines(fn):
    assert isinstance(read_validator(fn), str)


def test_the_claim_is_decided_and_agrees_with_enumeration(served):
    row = T.row(M.check_name, "for name in L[anytext], assuming f is defined, f(name) == name")
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    assert T.on_smt(row)
    for text in T.enumerated("ab-z\n", 4):
        try:
            returned = M.check_name(text)
        except ValueError:
            assert not T.accepted_by(T.SLUG, "match", text)
        else:
            assert returned == text and T.accepted_by(T.SLUG, "match", text)
    wrong = T.row(M.check_name, "for name in L[anytext], f(name) == name")
    assert wrong.verdict == "falsified", (wrong.verdict, wrong.note)


def test_the_row_stamps_the_constant(served):
    row = T.row(M.check_name, "for name in L[slugs], f(name) == name")
    assert row.verdict == "proven", (row.verdict, row.note)
    stamped = row.meta["mathema.language_memberships"]
    assert any(key.endswith("SETTING") for key in stamped), stamped


_MODULE = '''
import re

import stale_words  # noqa: F401

_PAT = re.compile(r"[a-z]+")
SETTING = {setting!r}


def check(text: str) -> str:
    """Return text if it matches, else raise ValueError."""
    if not _PAT.fullmatch(text):
        raise ValueError(f"{{SETTING}}: {{text!r}}")
    return text
'''


def _verify_in_a_new_process(root):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root), repo])}
    run = subprocess.run(
        [sys.executable, "-c", "import sys; from mathema.cli import main; "
                               "sys.argv[0] = 'mathema'; raise SystemExit(main())",
         "verify", "--root", str(root), "--lenient"],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=600)
    return run.stdout + run.stderr


def _project(root, setting):
    from test_a_moved_language_definition_makes_the_record_stale import _WORDS_MODULE
    (root / "stale_words.py").write_text(_WORDS_MODULE)
    (root / "stale_message.py").write_text(_MODULE.format(setting=setting))
    (root / "claims").mkdir(exist_ok=True)
    (root / "claims" / "stale_message.claims.yaml").write_text(textwrap.dedent("""
        stale_message.check:
          claims:
            - name: refuses_a_newline
              statement: 'for text in L[anytext], raises(f(text + "\\\\n"), ValueError)'
              route: derive
    """))


def test_a_changed_constant_makes_the_record_stale_in_a_second_process(tmp_path):
    _project(tmp_path, "record format")
    first = _verify_in_a_new_process(tmp_path)
    assert "stale_message.check: no baseline record" in first, first
    second = _verify_in_a_new_process(tmp_path)
    assert "1 unchanged since the last run" in second, second
    _project(tmp_path, "name format")
    third = _verify_in_a_new_process(tmp_path)
    assert "stale_message.check: the definition of" in third, third
    assert "SETTING moved" in third, third
