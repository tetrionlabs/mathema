# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When mathema's own battery cannot build a call to the function (a
string parameter with no declared domain, a call that raises for every
input built from the signature), the check is not run and leaves no
row. What it tried and why it could not stay on the record's meta under
`mathema.not_run`: the call as a statement, the reason, and the gap."""
import mathema


def pick(a, b, c):
    if a == 0:
        raise ValueError("a must be nonzero")
    return b / a + c


def label(name: str) -> str:
    return name.upper()


def _not_run(rec):
    return {r["check"]: r for r in rec.meta.get("mathema.not_run", [])}


def test_an_unsynthesisable_call_leaves_no_row_and_keeps_the_reason():
    rec = mathema.check(pick, claims=["for a in [0, 0], raises(f(a, b, c), ValueError)"])
    assert not [p for p in rec.probes if p.name == "callable"]
    assert "callable" not in repr(rec)
    row = _not_run(rec)["callable"]
    assert row["statement"] == "f(a, b, c) can be called"
    assert row["reason"].startswith("f could not be called with a value mathema "
                                    "built from the signature (a, b, c): ")
    assert row["gap"] == "input-synthesis"


def test_an_undeclared_string_parameter_leaves_no_row_and_keeps_the_reason():
    rec = mathema.check(label)
    assert not [p for p in rec.probes if p.name == "callable"]
    row = _not_run(rec)["callable"]
    assert row["statement"] == "f(name) can be called"
    assert "string with no declared domain" in row["reason"]
    assert row["gap"] == "string-domain-missing"
