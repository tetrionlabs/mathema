# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema.check(fn)` runs the built-in families, but the printed record
puts the function's own stated claims first and folds the rows mathema
volunteered under one count line; `render(families=True)` prints them
all. Which families run, and every verdict, are unchanged."""
import mathema


def percent_change_checked(old: float, new: float) -> float:
    """The change from old to new, as a percentage of old.

    Claims:
        rise_is_positive: for old in [0.01, 1e6], new in [0, 1e6], assuming new > old, f(old, new) > 0
        no_change_is_zero: for old in [0.01, 1e6], f(old, old) == 0
    """
    if old < 0.01:
        raise ValueError("old must be at least 0.01")
    return (new - old) / old * 100


def plain(x: float) -> float:
    return 2 * x


def test_the_stated_claims_come_first_and_the_families_fold_to_a_count():
    rec = mathema.check(percent_change_checked)
    names = {p.name for p in rec.probes}
    # the families still run
    assert {"commutative", "associative", "is_deterministic"} <= names
    text = str(rec)
    lines = text.splitlines()
    assert lines[1].lstrip().startswith("rise_is_positive "), text
    assert "commutative" not in text and "associative" not in text, text
    assert "no_change_is_zero" in text, text
    count = lines[-1]
    volunteered = [p for p in rec.probes
                   if (p.meta or {}).get("mathema.surface") == "mathema"
                   and not (p.meta or {}).get("mathema.policy")]
    assert count.lstrip().startswith(f"{len(volunteered)} built-in checks: "), count
    assert "falsified" in count and "render(families=True)" in count, count


def test_render_with_families_prints_every_row():
    rec = mathema.check(percent_change_checked)
    full = rec.render(families=True)
    assert "commutative" in full and "associative" in full, full
    assert "built-in checks:" not in full
    assert repr(rec) == rec.render()


def test_a_record_with_no_stated_claim_prints_every_row():
    rec = mathema.check(plain)
    assert str(rec) == rec.render(families=True)
