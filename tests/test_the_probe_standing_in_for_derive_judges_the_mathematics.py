# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When derive cannot settle a claim (the wall clock, or sympy unable to
close the identity), the probe stands in for it on the mathematics
line. A point where the float computation gives no value, or misses the
result beyond its precision, while the claim holds in exact arithmetic
is then the computation line's finding, never a falsification of the
mathematics: between a fast machine and a slow one the headline moves
from proven to holds, and no further."""
import importlib.util
import re
import textwrap

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.records import Probe


@pytest.fixture(scope="module")
def ema(tmp_path_factory):
    p = tmp_path_factory.mktemp("ema") / "emamod.py"
    p.write_text(textwrap.dedent('''
        def ema(x: list, alpha: float) -> float:
            """Exponentially weighted moving average."""
            y = x[0]
            for v in x[1:]:
                y = alpha * v + (1 - alpha) * y
            return y
    '''))
    spec = importlib.util.spec_from_file_location("emamod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.ema


def _law(fn, name):
    return next(c for c in mathema.suggest_claims(fn)
                if getattr(c, "name", None) == name)


# the equivariances with the empty input excluded by the premise: with
# companions on the record then has exactly two lines, the mathematics
# and the [float] computation (an empty-input line would be folded into
# the headline)
_LAWS = {
    "scale_equivariant": (
        "for x in R^n, assuming len(x) >= 1, let c be [-5, 5], "
        "c*f(x, alpha) == f(g(x, c), alpha)",
        {"g": "mathema.f.scale_seq"}),
    "translation_equivariant": (
        "for x in R^n, assuming len(x) >= 1, let c be [-5, 5], "
        "f(x, alpha) + c == f(g(x, c), alpha)",
        {"g": "mathema.f.shift_seq"}),
}


def _bound(name, **kw):
    text, funcs = _LAWS[name]
    return claim(text, funcs=funcs, **kw)


def _with_companion(fn, cj):
    """The claim's own record and its `[float]` line."""
    rows = check_conjectures(fn, [cj], float_companions=True)
    (companion,) = [p for p in rows if p.name.endswith("[float]")]
    (main,) = [p for p in rows if p.name == companion.name[:-len("[float]")]]
    assert len(rows) == 2, [p.name for p in rows]
    return main, companion


def _derive_cut_short(status: str):
    """A derive stage that reports it could not settle the claim, as a
    proof attempt cut by the wall clock does (status "undecided"), or
    as derive does for a claim it cannot read (status "unsupported")."""
    def stage(ctx, fn, facts, extensive):
        ctx.derive_undecided = Probe(
            ctx.cj.name, ctx.statement, "unknown", route="derive",
            note=f"{ctx.note}; derive could not decide it",
            meta={"mathema.derive_status": status,
                  **({"mathema.timeout": "fast"} if status == "undecided" else {})})
        return None
    return stage


@pytest.fixture
def derive_cut_by_the_clock(monkeypatch):
    monkeypatch.setattr(mathema.conjecture, "_adjudicate_derive",
                        _derive_cut_short("undecided"))


@pytest.fixture
def derive_does_not_apply(monkeypatch):
    monkeypatch.setattr(mathema.conjecture, "_adjudicate_derive",
                        _derive_cut_short("unsupported"))


@pytest.mark.needs_full_proof_budget
def test_derive_proves_the_equivariances_and_the_computation_line_falsifies_at_the_float_limit(ema):
    # the fast machine: the mathematics proven, the [float] line meeting
    # the float-limit corner where alpha * v overflows to nan
    for name in ("scale_equivariant", "translation_equivariant"):
        main, companion = _with_companion(ema, _bound(name))
        assert main.verdict == "proven", (name, main.verdict, main.note)
        assert companion.verdict == "falsified", (name, companion.note)


