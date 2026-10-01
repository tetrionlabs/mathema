# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Closures with nonlocal state, examined as the function itself."""


def _make_counter():
    count = 0

    def w_counter(x: float) -> float:
        nonlocal count
        count += 1
        return x + count
    return w_counter


def _make_box():
    box = [0.0]

    def w_box(x: float) -> float:
        box[0] += x
        return box[0]
    return w_box


def _make_reader():
    seen = {"n": 0}

    def r_reader(x: float) -> float:
        return x + seen["n"]

    def bump():
        seen["n"] += 1
    return r_reader, bump


w_counter = _make_counter()
w_box = _make_box()
r_reader, _bump = _make_reader()


def r_split_set(s: str) -> str:
    return ",".join(set(s.split()))


def p_nonlocal_local(x: float) -> float:
    t = 0.0

    def add(v):
        nonlocal t
        t += v
    add(x)
    return t
