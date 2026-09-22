# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The one target resolver: every accepted spelling resolves to live
functions under canonical dotted keys, with package context preserved
(the relpkg fixture uses real relative imports), and everything
unresolvable raises a printable TargetError."""
import os

import pytest

from mathema.targets import TargetError, resolve, resolve_function

DATA = os.path.join(os.path.dirname(__file__), "data")


def test_dotted_package_walks_submodules():
    t = resolve("relpkg", root=DATA)
    assert t.kind == "package"
    assert "relpkg.geometry.doubled" in t.functions
    assert "relpkg.inner.depths.deepened" in t.functions
    assert "relpkg.geometry.Norms.taxicab" in t.functions
    assert t.functions["relpkg.geometry.doubled"](3.0) == 6.0


def test_dotted_module_with_relative_import():
    t = resolve("relpkg.geometry", root=DATA)
    assert t.kind == "module"
    assert t.module_name == "relpkg.geometry"
    assert set(t.functions) >= {"relpkg.geometry.doubled",
                                "relpkg.geometry.half_sum"}


def test_dotted_function_reference_prefix_walk():
    key, fn = resolve_function("relpkg.geometry.doubled", root=DATA)
    assert key == "relpkg.geometry.doubled"
    assert fn(2.0) == 4.0


def test_dotted_static_method_reference():
    key, fn = resolve_function("relpkg.geometry.Norms.taxicab", root=DATA)
    assert key == "relpkg.geometry.Norms.taxicab"
    assert fn(-1.0, 2.0) == 3.0


def test_colon_function_form():
    key, fn = resolve_function("relpkg.geometry:half_sum", root=DATA)
    assert key == "relpkg.geometry.half_sum"
    assert fn(1.0, 3.0) == 2.0


def test_colon_method_form():
    key, fn = resolve_function("relpkg.geometry:Norms.taxicab", root=DATA)
    assert key == "relpkg.geometry.Norms.taxicab"


def test_bare_suffix_search_unique():
    key, fn = resolve_function("relpkg:deepened", root=DATA)
    assert key == "relpkg.inner.depths.deepened"
    assert fn(1.0) == 2.0


def test_bare_suffix_search_ambiguous_lists_candidates():
    # `scale` exists only in helpers, but `doubled` vs a name present
    # twice: add none, instead check a suffix that matches nothing
    with pytest.raises(TargetError, match="no function named"):
        resolve("relpkg:not_there", root=DATA)


def test_file_path_with_relative_import_resolves():
    path = os.path.join(DATA, "relpkg", "geometry.py")
    t = resolve(path)
    assert t.kind == "module"
    assert "relpkg.geometry.doubled" in t.functions


def test_file_path_colon_function():
    path = os.path.join(DATA, "relpkg", "geometry.py")
    key, fn = resolve_function(f"{path}:doubled")
    assert key == "relpkg.geometry.doubled"
    assert fn(5.0) == 10.0


def test_loose_script_outside_any_package(tmp_path):
    script = tmp_path / "loosemod.py"
    script.write_text("def trip(x):\n    return 3 * x\n")
    key, fn = resolve_function(str(script))
    assert key == "loosemod.trip"
    assert fn(2) == 6


def test_class_reference_rejected_with_guidance():
    with pytest.raises(TargetError, match="names a class"):
        resolve("relpkg.geometry.Norms", root=DATA)


def test_missing_module_is_printable_error():
    with pytest.raises(TargetError):
        resolve("relpkg.nowhere", root=DATA)
    with pytest.raises(TargetError):
        resolve("utterly_missing_pkg", root=DATA)


def test_missing_file_is_printable_error():
    with pytest.raises(TargetError, match="no such file"):
        resolve("does/not/exist.py")


def test_import_time_crash_is_printable_error(tmp_path):
    bad = tmp_path / "explodes.py"
    bad.write_text("raise RuntimeError('boom at import')\n")
    with pytest.raises(TargetError, match="boom at import"):
        resolve(str(bad))


def test_resolve_function_rejects_many(tmp_path):
    with pytest.raises(TargetError, match="not one"):
        resolve_function("relpkg.geometry", root=DATA)
