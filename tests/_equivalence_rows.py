# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The two rows an `f =:= g` claim records: the claim's own row (its
mathematics, or the probe's row when derive could not reach the bodies)
and its computation row, `NAME[float]`, which carries
`mathema.companion_of`."""


def claim_row(probes):
    """The one row in `probes` that is not a computation row."""
    (row,) = [p for p in probes
              if not (p.meta or {}).get("mathema.companion_of")]
    return row


def computation_row(probes):
    """The one computation row in `probes`, or None when there is none."""
    rows = [p for p in probes if (p.meta or {}).get("mathema.companion_of")]
    assert len(rows) <= 1, rows
    return rows[0] if rows else None
