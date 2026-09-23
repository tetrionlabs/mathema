# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Pre-commit check: every tracked SOURCE file in the repository must
start with the project's two-line SPDX header, in whichever comment
syntax that language uses. Exits 1 and lists the offending files if any
are missing it; exits 0 silently otherwise.

Source is what the BUSL covers. Documentation prose and the docs
stylesheets are CC BY 4.0 (see LICENSING.md), so `.md` and `.css` are
deliberately outside this check, as are configuration files, which
carry no licence header by convention. An extension this module does
not know is skipped rather than guessed at: adding a language means
adding it to `_COMMENT_PREFIX`, which is also what puts it in the
tracked-file sweep.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

_HASH, _SLASH = "#", "//"

# Extension to the line-comment syntax its licence header is written
# in. The slash-comment block covers the runtimes the multi-language
# adaptors target, so an adaptor's source is gated the day it lands.
_COMMENT_PREFIX = {
    ".py": _HASH, ".sh": _HASH, ".bash": _HASH,
    ".c": _SLASH, ".h": _SLASH, ".cpp": _SLASH, ".hpp": _SLASH,
    ".cc": _SLASH, ".hh": _SLASH,
    ".js": _SLASH, ".mjs": _SLASH, ".cjs": _SLASH,
    ".ts": _SLASH, ".tsx": _SLASH, ".jsx": _SLASH,
    ".rs": _SLASH, ".go": _SLASH, ".java": _SLASH, ".kt": _SLASH,
    ".scala": _SLASH, ".swift": _SLASH,
}


def _header_for(path: str) -> tuple[str, str] | None:
    """Intent:
        The two header lines this file must start with, written in its
        own comment syntax, or None when the extension is not source
        this check governs.
    """
    prefix = _COMMENT_PREFIX.get(pathlib.Path(path).suffix)
    if prefix is None:
        return None
    return (f"{prefix} SPDX-License-Identifier: BUSL-1.1",
            f"{prefix} Copyright 2026 Tetrion Ltd")


def _tracked_source_files() -> list[str]:
    patterns = [f"*{ext}" for ext in _COMMENT_PREFIX]
    result = subprocess.run(
        ["git", "ls-files", "--", *patterns],
        capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def check_headers(paths: list[str]) -> list[str]:
    """The subset of `paths` missing the two-line SPDX header at the
    very top of the file, each checked in its own comment syntax. Takes
    an explicit path list (rather than always discovering them itself)
    so a pre-commit hook can pass just the staged files. A path whose
    extension this check does not govern, documentation or a stylesheet
    or a config file, is passed over rather than reported."""
    missing = []
    for path in paths:
        header = _header_for(path)
        if header is None:
            continue
        with open(path, encoding="utf-8") as f:
            first = f.readline().rstrip("\n")
            # an executable script carries a shebang before anything
            # else; the SPDX convention explicitly allows the licence
            # header to follow it
            if first.startswith("#!"):
                first = f.readline().rstrip("\n")
            second = f.readline().rstrip("\n")
        if (first, second) != header:
            missing.append(path)
    return missing


def main(argv: list[str] | None = None) -> int:
    paths = argv if argv else _tracked_source_files()
    missing = check_headers(paths)
    if missing:
        print("Missing the required SPDX license header:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
