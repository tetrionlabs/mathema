# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `symbology` capability provider is optional third-party code that
claim rendering consults. A provider that answers changes the rendered
names; a provider that raises is skipped for that render with one
warning naming it, and the claim renders with mathema's own names."""
import sys
import types
import warnings
from importlib.metadata import EntryPoint

import pytest

from mathema import _providers
from mathema._timeout import _WallClockExpired
from mathema.conjecture import claim
from mathema.spec import render_claim_text

_MODULE = "fake_symbology_provider"
_CLAIM = "for spot in [1, 500], strike in [1, 500], f(spot, strike) >= 0"


class _Finance:
    _MAP = {"spot": "S", "strike": "K"}

    @staticmethod
    def symbol_for_param(name):
        return _Finance._MAP.get(name)


class _RaisingParam:
    @staticmethod
    def symbol_for_param(name):
        raise RuntimeError("provider bug")


class _RaisingFunc:
    @staticmethod
    def symbol_for_param(name):
        return {"spot": "S"}.get(name)

    @staticmethod
    def symbol_for_func(name):
        raise ValueError("provider bug")


class _Interrupted:
    @staticmethod
    def symbol_for_param(name):
        raise _WallClockExpired()


@pytest.fixture()
def install(monkeypatch):
    """Register `provider` as the `symbology` entry point, loaded
    through the same discovery path an installed package uses."""
    module = types.ModuleType(_MODULE)
    monkeypatch.setitem(sys.modules, _MODULE, module)
    monkeypatch.setattr(_providers, "_warned_failures", set())

    def _install(provider):
        module.Provider = provider
        ep = EntryPoint(name="symbology", value=f"{_MODULE}:Provider",
                        group=_providers.CAPABILITY_GROUP)
        monkeypatch.setattr(_providers, "_discovered",
                            lambda: {"symbology": ep})
        _providers._load.cache_clear()

    yield _install
    _providers._load.cache_clear()


def test_a_symbology_provider_renames_parameters(install):
    install(_Finance)
    text = render_claim_text(claim(_CLAIM), unicode=False)
    assert "let S = spot" in text and "let K = strike" in text


def test_a_raising_provider_falls_back_to_default_names_with_one_warning(install):
    default = render_claim_text(claim(_CLAIM), unicode=False)
    install(_RaisingParam)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = render_claim_text(claim(_CLAIM), unicode=False)
        second = render_claim_text(claim(_CLAIM), unicode=False)
    assert first == second == default
    messages = [str(w.message) for w in caught]
    assert len(messages) == 1
    assert f"{_MODULE}:Provider" in messages[0]
    assert "provider bug" in messages[0]


def test_a_provider_raising_in_its_function_hook_drops_all_its_renames(install):
    default = render_claim_text(
        claim("let g = numpy.exp, for spot in [0, 1], g(spot) >= 1"),
        unicode=False)
    install(_RaisingFunc)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        text = render_claim_text(
            claim("let g = numpy.exp, for spot in [0, 1], g(spot) >= 1"),
            unicode=False)
    assert text == default
    assert "let S" not in text
    assert len(caught) == 1


def test_a_wall_clock_interrupt_inside_a_provider_is_not_swallowed(install):
    install(_Interrupted)
    with pytest.raises(_WallClockExpired):
        render_claim_text(claim(_CLAIM), unicode=False)


class _Colliding:
    _MAP = {"spot": "S", "strike": "rate"}

    @staticmethod
    def symbol_for_param(name):
        return _Colliding._MAP.get(name)


def test_a_provider_renaming_onto_another_parameter_is_refused(install):
    law = ("for spot in [1, 500], strike in [1, 500], rate in [0, 1], "
           "f(spot, strike, rate) >= 0")
    default = render_claim_text(claim(law), unicode=False)
    install(_Colliding)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        text = render_claim_text(claim(law), unicode=False)
    assert text == default
    assert "let S" not in text
    messages = [str(w.message) for w in caught]
    assert len(messages) == 1
    assert f"{_MODULE}:Provider" in messages[0]
    assert "'rate'" in messages[0] and "strike" in messages[0]
    reparsed = claim(text)
    assert set(reparsed.domain) == {"spot", "strike", "rate"}
