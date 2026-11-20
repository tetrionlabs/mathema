# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The soundness epoch counts tightenings of the reading of `raise` that
were released. None has been released yet, so the epoch is 1: a row
stamped by the reading of this release, at any commit before its
release, is stamped 1 and stays current, and only a row with no stamp is
from an earlier epoch."""


def _row(stamp):
    meta = {} if stamp is None else {"mathema.soundness_epoch": stamp}
    return {"name": "rejects", "statement": "for x in [-5, -1], raises(f(x), ValueError)",
            "verdict": "proven", "route": "derive", "meta": meta}


def test_a_row_stamped_before_and_after_this_branch_is_epoch_one():
    from mathema.soundness_epoch import SOUNDNESS_EPOCH, STAMP, stale_rows, stamp
    assert SOUNDNESS_EPOCH == 1
    row = _row(None)
    assert stamp(row)["meta"][STAMP] == 1
    assert stale_rows({"claims": [stamp(row)]}) == []
    assert stale_rows({"claims": [_row(1)]}) == []
    assert stale_rows({"claims": [_row(None)]}) == ["rejects"]


