# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An int with more decimal digits than Python converts to or from
text by default (4300) is written to a record and reads back equal,
as a plain record value and as a falsifying witness, under every YAML
reader mathema reads records with; the process-wide digit limit is
left as it was."""
import sys

import pytest
import yaml

from mathema.conjecture import _pinned_arg_sets, _yaml_safe_args, claim
from mathema.spec import _SAFE_LOADER, dump_yaml, load_verified, save_verified_entry

LONG_INTS = [pytest.param(sign * (10 ** (digits - 1) + 7), id=f"{sign:+d}x{digits}")
             for digits in (4301, 20000) for sign in (1, -1)]


def _entry(meta):
    return {"identity": {"form": "abc"}, "meta": meta, "claims": []}


@pytest.mark.parametrize("value", LONG_INTS)
def test_a_long_int_record_value_reads_back_equal(value, tmp_path):
    limit = sys.get_int_max_str_digits()
    save_verified_entry("pkg.mod.f", _entry({"big": value, "rows": [value]}),
                        str(tmp_path))
    meta = load_verified(str(tmp_path))["pkg.mod.f"]["entry"]["meta"]
    assert meta["big"] == value and meta["rows"] == [value]
    text = (tmp_path / ".mathema" / "verified" / "pkg.mod.f.yaml").read_text()
    for loader in (yaml.SafeLoader, _SAFE_LOADER):
        assert yaml.load(text, Loader=loader)["pkg.mod.f"]["meta"]["big"] == value
    assert sys.get_int_max_str_digits() == limit


@pytest.mark.parametrize("value", LONG_INTS)
def test_a_long_int_witness_replays_equal(value):
    safe = _yaml_safe_args((value, [value]))
    written = dump_yaml({"meta": {"mathema.counterexample_args": safe}})
    for loader in (yaml.SafeLoader, _SAFE_LOADER):
        back = yaml.load(written, Loader=loader)["meta"]["mathema.counterexample_args"]
        cj = claim("f(x, y) == 0")
        cj.pins = [{"args": back}]
        assert _pinned_arg_sets(cj, 2) == [[value, [value]]]


def test_an_int_within_the_limit_is_still_written_in_decimal():
    assert dump_yaml({"v": -(10 ** 4299)}) == f"v: {-(10 ** 4299)}\n"
