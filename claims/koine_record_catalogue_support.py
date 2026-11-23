# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claim about which catalogue terms the KOINE claims
range over is stated over.

The claims of `claims/koine_record_language_support.py` and those built
on it range over `TERMS`, the record-language oracle's catalogue terms
less those holding a list node, which the KOINE route declines by name
in this version. The claim here says no term is left out for any other
reason: a term is left out exactly when it holds a list node, and the
route then declines it. On the oracle's catalogue at the time of
writing that is one term of thirty-seven.

The function takes an index into `ALL_TERMS`, the oracle's catalogue,
and returns the truth of the statement, so the claim reads
`f(i) == True`."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _language_support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_language_support", _HERE / "koine_record_language_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


L = _language_support()
ALL_TERMS = L.REF.TERMS


def _holds_a_list(node) -> bool:
    if isinstance(node, dict):
        return node.get("op") == "list" or any(_holds_a_list(x) for x in node.values())
    if isinstance(node, list):
        return any(_holds_a_list(x) for x in node)
    return False


def a_term_is_left_out_exactly_when_it_holds_a_list(i: int) -> bool:
    """Whether catalogue term `i` is left out of the terms the KOINE
    claims range over exactly when it holds a list node, and the route
    declines a term left out by name."""
    from mathema.koine import record_membership
    term = ALL_TERMS[int(i)]
    left_out = not any(t is term for t in L.TERMS)
    if left_out != _holds_a_list(term):
        return False
    if not left_out:
        return True
    try:
        record_membership.membership_document(term)
    except record_membership.Declined as e:
        return "list" in str(e)
    return False
