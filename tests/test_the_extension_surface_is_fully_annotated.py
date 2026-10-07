# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every callable the extension surface exports is fully annotated.

mathema ships `py.typed`, so a package registering through the
extension surface is type-checked against it: a parameter or a return
left unannotated there reads as `Any` to the package's own checker and
hides a mismatch. Every parameter (`self` aside) and every return of a
public callable in `mathema.interfaces.extension` carries an
annotation.
"""
from __future__ import annotations

import inspect

import pytest

import mathema.interfaces.extension as extension


def _public_callables() -> list:
    names = set(extension.__all__) | {n for n in dir(extension)
                                     if not n.startswith("_")}
    out = []
    for name in sorted(names):
        obj = getattr(extension, name)
        if inspect.isroutine(obj) and not isinstance(obj, type):
            out.append(name)
    return out


@pytest.mark.parametrize("name", _public_callables())
def test_every_parameter_and_the_return_are_annotated(name):
    obj = getattr(extension, name)
    signature = inspect.signature(obj)
    unannotated = [p.name for p in signature.parameters.values()
                   if p.name != "self"
                   and p.annotation is inspect.Parameter.empty]
    assert unannotated == [], f"{name}: parameters without a type: {unannotated}"
    assert signature.return_annotation is not inspect.Signature.empty, \
        f"{name}: no return type"


def test_the_surface_names_more_than_a_few_callables():
    assert len(_public_callables()) >= 30
