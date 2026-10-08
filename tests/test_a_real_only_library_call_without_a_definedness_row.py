# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The mathematics line is exact over the reals: a library call lifted to
a function with no real value somewhere (a square root, a logarithm, an
arcsine) has no value there whether or not any compendium row states its
definedness, and never satisfies a claim through a complex value. A
project compendium entry that restates numpy.sqrt without its
definedness row therefore leaves `f(x) * f(x) == x` over [-4, 4]
falsified (ruling of 2026-10-01: the mathematics is exact over the
numbers as written)."""
import textwrap

import pytest

np = pytest.importorskip("numpy")


@pytest.fixture
def sqrt_without_definedness(tmp_path):
    from mathema import compendium
    path = tmp_path / "claims" / "npx.claims.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(textwrap.dedent("""
        compendium: numpy
        versions: ">=2.0"
        numpy.sqrt:
          claims:
            - name: grows
              statement: "for x in [0, 4], y in [0, 4], assuming x <= y, f(x) <= f(y)"
        numpy.log:
          claims:
            - name: grows
              statement: "for x in [1, 4], y in [1, 4], assuming x <= y, f(x) <= f(y)"
        numpy.arcsin:
          claims:
            - name: grows
              statement: "for x in [0, 1], y in [0, 1], assuming x <= y, f(x) <= f(y)"
    """))
    compendium.uninstall()
    compendium.register_library_claims(str(tmp_path))
    yield
    compendium.uninstall()


def root(x: float) -> float:
    return float(np.sqrt(x))


def logarithm(x: float) -> float:
    return float(np.log(x))


def arcsine(x: float) -> float:
    return float(np.arcsin(x))


def _verdict(fn, law):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


@pytest.mark.parametrize("fn, law", [
    (root, "for x in [-4, 4], f(x) * f(x) == x"),
    (root, "for x in [-4, 4], f(x) == f(x)"),
    (logarithm, "for x in [-4, 4], f(x) == f(x)"),
    (arcsine, "for x in [-4, 4], f(x) == f(x)"),
])
def test_no_real_value_is_never_proven(sqrt_without_definedness, fn, law):
    p = _verdict(fn, law)
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_inside_the_real_domain_it_still_proves(sqrt_without_definedness):
    assert _verdict(root, "for x in [0, 4], f(x) * f(x) == x").verdict == "proven"
