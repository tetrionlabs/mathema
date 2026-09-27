# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A numpy ufunc reads with the signature numpy documents for it on
every numpy: `(x1, x2, /, out=None, *, where=True, ...)` for a binary
ufunc, `(x, /, ...)` for a unary one. numpy releases before 2.3 give
ufuncs no `inspect.signature`, so the signature is built from the
ufunc's `nin`/`nout`; the tests here force that path on any numpy by
making `inspect.signature` refuse a ufunc, as those releases do."""
import inspect
import warnings

import pytest

np = pytest.importorskip("numpy")

_BINARY = ("(x1, x2, /, out=None, *, where=True, casting='same_kind', "
           "order='K', dtype=None, subok=True, signature=None)")
_UNARY = ("(x, /, out=None, *, where=True, casting='same_kind', "
          "order='K', dtype=None, subok=True, signature=None)")
_UNARY_TWO_OUT = ("(x, /, out=(None, None), *, where=True, "
                  "casting='same_kind', order='K', dtype=None, subok=True, "
                  "signature=None)")
_GUFUNC = ("(x1, x2, /, out=None, *, axes=<no value>, axis=<no value>, "
           "keepdims=False, casting='same_kind', order='K', dtype=None, "
           "subok=True, signature=None)")


@pytest.fixture
def ufuncs_unsigned(monkeypatch):
    """`inspect.signature` refuses every ufunc, as on numpy 2.2."""
    real = inspect.signature

    def refusing(obj, *args, **kwargs):
        if isinstance(obj, np.ufunc):
            raise ValueError(f"callable {obj!r} is not supported by signature")
        return real(obj, *args, **kwargs)
    monkeypatch.setattr(inspect, "signature", refusing)


@pytest.mark.parametrize("fn, text", [
    (np.divide, _BINARY), (np.true_divide, _BINARY),
    (np.reciprocal, _UNARY), (np.sqrt, _UNARY),
    (np.modf, _UNARY_TWO_OUT), (np.matmul, _GUFUNC)])
def test_a_ufunc_reads_with_its_documented_signature(ufuncs_unsigned, fn, text):
    from mathema._signatures import callable_signature
    sig = callable_signature(fn)
    assert str(sig) == text
    kinds = [p.kind for p in sig.parameters.values()]
    assert kinds[0] is inspect.Parameter.POSITIONAL_ONLY


@pytest.mark.parametrize("fn", [np.divide, np.reciprocal, np.modf, np.matmul])
def test_the_built_signature_matches_the_one_numpy_reports(fn):
    from mathema._signatures import callable_signature, ufunc_signature
    try:
        reported = inspect.signature(fn)
    except ValueError:
        pytest.skip("this numpy reports no ufunc signature")
    assert str(ufunc_signature(fn)) == str(reported)
    assert str(callable_signature(fn)) == str(reported)


def test_a_callable_without_a_signature_still_raises():
    import math

    from mathema._signatures import callable_signature
    with pytest.raises(ValueError):
        callable_signature(math.log)


def test_the_division_rows_place_their_parameters(ufuncs_unsigned):
    from mathema.compendium import _signature_params
    assert _signature_params("numpy.divide", ["x1", "x2"])[:2] == ["x1", "x2"]
    assert _signature_params("numpy.reciprocal", ["x"])[:1] == ["x"]


def test_every_bundled_row_registers_without_a_report(ufuncs_unsigned):
    from mathema import compendium
    compendium.uninstall()
    compendium._REPORTED.clear()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            compendium.register_library_claims(None)
    finally:
        compendium.uninstall()


def test_divide_is_checked_over_x1_and_x2(ufuncs_unsigned):
    import mathema
    from mathema.compendium import ensure_bundled
    from mathema.conjecture import claim
    ensure_bundled()
    rec = mathema.check(np.divide, claims=[claim("x2 != 0", name="is_defined")])
    (row,) = [p for p in rec.probes if p.name == "is_defined"]
    assert row.verdict == "holds", row.note


def test_a_ufunc_states_the_defaults_it_kept(ufuncs_unsigned):
    import mathema
    rec = mathema.check(np.mean, claims=[
        "let g = numpy.sqrt, for a in R^n, g(f(a) * f(a)) >= 0"])
    (p,) = [p for p in rec.probes
            if p.meta.get("mathema.surface") == "declared"]
    assert p.verdict == "holds", p.note
    assert p.meta["mathema.defaults"]["numpy.sqrt"]["out"] == "None"
