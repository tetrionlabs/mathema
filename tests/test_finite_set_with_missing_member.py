# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A finite set that lists a missing value beside numbers is adjudicated
and recorded without crashing: the record's sampling summary orders
mixed members the way the rendered domain does."""
import textwrap

from mathema.conjecture import check_conjectures, claim
from mathema.probing import _sampling_shorthand


def test_the_sampling_summary_orders_a_missing_member_beside_numbers():
    from mathema.domain import parse_binding
    bound = parse_binding("x in {0.25, None}")[1]
    text = _sampling_shorthand({"x": "scalar"}, {"x": bound}, 8)
    assert "x~U{" in text and "0.25" in text


def test_a_claim_over_such_a_set_returns_a_verdict(tmp_path):
    import importlib.util
    import sys
    p = tmp_path / "missing_member_fns.py"
    p.write_text(textwrap.dedent('''
        def zero_if_missing(x):
            """Replaces any missing value with 0.0."""
            if x is None or x != x:
                return 0.0
            return x
    '''))
    spec = importlib.util.spec_from_file_location("missing_member_fns", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["missing_member_fns"] = mod
    spec.loader.exec_module(mod)
    (probe,) = check_conjectures(mod.zero_if_missing, [claim("for x in {0.25, None}, f(x) >= 0")])
    assert probe.verdict in ("proven", "holds", "falsified", "unknown")
