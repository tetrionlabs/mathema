# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Soundness epochs: which stored verdicts a stricter engine reads again.

A verdict in a record was reached by the engine that wrote it. When a
release reads some kind of evidence more strictly than an earlier one,
a verdict of that kind written before is not known to stand, even
though nothing about the function changed. Each such tightening is one
epoch: `SOUNDNESS_EPOCH` is the current one, and `EPOCH_SCOPES` says,
for each epoch, which rows the tightening could have decided
differently. A row in any epoch's scope is stamped, when written, with
the epoch of the engine that wrote it (`STAMP`, a key of the row's
`meta`); a row with no stamp counts as epoch 0. A stored row is stale
when some epoch later than its stamp has it in scope: verify then
checks its function again, once, and the record it writes carries the
current stamp.
"""
from __future__ import annotations

import re

#: the row meta key holding the epoch of the engine that wrote the row
STAMP = "mathema.soundness_epoch"

#: the current soundness epoch
SOUNDNESS_EPOCH = 1

#: the trigger a re-check under a later epoch records
TRIGGER = "soundness-epoch"

_RAISES = re.compile(r"\braises\s*\(")
_GATES = ("is_missing_safe", "is_absent_safe")


def _route(row: dict) -> str:
    return str(row.get("route") or "").split(":", 1)[0]


def reads_a_raise(row: dict) -> bool:
    """Intent:
        Whether a stored row's verdict is `proven` from reading a
        `raise` statement: a `raises(...)` claim on the derive route, or
        on the examine route a missing-value policy that raises or one
        of the gates read from such policies.
    """
    if str(row.get("verdict") or "").split(":", 1)[0] != "proven":
        return False
    route = _route(row)
    if route == "derive":
        return bool(_RAISES.search(str(row.get("statement") or "")))
    if route == "examine":
        policy = (row.get("meta") or {}).get("mathema.policy")
        if isinstance(policy, dict):
            return policy.get("behaviour") == "raises"
        text = f"{row.get('name') or ''} {row.get('statement') or ''}"
        return any(gate in text for gate in _GATES)
    return False


#: for each epoch, the rows the tightening it names could decide
#: differently. Epoch 1: a `raise` is read only when everything Python
#: runs on the way to it cannot raise something else first.
EPOCH_SCOPES = {1: reads_a_raise}


def in_scope(row: dict) -> bool:
    """Whether any epoch has this row in its scope."""
    return any(scope(row) for scope in EPOCH_SCOPES.values())


def stamp(row: dict) -> dict:
    """`row` with the current epoch stamped on its meta when some epoch
    has it in scope; otherwise unchanged."""
    if not in_scope(row):
        return row
    return {**row, "meta": {**(row.get("meta") or {}), STAMP: SOUNDNESS_EPOCH}}


def stamped_epoch(row: dict) -> int:
    """The epoch a stored row was written at, 0 when it has no stamp."""
    found = (row.get("meta") or {}).get(STAMP)
    return found if isinstance(found, int) and not isinstance(found, bool) else 0


def stale_rows(entry: dict) -> list:
    """Intent:
        The names of a stored record entry's rows written before an
        epoch that has them in scope, in record order.
    """
    out = []
    for row in (entry or {}).get("claims") or []:
        if not isinstance(row, dict):
            continue
        written = stamped_epoch(row)
        if any(epoch > written and scope(row) for epoch, scope in EPOCH_SCOPES.items()):
            out.append(row.get("name") or row.get("statement") or "")
    return out
