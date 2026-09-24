# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Locking a function: pinning its form hash so the body cannot change
under a CDD loop.

A lock says "this implementation is settled": `mathema verify` refuses
to re-adjudicate a locked function whose form hash has moved, fails the
run, and leaves the old record exactly as it was, so an agent editing a
locked body gets a clean stop rather than a quietly shifted baseline.
Docstring edits never trip it, since the form hash strips docstrings
before hashing; re-authoring claims on an unchanged body adjudicates
normally too. The lock pins the body, nothing else.

Locking is the safe direction and an agent may do it. Unlocking is a
human decision: the verb is CLI-only, has no `--yes`, and prompts for
the PIN when one is configured (see `mathema.auth`).

The flag lives in `.mathema/meta/locks.yaml`, the curation corner of
the store, deliberately not in the verified record alone: records are
rebuilt from scratch on every adjudication, and a lock has to survive
the very sweep it is blocking. The record carries a `locked` stamp as a
reflection (covered by the integrity checksum), so deleting the meta
entry by hand is detectable: a record that says locked with no meta
entry behind it fails the sweep as a lock removed outside
`mathema unlock`.
"""
from __future__ import annotations

import datetime
import os


class LockError(Exception):
    """A lock operation that cannot proceed: unknown key, a re-lock at
    a different form, an unlock of an unlocked function."""


def locks_path(root: str = ".") -> str:
    """The lock file under the store's meta/ area:
    `.mathema/meta/locks.yaml`, `{key: {form, at, by, note}}`.
    Committed with the store, like the rest of `.mathema/`."""
    return os.path.join(root, ".mathema", "meta", "locks.yaml")


def load_locks(root: str = ".") -> dict:
    """Every lock, `{}` on a missing or unreadable file (a lock file
    that cannot be read must not silently unlock anything, so a parse
    error raises rather than returning empty)."""
    import yaml
    path = locks_path(root)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _write_locks(root: str, data: dict) -> None:
    import yaml
    path = locks_path(root)
    from .spec import atomic_write_text
    atomic_write_text(
        path, "# locked functions: the form hash each is pinned at.\n"
              "# `mathema lock KEY` adds one; only `mathema unlock KEY`\n"
              "# (a human act) removes one.\n"
        + yaml.safe_dump(data, sort_keys=True, allow_unicode=True))


def lock(root: str, key: str, form: str, *, by: str | None = None,
         note: str | None = None) -> dict:
    """Pin `key` at `form`. Re-locking at the same form is a no-op
    (returns the existing entry); at a different form it refuses, since
    moving a lock is exactly what `unlock` exists to make deliberate."""
    locks = load_locks(root)
    existing = locks.get(key)
    if existing:
        if existing.get("form") == form:
            return existing
        raise LockError(
            f"{key} is already locked at form {existing.get('form')} "
            f"(the code is now {form}); a human runs `mathema unlock "
            f"{key}` before it can be re-locked")
    entry = {"form": form, "at": datetime.date.today().isoformat()}
    if by:
        entry["by"] = by
    if note:
        entry["note"] = note
    locks[key] = entry
    _write_locks(root, locks)
    return entry


def unlock(root: str, key: str) -> dict:
    """Remove `key`'s lock entry, returning what it was. The caller
    (the CLI verb) is responsible for the human gate; this function is
    the mechanical half only."""
    locks = load_locks(root)
    if key not in locks:
        raise LockError(f"{key} is not locked")
    entry = locks.pop(key)
    _write_locks(root, locks)
    return entry


def lock_state(key: str, current_form: str | None, locks: dict,
               verified_entry: dict | None) -> str | None:
    """Intent:
        One key's lock condition, for the sweep: `None` (not locked,
        nothing stamped), "held" (locked, form unchanged), "changed"
        (locked, the body moved), or "removed-outside" (the record
        still carries a lock stamp but the meta entry is gone, i.e.
        someone deleted the lock without `mathema unlock`).
    """
    meta_entry = locks.get(key)
    stamped = (verified_entry or {}).get("locked")
    if meta_entry is None:
        return "removed-outside" if isinstance(stamped, dict) else None
    if current_form is not None and meta_entry.get("form") != current_form:
        return "changed"
    return "held"
