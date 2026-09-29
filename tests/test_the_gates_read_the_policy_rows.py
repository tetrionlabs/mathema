# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_missing_safe(f)` and `is_absent_safe(f)` state complete knowledge
of what f does with a value that is not there: every parameter that
admits the kind has a policy the code follows at every member. Proven
when each member's policy is derived (a guard in the body, a library's
own policy row) or stated and confirmed, or was called at every case;
holds when some member is confirmed by execution alone; falsified on a
contradiction, a member treated more than one way, a raise no claim
accounts for, or a None from present inputs the return type does not
declare. The record names each parameter's members, policy and source.
Neither is asserted by default; `mathema claims --suggest` offers them."""
import math
from typing import Optional

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


def root(x: float) -> float:
    return math.sqrt(x)


def root_guarded(x: float) -> float:
    if x != x:
        raise ValueError("x is nan")
    return math.sqrt(x)


def root_opt(x: Optional[float]) -> float:
    return math.sqrt(x)


def ident(x):
    return x


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def total(xs: list) -> float:
    return sum(xs)


def nan_sum(xs: list) -> float:
    return sum(x for x in xs if x is not None and x == x)


def pick(x: float) -> Optional[float]:
    return None if x > 0.5 else x


def pick_undeclared(x: float) -> float:
    return None if x > 0.5 else x


def ratio(x: Optional[float], y: float) -> float:
    if x != x:
        raise ValueError("x is nan")
    return x / (1.0 + y * y)


def count(n: int) -> int:
    return n + 1


def _gate(fn, text, *more, value=None):
    claims = [claim(value, name="c")] if value else []
    rows = check_conjectures(fn, claims + [claim(m) for m in more] + [claim(text)])
    return rows[-1]


def test_a_library_row_proves_the_missing_gate():
    row = _gate(root, "is_missing_safe(f)")
    assert (row.name, row.verdict) == ("is_missing_safe[f]", "proven"), row.note
    assert row.sketch == ("x (float): nan propagates, from math.sqrt's own policy row")


def test_a_guard_proves_the_missing_gate():
    row = _gate(root_guarded, "is_missing_safe(f)")
    assert row.verdict == "proven", row.note
    assert row.sketch == "x (float): nan raises ValueError, from the guard on line 2"


def test_a_lone_scalar_called_at_every_case_proves_it():
    row = _gate(ident, "is_missing_safe(f)")
    assert row.verdict == "proven", row.note
    assert row.sketch == "x (unannotated): nan propagates, called at every case"
    row = _gate(ident, "is_absent_safe(f)")
    assert row.verdict == "proven", row.note


def test_an_unaccounted_raise_falsifies_the_absent_gate():
    row = _gate(root_opt, "is_absent_safe(f)")
    assert row.verdict == "falsified"
    assert row.counterexample == "x = None: f raised TypeError"
    assert row.note.startswith("f raised TypeError at x = None, and no claim says it may")


def test_a_stated_raise_accounts_for_it():
    row = _gate(root_opt, "is_absent_safe(f)", "absent(f, x) raises(TypeError)")
    assert row.verdict == "proven", row.note
    assert row.sketch == "x (float): None raises TypeError, stated"


def test_a_raise_at_a_list_slot_falsifies_the_missing_gate():
    row = _gate(total, "is_missing_safe(f)", value="for xs in [0, 1]^n, f(xs) >= 0")
    assert row.verdict == "falsified"
    assert "null" in row.counterexample


def test_a_drop_confirmed_by_execution_alone_holds():
    row = _gate(nan_sum, "is_missing_safe(f)", value="for xs in [0, 1]^n, f(xs) >= 0")
    assert row.verdict == "holds", row.note
    assert row.sketch == ("xs (list): null drops, observed on the draws; nan drops, "
                          "observed on the draws")


def test_a_contradicted_stated_row_falsifies_the_gate():
    row = _gate(clamp01, "is_missing_safe(f)", "missing(f, x) propagates")
    assert row.verdict == "falsified"
    assert row.note.startswith("missing_f_x_propagates (missing(f, x) propagates) is "
                               "falsified")


def test_a_declared_optional_return_accounts_for_its_none():
    row = _gate(pick, "is_absent_safe(f)", value="for x in [0, 1], f(x) <= 1")
    assert row.verdict == "proven", row.note
    assert "the result: None at x = " in row.sketch
    assert row.sketch.endswith("from present inputs, as the return type "
                               "Optional[float] declares")


def test_an_undeclared_none_falsifies_the_absent_gate():
    row = _gate(pick_undeclared, "is_absent_safe(f)", value="for x in [0, 1], f(x) <= 1")
    assert row.verdict == "falsified"
    assert "which its return type does not declare" in row.note


def test_guard_coverage_is_reported_per_member():
    row = _gate(ratio, "is_absent_safe(f)")
    assert row.verdict == "falsified"
    missing = _gate(ratio, "is_missing_safe(f)")
    assert missing.meta["mathema.gate"]["parameters"]["x"] == [
        {"member": "nan", "behaviour": "raises", "exception": "ValueError",
         "source": "guard", "guarded": True}]


def test_nothing_admitting_the_kind_proves_it_vacuously():
    row = _gate(count, "is_missing_safe(f)")
    assert row.verdict == "proven"
    assert row.note.startswith("no parameter admits a missing value")


def test_the_gates_are_never_asserted_by_default():
    rec = mathema.check(root_opt)
    names = {p.name for p in rec.probes}
    assert "is_missing_safe[f]" not in names and "is_absent_safe[f]" not in names


def test_the_claims_command_suggests_the_gates(tmp_path, monkeypatch, capsys):
    (tmp_path / "gmod.py").write_text(
        "# SPDX-License-Identifier: BUSL-1.1\n# Copyright 2026 Tetrion Ltd\n"
        "import math\nfrom typing import Optional\n\n"
        "def root_opt(x: Optional[float]) -> float:\n    return math.sqrt(x)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    from mathema.cli import main
    assert main(["claims", "gmod.root_opt", "--root", str(tmp_path), "--suggest"]) == 0
    out = capsys.readouterr().out
    assert "is_missing_safe[f]" in out and "is_absent_safe[f]" in out


def test_a_gate_is_no_premise():
    (row,) = check_conjectures(root_guarded, [claim(
        "assuming is_absent_safe(f), for x in [0, 1], f(x) >= 0")])
    assert row.verdict == "skipped:misspecified"


@pytest.mark.parametrize("text", ["is_absent_safe(f)", "is_absent_safe(x)"])
def test_the_absent_gate_parses(text):
    assert claim(text).relation == "is_absent_safe"
