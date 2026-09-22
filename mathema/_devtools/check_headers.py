# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Pre-commit check: every tracked `.py` file in the repository must
start with the project's two-line SPDX header. Exits 1 and lists the
offending files if any are missing it; exits 0 silently otherwise.
"""
from __future__ import annotations

import subprocess
import sys

_HEADER = (
    "# SPDX-License-Identifier: BUSL-1.1",
    "# Copyright 2026 Tetrion Ltd",
)


def _tracked_python_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--", "*.py"],
        capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def check_headers(paths: list[str]) -> list[str]:
    """The subset of `paths` missing the two-line SPDX header at the
    very top of the file. Takes an explicit path list (rather than
    always discovering them itself) so a pre-commit hook can pass just
    the staged files."""
    missing = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            first = f.readline().rstrip("\n")
            # an executable script carries a shebang before anything
            # else; the SPDX convention explicitly allows the licence
            # header to follow it
            if first.startswith("#!"):
                first = f.readline().rstrip("\n")
            second = f.readline().rstrip("\n")
        if (first, second) != _HEADER:
            missing.append(path)
    return missing


def main(argv: list[str] | None = None) -> int:
    paths = argv if argv else _tracked_python_files()
    missing = check_headers(paths)
    if missing:
        print("Missing the required SPDX license header:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
