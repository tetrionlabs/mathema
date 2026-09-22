# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The deprecation mechanism the extension change policy names: an old
spelling survives one minor release behind a DeprecationWarning that
states its replacement and its removal release."""
import sys
import types

import pytest

from mathema._deprecation import deprecated_alias, warn_deprecated


def test_the_warning_names_all_three_facts():
    with pytest.warns(DeprecationWarning) as caught:
        warn_deprecated("mathema.old_thing", use="new_thing",
                        remove_in="0.7")
    (w,) = caught
    text = str(w.message)
    assert "mathema.old_thing" in text
    assert "new_thing" in text
    assert "0.7" in text


def test_a_module_alias_warns_on_touch_and_stays_silent_on_import():
    mod = types.ModuleType("fake_extension_surface")
    mod.renamed = lambda: 41
    mod.__getattr__ = deprecated_alias(mod.__name__, {
        "old_spelling": (mod.renamed, "renamed", "0.7")})
    sys.modules[mod.__name__] = mod
    try:
        with pytest.warns(DeprecationWarning, match="old_spelling"):
            assert mod.old_spelling() == 41
        with pytest.raises(AttributeError):
            mod.never_existed
    finally:
        del sys.modules[mod.__name__]
