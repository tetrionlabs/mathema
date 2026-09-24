# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""House-style gate for every text surface that ships.

Checks two things the project has decided about its own prose, both of
which are easy to reintroduce by hand and tedious to catch by eye:

1. **No em-dash, and no double-hyphen standing in for one.** Use a
   comma, a colon, parentheses, or split the sentence. This covers
   docstrings, comments, markdown, error text and CLI help, since all
   of them reach a reader.
2. **No reference to a gitignored `.smd` process note.** Those files
   are never published, so a shipped comment pointing at one sends a
   reader somewhere that does not exist.

Run over the whole tree, or over an explicit path list so a pre-commit
hook can pass just the staged files.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

# ' -- ' anywhere, plus a wrapped dash at the start or end of a line.
# A run of three or more is a markdown rule or a comment banner, not
# punctuation, so it is left alone.
_DASH = re.compile(r"(?<!-) -- (?!-)|(?<!-) --\s*$|^\s*(?:#|//|\*)?\s*-- (?!-)")
_EMDASH = re.compile("—")
_PRIVATE_NOTE = re.compile(r"\.smd\b")

# `--` is a shell argument separator, not punctuation, so a line that
# invokes a command is code and exempt from the dash rule (`git
# ls-files -- '*.py'` must keep its separator).
_SHELL_LINE = re.compile(r"^\s*(-\s*)?(run|entry|args|command|script):|\$\(|"
                         r"^\s*\$ |^\s*(python|pip|git|pytest|mathema|mkdocs) ")

_TEXT_SUFFIXES = (".py", ".md", ".toml", ".yml", ".yaml", ".cfg", ".css")
_SKIP_DIRS = {".git", ".venv", "venv", "build", "dist", "site", "node_modules",
              "__pycache__", ".smd", ".mathema", "design", ".pytest_cache"}
# the licence is verbatim third-party text and is never rewritten
_SKIP_FILES = {"LICENSE.md", "LICENSE", "CLA.md"}


def _tracked_text_files():
    """Every text file in the repository, from git when it is
    available (so ignored files are skipped for free) and from a walk
    otherwise."""
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True,
                             text=True, check=True).stdout
        paths = [p for p in out.splitlines() if p.endswith(_TEXT_SUFFIXES)]
        if paths:
            return paths
    except (OSError, subprocess.CalledProcessError):
        pass
    found = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        found += [os.path.join(root, f) for f in files
                  if f.endswith(_TEXT_SUFFIXES)]
    return found


def check_prose(paths):
    """Intent:
        The house-style findings for `paths`, as
        `(path, line_number, kind, text)` tuples. An unreadable file is
        skipped rather than raising: this is a lint, not a parser.
    """
    findings = []
    for path in paths:
        if os.path.basename(path) in _SKIP_FILES:
            continue
        # this file necessarily contains every pattern it looks for
        if os.path.basename(path) == os.path.basename(__file__):
            continue
        if any(part in _SKIP_DIRS for part in path.split(os.sep)):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines, 1):
            text = line.rstrip("\n")
            if _EMDASH.search(text):
                findings.append((path, i, "em-dash", text.strip()))
            elif _DASH.search(text) and not _SHELL_LINE.search(text):
                findings.append((path, i, "double-hyphen", text.strip()))
            if path.endswith(".gitignore"):
                continue
            if _PRIVATE_NOTE.search(text):
                findings.append((path, i, "private-note", text.strip()))
    return findings


def main(argv: list[str] | None = None) -> int:
    paths = argv if argv else _tracked_text_files()
    findings = check_prose(paths)
    if not findings:
        return 0
    print("House-style findings (see docs/mathema-docstring.md):",
          file=sys.stderr)
    for path, line, kind, text in findings:
        print(f"  {path}:{line}: {kind}", file=sys.stderr)
        print(f"      {text[:100]}", file=sys.stderr)
    print(f"\n{len(findings)} finding(s). Use a comma, a colon, parentheses, "
          "or split the sentence.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
