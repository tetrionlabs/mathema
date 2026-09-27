# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The language adaptors are asked in an explicit order: an adaptor may
carry `__mathema_adaptor_priority__` (an int, default 0), higher asked
first, ties broken by entry-point name. So a library-specific adaptor
(a model class that is also a dataclass) wins over a structural one
whatever the names are. `language_adaptors()` on the extension surface
is that ordered registry, so a package that builds on adaptors finds a
third party's the same way it finds its own."""
import pytest

import mathema.languages as languages
from mathema.interfaces import extension
from mathema.languages import StringLanguage

GENERAL = StringLanguage("general_text", char_ok=lambda c: True)
SPECIFIC = StringLanguage("specific_text", char_ok=str.isalpha)


class _Entry:
    def __init__(self, name, obj):
        self.name, self.value, self._obj = name, f"pkg:{name}", obj

    def load(self):
        return self._obj


class Marked:
    """A schema class both adaptors below accept."""


def general(obj):
    """Accepts any class."""
    return GENERAL if isinstance(obj, type) else None


def specific(obj):
    """Accepts only `Marked`."""
    return SPECIFIC if obj is Marked else None


specific.__mathema_adaptor_priority__ = 100


@pytest.fixture
def registry(monkeypatch):
    def install(*entries):
        monkeypatch.setattr(languages, "_discovered_adaptors", lambda: tuple(entries))
        languages._loaded_adaptors.cache_clear()
    yield install
    languages._loaded_adaptors.cache_clear()


def test_a_higher_priority_is_asked_first_whatever_the_names(registry):
    registry(_Entry("aaa_general", general), _Entry("zzz_specific", specific))
    assert [name for name, _ in languages.language_adaptors()] == ["zzz_specific", "aaa_general"]
    language, adaptor = languages.adapt_annotation(Marked)
    assert (language, adaptor) == (SPECIFIC, "zzz_specific")
    assert languages.adapt_annotation(int) == (GENERAL, "aaa_general")


def test_equal_priorities_fall_back_to_the_name(registry):
    registry(_Entry("b_general", general), _Entry("a_general", general))
    assert [name for name, _ in languages.language_adaptors()] == ["a_general", "b_general"]


def test_a_priority_that_is_not_an_int_counts_as_zero(registry):
    def odd(obj):
        """Accepts nothing."""
        return None
    odd.__mathema_adaptor_priority__ = "high"
    registry(_Entry("b_odd", odd), _Entry("a_general", general))
    assert [name for name, _ in languages.language_adaptors()] == ["a_general", "b_odd"]


def test_the_ordered_registry_is_on_the_extension_surface():
    assert "language_adaptors" in extension.SURFACE["languages"]
    assert extension.language_adaptors is languages.language_adaptors
