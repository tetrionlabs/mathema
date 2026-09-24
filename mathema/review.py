# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Review the verified store by CLAIMS, not by raw YAML diff.

`mathema review [<ref>]` compares the verified records at a git ref (the
base, default HEAD) against the working tree and reports what changed at
the level that matters: which verdicts flipped, which claims were added or
removed, which are newly falsified, and which records a human reconciled.
It is the reviewer-facing counterpart to a git diff over
`.mathema/verified/`, whose YAML noise (re-anchored lineage, reordered
rows) hides the handful of facts a reviewer actually needs. The shape
mirrors `badges.ci_snapshot`: a human summary and a `--format json` a CI
job can post as a PR comment.
"""
from __future__ import annotations

import subprocess


class UnknownRef(ValueError):
    """The base ref does not name a commit in this repository."""


def _git(root: str, *args: str) -> "str | None":
    """A git command's stdout, or None when git fails (not a repo, an
    unknown ref, an absent path)."""
    try:
        r = subprocess.run(["git", *args], cwd=root or ".",
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def _records_at_ref(root: str, ref: str) -> dict:
    """`{key: entry}` for every verified record as it stood at `ref`."""
    import os
    import yaml
    listing = _git(root, "ls-tree", "-r", "--name-only", ref, "--",
                   ".mathema/verified")
    out: dict = {}
    for path in (listing or "").splitlines():
        if not path.endswith(".yaml"):
            continue
        blob = _git(root, "show", f"{ref}:{path}")
        if blob is None:
            continue
        try:
            doc = yaml.safe_load(blob) or {}
        except Exception:
            continue
        for key, entry in doc.items():
            out[key] = entry
    _ = os  # (kept for parity with the working-tree loader)
    return out


def _records_working(root: str) -> dict:
    """`{key: entry}` for the working-tree verified store."""
    from .spec import load_verified
    return {k: info["entry"] for k, info in load_verified(root).items()}


def _claim_statements(entry: dict) -> dict:
    """`{claim-name: statement}` for one record's live claims."""
    return {c["name"]: c.get("statement") or c.get("law") or ""
            for c in entry.get("claims") or [] if c.get("name")}


def _retired_rows(entry: dict) -> set:
    """Every row of the record's retirement sections, as
    `section:name` labels."""
    return {f"{section}:{r.get('name')}"
            for section in ("discoveries", "historical", "superseded")
            for r in entry.get(section) or [] if isinstance(r, dict)}


def _claim_verdicts(entry: dict) -> dict:
    """`{claim-name: verdict}` for one record's live claims."""
    out = {}
    for c in entry.get("claims") or []:
        name = c.get("name")
        if name:
            out[name] = c.get("verdict") or ""
    return out


