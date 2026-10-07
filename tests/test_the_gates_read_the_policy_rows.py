# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_missing_safe(f)` and `is_absent_safe(f)` state complete knowledge
of what f does with a value that is not there: every parameter that
admits the kind has a policy the code follows at every member. Proven
when each member's policy is derived (a guard in the body, a library's
own policy row) or stated and confirmed; holds when some member is
confirmed by execution alone, a scalar called at every member included,
and never proven beside a row the code contradicts; falsified on a
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


def test_a_lone_scalar_called_at_every_case_holds():
    row = _gate(ident, "is_missing_safe(f)")
    assert row.verdict == "holds", row.note
    assert row.sketch == ("x (unannotated): nan propagates, confirmed by calling f at "
                          "x = nan; no claim states it yet")
    row = _gate(ident, "is_absent_safe(f)")
    assert row.verdict == "holds", row.note


def test_a_row_the_code_contradicts_leaves_the_gate_at_holds():
    row = _gate(clamp01, "is_missing_safe(f)")
    assert row.verdict == "holds", row.note


def test_a_stated_and_confirmed_row_proves_the_gate():
    row = _gate(clamp01, "is_missing_safe(f)", "missing(f, x) drops")
    assert row.verdict == "proven", row.note
    assert row.sketch == "x (float): nan drops, stated"


def test_the_absent_gate_calls_f_at_present_inputs_itself():
    row = _gate(pick_undeclared, "is_absent_safe(f)")
    assert row.verdict == "falsified", row.note
    assert row.counterexample.startswith("x = ")
    assert row.counterexample.endswith(": f returned None")


def test_an_unaccounted_raise_falsifies_the_absent_gate():
    row = _gate(root_opt, "is_absent_safe(f)")
    assert row.verdict == "falsified"
    assert row.counterexample == "x = None: f raised TypeError"
    assert row.note == "x (float): None raises TypeError, and no claim says it may"
    assert row.meta["mathema.gate"]["reason"] == (
        "f raised TypeError at x = None, and no claim says it may")


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
    # the count moved from 126 when sequence corners were turned on
    # (ruling of 2026-10-05)
    assert row.sketch == ("xs (list): null and nan drop, confirmed on the 131 draws of "
                          "c; no claim states it yet")


def test_a_contradicted_stated_row_falsifies_the_gate():
    row = _gate(clamp01, "is_missing_safe(f)", "missing(f, x) propagates")
    assert row.verdict == "falsified"
    assert row.sketch == ("x (float): nan drops, contradicting the stated "
                          "`missing(f, x) propagates`")
    assert row.meta["mathema.gate"]["reason"].startswith(
        "missing(f, x) propagates is falsified")


def test_a_declared_optional_return_accounts_for_its_none():
    row = _gate(pick, "is_absent_safe(f)", value="for x in [0, 1], f(x) <= 1")
    assert row.verdict == "proven", row.note
    assert "the result may be None, as the return type Optional[float] declares (f " \
        "returned None at x = " in row.sketch
    assert row.sketch.endswith("as the return type Optional[float] declares (f returned "
                               "None at x = 1.0 from present inputs)")


def test_an_undeclared_none_falsifies_the_absent_gate():
    row = _gate(pick_undeclared, "is_absent_safe(f)", value="for x in [0, 1], f(x) <= 1")
    assert row.verdict == "falsified"
    assert "and its return type float does not declare it" in row.note


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


def test_the_absent_gate_round_trips_through_the_store():
    from mathema.spec import canonical_claim_text, declare, entry_claims
    cj = claim("is_absent_safe(f)")
    assert canonical_claim_text(cj) == "is_absent_safe(f)"
    (again,) = entry_claims({"claims": [declare(cj)]})
    assert again.relation == "is_absent_safe"


def none_default(x: float = None) -> float:
    return x + 1.0


def test_a_float_that_defaults_to_none_is_misspecified():
    row = _gate(none_default, "is_absent_safe(f)")
    assert row.verdict == "skipped:misspecified"
    assert row.note == ("x is annotated float but defaults to None; annotate it "
                        "Optional[float] or change the default")
    stated = check_conjectures(none_default, [claim("absent(f, x) raises(TypeError)")])[-1]
    assert stated.verdict == "skipped:misspecified"
    assert stated.note == row.note
