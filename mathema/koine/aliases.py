# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Short names for KOINE paths, read from `data/aliases.yaml`.

A path is KOINE's own name for an operation and never changes; an alias
is a short name for it (`div_trunc`, `round_ties_up`) and may change.
Every consumer of a short name, such as the renderer's helper calls,
reads it from this one table.
"""
from __future__ import annotations

import functools
import pathlib

import yaml

_TABLE = pathlib.Path(__file__).parent / "data" / "aliases.yaml"


@functools.lru_cache(maxsize=1)
def aliases() -> dict[str, str]:
    """Intent:
        `{alias: path}`, as the table states it.

    Raises:
        ValueError: two aliases name one path, or an alias is not an
            identifier.
    """
    table = yaml.safe_load(_TABLE.read_text()) or {}
    paths: dict = {}
    for alias, path in table.items():
        if not str(alias).isidentifier():
            raise ValueError(f"alias {alias!r} is not an identifier")
        if path in paths:
            raise ValueError(f"{path} has two aliases: {paths[path]} and {alias}")
        paths[path] = alias
    return {str(a): str(p) for a, p in table.items()}


def path_of(alias: str) -> str | None:
    """Intent:
        The KOINE path `alias` names, or None.
    """
    return aliases().get(alias)


def alias_of(path: str) -> str | None:
    """Intent:
        The short name for `path`, or None when it has none.
    """
    return next((a for a, p in aliases().items() if p == path), None)
