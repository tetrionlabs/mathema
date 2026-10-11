# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One run's shared reads: inside `run_scope()`, the claims-file scan,
the verified store, the library claims and claim parses are each worked
out once and shared by every caller, instead of once per caller.

Outside a scope nothing is kept, and every read goes to the disk as it
always does. A file written inside a scope through
`spec.atomic_write_text` drops whatever was kept from it (`wrote`), so
a later read in the same run sees the new contents. Nothing here
outlives the scope or is written anywhere.
"""
from __future__ import annotations

import contextlib
import os

#: the kept reads of the run in progress, by kind, or None outside a run
_STATE: "dict | None" = None


@contextlib.contextmanager
def run_scope():
    """Intent:
        Share reads within the block (see the module docstring). A
        scope opened inside another one joins it, and everything kept
        is dropped when the outermost scope ends.
    """
    global _STATE
    if _STATE is not None:
        yield
        return
    _STATE = {}
    try:
        yield
    finally:
        _STATE = None


def kept(kind: str) -> "dict | None":
    """Intent:
        The run's store of reads of one `kind` (a dict the caller
        fills and reads by its own keys), or None outside a run.
    """
    if _STATE is None:
        return None
    return _STATE.setdefault(kind, {})


def wrote(path: str) -> None:
    """Intent:
        Forget what the run kept from the file at `path`, just
        written: its verified record, the merged store view built from
        it, and, for a claims file, the claims-file scan and every read
        built from claims files.

    Notes:
        Outside a run this does nothing.
    """
    if _STATE is None:
        return
    from .spec import _is_claim_file
    real = os.path.join(os.path.realpath(os.path.dirname(
        os.path.abspath(path))), os.path.basename(path))
    _STATE.get("verified_file", {}).pop(real, None)
    _STATE.pop("verified_listing", None)
    _STATE.pop("verified_view", None)
    if _is_claim_file(os.path.dirname(real), os.path.basename(real)):
        for kind in ("claims_paths", "library_claims", "claims_valid"):
            _STATE.pop(kind, None)
