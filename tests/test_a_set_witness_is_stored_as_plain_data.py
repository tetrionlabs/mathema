# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A falsifying argument that is a set (or holds one) is stored in the
record as plain data, so the JSON report and the YAML record can both
write it, and a later run replays it as the set it was."""
import json

import yaml

from mathema.conjecture import (_pinned_arg_sets, _yaml_safe_args,
                                check_conjectures, claim)


def test_set_arguments_become_plain_data():
    args = (frozenset({2.0, 1.0}), {"k": frozenset({"b", "a"})}, [{3}])
    safe = _yaml_safe_args(args)
    json.dumps(safe)
    yaml.safe_dump(safe)
    assert safe == [{"frozenset": [1.0, 2.0]},
                    {"k": {"frozenset": ["a", "b"]}},
                    [{"set": [3]}]]


def test_a_stored_set_replays_as_the_set_it_was():
    args = (frozenset({2.0, 1.0}), {"k": frozenset({"a"})}, [{3}])
    cj = claim("f(x, y, z) == 0")
    cj.pins = [{"args": _yaml_safe_args(args)}]
    assert _pinned_arg_sets(cj, 3) == [
        [frozenset({1.0, 2.0}), {"k": frozenset({"a"})}, [{3}]]]


def size_less_100(xs: frozenset) -> int:
    return len(xs) - 100


def test_a_falsified_claim_over_a_frozenset_writes_as_json():
    (p,) = check_conjectures(size_less_100, [claim(
        "f(xs) >= 0", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    json.dumps(p.meta)
