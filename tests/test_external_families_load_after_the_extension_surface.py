# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim family registered by another package is read whatever the
import order, and a failed load is never the last word.

A family's module imports `mathema.interfaces.extension`, the surface
a registered package is told to import. Parsing a claim must therefore
never load the families (the predicate a family owns is its entry
point's name, read without loading), importing the extension surface
must parse no claim of its own, and a load that fails is warned about
once and tried again on the next call rather than cached as absent for
the rest of the process.
"""
import os
import subprocess
import sys
import textwrap
import warnings

import pytest

from mathema import families
from mathema.conjecture import claim

_STUB = '''
    from mathema.interfaces.extension import ProofResult, SafetyFamily


    def _derive(fn, facts, lhs_src, rhs_src, relation, domain=None,
                tolerance=None):
        return ProofResult("proven", sketch="the stub family proves it")


    family = SafetyFamily("is_stub_safe", derive=_derive)
'''

_ENTRY_POINTS = """\
[mathema.claim_families]
is_stub_safe = stub_family:family
"""


def _write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


@pytest.fixture
def site(tmp_path):
    """A directory holding the stub family and the distribution metadata
    that registers it under `mathema.claim_families`."""
    root = tmp_path / "site"
    _write(root / "stub_family.py", _STUB)
    _write(root / "stub_family-1.0.dist-info" / "METADATA",
           "Metadata-Version: 2.1\nName: stub_family\nVersion: 1.0\n")
    _write(root / "stub_family-1.0.dist-info" / "entry_points.txt",
           _ENTRY_POINTS)
    _write(root / "gain_mod.py", """
        def gain(x: float) -> float:
            return 2 * x
    """)
    return root


def _run(site, script: str):
    env = dict(os.environ, PYTHONPATH=str(site))
    env.pop("VIRTUAL_ENV", None)
    return subprocess.run([sys.executable, "-c", textwrap.dedent(script)],
                          cwd=str(site), capture_output=True, text=True,
                          env=env)


def test_a_family_importing_the_extension_surface_is_read_after_it(site):
    """The extension surface is imported first, as a package does; the
    stub family, discovered afterwards, parses, loads and adjudicates."""
    out = _run(site, """
        import warnings
        warnings.simplefilter("error")
        import mathema.interfaces.extension
        from mathema import families
        from mathema.conjecture import check_conjectures, claim
        from gain_mod import gain

        cj = claim("is_stub_safe(x)")
        assert cj.relation == "is_stub_safe", cj
        assert "is_stub_safe" in families.families()
        (p,) = check_conjectures(gain, [cj])
        print(p.verdict, p.route)
    """)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["proven", "examine"], out.stdout


def test_importing_the_extension_surface_parses_no_claim(site):
    """`import mathema.interfaces.extension` in a fresh interpreter never
    reaches the claim parser (`conjecture.claim`)."""
    out = _run(site, """
        import sys
        import mathema.conjecture as conjecture
        parser = conjecture.claim.__code__
        parsed = []

        def profile(frame, event, arg):
            if event == "call" and frame.f_code is parser:
                parsed.append(frame.f_back.f_code.co_name)
        sys.setprofile(profile)
        import mathema.interfaces.extension
        sys.setprofile(None)
        print(len(parsed), sorted(set(parsed)))
    """)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split()[0] == "0", out.stdout


class _FlakyEntryPoint:
    """An entry point whose first load fails and whose later loads give
    a family."""
    name = "is_flaky_safe"
    value = "flaky:family"

    def __init__(self):
        self.loads = 0

    def load(self):
        self.loads += 1
        if self.loads == 1:
            raise ImportError("partially initialised module")
        from mathema.claim_families import SafetyFamily
        from mathema.symbolic import ProofResult
        return SafetyFamily("is_flaky_safe", derive=lambda *a, **k: ProofResult(
            "proven", sketch="flaky"))


@pytest.fixture
def flaky(monkeypatch):
    ep = _FlakyEntryPoint()
    monkeypatch.setattr(families, "entry_points", lambda **_: [ep])
    families._reset_discovery()
    try:
        yield ep
    finally:
        families._reset_discovery()


def test_a_predicate_is_known_from_its_entry_point_without_loading(flaky):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        cj = claim("is_flaky_safe(x)")
    assert cj.relation == "is_flaky_safe"
    assert "is_flaky_safe" in families.registered_predicates()
    assert flaky.loads == 0


def test_a_failed_load_warns_once_and_is_tried_again(flaky):
    with pytest.warns(UserWarning, match="is_flaky_safe"):
        first = families.families()
    assert "is_flaky_safe" not in first
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        second = families.families()
    assert "is_flaky_safe" in second
    assert flaky.loads == 2