def review(root: str = ".", ref: str = "HEAD") -> dict:
    """Intent:
        The claim-level delta between the verified store at `ref` (the
        base) and the working tree. Returns `{"base", "summary",
        "changes"}`: `summary` counts the movements, `changes` lists them
        per function key, each `{key, added, removed, flipped, reconciled,
        newly_falsified, restated, retired_added, retired_dropped}`, so a
        reviewer reads the handful of facts a raw YAML diff buries.
        `restated` is a claim whose statement changed under the same
        name; `retired_added`/`retired_dropped` are rows of the
        `discoveries`, `historical` and `superseded` sections, as
        `section:name`.

    Raises:
        UnknownRef: `ref` does not name a commit (the default `HEAD` of
            a repository with no commit yet reads as an empty base).
    """
    from .records import classify_verdict
    if _git(root, "rev-parse", "--verify", "--quiet",
            f"{ref}^{{commit}}") is not None:
        old = _records_at_ref(root, ref)
    elif ref == "HEAD" and _git(root, "rev-parse", "--git-dir") is not None:
        # a repository with no commit yet: the base is an empty store
        old = {}
    else:
        raise UnknownRef(f"review: {ref!r} is not a commit in the "
                         f"repository at {root}")
    new = _records_working(root)
    changes = []
    totals = {"flipped": 0, "added": 0, "removed": 0,
              "newly_falsified": 0, "reconciled": 0, "keys_changed": 0,
              "restated": 0, "retired_added": 0, "retired_dropped": 0}
    for key in sorted(set(old) | set(new)):
        oe, ne = old.get(key) or {}, new.get(key) or {}
        ov, nv = _claim_verdicts(oe), _claim_verdicts(ne)
        added = sorted(set(nv) - set(ov))
        removed = sorted(set(ov) - set(nv))
        flipped = [{"claim": n, "from": ov[n], "to": nv[n]}
                   for n in sorted(set(ov) & set(nv)) if ov[n] != nv[n]]
        newly_falsified = [f["claim"] for f in flipped
                           if classify_verdict(f["to"]) == "falsified"]
        newly_falsified += [n for n in added
                            if classify_verdict(nv[n]) == "falsified"]
        reconciled = bool((ne.get("identity") or {}).get("reconciled")) and \
            not (oe.get("identity") or {}).get("reconciled")
        os_, ns_ = _claim_statements(oe), _claim_statements(ne)
        restated = [{"claim": n, "from": os_[n], "to": ns_[n]}
                    for n in sorted(set(os_) & set(ns_))
                    if os_[n] != ns_[n]]
        o_ret, n_ret = _retired_rows(oe), _retired_rows(ne)
        retired_added = sorted(n_ret - o_ret)
        retired_dropped = sorted(o_ret - n_ret)
        if not (added or removed or flipped or reconciled or restated
                or retired_added or retired_dropped):
            continue
        changes.append({"key": key, "added": added, "removed": removed,
                        "flipped": flipped, "newly_falsified": newly_falsified,
                        "reconciled": reconciled, "restated": restated,
                        "retired_added": retired_added,
                        "retired_dropped": retired_dropped})
        totals["restated"] += len(restated)
        totals["retired_added"] += len(retired_added)
        totals["retired_dropped"] += len(retired_dropped)
        totals["keys_changed"] += 1
        totals["flipped"] += len(flipped)
        totals["added"] += len(added)
        totals["removed"] += len(removed)
        totals["newly_falsified"] += len(newly_falsified)
        totals["reconciled"] += 1 if reconciled else 0
    return {"base": ref, "summary": totals, "changes": changes}


def render(result: dict) -> str:
    """The review delta as a human summary."""
    s = result["summary"]
    if not s["keys_changed"]:
        return f"No claim changes in the verified store since {result['base']}."
    lines = [f"Claim changes since {result['base']}: "
             f"{s['keys_changed']} function(s), {s['flipped']} verdict "
             f"flip(s), {s['added']} added, {s['removed']} removed, "
             f"{s['newly_falsified']} newly falsified, {s['reconciled']} "
             f"reconciled"
             + "".join(f", {s[k]} {word}" for k, word in (
                 ("restated", "restated"),
                 ("retired_added", "retirement row(s) added"),
                 ("retired_dropped", "retirement row(s) dropped"))
                 if s.get(k))
             + ".", ""]
    for ch in result["changes"]:
        lines.append(f"{ch['key']}"
                     + ("  [reconciled]" if ch["reconciled"] else ""))
        for f in ch["flipped"]:
            mark = "  !!" if f["to"] in ("falsified", "invalidated") else ""
            lines.append(f"    {f['claim']}: {f['from']} -> {f['to']}{mark}")
        for n in ch["added"]:
            lines.append(f"    + {n}")
        for n in ch["removed"]:
            lines.append(f"    - {n}")
        for r in ch.get("restated") or []:
            lines.append(f"    {r['claim']}: restated {r['from']!r} -> "
                         f"{r['to']!r}")
        for label in ch.get("retired_added") or []:
            section, name = label.split(":", 1)
            lines.append(f"    + {section} row {name}")
        for label in ch.get("retired_dropped") or []:
            section, name = label.split(":", 1)
            lines.append(f"    - {section} row {name} dropped  !!")
    return "\n".join(lines)
