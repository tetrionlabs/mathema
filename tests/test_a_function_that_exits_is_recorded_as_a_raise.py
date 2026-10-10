# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function under test that ends with `SystemExit` (argparse on a bad
argument list, a bare `sys.exit(3)`) has raised, like any other
exception: a value claim at that input is falsified with a witness
naming `SystemExit` and its exit code, `raises(..., SystemExit)` is a
claim that can be stated and decided, and the exit never ends the
caller's own process. `KeyboardInterrupt` still propagates."""
import argparse
import json
import subprocess
import sys
import textwrap

import pytest

import mathema
from tests.test_cli_verify import _env_with_repo_on_path


def parse(argv: list[str]) -> dict:
    return vars(argparse.ArgumentParser().parse_args(argv))


def parse_raising(argv: list[str]) -> dict:
    try:
        return parse(argv)
    except SystemExit as exc:
        raise ValueError(exc.code) from None


def leave(code: int) -> int:
    if code > 3:
        sys.exit(code)
    return code


def leave_raising(code: int) -> int:
    if code > 3:
        json.loads("not json")
    return code


def leave_explicitly(code: int) -> int:
    if code > 3:
        raise SystemExit(code)
    return code


def interrupt(code: int) -> int:
    raise KeyboardInterrupt


def _one(fn, claim, **kw):
    (p,) = mathema.check_conjectures(fn, [claim], **kw)
    return p


def test_a_value_claim_at_an_exiting_input_is_falsified_naming_the_exit():
    p = _one(parse, 'f(["--n", "x"]) == {"n": 0}')
    assert p.verdict == "falsified"
    assert "raised SystemExit (exit code 2)" in p.counterexample, p


def test_raises_systemexit_is_decided_like_any_other_raise():
    exiting = _one(parse, 'raises(f(["--n", "x"]), SystemExit)')
    raising = _one(parse_raising, 'raises(f(["--n", "x"]), ValueError)')
    assert exiting.verdict in ("proven", "holds"), exiting
    assert exiting.verdict == raising.verdict, (exiting, raising)


def test_raises_systemexit_reaches_the_verdict_an_ordinary_raise_reaches():
    exiting = _one(leave, "for code in [4, 9], raises(f(code), SystemExit)")
    raising = _one(leave_raising,
                   "for code in [4, 9], raises(f(code), json.JSONDecodeError)")
    assert exiting.verdict == raising.verdict, (exiting, raising)


def test_an_explicit_raise_systemexit_is_proven_over_a_finite_domain():
    p = _one(leave_explicitly, "for code in [4, 9], raises(f(code), SystemExit)")
    assert p.verdict == "proven", p


def test_an_explicit_raise_systemexit_falsifies_a_value_claim():
    p = _one(leave_explicitly, "for code in [0, 9], f(code) == code")
    assert p.verdict == "falsified", p


def test_a_finite_domain_value_claim_over_an_exit_is_falsified():
    p = _one(leave, "for code in {1, 2, 3, 4}, f(code) == code")
    assert p.verdict == "falsified", p
    assert "SystemExit" in p.counterexample


def test_check_records_an_exit_instead_of_ending_the_caller():
    record = mathema.check(leave, claims=["for code in [0, 9], f(code) <= 3"])
    verdicts = {p.name: p.verdict for p in record.probes}
    assert "falsified" in verdicts.values(), verdicts


def test_check_with_suggested_claims_survives_an_exiting_function():
    mathema.check(parse)
    mathema.check(leave)


def test_keyboard_interrupt_from_the_function_still_propagates():
    with pytest.raises(KeyboardInterrupt):
        mathema.check_conjectures(interrupt, ["f(1) == 1"])


def test_the_cli_exits_with_its_own_code_not_the_function_s(tmp_path):
    (tmp_path / "exiting.py").write_text(textwrap.dedent("""\
        # SPDX-License-Identifier: BUSL-1.1
        # Copyright 2026 Tetrion Ltd
        import sys


        def leave(code: int) -> int:
            if code > 3:
                sys.exit(7)
            return code
        """))
    script = ("import sys; from mathema.cli import main; "
              "sys.exit(main(['check', 'exiting.py:leave', '--claim', "
              "'for code in [0, 9], f(code) <= 3', '--format', 'json']))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True,
                       env=_env_with_repo_on_path())
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "SystemExit (exit code 7)" in r.stdout, r.stdout
