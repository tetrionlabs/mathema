# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/_providers.py: the capability lookup, entry-point
discovery, caching, and fail-soft fallback."""
from unittest.mock import MagicMock, patch

from mathema import _providers


def teardown_function(_fn):
    _providers._discovered.cache_clear()
    _providers._load.cache_clear()


def test_no_provider_registered_returns_default():
    sentinel = object()
    with patch("mathema._providers.entry_points", return_value=[]):
        assert _providers.get_provider("nonexistent", default=sentinel) is sentinel


def test_no_provider_registered_returns_none_by_default():
    with patch("mathema._providers.entry_points", return_value=[]):
        assert _providers.get_provider("nonexistent") is None


def test_registered_provider_is_returned():
    def real_provider():
        return "real"

    ep = MagicMock()
    ep.name = "thing"
    ep.load.return_value = real_provider
    with patch("mathema._providers.entry_points", return_value=[ep]):
        assert _providers.get_provider("thing") is real_provider


def test_broken_provider_falls_back_to_default_with_a_warning():
    ep = MagicMock()
    ep.name = "thing"
    ep.load.side_effect = RuntimeError("boom")
    sentinel = object()
    with patch("mathema._providers.entry_points", return_value=[ep]):
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _providers.get_provider("thing", default=sentinel)
        assert result is sentinel
        assert any("thing" in str(w.message) for w in caught)


def test_discovery_is_cached_across_calls():
    ep = MagicMock()
    ep.name = "thing"
    ep.load.return_value = "value"
    with patch("mathema._providers.entry_points", return_value=[ep]) as mock_ep:
        _providers.get_provider("thing")
        _providers.get_provider("thing")
        assert mock_ep.call_count == 1
