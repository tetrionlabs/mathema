# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An integer result too large for a float is compared exactly and never
crashes adjudication: `for n in N, f(n) >= 1` on factorial returns a
verdict, and the ordering margin reads a huge exact difference without
converting it."""
import textwrap

from mathema.conjecture import check_conjectures, claim
from mathema.probing import ordering_shortfall


def test_the_margin_of_a_huge_exact_difference_is_read_exactly():
    assert ordering_shortfall(10 ** 400, 1, ">=") == 0.0
    assert ordering_shortfall(1, 10 ** 400, "<=") == 0.0
    assert ordering_shortfall(10 ** 400 + 5, 10 ** 400, "<=") == 5.0
    assert ordering_shortfall(10 ** 400, 10 ** 400 + 5, ">=") == 5.0


def test_a_claim_over_factorial_returns_a_verdict(tmp_path):
    import importlib.util
    import sys
    p = tmp_path / "huge_int_fns.py"
    p.write_text(textwrap.dedent('''
        def fact(n: int) -> int:
            """n factorial."""
            if n == 0:
                return 1
            return n * fact(n - 1)
    '''))
    spec = importlib.util.spec_from_file_location("huge_int_fns", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["huge_int_fns"] = mod
    spec.loader.exec_module(mod)
    (probe,) = check_conjectures(mod.fact, [claim("for n in N, f(n) >= 1")])
    assert probe.verdict in ("holds", "falsified", "unknown", "proven"), probe
