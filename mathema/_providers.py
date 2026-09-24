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
`default`. A provider that loads but raises while being called is the
call site's to catch; `report_provider_failure` gives every call site
the same once-per-provider warning.
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


_warned_failures: set = set()


def provider_label(name: str) -> str:
    """The entry-point value (`package.module:object`) registered for
    capability `name`, the spelling a warning names a provider by, or
    `name` itself when nothing is registered under it."""
    ep = _discovered().get(name)
    return ep.value if ep is not None else name


def report_provider_failure(name: str, exc: Exception) -> None:
    """Intent:
        Warn that the provider for capability `name` raised `exc` while
        being called and was skipped, once per provider per process.

    Notes:
        A second failure from the same provider is silent, so a provider
        that raises on every render produces one warning, not one per
        claim.
    """
    label = provider_label(name)
    if (name, label) in _warned_failures:
        return
    _warned_failures.add((name, label))
    warnings.warn(f"mathema: provider {label!r} for capability {name!r} "
                  f"raised ({exc!r}), skipped for this call, falling back "
                  f"to mathema's own rendering", stacklevel=3)


def report_provider_rejection(name: str, reason: str) -> None:
    """Intent:
        Warn that the provider for capability `name` returned answers
        mathema refused (`reason` says why), so it was skipped for this
        call, once per provider per process.

    Notes:
        Shares the once-per-provider record with
        `report_provider_failure`: a provider is warned about once,
        whichever way it first went wrong.
    """
    label = provider_label(name)
    if (name, label) in _warned_failures:
        return
    _warned_failures.add((name, label))
    warnings.warn(f"mathema: provider {label!r} for capability {name!r} "
                  f"was refused ({reason}), skipped for this call, falling "
                  f"back to mathema's own rendering", stacklevel=3)