def test_a_corner_where_the_claim_holds_exactly_is_a_computation_finding(
        ema, derive_cut_by_the_clock):
    # the slow machine, no computation line asked for: the probe judges
    # the mathematics by its draws, and f returning nan at the float
    # limit (where the claim holds exactly) is noted, not a witness
    (p,) = check_conjectures(ema, [_law(ema, "translation_equivariant")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
    assert p.route == "probe"
    assert p.counterexample is None
    assert p.meta["mathema.derive_status"] == "undecided"
    finding = p.meta["mathema.computation_finding"]
    assert "exact arithmetic" in finding and "finding about the computation" in finding
    assert finding in p.note


@pytest.mark.needs_full_proof_budget
def test_with_a_computation_line_the_corner_is_its_witness_either_way(
        ema, monkeypatch):
    # the computation line meets the float-limit corner on the fast
    # machine and the slow one alike, and is falsified there with the
    # same reason: only the mathematics line moves, from proven to holds,
    # so the headline (falsified by the computation line) is the same
    fast = {name: _with_companion(ema, _bound(name))
            for name in ("scale_equivariant", "translation_equivariant")}
    monkeypatch.setattr(mathema.conjecture, "_adjudicate_derive",
                        _derive_cut_short("undecided"))
    for name, (proven, fast_line) in fast.items():
        held, slow_line = _with_companion(ema, _bound(name))
        assert (proven.verdict, held.verdict) == ("proven", "holds"), \
            (name, proven.verdict, held.verdict, held.counterexample, held.note)
        assert held.counterexample is None
        assert fast_line.verdict == slow_line.verdict == "falsified", \
            (name, fast_line.note, slow_line.note)
        for line in (fast_line, slow_line):
            # the witness: alpha at a magnitude where alpha * v overflows
            alpha = float(re.search(r"alpha = (\S+?)[,:]", line.counterexample).group(1))
            assert abs(alpha) > 1e100, (name, line.counterexample)
            assert "exact arithmetic" in line.note or \
                line.stratum["cause"].endswith("numerical-instability"), \
                (name, line.note, line.stratum)


def test_a_float_miss_where_the_claim_holds_exactly_is_not_the_mathematics_line_s(
        ema, derive_cut_by_the_clock):
    # scale_equivariant's draws reach an ill-conditioned point (alpha of
    # magnitude 1e10, where the float sides differ beyond the allowance
    # while the claim holds exactly) before any corner: the mathematics
    # line is untouched by it, and with no computation line asked for the
    # miss is noted with its condition number
    (p,) = check_conjectures(ema, [_law(ema, "scale_equivariant")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
    finding = p.meta["mathema.computation_finding"]
    assert "exact arithmetic" in finding, finding
    assert "κ" in finding or "no value" in finding, finding


def plus_one(x: float) -> float:
    return x + 1.0


def test_a_stand_in_whose_computation_is_clean_shows_one_line(
        derive_cut_by_the_clock):
    # the companion sweep ran the corners of [0, 1] and held: the stand-in's
    # own line already says the computation held, so no second line
    rows = check_conjectures(plus_one, [claim("for x in [0, 1], f(x) == x + 1")],
                             float_companions=True)
    assert [p.verdict for p in rows] == ["holds"], [(p.name, p.verdict) for p in rows]
    assert "mathema.float_companion" not in rows[0].meta


def test_a_probe_route_claim_is_the_computation_and_the_corner_falsifies_it(ema):
    law = _law(ema, "translation_equivariant")
    (p,) = check_conjectures(ema, [claim(law.raw, route="probe", funcs=law.funcs)])
    assert p.verdict == "falsified"
    assert "returned nan" in p.counterexample, p.counterexample


def test_where_derive_does_not_apply_the_probe_is_the_computation_line(
        ema, derive_does_not_apply):
    # an unliftable or unsupported claim has no mathematics line to stand
    # in for: the probe's verdict is the computation's, and the corner
    # falsifies it as before
    (p,) = check_conjectures(ema, [_law(ema, "translation_equivariant")])
    assert p.verdict == "falsified"
    assert "returned nan" in p.counterexample, p.counterexample
    assert "mathema.computation_finding" not in p.meta
