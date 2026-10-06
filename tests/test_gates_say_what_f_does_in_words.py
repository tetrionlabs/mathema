# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The gates, the empty-input check and the runtime guard, read as
sentences: a gate row gives its reason, its counterexample and its next
step on the record, in the words the policy rows use; `is_empty_safe`
says what it called f with and what came back; `enforce_domain` says it
raised before f ran; the one-line summaries name the rows to settle."""
import math
import statistics
from typing import Optional

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pl = pytest.importorskip("polars")


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def root_opt(x: Optional[float]) -> float:
    return math.sqrt(x)


def total(xs: list) -> float:
    return sum(xs)


def ratio(x: Optional[float], y: float) -> float:
    if x != x:
        raise ValueError("x is nan")
    return x / (1.0 + y * y)


def pick(x: float) -> Optional[float]:
    return None if x > 0.5 else x


def pick_undeclared(x: float) -> float:
    return None if x > 0.5 else x


def mean_pd(xs: pd.Series) -> float:
    return float(xs.mean())


def mean_np(xs: np.ndarray) -> float:
    return float(np.mean(xs))


def sum_pd(xs: pd.Series) -> float:
    return float(xs.sum())


def mean_list(xs: list) -> float:
    return statistics.mean(xs)


def mean_guarded(xs: list) -> float:
    if len(xs) == 0:
        raise ValueError("empty")
    return statistics.mean(xs)


def det(A: np.ndarray) -> float:
    return float(np.linalg.det(A))


def col_mean(df: pd.DataFrame) -> float:
    return float(df["r"].mean())


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def _record(fn, *texts):
    return mathema.check(fn, claims=[mathema.claim(t, name=f"c{i}")
                                     for i, t in enumerate(texts)])


def _row(rec, name):
    return next(p for p in rec.probes if p.name == name)


def _lines_under(rec, name):
    lines = repr(rec).splitlines()
    at = next(i for i, ln in enumerate(lines) if f" {name}:" in ln)
    out = [lines[at]]
    for ln in lines[at + 1:]:
        if not ln.startswith("           "):
            break
        out.append(ln)
    return out


# --- the gate row -----------------------------------------------------------

def test_a_gate_proven_by_calling_f_says_no_claim_states_it_yet():
    rec = _record(clamp01, "for x in R, 0 <= f(x) <= 1", "is_missing_safe(f)")
    assert _lines_under(rec, "c1")[1] == (
        "           x (float): nan drops, confirmed by calling f at x = nan; no claim "
        "states it yet")


def test_a_falsified_gate_prints_its_reason_and_next_step():
    rec = _record(total, "for xs in [0, 1]^n, f(xs) >= 0", "is_missing_safe(f)")
    under = _lines_under(rec, "c1")
    assert under[1] == (
        "           xs (list): null raises TypeError, and no claim says it may; nan "
        "propagates, confirmed on the 43 draws of c0[float]; no claim states it yet")
    assert under[2] == "           counterexample xs = [null]: f raised TypeError"
    assert under[3:5] == [
        "           (i) if the raise is intended, state: missing(f, xs, null) "
        "raises(TypeError)",
        "           (ii) if not, make f skip or fill the null slot"], under[3:5]


def test_a_gate_alone_still_says_what_to_do():
    rec = _record(root_opt, "is_absent_safe(f)")
    under = _lines_under(rec, "c0")
    assert under[1] == ("           x (float): None raises TypeError, and no claim says "
                        "it may")
    assert under[4] == ("           (i) if the raise is intended, state: absent(f, x) "
                        "raises(TypeError)"), under


def test_a_library_named_once_and_the_odd_member_said_once():
    rec = _record(mean_pd, "for xs in [0, 1]^n, 0 <= f(xs) <= 1", "is_missing_safe(f)")
    assert _lines_under(rec, "c1")[1] == (
        "           xs (pandas.Series): nan and null follow pandas.Series.mean's own "
        "policy row (drops when values remain, propagates when every slot is missing); "
        "NA does not: f raises TypeError when every slot is NA")


def test_an_undeclared_none_is_the_gate_reason():
    rec = _record(pick_undeclared, "for x in [0, 1], f(x) <= 1", "is_absent_safe(f)")
    assert _lines_under(rec, "c1")[1] == (
        "           x (float) admits no None; f returned None at x = 1.0 from present "
        "inputs, and its return type float does not declare it")


def test_a_declared_none_reads_as_a_sentence():
    rec = _record(pick, "for x in [0, 1], f(x) <= 1", "is_absent_safe(f)")
    assert _lines_under(rec, "c1")[1] == (
        "           x (float) admits no None; the result may be None, as the return "
        "type Optional[float] declares (f returned None at x = 1.0 from present "
        "inputs)")


def test_a_witness_lists_parameters_in_signature_order():
    (row,) = check_conjectures(ratio, [claim("is_absent_safe(f)")])
    assert row.counterexample.startswith("x = None, y = ")


def test_the_gate_payload_says_unstated_not_none():
    (row,) = check_conjectures(root_opt, [claim("is_absent_safe(f)")])
    (entry,) = row.meta["mathema.gate"]["parameters"]["x"]
    assert entry["source"] == "unstated"


# --- a class row a stated member row settles -----------------------------

def test_a_stated_member_row_narrows_the_library_row():
    # mean of an empty Series is nan, stated as its empty policy
    rec = _record(mean_pd, "for xs in [0, 1]^n, 0 <= f(xs) <= 1",
                  "assuming count(xs) == 0, missing(f, xs, NA) raises(TypeError)",
                  "f([]) in {missing}")
    row = _row(rec, "missing[xs, count == 0]")
    assert row.verdict == "proven", (row.verdict, row.meta["mathema.policy"])
    assert row.meta["mathema.policy"]["reason"].endswith("; NA is stated separately")


# --- a premise on len ----------------------------------------------------

def test_a_len_premise_is_read():
    rec = _record(ema, "for x in [0, 1]^n, alpha in [0, 1], f(x, alpha) <= 1",
                  "assuming len(x) == 1, missing(f, x, null) converts")
    assert _row(rec, "c1").verdict == "holds", _row(rec, "c1").note


# --- is_empty_safe --------------------------------------------------------

def test_an_empty_input_says_what_was_built_and_what_came_back():
    (row,) = check_conjectures(mean_np, [claim("is_empty_safe(xs)")])
    assert row.counterexample == ("xs = [] (an empty numpy.ndarray): f returned nan "
                                  "for the empty input; raise, or return a value")
    (row,) = check_conjectures(sum_pd, [claim("is_empty_safe(xs)")])
    assert row.verdict == "proven"
    assert row.sketch == "xs = [] (an empty float Series): f returned 0.0"


def test_an_unguarded_raise_at_the_empty_input_says_what_to_do():
    (row,) = check_conjectures(mean_list, [claim("is_empty_safe(xs)")])
    assert row.counterexample == (
        "xs = [] (an empty list): f raised StatisticsError with no guard for the "
        "empty input; guard it (`if not xs: raise ValueError(...)`) so the raise is "
        "deliberate, or return a value")


def test_a_guarded_raise_at_the_empty_input_is_said():
    (row,) = check_conjectures(mean_guarded, [claim("is_empty_safe(xs)")])
    assert row.verdict == "proven"
    assert row.sketch == ("xs = [] (an empty list): f raised ValueError behind the "
                          "guard on line 2")


def test_an_empty_matrix_is_zero_by_zero():
    (row,) = check_conjectures(det, [claim("is_empty_safe(A)")])
    assert row.verdict == "proven", (row.verdict, row.counterexample)
    assert row.sketch == "A = [] (an empty 0 by 0 numpy.ndarray): f returned 1.0"


def test_the_function_wide_empty_check_reaches_the_containers():
    (row,) = check_conjectures(mean_np, [claim("is_empty_safe(f)")])
    assert row.verdict == "falsified", (row.verdict, row.note)


# --- the column bound -----------------------------------------------------

def test_a_column_bound_holds_on_the_classified_calls():
    rec = _record(col_mean, "for df.r in [0, 1]^n, 0 <= f(df) <= 1", "is_missing_safe(f)")
    for p in rec.probes:
        cx = p.counterexample or ""
        assert "-1e+06" not in cx and "2.0" not in cx, (p.name, cx)


def col_total(df: pd.DataFrame) -> float:
    return float(df["w"].sum())


def test_a_column_bound_bounds_the_companions_corners():
    rec = _record(col_total, "for df.w in [0, 1]^n, f(df) >= 0")
    companion = _row(rec, "c0[float, pandas.DataFrame]")
    assert companion.verdict == "holds", companion.counterexample


# --- the runtime guard ------------------------------------------------------

def test_enforce_domain_says_it_raised_before_f_ran():
    @mathema.enforce_domain()
    @mathema.claims_decorator("absent(f, x) raises(TypeError)")
    def root(x: Optional[float]) -> float:
        return math.sqrt(x)
    with pytest.raises(TypeError) as err:
        root(None)
    assert str(err.value) == "enforce_domain is active and raised TypeError because x is None"


def test_enforce_domain_at_exit_reads_as_a_sentence():
    @mathema.enforce_domain()
    @mathema.claims_decorator("missing(f, x) propagates")
    def clamp(x: float) -> float:
        return max(0.0, min(1.0, x))
    with pytest.raises(mathema.MissingValueError) as err:
        clamp(float("nan"))
    assert str(err.value) == ("clamp(): at x = nan f returned 1.0, dropping the hole, "
                              "but its policy says propagates (missing(f, x) propagates)")


# --- the listing header and the one-line summaries ---------------------------

def test_the_listing_names_what_no_claim_covers_yet(tmp_path, monkeypatch, capsys):
    (tmp_path / "gwords.py").write_text(
        "# SPDX-License-Identifier: BUSL-1.1\n# Copyright 2026 Tetrion Ltd\n"
        "import math\nfrom typing import Optional\n\n"
        "def root_opt(x: Optional[float]) -> float:\n"
        "    \"\"\"Claims:\n        nonneg: for x in [0, 4], f(x) >= 0\n    \"\"\"\n"
        "    return math.sqrt(x)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    from mathema.cli import main
    main(["claims", "gwords.root_opt", "--root", str(tmp_path)])
    assert ("  not covered by any claim yet (the line beneath says what to write, or "
            "what to change; --write leaves these out):") in capsys.readouterr().out


def test_the_check_line_names_the_row_to_settle(tmp_path, monkeypatch, capsys):
    (tmp_path / "cmod.py").write_text(
        "# SPDX-License-Identifier: BUSL-1.1\n# Copyright 2026 Tetrion Ltd\n"
        "def clamp01(x: float) -> float:\n"
        "    \"\"\"Claims:\n        unit: for x in R, 0 <= f(x) <= 1\n    \"\"\"\n"
        "    return max(0.0, min(1.0, x))\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    from mathema.cli import main
    assert main(["check", "cmod.py:clamp01"]) == 1
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].endswith(
        "  <- 1 policy row to settle: missing[x], f drops a missing x (nan in, 1.0 out) "
        "where mathema's default says propagates"), lines[0]
    assert lines[1:4] == ["       (i) change f", "       (ii) write: missing(f, x) drops",
                          "       to list them, run: mathema claims cmod.clamp01"], lines


def test_a_compact_row_carries_the_reason_and_the_next_step():
    from mathema.records import claim_row
    rec = _record(clamp01, "for x in R, 0 <= f(x) <= 1")
    row = claim_row(_row(rec, "missing[x]"))
    assert row["reason"].startswith("mathema's default word for a float, not a claim of "
                                    "yours")
    assert row["next"].startswith("(i) if 1.0 is the answer f should give")
    assert row["source"] == "default"


def test_a_real_valued_series_holds_no_nat():
    rec = _record(mean_pd, "for xs in [0, 1]^n, 0 <= f(xs) <= 1", "is_missing_safe(f)")
    for p in rec.probes:
        for text in (p.note or "", ((p.meta or {}).get("mathema.policy") or {}).get(
                "reason") or "", p.sketch or ""):
            assert "NaT" not in text, (p.name, text)


def test_a_chained_claim_says_a_gate_is_no_premise_once():
    (row,) = check_conjectures(mean_pd, [claim(
        "assuming is_missing_safe(f), for xs in [0, 1]^n, 0 <= f(xs) <= 1")])
    assert row.verdict == "skipped:misspecified"
    assert "link 1" not in row.note and row.note.count("is not a premise") == 1


def test_a_problem_after_a_command_starts_its_own_line():
    from mathema.verify import problems_text
    text = problems_text(["1 policy row to settle: missing[x]\n(i) change f\n"
                          "to list them, run: mathema claims k", "c unknown: no proof"])
    lines = text.splitlines()
    # a command is the last thing on its line, so the next problem starts a line
    assert lines[2] == "       to list them, run: mathema claims k", lines
    assert lines[3] == "       c unknown: no proof", lines


def test_a_first_falsification_note_puts_each_command_last_on_its_line():
    from types import SimpleNamespace

    from mathema.verify import _initially_falsified_hint
    p = SimpleNamespace(name="at_most_the_largest", statement="f(a) <= max(a)",
                        meta={}, verdict="falsified")
    (note,) = _initially_falsified_hint("numpy.ptp", [p], {}, "claims/numpy.claims.yaml")
    lines = note.splitlines()
    assert lines[0] == ("note numpy.ptp: at_most_the_largest initially "
                        "falsified: the installed library does not do what the "
                        "row states:"), lines
    assert lines[1:] == [
        "  (i) to record the falsification as a discovery, run: mathema accept "
        "numpy.ptp at_most_the_largest --as discovery",
        "  (ii) correct the row in claims/numpy.claims.yaml, then run: "
        "mathema accept numpy.ptp at_most_the_largest --as superseded"], lines


def test_a_compendium_hint_puts_each_command_last_on_its_line():
    from mathema.compendium import _compendium_hint
    for verdict in ("unknown", None):
        text = _compendium_hint("compendium:math", "log_monotone", "math.log", verdict)
        commands = [line for line in text.splitlines() if "mathema accept" in line
                    or "mathema check" in line]
        assert commands, text
        for line in commands:
            # the command runs to the end of its line, after a colon
            assert "run: mathema " in line and ";" not in line.split("run: ", 1)[1], line
