# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A recorded counterexample replays as the value that broke the claim:
a string witness that happens to read as a complex number (`"j"`,
`"2J"`) stays a string, and a complex witness still replays as a
complex, whether written by this version or an older one."""
from types import SimpleNamespace

from mathema.conjecture import _pinned_arg_sets, _yaml_safe_args


def _replay(stored, kinds=None):
    cj = SimpleNamespace(pins=[{"args": stored}])
    return _pinned_arg_sets(cj, len(stored), kinds=kinds)


def test_a_string_that_reads_as_complex_stays_a_string():
    assert _replay(_yaml_safe_args(["j"]), kinds=["string"]) == [["j"]]
    assert _replay(_yaml_safe_args(["2J"]), kinds=["string"]) == [["2J"]]
    assert _replay(_yaml_safe_args(["jam"]), kinds=["string"]) == [["jam"]]


def test_a_complex_witness_still_replays_as_complex():
    assert _replay(_yaml_safe_args([1 + 2j]), kinds=["complex"]) == [[1 + 2j]]
    assert _replay(_yaml_safe_args([3j]), kinds=["unknown"]) == [[3j]]


def test_an_older_record_s_complex_spelling_still_replays():
    # records written before the tagged form stored "1+2j" as a string
    assert _replay(["1+2j"], kinds=["complex"]) == [[1 + 2j]]
    assert _replay(["1+2j"], kinds=["string"]) == [["1+2j"]]


def test_a_string_witness_in_a_mixed_call_keeps_its_type():
    stored = _yaml_safe_args(["j", 2.5, 1j])
    assert _replay(stored, kinds=["string", "scalar", "complex"]) == [["j", 2.5, 1j]]
