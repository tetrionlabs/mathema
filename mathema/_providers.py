# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A capability is a swappable *presentation* hook, how something
already computed should be shown, unrelated to claim adjudication
(that's `families.py`, a deliberately separate mechanism and a
deliberately separate entry-point group: a claim family answers "can
this be proven," a capability answers "how should this be shown," and
the two should never be discoverable through the same lookup).

Discovery is one thin, generic `importlib.metadata.entry_points()`
lookup, scanned once per process and cached. Fail-soft throughout,
matching `conjecture.py`'s own unrecognized-route handling: a missing
or broken provider never crashes the caller, it falls back to
`default`.
"""
from __future__ import annotations

import functools
import warnings
from importlib.metadata import entry_points

CAPABILITY_GROUP = "mathema.capabilities"


@functools.lru_cache(maxsize=1)
def _discovered():
    return {ep.name: ep for ep in entry_points(group=CAPABILITY_GROUP)}


@functools.lru_cache(maxsize=None)
def _load(name: str):
    ep = _discovered().get(name)
    if ep is None:
        return None
    try:
        return ep.load()
    except Exception as e:
        warnings.warn(f"mathema: provider {ep.value!r} for capability {name!r} "
                      f"failed to load ({e!r}), falling back", stacklevel=2)
        return None


def get_provider(name: str, default=None):
    """The one lookup every capability call site goes through. Returns
    the registered provider for `name` if one loads cleanly, else
    `default`, never raises."""
    provider = _load(name)
    return provider if provider is not None else default
