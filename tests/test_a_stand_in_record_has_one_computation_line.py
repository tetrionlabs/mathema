# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When the probe stands in for a derive that could not settle the claim
and the claim's `[float]` line then fails at a corner, the record has one
computation line: the `[float]` row carries the stand-in's draws as its
draw count, beside the corner failure, and the headline stays
falsified. The stand-in row keeps its own verdict and meta. Where derive
decides, the record is as before."""
import mathema


def average_charge(charges: list) -> float:
    return sum(charges) / len(charges)


def blended_price(old: float, new: float) -> float:
    return (old + new) / 2


_BETWEEN = ("for charges in R^n \\ {missing}, "
            "min(charges) <= average_charge(charges) <= max(charges)")


def _rows(rec):
    return {p.name: p for p in rec.probes}


def test_the_average_has_one_computation_line_with_the_draws_and_the_corner():
    rec = mathema.check(average_charge, claims=[mathema.claim(
        _BETWEEN, name="between")])
    rows = _rows(rec)
    main, line = rows["between"], rows["between[float]"]
    assert main.verdict == "holds" and main.route == "probe", main
    assert line.verdict == "falsified", line
    # the stand-in's draws are the [float] row's draw count
    assert main.n and line.n == main.n, (main.n, line.n)
    assert line.meta["mathema.drawn"] == main.meta["mathema.drawn"]
    # the stand-in row keeps what it recorded
    assert main.meta["mathema.float_companion"] == "between[float]"
    text = str(rec)
    computation = [ln for ln in text.splitlines()
                   if ln.split()[1:2] == ["computation"]]
    assert len(computation) == 1, text
    assert computation[0].split()[0] == "falsified", text
    assert f"across {main.n} draws" in computation[0], text
    assert "counterexample" in computation[0], text
    head = text.splitlines()[1]
    assert head.split("   ")[-1].startswith("falsified"), head


def test_where_derive_decides_the_record_is_unchanged():
    rec = mathema.check(blended_price, claims=[mathema.claim(
        "for old in R, new in R, "
        "min(old, new) <= blended_price(old, new) <= max(old, new)",
        name="between")])
    rows = _rows(rec)
    main, line = rows["between"], rows["between[float]"]
    assert main.verdict == "proven", main
    assert line.verdict == "falsified", line
    text = str(rec)
    assert any(ln.split()[:2] == ["proven", "mathematics"]
               for ln in text.splitlines()), text
    assert any(ln.split()[:2] == ["falsified", "computation"]
               for ln in text.splitlines()), text
