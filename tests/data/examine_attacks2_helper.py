# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Project classes and helpers for the second examine attack."""
LOG = []


class Acc:
    def __init__(self):
        self.total = 0.0

    def bump(self, x):
        self.total += x
        return self.total

    def leak(self, x):
        LOG.append(x)
        return x

    def absorb(self, xs):
        xs.append(1.0)
        return 0.0

    @property
    def prop(self):
        return self.total

    @prop.setter
    def prop(self, v):
        LOG.append(v)

    def __iadd__(self, other):
        LOG.append(other)
        return self
