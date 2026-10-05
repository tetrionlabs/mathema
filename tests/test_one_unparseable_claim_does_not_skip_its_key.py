# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One claim that does not parse is reported on its own, and the other
claims of its function are still adjudicated.

The run still fails, naming the claim that does not parse and where it
is declared, but the function's record holds a verdict for every claim
that does parse, so one typo never hides the rest of a function's
evidence.
"""
import sys
import textwrap

import yaml


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_the_other_claims_are_adjudicated_and_the_bad_one_named(
        tmp_path, monkeypatch):
    from mathema.verify import verify_project
    _write(tmp_path / "spkg" / "__init__.py", "")
    _write(tmp_path / "spkg" / "m.py", '''
        def total(xs: list) -> float:
            """The sum of the elements."""
            return sum(xs)
    ''')
    _write(tmp_path / "claims" / "m.claims.yaml", """
        spkg.m.total:
          claims:
            - name: nonneg
              statement: "for xs in [0, 1]^n, f(xs) >= 0"
            - name: garbled
              statement: "for xs in [0, 1]^n, f(xs) >>= 0"
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("spkg", "spkg.m"):
        sys.modules.pop(name, None)
    result = verify_project(str(tmp_path))
    assert any("garbled" in p and "does not parse" in p
               for p in result.problems), result.problems
    assert result.authoring_errors, result.lines
    record = yaml.safe_load((tmp_path / ".mathema" / "verified"
                             / "spkg.m.total.yaml").read_text())
    rows = {c["name"]: c for c in record["spkg.m.total"]["claims"]}
    assert rows["nonneg"]["verdict"] in ("proven", "holds"), rows
    assert "garbled" not in rows
