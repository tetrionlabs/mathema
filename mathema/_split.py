# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The split offer for a value claim falsified only below some length.

A claim over a sequence `r` can be false only on short inputs: a sample
statistic of one element has no value, `xs[1]` is past the end of a
one-element list, a division by `len(r) - 1` divides by zero. When
every witness lies at a length below some `k`, the claim splits into
two rows that hold:

- the claim itself, with `assuming len(r) >= k`;
- the region row `is_defined: len(r) >= k` on f, the lengths f has a
  value at.

`k` is the least length, from one past the witness's, at which the
claim with that premise is not falsified and the region row is not
falsified either, so every witness of the claim lies below it.

The empty input is not such a length: `R^n` runs from n = 1, and what
f does at `[]` is the empty-input line's fact (is_empty_safe, with its
own fixes), so a headline whose witness is the empty input offers no
split.
"""
from __future__ import annotations

import ast
import re

#: the longest length a split is searched up to
_MAX_AT = 6


def _witness_lengths(probe, seqs: list) -> dict:
    """`{sequence: length}` read off the witness of a falsified claim
    (`r = [0.0]`, `r=[0.0]`)."""
    out: dict = {}
    text = probe.counterexample or ""
    for name in seqs:
        m = re.search(rf"\b{re.escape(name)}\s*=\s*(\[[^\]]*\])", text)
        if m:
            try:
                out[name] = len(ast.literal_eval(m.group(1)))
            except (ValueError, SyntaxError):
                continue
    return out


def split_offer(fn, facts, cj, probe, text: str) -> "dict | None":
    """Intent:
        `{"param": r, "at": k}` when the falsified value claim `cj`
        (its record row `probe`, its full text `text`) holds once `assuming len(r) >= k` is
        added and f is defined exactly where `len(r) >= k`, every
        witness lying below `k`; None otherwise.
    """
    from .claims import check_conjectures, claim
    from .runtime_types import SEQUENCE_KINDS
    if probe.verdict != "falsified" or cj.relation not in (
            "==", "~=", "!=", "<=", ">=", "<", ">") or cj.negated:
        return None
    seqs = [p for p in facts.params
            if facts.param_kinds.get(p) in SEQUENCE_KINDS]
    lengths = _witness_lengths(probe, seqs)
    if len(lengths) != 1:
        return None
    (param, length), = lengths.items()
    if length == 0:
        # the witness is the empty input, the empty-input line's fact
        return None
    if not text:
        return None
    for at in range(max(length + 1, 2), _MAX_AT + 1):
        premise = f"len({param}) >= {at}"
        try:
            narrowed, region = check_conjectures(fn, [
                claim(f"assuming {premise}, {text}", route=cj.route,
                      funcs=cj.funcs),
                claim(premise, name="is_defined")])
        except Exception:
            return None
        if region.verdict.startswith(("holds", "proven")) and \
                narrowed.verdict.startswith(("holds", "proven")):
            return {"param": param, "at": at}
        if region.verdict == "falsified" and \
                "outside the stated region" in (region.counterexample or ""):
            # f has a value below `at`: a longer premise only widens
            # the gap between the region and where f has a value
            return None
    return None


def split_command(key: str, statement: str, offer: dict) -> str:
    """The command that writes the two rows of a split offer."""
    return (f'mathema claims {key} --split "{statement}" '
            f'--at "len({offer["param"]}) >= {offer["at"]}"')
