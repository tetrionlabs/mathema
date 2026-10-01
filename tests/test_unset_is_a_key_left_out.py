# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`unset` is the member of absence for a key or field left out of a
record. A parameter is always passed in a call, so `unset` on a plain
parameter is refused with a sentence, never executed as None."""
from typing import Optional

import pytest

from mathema.conjecture import InvalidConjecture, check_conjectures, claim

REFUSAL = ("x is a parameter, which every call passes, so it cannot be unset; "
           "unset is a key or field left out of a record. Write absent for x = None")


def root(y: float, x: Optional[float] = 4.0) -> float:
    return x + y


@pytest.mark.parametrize("text", [
    "for x in {1.0} | {unset}, f(1.0, x) >= 0",
    "for x in [0, 1] \\ {unset}, f(1.0, x) >= 0",
])
def test_unset_in_a_parameters_binding_is_refused(text):
    with pytest.raises(InvalidConjecture) as err:
        claim(text)
    assert REFUSAL in str(err.value)


def test_unset_as_a_parameters_member_in_a_policy_row_is_misspecified():
    (row,) = check_conjectures(root, [claim("absent(f, x, unset) drops")])
    assert row.verdict == "skipped:misspecified"
    assert row.note == REFUSAL


def test_unset_on_a_path_still_reads():
    from mathema.domain import ABSENT_UNSET
    cj = claim('for d.note in {"a"} | {unset}, len(f(d)) >= 0')
    assert ABSENT_UNSET not in cj.domain["d.note"].excluded
