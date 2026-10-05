# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function whose body uses its parameter as a numpy array, with no
annotation to say so."""
import numpy as np


def scaled_mean(a):
    return np.mean(a) * a.size
