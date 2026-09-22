# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The extension contract, pinned.

`mathema.interfaces.extension` states what a registered capability
provider may import and what core calls back on one. Both halves are
plain data, and both are copied here as literals: changing the real
manifest fails these tests, so a change to the surface is always a
deliberate edit with a version decision attached, never a side effect
of refactoring something behind it.
"""
import ast
import os

import pytest

from mathema.interfaces import extension

# --- the outbound half: what a provider imports ----------------------

EXPECTED_SURFACE = {
    "source_text": ("analyze_source", "SourceUnavailable",
                    "strip_docstring", "local_names"),
    "loop_structure": ("classify_loop_header", "bare_seq_name",
                       "seq_one_colon", "diagnose_fold"),
    "claim_text": ("normalize", "split_quantifier", "split_relation",
                   "parse_raises"),
    "domain_shape": ("bound_to_sympy_set", "domain_bound_from_json"),
    "rendering": ("render_loop_header", "render_condition", "Rendered",
                  "unparse_normalized", "LOOP_KIND_LABEL"),
    "lift_structure": ("ConditionedLift", "lift_conditioned"),
    "runtime": ("PointRuntime", "POINT_RUNTIME_PROTOCOL",
                "RUNTIME_CAPABILITIES", "runtime_problems",
                "verdict_ceiling"),
    "facts_ir": ("Facts", "LoopFact"),
    "targets": ("Target", "TargetError"),
    "inventory": ("function_dependencies",),
    "store": ("load_declared", "load_verified", "save_verified_entry"),
    "index": ("build_index",),
    "evidence": ("evidence_rank", "SUPPORTED_VERDICTS"),
}

MODULE_LEVEL = {"EXTENSION_API_VERSION", "SURFACE", "CAPABILITY_PROTOCOLS",
                "capability_problems"}


def _flat(surface):
    return [name for names in surface.values() for name in names]


def test_surface_matches_the_pin():
    assert extension.SURFACE == EXPECTED_SURFACE


def test_every_surface_name_resolves():
    missing = [n for n in _flat(extension.SURFACE)
               if not hasattr(extension, n)]
    assert missing == []


def test_all_is_exactly_the_surface_plus_module_level():
    assert set(extension.__all__) == set(_flat(extension.SURFACE)) | MODULE_LEVEL


def test_no_surface_name_is_private():
    assert [n for n in _flat(extension.SURFACE) if n.startswith("_")] == []


def test_api_version_is_an_integer():
    assert isinstance(extension.EXTENSION_API_VERSION, int)


def test_surface_names_are_unique_across_seams():
    flat = _flat(extension.SURFACE)
    assert len(flat) == len(set(flat))


# --- the package stays import-light ----------------------------------

def test_interfaces_package_imports_no_submodule():
    """An interface subpackage's dependency is an optional extra, so
    importing the package must not pull one in."""
    import mathema.interfaces as pkg
    tree = ast.parse(open(pkg.__file__).read())
    relative = [n for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.level]
    plain = [n for n in ast.walk(tree) if isinstance(n, ast.Import)]
    assert relative == [] and plain == []


def test_importing_interfaces_does_not_load_mcp():
    import subprocess
    import sys
    out = subprocess.run(
        [sys.executable, "-c",
         "import mathema.interfaces, sys; "
         "print('mathema.interfaces.mcp' in sys.modules)"],
        capture_output=True, text=True, cwd=os.path.join(
            os.path.dirname(__file__), os.pardir))
    assert out.stdout.strip() == "False", out.stderr


# --- the inbound half: what core calls on a provider -----------------

#: Empty since the describe_diagram hook was retired. The mechanism
#: stays for the next capability core calls back into.
EXPECTED_PROTOCOLS: dict = {}


def test_capability_protocols_match_the_pin():
    assert extension.CAPABILITY_PROTOCOLS == EXPECTED_PROTOCOLS


def _provider_calls(path: str, variable: str):
    """Every `variable.member(...)` call in `path`, as
    (member, keyword names)."""
    tree = ast.parse(open(path).read())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == variable):
            found.append((func.attr, tuple(k.arg for k in node.keywords)))
    return found


def test_describe_calls_no_capability_provider():
    """R001 retired the describe_diagram hook: core renders every tier
    itself. A reintroduced provider lookup would silently make the
    output depend on whether a package happened to be installed."""
    audit = os.path.join(os.path.dirname(__file__), os.pardir,
                         "mathema", "audit.py")
    with open(audit) as fh:
        source = fh.read()
    assert "describe_diagram" not in source
    assert _provider_calls(audit, "diagram") == []


@pytest.fixture()
def synthetic(monkeypatch):
    """The registry is empty today, so the checker is exercised against a
    protocol registered for the test."""
    monkeypatch.setitem(extension.CAPABILITY_PROTOCOLS, "demo",
                        {"Legend": (), "render": ("width", "depth")})
    return "demo"


def test_capability_problems_reports_a_missing_member(synthetic):
    class Partial:
        def render(self, *a, **k): ...

    problems = extension.capability_problems(Partial(), synthetic)
    assert any("Legend" in p for p in problems)


def test_capability_problems_reports_a_refused_keyword(synthetic):
    class Narrow:
        Legend = object
        def render(self, *, width): ...

    problems = extension.capability_problems(Narrow(), synthetic)
    assert any("depth" in p for p in problems)


def test_capability_problems_empty_for_a_conforming_provider(synthetic):
    class Full:
        Legend = object
        def render(self, *, width=80, depth=3): ...

    assert extension.capability_problems(Full(), synthetic) == []


# --- the documented surface is the real one --------------------------

def test_extending_page_table_matches_the_surface():
    """docs/extending.md lists the seams in a table. A name added to the
    manifest and not to the page would leave a provider author reading a
    surface that is missing it."""
    import re
    page = os.path.join(os.path.dirname(__file__), os.pardir,
                        "docs", "extending.md")
    with open(page) as fh:
        text = fh.read()
    documented = {}
    for row in re.finditer(r"^\| `(\w+)` \| (.+?) \|$", text, re.M):
        seam, names = row.group(1), row.group(2)
        if seam not in extension.SURFACE:
            continue
        documented[seam] = tuple(re.findall(r"`([^`]+)`", names))
    assert documented == extension.SURFACE


def test_save_verified_entry_round_trips_with_a_fresh_checksum(tmp_path):
    from mathema.interfaces.extension import load_verified, save_verified_entry
    from mathema.spec import integrity_checksum

    entry = {"name": "gain", "identity": {"form": "abc123"},
             "claims": [{"name": "bounded", "statement": "f(x) <= 1",
                         "verdict": "holds", "route": "probe"}]}
    save_verified_entry("gain", entry, str(tmp_path))
    stored = load_verified(str(tmp_path))["gain"]["entry"]
    assert stored["identity"]["integrity"] == integrity_checksum(stored)
    assert stored["claims"][0]["name"] == "bounded"
