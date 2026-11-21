# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An exception class defined in a module of its own, for a validator
in another module to raise."""


class ElsewhereError(ValueError):
    pass
