# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Claim shapes outside the curated lexicon keep the same round-trip
guarantees the lexicon's own invariants state: the canonical text is a
fixed point, the declared layer rebuilds the same claim, a verified row
rebuilds a claim that reaches the same verdict, and a project store
settles after one sweep (every later sweep is fresh, no row is added,
every stored statement parses back under its own name)."""
import subprocess
import sys

import pytest
import yaml

from mathema.conjecture import check_conjectures, claim
from mathema.spec import canonical_claim_text, declare, entry_claims
from tests.test_cli_verify import _run

_SOURCE = '''\
def shifted(x: float) -> float:
    return 1 / (1 - x)


def running_total(xs, y0):
    total = y0
    for v in xs:
        if v > 0:
            total = total + v
    return total


def doubled(x: float) -> float:
    return 2 * x


def summed(x: float) -> float:
    return x + x
'''

# (function, claim text, name or None)
_SHAPES = [
    ("shifted", "abs(f(x) - 1) >= 0", None),
    ("shifted", "abs(abs(f(x)) - 1) >= 0", "nested_abs"),
    ("shifted", "|f(x)| >= 0", "bars_single_term"),
    ("shifted", "not is_defined(f)", "not_total"),
    ("shifted", "not is_pole_safe(x)", None),
    ("shifted", "1 - x != 0", "is_defined"),
    ("shifted", "for x in [2, 5], f(x) != 0", None),
    ("running_total", "abs(f(xs, y0) - y0) <= abs(y0) + 1e9", "stays_close"),
    ("running_total", "f(xs, y0) - y0 + 0 >= 0", None),
    ("doubled", "f(x) == summed(x)", "matches_sibling"),
    ("doubled", "let g = roundtrip_fns.summed, f(x) == g(x)", "matches_let"),
]


def _identity(cj):
    return (cj.name, cj.lhs, cj.relation, cj.rhs, cj.negated,
            cj.assuming, tuple(sorted((cj.domain or {}).items())))


@pytest.fixture(scope="module")
def functions(tmp_path_factory):
    d = tmp_path_factory.mktemp("shapes")
    (d / "roundtrip_fns.py").write_text(_SOURCE)
    sys.path.insert(0, str(d))
    try:
        import roundtrip_fns
        yield roundtrip_fns
    finally:
        sys.path.remove(str(d))


@pytest.mark.parametrize("fname,text,name", _SHAPES)
def test_the_canonical_text_is_a_fixed_point(fname, text, name):
    # canonicalization may respell the authored text; from the canonical
    # text on, the claim is a fixed point
    cj = claim(text, name=name)
    once = canonical_claim_text(cj)
    again = claim(once, name=cj.name)
    assert canonical_claim_text(again) == once
    assert (again.name, again.relation, again.negated) == \
        (cj.name, cj.relation, cj.negated)


@pytest.mark.parametrize("fname,text,name", _SHAPES)
def test_the_declared_layer_rebuilds_the_same_claim(fname, text, name):
    cj = claim(text, name=name)
    (back,) = entry_claims({"claims": [declare(cj)]})
    assert _identity(back) == _identity(cj)


@pytest.mark.parametrize("fname,text,name", _SHAPES)
def test_a_verified_row_rebuilds_a_claim_with_the_same_verdict(
        functions, fname, text, name):
    fn = getattr(functions, fname)
    (p,) = check_conjectures(fn, [claim(text, name=name)])
    row = {"name": p.name, "statement": p.statement,
           "route": (p.route or "best").split(":", 1)[0]}
    if row["route"] not in ("derive", "probe"):
        row["route"] = "best"
    if p.domain is not None:
        row["domain"] = p.domain
    (rebuilt,) = entry_claims({"claims": [row]})
    (p2,) = check_conjectures(fn, [rebuilt])
    assert p2.verdict == p.verdict, (p.statement, p.verdict, p2.verdict)


def test_a_project_store_settles_after_one_sweep(tmp_path):
    (tmp_path / "roundtrip_fns.py").write_text(_SOURCE)
    rows = {}
    for fname, text, name in _SHAPES:
        entry = {"statement": text}
        if name:
            entry = {"name": name, **entry}
        rows.setdefault(f"roundtrip_fns.{fname}", []).append(entry)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "shapes.claims.yaml").write_text(
        yaml.safe_dump({k: {"claims": v} for k, v in rows.items()},
                       sort_keys=False))
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    def stored():
        out = {}
        for path in (tmp_path / ".mathema" / "verified").glob("*.yaml"):
            (key, entry), = yaml.safe_load(path.read_text()).items()
            out[key] = entry.get("claims") or []
        return out

    first = _run(tmp_path)
    assert "Traceback" not in first.stdout + first.stderr, first.stderr
    after_first = stored()
    for sweep in (2, 3):
        r = _run(tmp_path)
        assert "Traceback" not in r.stdout + r.stderr, r.stderr
        for line in r.stdout.splitlines():
            if line[:5].strip() in ("ok", "FAIL") and "roundtrip_fns." in line:
                assert ": fresh" in line, (sweep, line)
        assert stored() == after_first, f"sweep {sweep} rewrote a record"
    for key, claims in after_first.items():
        for row in claims:
            if not row.get("statement"):
                continue
            claim(row["statement"], name=row.get("name"))
