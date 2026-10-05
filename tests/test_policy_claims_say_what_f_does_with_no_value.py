# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A policy claim states what a function does with a value that is not
there: `missing(f, x) propagates`, `absent(f, x) raises(TypeError)`,
`missing(f, xs, null) drops`, `assuming count(xs) >= 1, missing(f, xs)
drops`. It is decided on the calls the check already made, on a floor of
its own only where none reached its case, and says where its verdict
came from. A record carries one for every parameter that admits a kind:
the default for a kind the type alone admits, the observed behaviour for
one the author admitted (a raise there unaccounted for until stated), a
derived one where a guard in the body says it."""
import math
from typing import Optional

import pytest

import mathema
from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.policy import Policy, parse_policy, policy_text
from mathema.spec import ClaimsFileError, canonical_claim_text, declare, entry_claims


def root(x: float) -> float:
    return math.sqrt(x)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def guarded(x: float) -> float:
    if x is None or x != x:
        raise ValueError("missing")
    return math.sqrt(x)


def double(x):
    return x * 2


def opt_root(x: Optional[float]) -> float:
    return math.sqrt(x)


def total(xs: list) -> float:
    return sum(xs)


def mean_pd(xs: "pandas.Series") -> float:  # noqa: F821
    return float(xs.mean())


# --- the text ----------------------------------------------------------

@pytest.mark.parametrize("text, policy", [
    ("missing(f, x) propagates", Policy("missing", "x", None, "propagates")),
    ("absent(f, x) raises(TypeError)", Policy("absent", "x", None, "raises", "TypeError")),
    ("missing(f, xs, null) raises", Policy("missing", "xs", "null", "raises")),
    ("absent(f) drops", Policy("absent", None, None, "drops")),
    ("None(f, x) raises", Policy("absent", "x", None, "raises")),
    ("assuming count(xs) >= 1, missing(f, xs) drops",
     Policy("missing", "xs", None, "drops", premise="count(xs) >= 1")),
])
def test_a_policy_reads_in_the_selector_form(text, policy):
    assert parse_policy(text) == policy


@pytest.mark.parametrize("sugar, canonical", [
    ("missing_propagates(f, x)", "missing(f, x) propagates"),
    ("missing_removed(f, xs, null)", "missing(f, xs, null) drops"),
    ("absent_raises(f)", "absent(f) raises"),
    ("None(f, x) raises(TypeError)", "absent(f, x) raises(TypeError)"),
])
def test_the_sugar_renders_as_the_selector_form(sugar, canonical):
    assert policy_text(parse_policy(sugar)) == canonical
    assert canonical_claim_text(claim(sugar)) == canonical


def test_a_policy_claim_round_trips_through_the_store():
    for text in ("missing(f, x) propagates", "assuming count(xs) >= 1, missing(f, xs) drops",
                 "absent(f, x) raises(TypeError)"):
        cj = claim(text)
        again = entry_claims({"claims": [declare(cj)]})[0]
        assert canonical_claim_text(again) == text
        assert again.relation == "policy"


def test_a_remedy_a_row_names_is_a_claim_that_parses():
    rec = mathema.check(clamp01, claims=[claim("for x in R, 0 <= f(x) <= 1", name="c")])
    row = next(p for p in rec.probes if (p.meta or {}).get("mathema.policy"))
    remedy = row.meta["mathema.policy"]["next"].split("write `", 1)[1].split("`", 1)[0]
    assert remedy == "missing(f, x) drops"
    assert claim(remedy).relation == "policy"


# --- a stated policy -----------------------------------------------------

def _rows(fn, *texts):
    return {p.statement: p for p in check_conjectures(fn, [claim(t) for t in texts],
                                                      float_companions=True)}


def test_a_stated_policy_is_confirmed_on_the_draws_the_check_made():
    rows = _rows(root, "for x in [0, 1], f(x) >= 0", "missing(f, x) propagates")
    row = rows["missing(f, x) propagates"]
    assert row.verdict == "holds", (row.verdict, row.note)
    assert row.note == "stated; confirmed on the 42 draws of f_x_ge_0[float]"


def test_a_policy_alone_runs_its_own_floor():
    row = _rows(clamp01, "missing(f, x) drops")["missing(f, x) drops"]
    assert row.verdict == "holds"
    assert row.note == "stated; confirmed by calling f at x = nan"


def test_a_contradicted_policy_carries_the_executed_witness_and_the_claim_to_write():
    row = _rows(clamp01, "missing(f, x) propagates")["missing(f, x) propagates"]
    assert row.verdict == "falsified"
    assert row.counterexample == "x = nan: f returned 1.0"
    assert row.note == ("stated; f drops instead: nan in, 1.0 out; state "
                        "`missing(f, x) drops` if that is intended, or change f")


def test_a_named_exception_must_be_the_one_raised():
    assert _rows(double, "absent(f, x) raises(TypeError)")[
        "absent(f, x) raises(TypeError)"].verdict == "holds"
    assert _rows(double, "absent(f, x) raises(ValueError)")[
        "absent(f, x) raises(ValueError)"].verdict == "falsified"


def test_a_guard_that_states_the_policy_proves_it():
    row = _rows(guarded, "missing(f, x) raises(ValueError)")["missing(f, x) raises(ValueError)"]
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.note.startswith("stated; from the guard on line 2; confirmed")


def test_a_member_narrows_the_policy():
    rows = _rows(total, "for xs in [0, 1]^n, f(xs) >= 0", "missing(f, xs, null) raises(TypeError)",
                 "missing(f, xs, nan) propagates", "missing(f, xs) propagates")
    assert rows["missing(f, xs, null) raises(TypeError)"].verdict == "holds"
    assert rows["missing(f, xs, nan) propagates"].verdict == "holds"
    whole = rows["missing(f, xs) propagates"]
    assert whole.verdict == "falsified"
    assert whole.counterexample.startswith("xs = [") and "TypeError" in whole.counterexample


def test_a_premise_decides_on_the_calls_that_meet_it():
    pytest.importorskip("pandas")
    rows = _rows(mean_pd, "for xs in [0, 1]^n, f(xs) >= 0",
                 "assuming count(xs) >= 1, missing(f, xs) drops", "missing(f, xs) drops")
    assert rows["assuming count(xs) >= 1, missing(f, xs) drops"].verdict == "holds"
    assert rows["missing(f, xs) drops"].verdict == "falsified"


def test_two_behaviours_for_one_case_are_refused():
    rows = check_conjectures(root, [claim("missing(f, x) drops"),
                                    claim("missing(f, x) propagates")])
    assert all(p.verdict == "skipped:misspecified" for p in rows)
    assert "state two behaviours for one case" in rows[0].note


def test_two_behaviours_for_one_case_are_refused_at_load(tmp_path):
    from mathema.spec import read_claims_file
    path = tmp_path / "p.claims.yaml"
    path.write_text("m.root:\n  claims:\n"
                    "    - statement: \"missing(f, x) drops\"\n"
                    "    - statement: \"missing(f, x) propagates\"\n")
    with pytest.raises(ClaimsFileError, match="state two behaviours for one case"):
        read_claims_file(str(path), "p.claims.yaml")


def test_premises_that_tell_the_cases_apart_are_no_contradiction():
    from mathema.policy import contradicting_policies
    assert contradicting_policies(["assuming count(xs) >= 1, missing(f, xs) drops",
                                   "assuming count(xs) == 0, missing(f, xs) propagates"]) is None


# --- the rows a record carries ------------------------------------------

def _policy_rows(fn, text):
    rec = mathema.check(fn, claims=[mathema.claim(text, name="c0")])
    return [p for p in rec.probes if (p.meta or {}).get("mathema.policy")]


def scaled(x: float) -> float:
    return 2.0 * x + 1.0


def test_a_library_row_composed_through_the_body_derives_the_policy():
    (row,) = _policy_rows(root, "for x in [0, 1], f(x) >= 0")
    assert (row.statement, row.verdict) == ("missing(f, x) propagates", "proven")
    assert row.meta["mathema.policy"]["source"] == "derived"
    assert row.meta["mathema.policy"]["reason"].startswith(
        "from math.sqrt's own policy row, which f calls; confirmed on the 42 draws of "
        "c0[float]")


def test_a_float_carries_its_default_propagation_row():
    (row,) = _policy_rows(scaled, "for x in [0, 1], f(x) >= 1")
    assert (row.statement, row.verdict) == ("missing(f, x) propagates", "holds")
    assert row.meta["mathema.policy"]["source"] == "default"
    assert row.meta["mathema.policy"]["reason"] == (
        "default for a float, which may be nan; confirmed on the 42 draws of c0[float]. "
        "Keep it by writing it (mathema claims "
        "test_policy_claims_say_what_f_does_with_no_value.scaled --write), or change the "
        "word to raises or drops if f should do otherwise")
    assert row.meta["mathema.surface"] == "mathema"


def test_a_silent_drop_contradicts_the_default():
    (row,) = _policy_rows(clamp01, "for x in R, 0 <= f(x) <= 1")
    assert (row.statement, row.verdict) == ("missing(f, x) propagates", "falsified")
    assert row.meta["mathema.policy"]["reason"] == (
        "mathema's default word for a float, not a claim of yours; f drops instead: nan "
        "in, 1.0 out")
    assert row.meta["mathema.policy"]["next"] == (
        "if 1.0 is the answer f should give for a missing x, write `missing(f, x) "
        "drops`; if not, make f raise or give nan back; or accept it as a discovery: "
        "mathema accept test_policy_claims_say_what_f_does_with_no_value.clamp01 "
        "missing[x] --as discovery --corrected \"missing(f, x) drops\"")


def test_an_unannotated_parameter_raises_on_none_by_default():
    rows = {p.statement: p for p in _policy_rows(double, "for x in [0, 1], f(x) == 2*x")}
    row = rows["absent(f, x) raises"]
    assert row.verdict == "holds"
    assert row.meta["mathema.policy"]["reason"] == (
        "default: x has no annotation, so it may be None, and f raises on it; confirmed "
        "on the 42 draws of c0[float]. Annotate x as float to exclude None, or write "
        "this row with mathema claims "
        "test_policy_claims_say_what_f_does_with_no_value.double --write")


def test_an_author_admitted_absence_that_raises_is_unaccounted_for():
    rows = {p.statement: p for p in _policy_rows(opt_root, "for x in [0, 1], f(x) >= 0")}
    row = rows["absent(f, x)"]
    assert row.verdict == "falsified"
    assert row.meta["mathema.policy"]["source"] == "observed"
    assert row.meta["mathema.policy"]["reason"] == (
        "f raised TypeError at x = None, and no claim says it may")
    assert row.meta["mathema.policy"]["next"] == (
        "x is Optional[float], so f promised to take None. If the raise is intended, "
        "state `absent(f, x) raises(TypeError)`; otherwise handle None in f, or annotate "
        "x as float; or accept the raise as a discovery (mathema accept "
        "test_policy_claims_say_what_f_does_with_no_value.opt_root absent[x] --as "
        "discovery) and state `absent(f, x) raises(TypeError)`")


def test_a_guard_derives_the_row():
    (row,) = _policy_rows(guarded, "for x in [0, 1], f(x) >= 0")
    assert (row.statement, row.verdict) == ("missing(f, x) raises(ValueError)", "proven")
    assert row.meta["mathema.policy"]["source"] == "derived"


def test_members_that_behave_differently_get_a_row_each():
    rows = {p.statement: p.verdict for p in _policy_rows(total, "for xs in [0, 1]^n, f(xs) >= 0")}
    # the null row states the default a list slot has, which the raise
    # contradicts
    assert rows == {"missing(f, xs, null) propagates": "falsified",
                    "missing(f, xs, nan) propagates": "holds"}


def test_a_stated_policy_replaces_the_default_row():
    rec = mathema.check(clamp01, claims=[mathema.claim("missing(f, x) drops")])
    rows = [p for p in rec.probes if (p.meta or {}).get("mathema.policy")]
    assert [(p.statement, p.verdict) for p in rows] == [("missing(f, x) drops", "holds")]


def test_a_contradicted_default_row_gates_verify():
    from mathema.verify import gate
    (row,) = _policy_rows(clamp01, "for x in R, 0 <= f(x) <= 1")
    assert row.verdict == "falsified"
    report = gate([row], strict=False)
    assert report.falsified == 1
    assert report.problems == [
        "1 policy row to settle: missing[x], f drops a missing x (nan in, 1.0 out) where "
        "mathema's default says propagates; write `missing(f, x) drops` or change f"]


def test_the_record_prints_a_policy_row_with_its_reason_and_next_step():
    rec = mathema.check(clamp01, claims=[mathema.claim("for x in R, 0 <= f(x) <= 1",
                                                       name="c0")])
    text = repr(rec)
    assert ("    falsified  policy       f(nan)   no missing policy stated; returns 1.0\n"
            "                            possible fixes: (i) mathema claims "
            "test_policy_claims_say_what_f_does_with_no_value.clamp01 --adopt 'missing[x]'"
            "  (ii) exclude nan  (iii) handle nan at entry") in text, text


def test_the_absent_word_parses_without_f():
    with pytest.raises(InvalidConjecture):
        claim("missing(g, x) propagates")


# --- the claims command --------------------------------------------------

_PMOD = (
    "# SPDX-License-Identifier: BUSL-1.1\n# Copyright 2026 Tetrion Ltd\n"
    "import math\nfrom typing import Optional\n\n"
    "def clamp(x: float) -> float:\n    return max(0.0, min(1.0, x))\n\n"
    "def lin(x: float) -> float:\n    return 2.0 * x + 1.0\n\n"
    "def root_opt(x: Optional[float]) -> float:\n    return math.sqrt(x)\n")
_PCLAIMS = (
    "pmod.clamp:\n  claims:\n    - name: unit\n"
    "      statement: \"for x in R, 0 <= f(x) <= 1\"\n"
    "pmod.lin:\n  claims:\n    - name: line\n"
    "      statement: \"for x in R, f(x) == 2*x + 1\"\n"
    "pmod.root_opt:\n  claims:\n    - name: nonneg\n"
    "      statement: \"for x in [0, 4], f(x) >= 0\"\n")


def _pproject(tmp_path, monkeypatch):
    (tmp_path / "pmod.py").write_text(_PMOD)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "p.claims.yaml").write_text(_PCLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def test_the_claims_command_groups_the_policy_rows_by_state(tmp_path, monkeypatch, capsys):
    _pproject(tmp_path, monkeypatch)
    from mathema.cli import main
    assert main(["claims", "pmod.clamp", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "pmod.clamp: 1 policy row about x" in out
    at = out.index("  contradicted by the code (change the word, the code, or accept it "
                   "as a discovery; --write writes these with the contradiction in the "
                   "note):")
    assert out[at + 1] == ("    falsified missing[x]: missing(f, x) propagates   "
                           "[mathema's default word for a float, not a claim of yours; "
                           "f drops instead: nan in, 1.0 out]")
    assert main(["claims", "pmod.root_opt", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "  not covered by any claim yet (the line beneath says what to write, or " \
           "what to change; --write leaves these out):" in out
    assert "    falsified absent[x]: f raised TypeError at x = None, and no claim says it " \
           "may" in out


def test_write_writes_every_row_with_a_true_note(tmp_path, monkeypatch, capsys):
    import datetime

    import yaml
    _pproject(tmp_path, monkeypatch)
    from mathema.cli import main
    today = datetime.date.today().isoformat()
    main(["claims", "pmod.clamp", "--root", str(tmp_path), "--write"])
    assert capsys.readouterr().out.strip() == (
        "pmod.clamp: wrote 1 policy row to claims/policies.claims.yaml: missing[x]. "
        "The code contradicts missing[x] (f drops, nan in, 1.0 out): change the word "
        "in the file, change f, or accept it as a discovery (mathema accept pmod.clamp "
        "missing[x] --as discovery --corrected \"missing(f, x) drops\")")
    main(["claims", "pmod.lin", "--root", str(tmp_path), "--write"])
    assert capsys.readouterr().out.strip() == (
        "pmod.lin: wrote 1 policy row to claims/policies.claims.yaml: missing[x]")
    main(["claims", "pmod.root_opt", "--root", str(tmp_path), "--write"])
    assert capsys.readouterr().out.strip() == (
        "pmod.root_opt: wrote 1 policy row to claims/policies.claims.yaml: missing[x]. "
        "Not written: absent[x], f raises TypeError at x = None and no claim says it "
        "may; state `absent(f, x) raises(TypeError)` yourself, or handle None in f")
    written = yaml.safe_load((tmp_path / "claims" / "policies.claims.yaml").read_text())
    assert written["pmod.clamp"] == {"claims": [{
        "name": "missing[x]", "statement": "missing(f, x) propagates",
        "note": f"written by mathema claims --write: mathema's default word for a "
                f"float, not a claim of yours; contradicted by the code on {today}: f "
                f"drops, nan in, 1.0 out"}]}
    assert written["pmod.lin"] == {"claims": [{
        "name": "missing[x]", "statement": "missing(f, x) propagates",
        "note": "written by mathema claims --write: mathema's default for a float, "
                "which may be nan"}]}
    assert written["pmod.root_opt"] == {"claims": [{
        "name": "missing[x]", "statement": "missing(f, x) propagates",
        "note": "written by mathema claims --write: from math.sqrt's own policy row, "
                "which f calls"}]}
    # the file mathema wrote loads, and the row is now declared
    assert main(["claims", "pmod.lin", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "  - missing[x]: missing(f, x) propagates" in out


# --- a bare claim completes its bindings from the signature ---------------

def test_a_bare_claim_draws_the_hole_its_annotation_admits():
    rec = mathema.check(scaled, claims=[mathema.claim("f(x) == 2*x + 1", name="c0")])
    (value,) = [p for p in rec.probes if p.name == "c0"]
    assert value.statement == "f(x) = 2*x + 1"
    rows = [p for p in rec.probes if (p.meta or {}).get("mathema.policy")]
    assert [(p.statement, p.verdict) for p in rows] == \
        [("missing(f, x) propagates", "holds")]
    assert rows[0].meta["mathema.policy"]["reason"].startswith("default for a float")
    assert "    proven     mathematics  f(x) = 2*x + 1" in repr(rec).splitlines(), repr(rec)


def test_a_bare_claim_on_a_list_carries_a_row_per_member():
    rows = {p.statement: p.verdict for p in _policy_rows(total, "f(xs) == sum(xs)")}
    assert rows == {"missing(f, xs, null) propagates": "falsified",
                    "missing(f, xs, nan) propagates": "holds"}


# --- every remedy a row prints is a claim that holds ----------------------

def floor_of(x: float) -> int:
    return math.floor(x)


def converted(x: float) -> Optional[float]:
    return None if x != x else x


def doubled(x: float) -> list:
    return [x, x]


def kept(xs: list) -> list:
    return [v for v in xs if v is not None and v == v]


def copied(xs: list) -> list:
    return list(xs)


def emptied(xs: list) -> Optional[list]:
    return None if any(v is None or v != v for v in xs) else list(xs)


def padded(xs: list) -> list:
    return list(xs) + [float("nan")]


_BEHAVIOURS = [
    (floor_of, "for x in [0, 10], f(x) <= x", "raises"),
    (clamp01, "for x in R, 0 <= f(x) <= 1", "drops"),
    (scaled, "for x in [0, 1], f(x) >= 1", "propagates"),
    (converted, "for x in [0, 1], f(x) == x", "converts"),
    (doubled, "for x in [0, 1], len(f(x)) == 2", "introduces"),
    (total, "for xs in [0, 1]^n, f(xs) >= 0", "raises"),
    (kept, "for xs in [0, 1]^n, len(f(xs)) <= len(xs)", "drops"),
    (copied, "for xs in [0, 1]^n, len(f(xs)) == len(xs)", "propagates"),
    (emptied, "for xs in [0, 1]^n, len(f(xs)) == len(xs)", "converts"),
    (padded, "for xs in [0, 1]^n, len(f(xs)) == len(xs) + 1", "introduces"),
]


def _remedies(rec) -> list:
    import re
    texts = []
    for p in rec.probes:
        pol = (p.meta or {}).get("mathema.policy") or {}
        for said in (p.note or "", pol.get("next") or "", pol.get("reason") or ""):
            texts += re.findall(r"`([^`]+)`", said)
    out = []
    for t in dict.fromkeys(texts):
        try:
            cj = claim(t)
        except InvalidConjecture:
            continue
        if cj.relation == "policy":
            out.append(t)
    return out


@pytest.mark.parametrize("fn, text, observed", _BEHAVIOURS,
                         ids=[f"{f.__name__}-{b}" for f, _, b in _BEHAVIOURS])
def test_every_remedy_a_row_prints_holds_once_written(fn, text, observed):
    param = "xs" if "xs" in text else "x"
    wrong = "drops" if observed == "raises" else "raises"
    rec = mathema.check(fn, claims=[mathema.claim(text, name="c0"),
                                    mathema.claim(f"missing(f, {param}) {wrong}")])
    remedies = _remedies(rec)
    assert remedies, "the contradicted row names no claim to write"
    for remedy in remedies:
        again = mathema.check(fn, claims=[mathema.claim(text, name="c0"),
                                          mathema.claim(remedy)])
        (row,) = [p for p in again.probes
                  if (p.meta or {}).get("mathema.policy") and p.statement == remedy]
        assert row.verdict == "holds", (remedy, row.verdict, row.note)


def test_a_member_row_remedy_names_its_member():
    rows = {p.statement: p for p in _policy_rows(total, "for xs in [0, 1]^n, f(xs) >= 0")}
    nxt = rows["missing(f, xs, null) propagates"].meta["mathema.policy"]["next"]
    assert "`missing(f, xs, null) raises(TypeError)`" in nxt


def test_an_array_holding_a_drawn_null_counts_it():
    from mathema._linalg_eval import as_array
    from mathema._missing_policy import classify_call
    held = as_array([None, float("nan")])
    assert classify_call({"xs": [None, float("nan")]}, held) == "propagates"
