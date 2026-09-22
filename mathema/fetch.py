# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Fetch a git repository into a local directory.

mathema is otherwise an offline tool: it reaches the network only when a
command explicitly asks it to fetch something (today, `mathema init
--agents`; a compendium install later). That fetch goes through `git`,
the one external program mathema already shells to, so it needs no HTTP
client and inherits whatever authentication the user's git is configured
with (SSH keys, a credential helper), which is what lets it reach a
private repository at all.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

# reason -> the plain-language cause, so a caller renders one message per
# outcome without re-parsing git's stderr itself
REASONS = {
    "ok": "cloned",
    "git-missing": "git is not installed or not on PATH",
    "unreachable": "could not reach the network",
    "auth": "access was refused (the repository may be private, or your "
            "git has no credentials for it)",
    "not-found": "no such repository (or it is private and hidden from you)",
    "timeout": "the clone took too long and was stopped",
    "failed": "git clone failed",
}


@dataclass
class FetchResult:
    """The outcome of a `clone_repo` call: `ok`, a `reason` key into
    `REASONS`, and git's own stderr in `detail` when it failed."""
    ok: bool
    reason: str
    detail: str = ""


def _classify(stderr: str) -> str:
    """Intent:
        Map git clone's stderr to a `REASONS` key, so the caller can
        say why in plain language. A private repository refused for
        lack of credentials lands on `auth` or `not-found` (GitHub
        hides a private repo behind a 404), and both read to the user
        as "you may need access".
    """
    s = (stderr or "").lower()
    if any(m in s for m in ("could not resolve host", "network is unreachable",
                            "connection timed out", "temporary failure in name",
                            "failed to connect")):
        return "unreachable"
    if any(m in s for m in ("authentication failed", "permission denied",
                            "could not read from remote", "publickey",
                            "could not read username")):
        return "auth"
    if any(m in s for m in ("repository not found", "not found",
                            "does not exist")):
        return "not-found"
    return "failed"


def clone_repo(url: str, dest: str, *, ref: str | None = None,
               timeout: int = 60) -> FetchResult:
    """Intent:
        Shallow-clone `url` (a git URL, or a local path / `file://`
        URL, which is what makes this testable offline) into `dest`,
        optionally at branch/tag `ref`. Returns a `FetchResult`;
        never raises, so a caller renders one message and exits
        cleanly whatever went wrong.
    Notes:
        `dest` must not already exist as a non-empty directory (git's
        own rule). Uses the same `subprocess.run` + timeout pattern as
        the rest of mathema's git calls.
    """
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += ["--", url, dest]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return FetchResult(False, "git-missing")
    except subprocess.TimeoutExpired:
        return FetchResult(False, "timeout")
    except Exception as e:                       # pragma: no cover - defensive
        return FetchResult(False, "failed", str(e))
    if r.returncode == 0:
        return FetchResult(True, "ok")
    return FetchResult(False, _classify(r.stderr), (r.stderr or "").strip())
