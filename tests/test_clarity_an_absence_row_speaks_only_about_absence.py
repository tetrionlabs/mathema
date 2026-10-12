# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An absence row (`absent[name]`, a stated `absent(f, name) ...`
policy) says what the function does when the parameter is absent. It
clears that parameter's absence source and nothing else: it does not
say what the function computes for the values it is given."""
from typing import Optional

from mathema.badges import _clarity_profile, _reductions


def greeting(name: Optional[str]) -> str:
    """A greeting, by name when there is one."""
    if name is None:
        return "Hello"
    return "Hello, " + name


_ROW = {"name": "absent[name]", "statement": "absent(f, name) == 'Hello'",
        "verdict": "proven", "route": "derive",
        "meta": {"mathema.policy": {"kind": "absent", "parameter": "name"}}}


def test_an_absence_row_clears_the_absence_source():
    profile = _clarity_profile(greeting, library_keys=frozenset())
    assert _reductions([_ROW], profile.pure, profile)["absence:name"] == 1.0


def test_an_absence_row_does_not_settle_what_the_function_computes():
    profile = _clarity_profile(greeting, library_keys=frozenset())
    r = _reductions([_ROW], profile.pure, profile)
    assert r["identity"] == r["extent"] == r["shape"] == 0.0
