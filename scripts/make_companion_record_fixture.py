# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Write the stored-record fixture under `tests/data/companion_record/`:
the records in its `verified/` folder.

Usage:
    python scripts/make_companion_record_fixture.py

Intent:
    Write, with the code of the day, a project whose verified records
    carry a `<name>[float]` computation row and an acceptance on it:
    `companionfix.scale_checked` accepts the row as evidence, and
    `companionfix.scale` accepts it as a risk. A risk is accepted only on
    an unknown row, so the generator sets the recorded verdict of
    `doubles[float]` in `scale` to `unknown` before the acceptance is
    planned and applied through `mathema.acceptance`, which stamps the
    claims fingerprint and the integrity checksum. The work is done in a
    temporary copy, and the records are copied to `verified/` (a test
    copies them back under `.mathema/verified/` of its own project).
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "tests" / "data" / "companion_record"


def main() -> int:
    sys.path.insert(0, str(HERE.parent))
    work = Path(tempfile.mkdtemp())
    shutil.copy(FIXTURE / "companionfix.py", work / "companionfix.py")
    sys.path.insert(0, str(work))
    os.chdir(work)
    import yaml

    import companionfix
    import mathema
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.spec import write_yaml

    root = str(work)
    for fn in (companionfix.scale, companionfix.scale_checked):
        mathema.write_spec(fn, root=root)

    risk_key = "companionfix.scale"
    path = work / ".mathema" / "verified" / f"{risk_key}.yaml"
    doc = yaml.safe_load(path.read_text())
    for row in doc[risk_key]["claims"]:
        if row["name"] == "doubles[float]":
            row["verdict"] = "unknown"
            row.pop("n", None)
            row["note"] = "the float64 computation was not settled"
    write_yaml(str(path), doc)
    apply_acceptance(plan_acceptance(root, risk_key, "doubles[float]",
                                     "risk", by="fixture"))
    apply_acceptance(plan_acceptance(root, "companionfix.scale_checked",
                                     "doubles[float]", "evidence",
                                     by="fixture"))
    target = FIXTURE / "verified"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(work / ".mathema" / "verified", target)
    shutil.rmtree(work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
