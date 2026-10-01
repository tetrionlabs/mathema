# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A row pinned with `let ddof be 1` stays pinned when its expression
passes the same name as a keyword (`std(a, ddof=1)`).

The keyword names the grammar word's own parameter; it is not a read of
the library parameter `ddof`. So `mathema compendium update` finds a
call `np.std(a, ddof=1)` covered by the bundled `definition@ddof=1`
row, pins only the rows that have no pinned twin (`is_defined`, which
one element breaks at ddof = 1, so it is recorded falsified), writes no
copy of `definition` under that name, and a second run succeeds.
"""
import os
import subprocess
import sys
import textwrap

import pytest

np = pytest.importorskip("numpy")


@pytest.mark.parametrize("statement, pins", [
    ("let ddof be 1, for a in R^n \\ {∅}, assuming dim(a) >= 2, "
     "f(a) ~= std(a, ddof=1)", {"ddof": 1}),
    ("let axis be 0, for a in R^(m,n) \\ {∅}, f(a) ~= mean(a, axis=0)",
     {"axis": 0}),
    ("let n be 2, for a in R^n \\ {∅}, assuming dim(a) >= 3, "
     "f(a) ~= a[2:] - 2 * a[1:-1] + a[:-2]", {"n": 2}),
])
def test_the_pin_is_read_from_the_let_binding(statement, pins):
    from mathema.compendium import row_pins
    assert row_pins({"name": "definition", "statement": statement}) == pins


def test_a_bound_read_in_the_statement_is_not_a_pin():
    from mathema.compendium import row_pins
    assert row_pins({"name": "r", "statement":
                     "let c be 2, for x in [0, 1], f(x) <= c"}) == {}


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _cli(root, *args):
    env = dict(os.environ, PYTHONPATH=str(root))
    env.pop("VIRTUAL_ENV", None)
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(args)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=env)


def test_update_finds_a_sample_std_call_covered_by_the_bundled_row(tmp_path):
    _write(tmp_path / "upd.py", '''
        import numpy as np


        def spread(a):
            """The sample standard deviation."""
            return np.std(a, ddof=1)
    ''')
    _write(tmp_path / "claims" / "upd.claims.yaml", """
        upd.spread:
          claims:
            - name: nonneg
              statement: 'for a in [0, 1]^n, f(a) >= 0'
    """)
    first = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert first.returncode == 0, first.stderr
    # one element has no sample deviation, so the generic region pinned
    # at ddof = 1 is false and recorded so, never written
    assert ("is_defined@ddof=1 (let ddof be 1, dim(a) >= 1) not added"
            in first.stdout + first.stderr)
    assert "falsified against the installed library" in first.stdout + first.stderr
    # the bundled definition@ddof=1 covers the call: no copy of
    # definition is pinned, and nothing else holds, so no file is written
    assert "definition@ddof=1" not in first.stdout + first.stderr
    assert not (tmp_path / "claims" / "numpy.claims.yaml").exists()
    assert (tmp_path / ".mathema" / "verified" / "numpy.std.yaml").exists()
    again = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert again.returncode == 0, again.stderr
