# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What the function under test prints while mathema calls it (a
command-line function's `--help`, argparse's usage on an error, a
debugging print) is kept off the terminal: the check's own output is
the record, never the function's output once per call. The function
still runs as it would: it can write to the streams, their buffers
and their file descriptors, and its verdicts are unchanged."""
import importlib.util
import sys
import textwrap

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim

BODY = '''
import argparse
import sys


def loud(x: float) -> float:
    print("LOUD-STDOUT", x)
    print("LOUD-STDERR", x, file=sys.stderr)
    return 2.0 * x


def raw(x: float) -> float:
    sys.stdout.buffer.write(b"RAW-BYTES\\n")
    sys.stdout.flush()
    return x


def cli(s: str) -> int:
    parser = argparse.ArgumentParser(prog="cli")
    parser.add_argument("word")
    return len(parser.parse_args([s]).word)
'''


@pytest.fixture
def mod(tmp_path):
    path = tmp_path / "printing_module.py"
    path.write_text(textwrap.dedent(BODY))
    spec = importlib.util.spec_from_file_location("printing_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_printing_function_prints_nothing_while_checked(mod, capsys):
    rows = mathema.check(mod.loud, claims=["for x in [0, 1], f(x) >= 0"]).probes
    out, err = capsys.readouterr()
    assert "LOUD" not in out and "LOUD" not in err, (out[:200], err[:200])
    (row,) = [p for p in rows if p.name == "f_x_ge_0"]
    assert row.verdict in ("proven", "holds"), row.verdict


def test_argparse_help_and_usage_stay_off_the_terminal(mod, capsys):
    check_conjectures(mod.cli, [claim("is_language_defined(s)", route="best")])
    out, err = capsys.readouterr()
    assert "usage: cli" not in out and "usage: cli" not in err, (out[:200], err[:200])


def test_a_function_writing_to_the_stream_buffer_still_runs(mod, capsys):
    (row,) = check_conjectures(mod.raw, [claim("for x in [0, 1], f(x) == x",
                                               route="probe")])
    assert row.verdict == "holds", (row.verdict, row.note)
    assert "RAW-BYTES" not in capsys.readouterr().out


def test_the_streams_are_given_back_after_the_check(mod):
    before = (sys.stdout, sys.stderr)
    mathema.check(mod.loud, claims=["for x in [0, 1], f(x) >= 0"])
    assert (sys.stdout, sys.stderr) == before


def test_mathema_own_output_still_shows(capsys):
    from mathema._exits import call

    def speaks():
        print("FROM-THE-FUNCTION")
        return 1

    print("BEFORE")
    assert call(speaks) == 1
    print("AFTER")
    out = capsys.readouterr().out
    assert out == "BEFORE\nAFTER\n", out


def test_another_thread_writes_through_while_a_call_runs(capsys):
    import threading

    from mathema._exits import call
    started, release = threading.Event(), threading.Event()

    def waits():
        started.set()
        release.wait(5)
        return 1

    worker = threading.Thread(target=lambda: call(waits))
    worker.start()
    started.wait(5)
    print("OTHER-THREAD")
    release.set()
    worker.join(5)
    assert "OTHER-THREAD" in capsys.readouterr().out
