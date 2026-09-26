# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Export a library's verified claims as a compendium claims file.

A library author who has run `mathema verify` on their package holds a
verified store of claims about their own functions.
`export_compendium` turns the proven and held rows for one library into
a claims file in the compendium shape (`compendium: <library>`,
`versions: ">=<installed major.minor>"`, one key per function), which a
downstream project drops into its own claims directory. Each row
carries the verdict it reached here as its claimed level
(`meta: {mathema.compendium_claimed: holds}`); a consumer still verifies
or accepts it, since a compendium row is testimony until then.
"""
from __future__ import annotations

_SUPPORTED = ("proven", "holds")

#: authoring surfaces whose rows are regenerated on every run rather
#: than stated by anyone, so they are not the library's claims
_GENERATED_SURFACES = ("builtin", "mathema")


def _installed(library: str) -> "str | None":
    from . import _installed_version
    return _installed_version(library)


def export_compendium(library: str, root: str = ".") -> dict:
    """Intent:
        The compendium claims file for `library`, as the mapping
        `spec.write_yaml` writes: `compendium`, `versions`, then one
        entry per verified `<library>.*` key holding its proven and
        held rows, each stamped with the verdict it reached as
        `mathema.compendium_claimed`.

    Notes:
        `versions` is `">=<major.minor>"` of the installed library, or
        `"*"` for the standard library or a library with no installed
        version. The built-in battery rows and pseudo-claims (a row
        whose statement is its own name, `dependencies_current`) are
        left out: they are regenerated for every function, never
        claimed about it. A key with no row to transfer is left out.
        The record's intent travels with the rows when a compendium
        file's curator stated it, or when the function has Python
        source; a source-less function's other recorded intent is only
        its docstring's first line.
    """
    from ..spec import load_verified

    installed = _installed(library)
    if installed and installed != "*":
        versions = ">=" + ".".join(installed.split(".")[:2])
    else:
        versions = "*"
    out: dict = {"compendium": library, "versions": versions}
    for key, info in sorted(load_verified(root).items()):
        if key.split(".")[0] != library:
            continue
        entry = (info.get("entry") if isinstance(info, dict) else info) or {}
        rows = []
        for c in entry.get("claims") or []:
            if c.get("verdict") not in _SUPPORTED:
                continue
            statement = c.get("statement") or c.get("law") or ""
            if not statement or statement == c.get("name"):
                continue
            meta = c.get("meta") or {}
            if meta.get("mathema.surface") in _GENERATED_SURFACES:
                continue
            row = {"name": c.get("name"), "statement": statement}
            if c.get("route") and c.get("route") != "best":
                row["route"] = c["route"]
            row["meta"] = {"mathema.compendium_claimed": c["verdict"]}
            rows.append(row)
        if rows:
            body: dict = {}
            source_less = (entry.get("identity") or {}).get(
                "source_available") is False
            curated = (entry.get("meta") or {}).get(
                "mathema.intent_provenance") == "compendium"
            if entry.get("intent") and (curated or not source_less):
                body["intent"] = entry["intent"]
            body["claims"] = rows
            out[key] = body
    return out


def default_export_path(library: str, root: str = ".") -> str:
    """Where `mathema compendium export` writes by default:
    `claims/<library>.claims.yaml` under the project root, a place the
    claims-file discovery reads."""
    import os
    return os.path.join(root, "claims", f"{library}.claims.yaml")


def write_compendium(library: str, root: str = ".",
                     out: "str | None" = None) -> str:
    """Write `export_compendium(library)` to `out` (default
    `default_export_path`), returning the path."""
    from ..spec import write_yaml
    path = out or default_export_path(library, root)
    data = export_compendium(library, root)
    write_yaml(path, data, header=(
        f"claims about {library}'s functions, exported from a verified "
        f"store; each row's\nmathema.compendium_claimed is the verdict it "
        f"reached there, and a consumer\nverifies or accepts it before "
        f"resting a claim on it"))
    return path
