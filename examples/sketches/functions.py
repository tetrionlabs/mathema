# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
import math

def fourier_sum(a0: float, a: list, b: list, x: float) -> float:
    """Partial Fourier sum S_N(x) from cosine coeffs a and sine coeffs b."""
    s = a0 / 2
    for k, (ak, bk) in enumerate(zip(a, b), start=1):
        s = s + ak * math.cos(k * x) + bk * math.sin(k * x)
    return s

def gc_distance(phi1: float, lam1: float, phi2: float, lam2: float) -> float:
    """Great-circle distance on the unit sphere (radians): haversine formula."""
    h = math.sin((phi2 - phi1) / 2) ** 2 \
        + math.cos(phi1) * math.cos(phi2) * math.sin((lam2 - lam1) / 2) ** 2
    return 2 * math.asin(math.sqrt(h))

if __name__ == "__main__":
    import mathema
    print(mathema.check(fourier_sum))
    print()
    print(mathema.check(gc_distance))
