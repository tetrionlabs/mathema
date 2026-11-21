# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness mapping never reads back as an escaped string, and a
mapping key holding a lone surrogate is stored and read back.

A real witness that is a mapping with the single key `escaped_str` is
written in a spelling the `escaped_str` string tag cannot be read
from, so it replays as the mapping it was even when its value is text
that looks like an escaped surrogate. A mapping whose key holds a lone
surrogate is written with its keys escaped and reads back with the
same keys. The `complex`, `set` and `frozenset` tags read back as they
did.
"""
import pytest
import yaml

from mathema.conjecture import _restored_value, _yaml_safe_args
from mathema.spec import _SAFE_LOADER, dump_yaml


def _round_trip(value):
    written = dump_yaml({"args": _yaml_safe_args((value,))})
    (back,) = yaml.load(written, Loader=_SAFE_LOADER)["args"]
    return _restored_value(back)


@pytest.mark.parametrize("mapping", [
    {"escaped_str": "\\uD800"},
    {"escaped_str": "a\\uDC00\\\\b"},
    {"escaped_str": "plain"},
    {"escaped_str": {"escaped_str": "\\uD800"}},
    {"escaped_str": ["\\uD800"]},
])
def test_a_mapping_with_the_tag_key_reads_back_as_the_mapping(mapping):
    assert _round_trip(mapping) == mapping


@pytest.mark.parametrize("mapping", [
    {"\ud800": 1},
    {"a\udc00\\b": "\ud800", "plain": 2},
    {"escaped_str": 1, "\ud83d": 2},
])
def test_a_mapping_key_holding_a_lone_surrogate_reads_back(mapping):
    assert _round_trip(mapping) == mapping


@pytest.mark.parametrize("value", [
    1 + 2j, {1, 2}, frozenset({"a"}), "\ud800", {"k": 1 - 1j}, [{3}],
])
def test_the_other_tags_read_back_as_before(value):
    assert _round_trip(value) == value
