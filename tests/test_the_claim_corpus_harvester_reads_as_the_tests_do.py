# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim corpus harvester pins the readings the tests make.

`tests/data/claim_corpus.json` is compared with what the code computes
inside the test suite, where `tests/conftest.py` turns every installed
capability provider off. A display provider (a symbology package)
renames parameters in the rendered text, so the harvester reads each
claim with providers off by default too, and with them on only when
asked (`--with-providers`).
"""
import importlib.util
import pathlib
import types

import pytest

from mathema import _providers

HARVEST = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "harvest_claim_corpus.py"

TEXTS = [
    "for price in [0, 100], f(price) <= 2500",
    'for x in [0, 1], f(x, "a") >= 0',
    "for rate in [0, 1], f(price, rate) <= price",
]


@pytest.fixture
def harvest():
    spec = importlib.util.spec_from_file_location("harvest_claim_corpus", HARVEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def renaming_provider(monkeypatch):
    """A display provider that spells `price` as `P`, installed the way
    an entry point would be."""
    provider = types.SimpleNamespace(
        symbol_for_param=lambda name: "P" if name == "price" else None)
    entry = types.SimpleNamespace(name="symbology", value="fake:symbology",
                                  load=lambda: provider)
    monkeypatch.setattr(_providers, "entry_points", lambda **_: [entry])
    _providers._discovered.cache_clear()
    _providers._load.cache_clear()
    yield
    _providers._discovered.cache_clear()
    _providers._load.cache_clear()


def test_the_harvester_reads_with_providers_off_by_default(harvest, renaming_provider):
    with harvest.providers_off():
        test_time = {t: harvest.read_claim(t) for t in TEXTS}
    assert harvest.read_claims(TEXTS) == test_time


def test_with_providers_the_display_provider_is_read(harvest, renaming_provider):
    with_providers = harvest.read_claims(TEXTS, with_providers=True)
    assert "let P = price" in with_providers[TEXTS[0]]["ascii"], with_providers[TEXTS[0]]


def test_providers_are_back_after_the_harvest(harvest, renaming_provider):
    harvest.read_claims(TEXTS)
    assert _providers.get_provider("symbology") is not None
