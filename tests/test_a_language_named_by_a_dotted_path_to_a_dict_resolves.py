# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language named by a dotted path to a module-level dict resolves.

A JSON Schema written as a dict at module level (`L[shop.webhooks.
CHARGE_EVENT]`) is a plain data value: it is judged by the module that
holds it, the author's own, not by the module its type comes from
(`dict` is defined in `builtins`). Callables and classes keep their
own reading, so `L[os.system]`, a dunder on the path, and any value
held by a system module stay refused.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from mathema import languages
from mathema._claim_reach import walk_refusal
from mathema.domain import LanguageRef
from mathema.languages import UnknownLanguage, resolve

_WEBHOOKS = '''
    import os as osmod
    import sys as sysmod
    from os import environ as ENV

    CHARGE_EVENT = {
        "type": "object",
        "properties": {"amount": {"type": "number", "minimum": 0},
                       "currency": {"type": "string", "enum": ["EUR", "USD"]}},
        "required": ["amount", "currency"],
    }
    EVENT_TYPES = ["charge", "refund"]
'''


class _Schema:
    """A finite language standing for a dict schema."""
    kind, level = "mapping", "finite"

    def __init__(self, schema):
        self.schema = schema
        self.name = "charge_event"

    def contains(self, value):
        return isinstance(value, dict)

    def explain(self, value):
        return None

    def sample(self, rng):
        return {"amount": 1.0, "currency": "EUR"}

    def members(self):
        return [{"amount": 1.0, "currency": "EUR"}]

    def hazards(self):
        return ()

    def outside(self, rng):
        return {"amount": -1.0}

    def shrink(self, value):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return f"L[{self.name}]"

    def to_json(self):
        return dict(self.schema)


class _Entry:
    def __init__(self, name, value, obj):
        self.name, self.value, self._obj = name, value, obj

    def load(self):
        return self._obj


@pytest.fixture
def shop(tmp_path, monkeypatch):
    pkg = tmp_path / "shop"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "webhooks.py").write_text(textwrap.dedent(_WEBHOOKS))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("shop", "shop.webhooks"):
        sys.modules.pop(name, None)

    def adapt(obj):
        return _Schema(obj) if isinstance(obj, dict) and "type" in obj else None

    monkeypatch.setattr(languages, "_discovered_adaptors",
                        lambda: (_Entry("schema", "pkg.mod:adapt", adapt),))
    languages._loaded_adaptors.cache_clear()
    yield
    languages._loaded_adaptors.cache_clear()
    for name in ("shop", "shop.webhooks"):
        sys.modules.pop(name, None)


def test_a_module_level_dict_schema_resolves(shop):
    assert walk_refusal("shop.webhooks.CHARGE_EVENT") is None
    assert walk_refusal("shop.webhooks.EVENT_TYPES") is None
    language, source = resolve(LanguageRef("shop.webhooks.CHARGE_EVENT"))
    assert source == "adaptor schema"
    assert language.to_json()["required"] == ["amount", "currency"]


@pytest.mark.parametrize("path", ["os.system", "math.__builtins__.exec",
                                  "os.environ"])
def test_a_system_function_dunder_or_system_value_stays_refused(path):
    with pytest.raises(UnknownLanguage, match="may not name"):
        resolve(LanguageRef(path))


@pytest.mark.parametrize("path, module", [
    ("shop.webhooks.sysmod.modules", "sys"),
    ("shop.webhooks.osmod.environ", "os"),
    ("shop.webhooks.ENV", "os"),
])
def test_a_value_held_by_a_system_module_stays_refused(shop, path, module):
    said = walk_refusal(path)
    assert said is not None and "may not name" in said, said
    assert module in said, said
    with pytest.raises(UnknownLanguage, match="may not name"):
        resolve(LanguageRef(path))
