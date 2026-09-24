# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Re-running verify on an unchanged project leaves the record unchanged.

An unnamed declared claim is stored under its canonical spelling, which
can differ from the text the author wrote (`f(xs, y0) - y0 + 0 >= 0`
is stored as `-y0 + f(xs, y0) >= 0`). The next verify has to recognise
that stored row as the same declared claim, not as a separate claim to
keep adjudicating beside it.
"""
import pytest
import yaml

_BODY = '''\
def running_total(xs, y0):
    total = y0
    for v in xs:
        if v > 0:
            total = total + v
    return total
'''


@pytest.mark.parametrize("statement", [
    "f(xs, y0) - y0 + 0 >= 0",
    "abs(f(xs, y0) - y0) <= sum(abs(v) for v in xs)",
])
def test_an_unnamed_claim_keeps_one_row_across_runs(tmp_path, monkeypatch, statement):
    import importlib
    import sys

    from mathema.verify import verify_project
    sys.modules.pop("stablerec", None)
    importlib.invalidate_caches()
    (tmp_path / "stablerec.py").write_text(_BODY)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(
        yaml.safe_dump({"stablerec.running_total": {"claims": [{"statement": statement}]}}))
    monkeypatch.syspath_prepend(str(tmp_path))

    record = tmp_path / ".mathema" / "verified" / "stablerec.running_total.yaml"
    for _ in range(3):
        verify_project(root=str(tmp_path))
        rows = yaml.safe_load(record.read_text())["stablerec.running_total"]["claims"]
        declared = [r for r in rows if r.get("name") != "dependencies_current"]
        assert len(declared) == 1, [r.get("name") for r in declared]
