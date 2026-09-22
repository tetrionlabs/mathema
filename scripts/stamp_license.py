#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Stamp the release version and concrete Change Date into LICENSE.md.

BUSL 1.1 requires each released version to carry its own Change Date
(release date + 4 years). The repository copy of LICENSE.md carries the
projected formula wording; this script rewrites two parameters at
release time so the tagged artefact carries concrete values:

  Licensed Work:  "mathema"            -> "mathema <version>"
  Change Date:    formula paragraph    -> "<release date + 4 years>"

Intent: run by the release workflow before building, and again with
--check after building, so an unstamped LICENSE fails the release
rather than shipping. The BUSL body's anniversary clause means a missed
stamp shortens protection rather than extending it; this script exists
so the question never arises.

Usage:
  python scripts/stamp_license.py --version 0.6.0 [--date 2026-09-16]
  python scripts/stamp_license.py --version 0.6.0 --check
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re

LICENSE = pathlib.Path(__file__).resolve().parents[1] / "LICENSE.md"


def change_date(release: dt.date) -> dt.date:
    """Release date plus four years.

    Four years on from 29 February is normally 29 February again, since
    leap years repeat every four. The exception is a century that is not
    a leap year (2096 to 2100), where the day falls back to 28 February.
    """
    try:
        return release.replace(year=release.year + 4)
    except ValueError:
        return release.replace(year=release.year + 4, day=28)


def stamp(text: str, version: str, release: dt.date) -> str:
    """Return LICENSE text with both parameters stamped for this release."""
    stamped_date = change_date(release).isoformat()

    # Licensed Work: append the version, preserving column alignment.
    text, n = re.subn(
        r"(Licensed Work:\s+mathema)(?: [0-9][^\n]*)?\n",
        rf"\g<1> {version}\n",
        text,
        count=1,
    )
    if n != 1:
        raise SystemExit("stamp: could not find the Licensed Work parameter")

    # Change Date: replace everything between the label and the next
    # parameter (Change License) with the concrete date.
    replacement = (
        f"Change Date:          {stamped_date}\n"
        f"                      (four years from the {release.isoformat()}\n"
        f"                      release of version {version})\n\n"
    )
    text, n = re.subn(
        r"Change Date:.*?\n\n(?=Change License:)",
        replacement,
        text,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        raise SystemExit("stamp: could not find the Change Date parameter")
    return text


def check(text: str, version: str) -> None:
    """Fail unless LICENSE carries this version and a concrete date."""
    if not re.search(rf"Licensed Work:\s+mathema {re.escape(version)}\n", text):
        raise SystemExit(f"check: Licensed Work is not stamped with {version}")
    m = re.search(r"Change Date:\s+(\d{4}-\d{2}-\d{2})", text)
    if not m:
        raise SystemExit("check: Change Date is not a concrete date")
    stamped = dt.date.fromisoformat(m.group(1))
    if stamped > change_date(dt.date.today()):
        raise SystemExit(f"check: Change Date {stamped} is more than 4 years out")
    print(f"check: LICENSE stamped for mathema {version}, converts {stamped}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", required=True, help="release version, e.g. 0.6.0")
    p.add_argument("--date", help="release date YYYY-MM-DD (default: today)")
    p.add_argument("--check", action="store_true", help="verify instead of write")
    args = p.parse_args()

    text = LICENSE.read_text(encoding="utf-8")
    if args.check:
        check(text, args.version)
        return
    release = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    LICENSE.write_text(stamp(text, args.version, release), encoding="utf-8")
    print(f"stamped: mathema {args.version}, Change Date {change_date(release)}")


if __name__ == "__main__":
    main()
