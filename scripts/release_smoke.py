# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A few claims whose verdicts are settled, run against an installed mathema.

Intent:
    Confirms that a built and installed distribution reads, derives,
    falsifies and records: an exact identity is proven, a false one is
    falsified with a witness, and the installed version is the one being
    released. Exits non-zero, naming the claim, on any other verdict.
"""
from __future__ import annotations

import sys

import mathema


def double(x: float) -> float:
    """Twice x."""
    return x + x


def ratio_of_tenths(k: int) -> float:
    """k tenths, as a float."""
    return k * 0.1


EXPECTED = [
    (double, "for x in [-10, 10], f(x) == 2 * x", "proven"),
    (double, "for x in [1, 10], f(x) == 3 * x", "falsified"),
    (ratio_of_tenths, "for k in [0, 20] subset Z, f(k) ~= k / 10", "proven"),
]


def main(argv: list[str]) -> int:
    """Run each claim and compare its verdict's head with the expected one."""
    if len(argv) > 1 and mathema.__version__ != argv[1]:
        print(f"installed mathema is {mathema.__version__}, expected {argv[1]}")
        return 1
    wrong = 0
    for fn, law, want in EXPECTED:
        (probe,) = mathema.claims.check_conjectures(fn, [mathema.claim(law, name="smoke")])
        got = str(probe.verdict).split(":")[0]
        mark = "ok " if got == want else "BAD"
        print(f"{mark} {fn.__name__}: {law} -> {probe.verdict} (route {probe.route}), expected {want}")
        wrong += got != want
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
