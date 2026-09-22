# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The global unicode/ascii output preference. Stdlib-only leaf, so both
the claim grammar and the domain model can read one shared preference
without importing each other.

The preference chooses between the grammar's two equivalent output
spellings (`≤`/`∈`/`⊂` vs `<=`/`in`/`subset`): a caller rendering claim
text (`spec.render_claim_text`) or a domain (`render_domain`) without
stating a preference gets this one. Seeded from the `MATHEMA_UNICODE`
environment variable at import time (`0`/`false`/`False`/empty means
ascii, anything else; including unset; means unicode, the default
either way), then freely changeable at runtime via
`set_unicode_output()`. `render_domain_bound()` deliberately does not
read this; its own `ascii_mode=True` is fixed, for a specific
always-hand-typed surface (the docstring `Domain:` block), not this
general preference.
"""
from __future__ import annotations

import os

_unicode_output = os.getenv("MATHEMA_UNICODE", "1") not in ("0", "false", "False", "")


def set_unicode_output(enabled: bool) -> None:
    """Set the global preference between the grammar's two output
    spellings (see the module-level note above), affects every future
    call to `render_claim_text()`/`render_domain()` that doesn't state
    its own `unicode`/`ascii_mode` explicitly. Takes effect immediately,
    process-wide; there's no scoped/context-manager form of this yet."""
    global _unicode_output
    _unicode_output = bool(enabled)


def get_unicode_output() -> bool:
    """The current global unicode/ascii output preference, `True`
    unless `set_unicode_output(False)` was called, or the
    `MATHEMA_UNICODE` environment variable was set to a falsy value
    before this module was first imported."""
    return _unicode_output
