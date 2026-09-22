# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The intent rung ladder: any stated intent (an explicit Intent:
block included) sits at `declared`; `documented` is a HUMAN act
(mathema accept --intent), binding to the signature, the raised-
exception surface, and the intent text; a body-only refactor keeps
the acceptance, any of those three changing re-opens it. Concept
acceptance rides the same verb: accepted tags earn the documented
rung and survive rewrites; dismissed suggestions never re-offer."""
import os
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_BODY = '''
def price(x: float) -> float:
    """Prices the thing.

    Intent:
        Twice x, always.
    """
    if x < 0:
        raise ValueError("negative")
    return 2.0 * x
'''


def _project(tmp_path, body=_BODY):
    import shutil
    pkg = tmp_path / "ipkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(body))
    shutil.rmtree(pkg / "__pycache__", ignore_errors=True)
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "ipkg.mod.price:\n"
        "  claims:\n"
        "    - name: doubles\n"
        "      statement: 'for x in [0,5], f(x) == 2*x'\n"
        "      route: derive\n")
    return dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))


def _run(tmp_path, env, *argv):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main({list(argv)!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _record(tmp_path):
    import yaml
    path = tmp_path / ".mathema" / "verified" / "ipkg.mod.price.yaml"
    return yaml.safe_load(path.read_text())["ipkg.mod.price"]


def test_stated_intent_is_declared_until_accepted(tmp_path):
    env = _project(tmp_path)
    r = _run(tmp_path, env, "verify", "--root", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    entry = _record(tmp_path)
    assert entry["intent"] == "Prices the thing."
    # an explicit Intent: block no longer auto-earns "documented"
    assert (entry.get("meta") or {}).get(
        "mathema.intent_provenance") == "declared"
    assert entry.get("raises") == ["ValueError"]


def test_acceptance_survives_body_refactor_not_interface_change(tmp_path):
    env = _project(tmp_path)
    _run(tmp_path, env, "verify", "--root", str(tmp_path))
    r = _run(tmp_path, env, "accept", "ipkg.mod.price", "--intent",
             "--by", "babbage", "--yes", "--root", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    entry = _record(tmp_path)
    assert entry["intent_accepted"]["by"] == "babbage"
    assert (entry.get("meta") or {}).get(
        "mathema.intent_provenance") == "documented"

    # body-only refactor: same signature, same raises; acceptance holds
    _project(tmp_path, '''
def price(x: float) -> float:
    """Prices the thing.

    Intent:
        Twice x, always.
    """
    if x < 0:
        raise ValueError("negative")
    doubled = x + x
    return doubled
''')
    r = _run(tmp_path, env, "verify", "--root", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    entry = _record(tmp_path)
    assert not entry["intent_accepted"].get("stale")
    assert (entry.get("meta") or {}).get(
        "mathema.intent_provenance") == "documented"

    # signature change: the acceptance re-opens
    _project(tmp_path, '''
def price(amount: float) -> float:
    """Prices the thing.

    Intent:
        Twice amount, always.
    """
    if amount < 0:
        raise ValueError("negative")
    return 2.0 * amount
''')
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "ipkg.mod.price:\n  claims: []\n")
    r = _run(tmp_path, env, "verify", "--root", str(tmp_path))
    entry = _record(tmp_path)
    assert entry["intent_accepted"].get("stale") is True
    assert (entry.get("meta") or {}).get(
        "mathema.intent_provenance") == "declared"


def test_concept_acceptance_and_dismissal(tmp_path):
    env = _project(tmp_path, '''
def price(x: float) -> float:
    """Prices via the #closed-form rule.

    Intent:
        Twice x, always.
    """
    return 2.0 * x
''')
    r = _run(tmp_path, env, "verify", "--root", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    entry = _record(tmp_path)
    # the inline #tag spelling authored a declared concept
    assert "closed-form" in (entry.get("meta") or {}).get("concepts", [])
    r = _run(tmp_path, env, "accept", "ipkg.mod.price",
             "--concepts", "closed-form",
             "--dismiss-concepts", "scaling",
             "--by", "babbage", "--yes", "--root", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    entry = _record(tmp_path)
    assert entry["concepts_accepted"] == ["closed-form"]
    # the dismissal lives in the store's curation corner
    curated = (tmp_path / ".mathema" / "meta" / "concepts.yaml").read_text()
    assert "scaling" in curated and "concepts_dismissed" in curated
    # a re-verify keeps the acceptance and stamps the documented rung
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "ipkg.mod.price:\n"
        "  claims:\n"
        "    - name: nonneg\n"
        "      statement: 'for x in [0,5], f(x) >= 0'\n"
        "      route: derive\n")
    r = _run(tmp_path, env, "verify", "--root", str(tmp_path))
    entry = _record(tmp_path)
    assert entry.get("concepts_accepted") == ["closed-form"]
    sources = (entry.get("meta") or {}).get("mathema.concept_sources") or {}
    assert "closed-form" in sources.get("documented", [])
