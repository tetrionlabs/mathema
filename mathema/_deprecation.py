# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The one spelling of a deprecation.

The extension interface's change policy: a removal, rename, or changed
signature raises the extension API version, with the old spelling kept
one minor release behind a `DeprecationWarning`. This module is that
warning's single implementation, so every deprecation names the same
three facts (what is going, what replaces it, which release removes
it) and a `-W error::DeprecationWarning` run surfaces every use.
"""
from __future__ import annotations

import warnings


def warn_deprecated(old: str, *, use: str, remove_in: str) -> None:
    """Emit the deprecation warning shape: what is deprecated, what to
    use instead, and the release that removes it. `stacklevel=3` points
    the warning at the caller's caller, the site actually using the old
    spelling, whether it arrived through a wrapper function or a module
    `__getattr__`."""
    warnings.warn(
        f"mathema: {old} is deprecated and will be removed in "
        f"{remove_in}; use {use}",
        DeprecationWarning, stacklevel=3)


def deprecated_alias(module: str, aliases: dict):
    """A module-level `__getattr__` (PEP 562) that serves renamed names
    one release longer. `aliases` maps each old name to `(value, use,
    remove_in)`; touching the old name warns once per site and returns
    the value, any other missing name raises AttributeError exactly as
    an unaliased module would.

        # at the bottom of the module keeping the alias
        __getattr__ = deprecated_alias(__name__, {
            "old_name": (new_name, "new_name", "0.7"),
        })

    Import-time cost is zero: nothing happens until the old spelling is
    actually touched."""
    def __getattr__(name: str):
        if name in aliases:
            value, use, remove_in = aliases[name]
            warn_deprecated(f"{module}.{name}", use=use, remove_in=remove_in)
            return value
        raise AttributeError(f"module {module!r} has no attribute {name!r}")
    return __getattr__
