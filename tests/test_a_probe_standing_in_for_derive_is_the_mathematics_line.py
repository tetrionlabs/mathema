# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When derive cannot decide a claim and the probe stands in for it, the
probe's verdict is shown on the mathematics line, and the computation
line beneath it is the float companion's: a record never shows two
computation lines that disagree."""
import mathema


def average_charge(charges: list) -> float:
    """The mean of a customer's charges."""
    return sum(charges) / len(charges)


_BETWEEN = ("for charges in R^n \\ {missing}, "
            "min(charges) <= average_charge(charges) <= max(charges)")


def _verdict_lines(text: str) -> list:
    return [line.split()[:2] for line in text.splitlines()
            if line.startswith("    ") and not line.startswith("     ")]


def test_the_stand_in_is_the_mathematics_line_above_the_computation():
    record = mathema.check(average_charge, claims=[
        mathema.claim(_BETWEEN, name="between")])
    main = next(p for p in record.probes if p.name == "between")
    assert main.route == "probe" and main.verdict == "holds"
    lines = _verdict_lines(str(record))
    assert lines[:2] == [["holds", "mathematics"],
                         ["falsified", "computation"]], str(record)


def test_a_probe_verdict_without_a_computation_line_stays_the_computation():
    from mathema._layout import _aspect
    from mathema.records import Probe
    row = Probe("between", _BETWEEN, "holds", route="probe", meta={})
    assert _aspect(row) == "computation"


def test_an_undecided_derive_with_no_companion_keeps_the_computation_line():
    from mathema._layout import _aspect
    from mathema.records import Probe
    row = Probe("bounded", _BETWEEN, "holds", route="probe",
                meta={"mathema.derive_status": "undecided"})
    assert _aspect(row) == "computation"
