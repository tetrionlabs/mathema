# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The Python side of the equivalence: the reference implementation,
and a thin ctypes shim over the compiled C++ one.

Build the library first (see README.md), then:

    python shim.py
"""
import ctypes
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_lib = ctypes.CDLL(os.path.join(_HERE, "libema.so")
                   if os.path.exists(os.path.join(_HERE, "libema.so"))
                   else os.path.join(_HERE, "libema.dylib"))
_lib.ema.restype = ctypes.c_double
_lib.ema.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_long,
                     ctypes.c_double]


def ema_cpp(x: list, alpha: float) -> float:
    """The C++ implementation, through the C ABI."""
    buf = (ctypes.c_double * len(x))(*x)
    return _lib.ema(buf, len(x), alpha)


def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def run() -> None:
    from mathema.claims import check_conjectures, claim
    (p,) = check_conjectures(ema, [claim("f =:= g",
                                         funcs={"g": ema_cpp})])
    print(f"verdict: {p.verdict}  route: {p.route}")
    print(f"note:    {p.note}")


if __name__ == "__main__":
    run()
