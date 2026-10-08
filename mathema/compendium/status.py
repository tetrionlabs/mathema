# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where a project stands with the libraries it calls.

`compendium_status` reads the project's functions (every key the
declared and verified stores know), resolves each call they make
through its import aliases, and reports, for every third-party library
called: its installed version, the claims files about it (bundled with
mathema or in the project, each with its `versions` range and whether
the installed version is inside it), the called functions no claims
file states anything about, and for each called function that has rows
how many of them are verified locally, trusted, falsified or unsettled.
The standard library is left out. Nothing is written.
"""
from __future__ import annotations

import os
import sys

def _is_stdlib(head: str) -> bool:
    stdlib: frozenset = getattr(sys, "stdlib_module_names", frozenset())
    return head in stdlib or head == "builtins"


def _library_version(library: str, files: list) -> "str | None":
    """The installed version of `library`, read through the loader's own
    lookup (`_installed_version`) with every alias its claims `files`
    declare."""
    from . import _installed_version
    aliases: list = []
    for f in files:
        aliases += [a for a in f.get("aliases", ()) if a not in aliases]
    return _installed_version(library, aliases)


def _in_project(head: str, root: str) -> bool:
    """Whether the top-level module `head` is the project's own: a
    package `own_packages` names, or a module whose file lies under
    `root` outside any installed-packages directory."""
    from . import own_packages
    if head in own_packages(root):
        return True
    module = sys.modules.get(head)
    path = getattr(module, "__file__", None)
    if not path:
        return False
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real.startswith(base + os.sep) and "site-packages" not in real


def _library_files(root: str) -> dict:
    """Intent:
        `{library: [{"source", "origin", "versions", "aliases",
        "in_range"}]}` for every claims file declaring `compendium:`,
        bundled ones first, whether or not its range admits the
        installed version.
    """
    from . import _bundled_dir, _display_path, applicable_tag
    from ..spec import claims_file_paths, read_claims_file
    bundled = _bundled_dir()
    out: dict = {}
    paths = [(p, "bundled") for p in claims_file_paths(bundled)]
    paths += [(p, "project")
              for p in claims_file_paths(root, exclude=(bundled,))]
    for path, origin in paths:
        where = _display_path(path, root)
        try:
            data = read_claims_file(path, where) or {}
        except Exception:
            continue
        library = data.get("compendium")
        if not isinstance(library, str):
            continue
        versions = str(data.get("versions", "*"))
        aliases = tuple(data.get("aliases") or ())
        out.setdefault(library, []).append({
            "source": where, "origin": origin, "versions": versions,
            "aliases": list(aliases),
            "in_range": applicable_tag(library, versions,
                                       aliases) is not None})
    return out


def _calls_by_library(root: str) -> dict:
    """Intent:
        `{library: {dotted function: number of project functions calling
        it}}` over the project's functions, third-party libraries only.
    """
    import warnings

    from . import is_library_record, load_library_claims, resolved_calls
    from .. import analyze
    from ..conjecture import _resolve_func_ref
    from ..spec import load_declared, load_verified

    library_keys = set(load_library_claims(root))
    verified = load_verified(root)
    declared = load_declared(root)
    out: dict = {}
    for key in sorted(set(verified) | set(declared)):
        if key in library_keys or is_library_record(
                (verified.get(key) or {}).get("entry") or {}):
            continue
        fn = _resolve_func_ref(key, root=root)
        if fn is None:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                facts = analyze(fn)
        except Exception:
            continue
        for called in resolved_calls(fn, facts) + _method_calls(
                fn, facts, root, library_keys):
            head = called.split(".")[0]
            if _is_stdlib(head) or _in_project(head, root):
                continue
            funcs = out.setdefault(head, {})
            funcs[called] = funcs.get(called, 0) + 1
    return out


def _method_calls(fn, facts, root: str, library_keys: set) -> list:
    """Intent:
        The library keys `fn` reaches through a value with a runtime
        type (`s.mean()` on a `pandas.Series` is `pandas.Series.mean`,
        `definitions.called_keys`), beyond its calls through import
        aliases: each one called as a method, or with claims of its own.
    """
    import ast

    from . import _resolve_called_keys
    from ..definitions import called_keys
    tree = getattr(facts, "tree", None)
    if tree is None:
        return []
    methods = {node.func.attr for node in ast.walk(tree)
               if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)}
    aliased = set(_resolve_called_keys(fn, facts))
    try:
        typed = called_keys(fn, facts, root) - aliased
    except Exception:
        return []
    return sorted(k for k in typed
                  if k in library_keys or k.rsplit(".", 1)[-1] in methods)


def _row_state(row: "dict | None") -> "tuple[str, str | None]":
    """The state of one library row as this project's store records it,
    with the accepted level for a trusted row."""
    from ..records import classify_verdict
    if not row:
        return "unsettled", None
    accepted = row.get("accepted") or {}
    if accepted.get("as") == "trusted" and not accepted.get("stale"):
        return "trusted", accepted.get("level") or row.get("verdict")
    kind = classify_verdict(row.get("verdict") or "")
    if kind in ("proven", "holds"):
        return "verified", None
    if kind in ("falsified", "invalidated"):
        return "falsified", None
    return "unsettled", None


def _unregistered_rows(key: str, rows: list) -> dict:
    """Intent:
        Each fact row of `key` whose region cannot be built, and so
        registers no guard or computation row, mapped to the reason.
        A row reading an array's shape or a matrix is left to the
        hazard generator and is not listed.
    """
    from . import _row_region, _Unbuildable, row_is_fact
    out: dict = {}
    for row in rows:
        if not row_is_fact(row):
            continue
        try:
            _row_region(key, row)
        except _Unbuildable as e:
            if str(e) != "shape":
                out[str(row.get("name"))] = str(e)
    return out


def compendium_status(root: str = ".",
                      library: "str | None" = None) -> dict:
    """Intent:
        The status of every third-party library the project calls (or of
        `library` alone), as data: `{"root", "standard_library",
        "libraries": [...]}`, each library `{"library", "version",
        "calls", "files", "no_claims", "functions"}`, sorted by call
        count, most called first. `files` lists every claims file about
        the library; `no_claims` the called functions no applicable
        file states a row for; `functions` maps each called function
        with rows to its call count, its number of rows, and how many
        are `verified` (proven or holds here), `trusted` (by accepted
        level), `falsified` and `unsettled` (never adjudicated here,
        unknown or skipped), and `unregistered`, each row whose region
        cannot be built mapped to the reason (`_unregistered_rows`).

    Notes:
        A call is counted once per project function that makes it.
        Standard-library calls are left out
        (`standard_library: "left out"`).
    """
    from . import load_library_claims
    from ..spec import load_verified

    root = os.path.abspath(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    calls = _calls_by_library(root)
    if library is not None:
        calls = {library: calls.get(library, {})}
    files = _library_files(root)
    claims = load_library_claims(root)
    verified = load_verified(root)
    libraries = []
    for lib, funcs in calls.items():
        entry: dict = {"library": lib,
                       "version": _library_version(lib, files.get(lib, [])),
                       "calls": sum(funcs.values()),
                       "files": files.get(lib, []), "no_claims": [],
                       "functions": {}}
        for key, n in sorted(funcs.items(), key=lambda kv: (-kv[1], kv[0])):
            rows = [r for r in ((claims.get(key) or {}).get("entry") or {})
                    .get("claims") or [] if r.get("name")]
            if not rows:
                entry["no_claims"].append(key)
                continue
            recorded = {r.get("name"): r for r in
                        ((verified.get(key) or {}).get("entry") or {})
                        .get("claims") or []}
            counts: dict = {"calls": n, "rows": len(rows), "verified": 0,
                            "trusted": {}, "falsified": 0, "unsettled": 0,
                            "unregistered": _unregistered_rows(key, rows)}
            for row in rows:
                state, level = _row_state(recorded.get(row["name"]))
                if state == "trusted":
                    counts["trusted"][level] = \
                        counts["trusted"].get(level, 0) + 1
                else:
                    counts[state] += 1
            entry["functions"][key] = counts
        libraries.append(entry)
    uncovered = _uncovered_calls(root, claims)
    for entry in libraries:
        entry["uncovered"] = [u for u in uncovered
                              if u["key"].split(".")[0] == entry["library"]]
    libraries.sort(key=lambda e: (-e["calls"], e["library"]))
    return {"root": root, "standard_library": "left out",
            "libraries": libraries}


def _uncovered_calls(root: str, claims: dict) -> list:
    """Intent:
        Each library call a project function makes with non-default
        literal arguments that no row of the function covers (no row
        pinned to them, and no row ranging over them at the values
        passed), as `{"key", "pins", "caller", "line"}`.
    """
    import warnings

    from . import row_pins
    from ..analysis import StateDependenceWarning
    from ..policy import parse_policy
    from .update import _open_pins, _pins_text, call_sites
    out: list = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", StateDependenceWarning)
        sites = call_sites(root, claims)
    for site in sites:
        if not site.pins:
            continue
        rows = [r for r in (claims.get(site.key) or {}).get("entry", {})
                .get("claims") or [] if isinstance(r, dict)
                and not parse_policy(str(r.get("statement") or ""))]
        covered = any(row_pins(r) == site.pins for r in rows) or any(
            _open_pins(r, site.pins) == ({}, None) for r in rows
            if not row_pins(r))
        if not covered:
            out.append({"key": site.key, "pins": _pins_text(site.pins),
                        "caller": site.caller, "line": site.line})
    return out


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def render_status(data: dict) -> str:
    """The text form of `compendium_status`: one block per library, most
    called first."""
    blocks = []
    for lib in data["libraries"]:
        head = f"{lib['library']} {lib['version'] or '(version unknown)'}"
        if not lib["calls"]:
            blocks.append(f"{head}: not called by any function in the "
                          f"project")
            continue
        lines = [f"{head}: {_plural(lib['calls'], 'call')}"]
        if lib["files"]:
            lines.append("  claims files:")
            lines.extend(
                f"    {f['source']} ({f['origin']}, {f['versions']}, "
                f"{'in range' if f['in_range'] else 'out of range'})"
                for f in lib["files"])
        else:
            lines.append("  claims files: none")
        width = max((len(k) for k in lib["functions"]), default=0)
        for key, c in lib["functions"].items():
            trusted = sum(c["trusted"].values())
            levels = ", ".join(f"{lvl}" if n == 1 else f"{n} {lvl}"
                               for lvl, n in sorted(c["trusted"].items()))
            lines.append(
                f"  {key:<{width}}  {_plural(c['calls'], 'call')}, "
                f"{_plural(c['rows'], 'row')}: "
                f"{c['verified']} verified locally, {trusted} trusted"
                + (f" ({levels})" if levels else "")
                + f", {c['falsified']} falsified, "
                  f"{c['unsettled']} unsettled")
            lines.extend(f"  {'':<{width}}  not registered: {name} ({why})"
                         for name, why in c["unregistered"].items())
        if lib["no_claims"]:
            lines.append("  no claims: " + ", ".join(lib["no_claims"]))
        if lib.get("uncovered"):
            lines.append(
                "  calls with arguments no row covers: "
                + "; ".join(f"{u['key']} {u['pins']} ({u['caller']}, line "
                            f"{u['line']})" for u in lib["uncovered"])
                + "; to add rows for them, run: mathema compendium update")
        blocks.append("\n".join(lines))
    if not blocks:
        blocks.append("no third-party library is called by a function in "
                      "the project")
    blocks.append("(standard library calls are left out)")
    return "\n\n".join(blocks)
