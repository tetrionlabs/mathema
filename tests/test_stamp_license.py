# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The licence stamper, which runs once per release and must be right.

BUSL 1.1 carries two per-release parameters: the Licensed Work's
version, and the Change Date on which that version converts to the
Change Licence. `scripts/stamp_license.py` writes both. A wrong date
here is a legal statement about when the code becomes AGPL, so the
stamper is tested against a fixture copy rather than trusted.

The script lives in `scripts/`, which is not a package and is not
shipped, so it is loaded by path.
"""
import datetime as dt
import importlib.util
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "stamp_license.py"


def _load():
    spec = importlib.util.spec_from_file_location("stamp_license", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


stamp_license = _load()

UNSTAMPED = """Business Source License 1.1

Parameters

Licensed Work:        mathema
                      The Licensed Work is (c) 2026 Tetrion Ltd.

Change Date:          Four years from the release date of each
                      version of the Licensed Work. (Prose describing
                      the rule, replaced at release.)

Change License:       GNU Affero General Public License v3.0 or
                      later (AGPL-3.0-or-later)
"""


def test_the_version_lands_on_the_licensed_work_parameter():
    out = stamp_license.stamp(UNSTAMPED, "0.6.0", dt.date(2026, 10, 1))
    assert "Licensed Work:        mathema 0.6.0\n" in out


def test_the_change_date_becomes_concrete_four_years_on():
    out = stamp_license.stamp(UNSTAMPED, "0.6.0", dt.date(2026, 10, 1))
    assert "Change Date:          2030-10-01\n" in out
    # the prose rule is gone, replaced by the date it resolved to
    assert "Four years from the release date" not in out
    # and the Change Licence is untouched
    assert "AGPL-3.0-or-later" in out


def test_stamping_is_idempotent():
    """Re-running the stamper on an already-stamped licence must be a
    no-op rather than appending a second version or nesting a date, so
    that a repeated local run before tagging is harmless."""
    once = stamp_license.stamp(UNSTAMPED, "0.6.0", dt.date(2026, 10, 1))
    twice = stamp_license.stamp(once, "0.6.0", dt.date(2026, 10, 1))
    assert once == twice


def test_a_leap_day_release_keeps_its_day_but_a_non_leap_century_does_not():
    """Four years on from 29 February is normally 29 February again,
    because leap years repeat every four. The exception is a century
    that is not a leap year."""
    assert stamp_license.change_date(dt.date(2028, 2, 29)) == dt.date(2032, 2, 29)
    # 2100 is not a leap year, so 2096-02-29 falls back to the 28th
    assert stamp_license.change_date(dt.date(2096, 2, 29)) == dt.date(2100, 2, 28)
    # and an ordinary date is simply four years on
    assert stamp_license.change_date(dt.date(2026, 10, 1)) == dt.date(2030, 10, 1)


def test_a_licence_missing_its_parameters_fails_loudly():
    """A silent no-op here would ship an unstamped licence."""
    with pytest.raises(SystemExit, match="Licensed Work"):
        stamp_license.stamp("no parameters here\n", "0.6.0", dt.date(2026, 10, 1))
    missing_date = UNSTAMPED.replace("Change Date:", "Effective Date:")
    with pytest.raises(SystemExit, match="Change Date"):
        stamp_license.stamp(missing_date, "0.6.0", dt.date(2026, 10, 1))


def test_check_accepts_a_stamped_licence_and_rejects_an_unstamped_one():
    # stamped as of today: check() rejects a Change Date further out
    # than four years from now, which is how a future-dated release
    # gets caught, so the fixture uses a real release date
    stamped = stamp_license.stamp(UNSTAMPED, "0.6.0", dt.date.today())
    stamp_license.check(stamped, "0.6.0")           # does not raise

    with pytest.raises(SystemExit, match="not stamped"):
        stamp_license.check(UNSTAMPED, "0.6.0")
    with pytest.raises(SystemExit, match="not stamped"):
        stamp_license.check(stamped, "0.7.0")       # wrong version


def test_check_rejects_a_change_date_further_out_than_the_licence_allows():
    """The Change Date is a promise that the code converts within four
    years. A date beyond that is a licence error, not a typo."""
    far = stamp_license.stamp(UNSTAMPED, "0.6.0", dt.date.today())
    far = far.replace(
        stamp_license.change_date(dt.date.today()).isoformat(),
        (dt.date.today().replace(year=dt.date.today().year + 6)).isoformat())
    with pytest.raises(SystemExit, match="more than 4 years"):
        stamp_license.check(far, "0.6.0")


def test_the_real_licence_file_carries_both_parameters_to_stamp():
    """A guard on the shipped LICENSE.md: if its parameter block is
    ever reworded so the stamper's patterns stop matching, that must
    fail here and not during a release."""
    text = (_ROOT / "LICENSE.md").read_text()
    out = stamp_license.stamp(text, "9.9.9", dt.date(2026, 10, 1))
    assert "Licensed Work:        mathema 9.9.9\n" in out
    assert "Change Date:          2030-10-01\n" in out


def test_check_rejects_a_future_dated_release():
    """Stamping for a release date in the future post-dates the
    licence conversion, so `check` refuses it. This is why the release
    workflow verifies the committed stamp rather than writing its own:
    a stamp written on a different day is a different promise."""
    later = dt.date.today() + dt.timedelta(days=30)
    future = stamp_license.stamp(UNSTAMPED, "0.6.0", later)
    with pytest.raises(SystemExit, match="more than 4 years"):
        stamp_license.check(future, "0.6.0")
