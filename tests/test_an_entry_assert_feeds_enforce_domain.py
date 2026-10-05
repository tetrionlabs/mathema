# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An assert at the top of a function's body that bounds a parameter
feeds `@enforce_domain`: the decorator rejects the call with
DomainError before the body runs, so the bound is a real guard that
cuts the working domain, whether or not Python strips asserts. A bare
assert without the decorator stays no guard."""
import textwrap

import pytest

from mathema import DomainError
from mathema.conjecture import check_conjectures, claim


def _module(tmp_path, name, body):
    import importlib.util
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_entry_assert_becomes_the_enforced_domain(tmp_path):
    mod = _module(tmp_path, "entry_assert", '''
        import math
        from mathema import enforce_domain

        @enforce_domain()
        def root(x: float) -> float:
            assert 0 <= x <= 4
            return math.sqrt(x)
    ''')
    assert mod.root(1.0) == 1.0
    with pytest.raises(DomainError, match="outside its declared domain"):
        mod.root(-1.0)
    (p,) = check_conjectures(mod.root,
                             [claim("for x in [-4, 4], is_defined(f)")])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.sketch, p.note)
