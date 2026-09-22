// SPDX-License-Identifier: BUSL-1.1
// Copyright 2026 Tetrion Ltd
// The C++ implementation of the exponentially weighted moving
// average, exposed through the C ABI so a ctypes shim can call it.
extern "C" double ema(const double* x, long n, double alpha) {
    double y = x[0];
    for (long i = 1; i < n; ++i)
        y = alpha * x[i] + (1.0 - alpha) * y;
    return y;
}
