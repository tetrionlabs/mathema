# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Export a library's verified claims as a compendium claims file.

A library author who has run `mathema verify` on their package holds a
verified store of claims about their own functions.
`export_compendium` turns the proven and held rows for one library into
a claims file in the compendium shape (`compendium: <library>`,
`versions:` the installed minor release, one key per function), which a
downstream project drops into its own claims directory. Each row
carries the verdict it reached here as its claimed level
(`meta: {mathema.compendium_claimed: holds}`) and the `note:` its
claims file states; a consumer still verifies or accepts it, since a
compendium row is testimony until then.
"""
from __future__ import annotations

import os

_SUPPORTED = ("proven", "holds")

#: authoring surfaces whose rows are regenerated on every run rather
#: than stated by anyone, so they are not the library's claims
_GENERATED_SURFACES = ("builtin", "mathema")


def _installed(library: str) -> "str | None":
    from . import _installed_version
    return _installed_version(library)


def _compendium_file_entries(library: str, root: str) -> list:
    """Intent:
        `(key, entry, bundled)` for every entry of every compendium file
        about `library`, bundled first, then the project's, whatever
        version range each file states: the rows as their files write
        them, and whether the file ships with mathema.
    """
    from . import _bundled_dir, pop_library_fields
    from ..spec import claims_file_paths, read_claims_file
    bundled = _bundled_dir()
    paths = claims_file_paths(bundled)
    paths += claims_file_paths(root, exclude=(bundled,))
    out: list = []
    for path in paths:
        try:
            data = read_claims_file(path, os.path.relpath(path, root)) or {}
        except Exception:
            continue
        if data.get("compendium") is None:
            continue
        data = dict(data)
        data.pop("grammar", None)
        fields = pop_library_fields(data)
        if fields.library != library:
            continue
        out.extend((k, e, path.startswith(bundled + os.sep))
                   for k, e in data.items() if isinstance(e, dict))
    return out


def _stated_rows(library: str, root: str) -> dict:
    """Intent:
        `{(key, claim name): (row, bundled)}` for every `<library>.*`
        row a claims file states: the compendium files about the library
        (bundled, then the project's, in or out of their version range),
        then the project's own claims files, a later file's row
        replacing an earlier one of the same name; `bundled` says
        whether the stating file ships with mathema.
    """
    from ..spec import load_declared

    entries = _compendium_file_entries(library, root)
    out: dict = {}
    for key, entry, bundled in entries:
        if key.split(".")[0] != library:
            continue
        for c in (entry or {}).get("claims") or []:
            if isinstance(c, dict) and c.get("name"):
                out[(key, c["name"])] = (c, bundled)
    for key, info in load_declared(root).items():
        if key.split(".")[0] != library or not isinstance(info, dict):
            continue
        for c in (info.get("entry") or {}).get("claims") or []:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            prior = out.get((key, c["name"]))
            if prior is not None and _same_row(prior[0], c):
                continue
            out[(key, c["name"])] = (c, False)
    return out


def _same_row(a: dict, b: dict) -> bool:
    """Whether two stated rows say the same thing (statement and note)."""
    return (str(a.get("statement") or a.get("law") or "")
            == str(b.get("statement") or b.get("law") or "")
            and a.get("note") == b.get("note"))


def _stated_notes(library: str, root: str) -> dict:
    """Intent:
        `{(key, claim name): note}` for every `<library>.*` row a claims
        file states a `note:` on (`_stated_rows`).
    """
    return {k: str(c["note"])
            for k, (c, _b) in _stated_rows(library, root).items()
            if c.get("note")}


def export_range(library: str, installed: "str | None",
                 root: str) -> str:
    """Intent:
        The `versions:` range an export of `library` writes: `"*"` for
        the standard library or a library with no installed version;
        `">=<major.minor>"` for the project's own package; otherwise the
        installed minor version alone (`">=1.24,<1.25"` on 1.24.4), the
        release its rows were checked against.
    """
    from . import _version_tuple, names_own_package
    if not installed or installed == "*":
        return "*"
    major, minor = (list(_version_tuple(installed)) + [0, 0])[:2]
    if names_own_package(library, root):
        return f">={major}.{minor}"
    return f">={major}.{minor},<{major}.{minor + 1}"


def export_compendium(library: str, root: str = ".",
                      notes: "list | None" = None) -> dict:
    """Intent:
        The compendium claims file for `library`, as the mapping
        `spec.write_yaml` writes: `compendium`, `versions`, then one
        entry per verified `<library>.*` key holding its proven and
        held rows, each stamped with the verdict it reached as
        `mathema.compendium_claimed`, and the `note:` the claims file
        that states the row gives it.

    Notes:
        `versions` is `export_range`. At or above the library's supported
        floor (`compendium.SUPPORTED_FLOORS`) the rows a bundled file
        states are left out, since mathema already ships them for that
        version, and one line saying so is appended to `notes`. The built-in battery rows and pseudo-claims (a row
        whose statement is its own name, `dependencies_current`) are
        left out: they are regenerated for every function, never
        claimed about it. A key with no row to transfer is left out.
        The record's intent travels with the rows, except for a function
        with no Python source, whose recorded intent is only its
        docstring's first line. A row's statement, route and note are the
        ones its claims file states (`_stated_rows`), never the record's
        rendering of the resolved claim, the route that decided it, or
        the note the adjudication wrote; a row no claims file states
        keeps the record's statement.
    """
    from ..spec import load_verified

    from . import SUPPORTED_FLOORS, below_floor
    installed = _installed(library)
    out: dict = {"compendium": library,
                 "versions": export_range(library, installed, root)}
    stated_rows = _stated_rows(library, root)
    covered = (library in SUPPORTED_FLOORS and bool(installed)
               and not below_floor(library, installed))
    left_out = 0
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
            stated, bundled = stated_rows.get((key, c.get("name")),
                                              ({}, False))
            if bundled and covered:
                left_out += 1
                continue
            stated_text = stated.get("statement") or stated.get("law")
            row = {"name": c.get("name"),
                   "statement": str(stated_text) if stated_text
                   else statement}
            asked = (stated.get("route") if stated
                     else (c.get("authored") or {}).get("route", c.get("route")))
            if asked and asked != "best":
                row["route"] = asked
            if stated.get("note"):
                row["note"] = str(stated["note"])
            row["meta"] = {"mathema.compendium_claimed": c["verdict"]}
            rows.append(row)
        if rows:
            body: dict = {}
            source_less = (entry.get("identity") or {}).get(
                "source_available") is False
            if entry.get("intent") and not source_less:
                body["intent"] = entry["intent"]
            body["claims"] = rows
            out[key] = body
    if left_out and notes is not None:
        short = ".".join(str(installed).split(".")[:2])
        notes.append(f"bundled rows already cover {library} {short}: "
                     f"{left_out} row{'s' if left_out != 1 else ''} a "
                     f"bundled file states left out of the export "
                     f"(mathema ships them for {library} >= "
                     f"{SUPPORTED_FLOORS[library]})")
    return out


def default_export_path(library: str, root: str = ".") -> str:
    """Where `mathema compendium export` writes by default:
    `claims/<library>.claims.yaml` under the project root, a place the
    claims-file discovery reads."""
    import os
    return os.path.join(root, "claims", f"{library}.claims.yaml")


def write_compendium(library: str, root: str = ".",
                     out: "str | None" = None,
                     notes: "list | None" = None) -> "str | None":
    """Write `export_compendium(library)` to `out` (default
    `default_export_path`), returning the path, or None when no row is
    left to export (nothing is written; `notes` says why)."""
    from ..spec import write_yaml
    path = out or default_export_path(library, root)
    data = export_compendium(library, root, notes=notes)
    if not set(data) - {"compendium", "versions"}:
        return None
    write_yaml(path, data, header=(
        f"claims about {library}'s functions, exported from a verified "
        f"store; each row's\nmathema.compendium_claimed is the verdict it "
        f"reached there, and a consumer\nverifies or accepts it before "
        f"resting a claim on it"))
    return path
