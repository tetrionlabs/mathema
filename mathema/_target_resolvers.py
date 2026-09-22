# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Target resolvers: how a language-tagged key becomes callables.

A target like `ts:src/ema.ts#ema` names a function that is not a
Python import at all. A registered resolver turns such a key into an
ordinary `targets.Target` whose values are Python callables (proxies
standing in for the foreign function), after which every downstream
stage (probing, gates, corroboration, records) runs unchanged; the
runtime contract those proxies satisfy is `interfaces.runtime`.

Discovery mirrors `_providers.py`: one entry-point scan per process,
per-name load caching, fail-soft throughout. The entry-point NAME is
the tag it serves (`ts`, `cpp`, `rs`), and the loaded object is a
callable `resolver(target, root) -> Target | None`, `None` meaning
"not mine" so resolution falls through to the ordinary import path.
"""
from __future__ import annotations

import functools
import warnings
from importlib.metadata import entry_points

RESOLVER_GROUP = "mathema.target_resolvers"


@functools.lru_cache(maxsize=1)
def _discovered() -> dict:
    return {ep.name: ep for ep in entry_points(group=RESOLVER_GROUP)}


@functools.lru_cache(maxsize=None)
def _load(name: str):
    ep = _discovered().get(name)
    if ep is None:
        return None
    try:
        return ep.load()
    except Exception as e:
        warnings.warn(f"mathema: target resolver {ep.value!r} registered "
                      f"under {name!r} failed to load ({e!r}), skipping it",
                      stacklevel=2)
        return None


def get_resolver(prefix: str, default=None):
    """The one lookup every tagged-target site goes through. Returns
    the registered resolver for `prefix` if one loads cleanly, else
    `default`, never raises."""
    resolver = _load(prefix)
    return resolver if resolver is not None else default
