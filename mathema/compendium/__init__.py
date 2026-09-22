# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The compendium: curated claims about well-known libraries.

A compendium file states facts ABOUT a library
(raise regions, nan regions, known limitations, a few bound claims)
in the declared claims-file shape, keyed by dotted function name.
mathema bundles light starters for `math` and `numpy` under
`mathema/compendium/`; a project adds or overrides under
`.mathema/compendium/*.yaml`, which wins per function key.

Three consumption paths:

- `raises_when` regions register into the partiality-lemma registry
  (`mathema.lemmas.register_raises_when`), so claims about CALLERS of
  a compendium-covered function adjudicate against its raise region exactly as
  they do against `math.sqrt`'s today.
- `nan_when` regions and raise regions feed a hazard generator:
  their boundary values become sampling hints for every numeric
  parameter of a function that calls a covered name. Coarse on
  purpose; a boundary is worth probing near even when the argument
  is an expression rather than a bare parameter.
- Stub `claims` are premises a claim may rest on
  (`assuming clip_lower holds, ...`). A compendium verdict never enters
  the evidence chain silently: the claim stays `unknown` with
  `missing-prerequisite`, and the note names the compendium row and the
  path forward (accept it as trusted, or reverify it against the
  installed library). The accept-or-reverify loop itself is
  acceptance-flow work, tracked in the design note.

A compendium file only applies when the installed package version falls inside
the file's `versions` range; a stale compendium entry contributes nothing rather
than stale facts. The only range spelling supported is
`">=X[,<Y]"` or `"*"`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompendiumFunction:
    """One covered function's facts."""

    key: str                                  # dotted name, e.g. numpy.clip
    params: tuple = ()
    claims: tuple = ()                        # declared-shape claim dicts
    raises_when: tuple = ()                   # (condition text, exc name)
    nan_when: tuple = ()                      # condition text
    limitations: tuple = ()
    provenance: str = ""                      # "compendium:numpy-2.1"


@dataclass(frozen=True)
class CompendiumPack:
    package: str
    versions: str
    origin: str
    functions: dict = field(default_factory=dict)


def _version_tuple(text: str) -> tuple:
    return tuple(int(p) for p in text.split(".")[:3] if p.isdigit())


def _version_in_range(installed: str, spec: str) -> bool:
    """The light range check: `"*"`, `">=X"`, or `">=X,<Y"`. Anything
    else is treated as not matching, loudly enough (the pack simply
    does not load) that a curator notices."""
    if spec.strip() == "*":
        return True
    have = _version_tuple(installed)
    for part in spec.split(","):
        part = part.strip()
        if part.startswith(">="):
            if have < _version_tuple(part[2:]):
                return False
        elif part.startswith("<"):
            if have >= _version_tuple(part[1:]):
                return False
        else:
            return False
    return True


def _installed_version(package: str) -> "str | None":
    if package in ("math",):                  # stdlib: always present
        return "*"
    try:
        from importlib import metadata
        return metadata.version(package)
    except Exception:
        return None


def _read_pack(path: str) -> "CompendiumPack | None":
    import yaml
    try:
        data = yaml.safe_load(open(path)) or {}
    except Exception:
        return None
    package = data.get("package")
    if not package:
        return None
    versions = str(data.get("versions", "*"))
    installed = _installed_version(package)
    if installed is None:
        return None                            # not installed: no facts
    if installed != "*" and not _version_in_range(installed, versions):
        return None                            # stale compendium entry: no facts
    tag = (f"compendium:{package}" if installed == "*"
           else f"compendium:{package}-{'.'.join(installed.split('.')[:2])}")
    functions = {}
    for key, entry in (data.get("functions") or {}).items():
        if not isinstance(entry, dict):
            continue
        functions[key] = CompendiumFunction(
            key=key,
            params=tuple(entry.get("params") or ()),
            claims=tuple(entry.get("claims") or ()),
            raises_when=tuple(
                (r.get("condition"), r.get("exception", "ValueError"))
                for r in (entry.get("raises_when") or ())
                if isinstance(r, dict) and r.get("condition")),
            nan_when=tuple(entry.get("nan_when") or ()),
            limitations=tuple(entry.get("limitations") or ()),
            provenance=tag)
    return CompendiumPack(package=package, versions=versions, origin=path,
                    functions=functions)


def load_compendium_packs(root: str = ".") -> list:
    """Every applicable compendium pack: bundled first, then
    `.mathema/compendium/`, which wins per function key at consumption
    time (later packs shadow earlier ones). Each base directory is read
    two ways, so both layouts work: a flat `<package>.yaml` file, and a
    per-package SUBDIRECTORY `<package>/*.yaml` split by category (the
    bundled numpy/math packs use the directory form). Every file still
    declares its own `package` and `versions`, so the directory name is
    organisation, not authority."""
    bundled = os.path.dirname(__file__)
    dirs = [bundled, os.path.join(root, ".mathema", "compendium")]
    packs = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            full = os.path.join(d, name)
            if os.path.isdir(full):
                for inner in sorted(os.listdir(full)):
                    if inner.endswith((".yaml", ".yml")):
                        pack = _read_pack(os.path.join(full, inner))
                        if pack is not None:
                            packs.append(pack)
            elif name.endswith((".yaml", ".yml")):
                pack = _read_pack(full)
                if pack is not None:
                    packs.append(pack)
    return packs


def _covered_by_library(root: str = ".") -> dict:
    """`{root_library: {covered short function name, ...}}` from the
    compendium (`numpy` -> {`sqrt`, `log`, `arcsin`, `clip`})."""
    out: dict = {}
    for key in compendium_functions(root):
        lib, _, short = key.rpartition(".")
        out.setdefault(lib.split(".")[0], set()).add(short)
    return out


def _resolve_called_roots(fn, facts) -> list:
    """Every call `fn` makes, resolved to `(root_library, short_name)`
    through fn's import aliases, so `np.sqrt` reads as `("numpy", "sqrt")`
    and a bare `arcsin` from `from numpy import arcsin` as
    `("numpy", "arcsin")`. `root_library` is None for a local or builtin
    call. Aliases come from module-level globals AND the function's own
    local imports (a lazy `import numpy as np` inside the body binds np
    only locally, never in __globals__) AND from-imports."""
    import ast
    alias_root: dict = {}
    for alias, mod in (getattr(fn, "__globals__", {}) or {}).items():
        name = getattr(mod, "__name__", "") or ""
        if name:
            alias_root[alias] = name.split(".")[0]
    tree = getattr(facts, "tree", None)
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    alias_root[a.asname or a.name.split(".")[0]] = \
                        a.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    alias_root.setdefault(a.asname or a.name,
                                          node.module.split(".")[0])
    called: set = set()
    for group in (getattr(facts, "call_groups", None) or {}).values():
        called.update(group)
    out: list = []
    for name in called:
        alias, dot, attr = name.rpartition(".")
        if dot:                                   # a dotted call, np.arcsin
            out.append((alias_root.get(alias), attr))
        else:                                     # a bare call, arcsin
            out.append((alias_root.get(name), name))
    return out


def libraries_called(fn, facts, root: str = ".") -> set:
    """The set of libraries whose COMPENDIUM-COVERED functions `fn`
    calls, resolving import aliases through fn's own globals so
    `np.sqrt` counts as `numpy.sqrt`. This is what is_compendium_safe is
    suggested and adjudicated for: a function that never touches a
    covered library function has nothing to check."""
    import sys
    covered = _covered_by_library(root)
    if not covered:
        return set()
    stdlib: frozenset = getattr(sys, "stdlib_module_names", frozenset())
    libs: set = set()
    for rootlib, short in _resolve_called_roots(fn, facts):
        # stdlib (math) is is_builtin_safe's domain; is_compendium_safe
        # covers THIRD-PARTY libraries (numpy, ...) only.
        if rootlib and rootlib not in stdlib \
                and rootlib in covered and short in covered[rootlib]:
            libs.add(rootlib)
    return libs


def hazard_call_sites(fn, facts, root: str = ".") -> tuple:
    """`(covered, uncovered)` counts of `fn`'s calls into external
    (non-stdlib) libraries, split by whether a compendium exists for the
    library at all. A covered call is a REDUCIBLE hazard,
    `is_compendium_safe` samples the callee's known nan/raise regions and
    can clear it; an uncovered call is a black box, no model of where it
    fails exists, so nothing can clear it. The clarity metric charges the
    two differently for exactly this reason."""
    import sys
    stdlib: frozenset = getattr(sys, "stdlib_module_names", frozenset())
    covered_libs = set(_covered_by_library(root))
    covered = uncovered = 0
    for rootlib, _short in _resolve_called_roots(fn, facts):
        if not rootlib or rootlib in stdlib:
            continue                              # local, builtin, or stdlib
        if rootlib in covered_libs:
            covered += 1
        else:
            uncovered += 1
    return covered, uncovered


def compendium_functions(root: str = ".") -> dict:
    """Function key -> CompendiumFunction, project files shadowing bundled."""
    out: dict = {}
    for pack in load_compendium_packs(root):
        out.update(pack.functions)
    return out


def premise_names(root: str = ".") -> dict:
    """Backward wrapper over `external_premises`: name -> the hint
    entry's text, for callers that only render notes."""
    out = {}
    for name, info in external_premises(root).items():
        if isinstance(info, dict) and info.get("hint"):
            out[name] = info["hint"]
    return out


def external_premises(root: str = ".", verified: "dict | None" = None) -> dict:
    """Intent:
        Everything a claim's `assuming <name> holds` may rest on
        OUTSIDE its own batch, resolved to data (adjudication itself
        never reads a file). Keys are both spellings: the dotted
        qualified reference (`numpy.clip.clip_lower`) for any verified
        row anywhere, and the bare claim name for COMPENDIUM-ORIGIN rows
        only, so a typo'd sibling reference can never silently borrow
        an unrelated function's claim.

    Notes:
        Entry shapes: {"verdict", "provenance", "key"} satisfies a
        premise at that level; {"ambiguous": [keys]} refuses a bare
        name two compendium entries share; {"hint": text, "key", "row", "claimed"}
        is a compendium row not yet accepted or reverified, which satisfies
        nothing and explains itself.
    """
    out: dict = {}
    if verified is None:
        from ..spec import load_verified
        try:
            verified = load_verified(root)
        except Exception:
            verified = {}

    def put_bare(name: str, entry: dict) -> None:
        prior = out.get(name)
        if prior is None:
            out[name] = entry
        elif prior.get("key") != entry.get("key"):
            keys = sorted(set(
                (prior.get("ambiguous") or [prior.get("key")])
                + [entry.get("key")]))
            out[name] = {"ambiguous": keys}

    # verified rows: dotted always; bare only for compendium-origin rows
    for key, info in (verified or {}).items():
        entry = info.get("entry") if isinstance(info, dict) else info
        for row in (entry or {}).get("claims") or []:
            name, verdict = row.get("name"), row.get("verdict")
            if not name or not verdict:
                continue
            meta = row.get("meta") or {}
            comp_tag = meta.get("mathema.compendium")
            if verdict == "declared":
                if comp_tag:
                    hint = {"hint": _compendium_hint(comp_tag, name, key),
                            "key": key,
                            "claimed": meta.get("mathema.compendium_claimed",
                                                "holds")}
                    out.setdefault(f"{key}.{name}", hint)
                    if meta.get("mathema.surface") == "compendium":
                        put_bare(name, dict(hint))
                continue
            resolved = {"verdict": verdict, "key": key,
                        "provenance": (f"{comp_tag}/{name}" if comp_tag
                                       else f"{key}/{name}")}
            out[f"{key}.{name}"] = resolved
            if meta.get("mathema.surface") == "compendium":
                put_bare(name, dict(resolved))

    # compendium rows not materialised yet: hints under both spellings
    for key, sf in compendium_functions(root).items():
        for c in sf.claims:
            name = c.get("name")
            if not name:
                continue
            hint = {"hint": _compendium_hint(sf.provenance, name, key),
                    "key": key, "row": dict(c),
                    "claimed": c.get("verdict", "holds"),
                    "compendium": sf.provenance}
            out.setdefault(f"{key}.{name}", hint)
            put_bare(name, dict(hint))
    return out


def _compendium_hint(tag: str, name: str, key: str) -> str:
    return (f"{tag} declares {name!r} for {key}; a compendium verdict is "
            f"never trusted silently: accept it "
            f"(mathema accept {key} {name} --as trusted) or let "
            f"mathema verify re-adjudicate it against the installed "
            f"library")


def _condition_builder(condition: str, params: tuple):
    """The entry's condition text as the callable shape the partiality
    registry takes: sympy symbols named by the entry's own params,
    substituted with the call's lifted arguments."""
    import sympy
    syms = sympy.symbols(" ".join(params), real=True) if params else ()
    if not isinstance(syms, tuple):
        syms = (syms,)
    cond = sympy.sympify(condition, {s.name: s for s in syms})

    def build(*args):
        return cond.subs(dict(zip(syms, args)), simultaneous=True)
    return build


_INSTALLED_FOR: set = set()


def install(root: str = ".") -> None:
    """Register every applicable compendium entry's automatic facts, once per
    root per process: raise regions into the partiality registry, and
    the boundary-hazard generator. Called by the joins (`verify`,
    `write_spec`, the CLI and MCP surfaces), never by `check()`
    itself, which stays IO-free."""
    marker = os.path.abspath(root)
    if marker in _INSTALLED_FOR:
        return
    _INSTALLED_FOR.add(marker)
    from ..lemmas import register_raises_when
    functions = compendium_functions(root)
    for key, sf in functions.items():
        for condition, exc in sf.raises_when:
            try:
                register_raises_when(
                    key, _condition_builder(condition, sf.params), exc)
            except Exception:
                continue
    from ..hazards import register_hazard_generator
    register_hazard_generator(
        "compendium", _boundary_generator(functions))


def _boundaries(condition: str) -> list:
    """The numeric boundary values of a single-variable condition of
    the supported light shapes (`x < c`, `x <= c`, `abs(x) > c`, and
    their mirrors); [] for anything richer."""
    import sympy
    try:
        rel = sympy.sympify(condition)
    except Exception:
        return []
    if not isinstance(rel, sympy.core.relational.Relational):
        return []
    diff = rel.lhs - rel.rhs
    free = list(diff.free_symbols)
    if len(free) != 1:
        return []
    try:
        roots = sympy.solve(sympy.Eq(diff, 0), free[0])
    except Exception:
        return []
    out = []
    for r in roots:
        try:
            out.append(float(r))
        except Exception:
            continue
    return out


def _boundary_generator(functions: dict):
    """Hazard points for callers of covered functions: each covered
    region's boundary value, offered on every numeric parameter of
    the caller. Coarse on purpose (the covered call's argument is often an
    expression over the caller's parameters, not one of them), and a
    wrong hint costs one sample."""
    def generate(fn, facts, domain):
        from ..hazards import HazardPoint
        called = set()
        for group in (getattr(facts, "call_groups", None) or {}).values():
            called.update(group)
        out = []
        for key, sf in functions.items():
            short = key.rsplit(".", 1)[-1]
            if key not in called and short not in called:
                continue
            regions = list(sf.nan_when) + [c for c, _ in sf.raises_when]
            for condition in regions:
                for value in _boundaries(condition):
                    for param in getattr(facts, "params", ()):
                        out.append(HazardPoint(
                            kind="compendium", param=param,
                            at=f"{key}: boundary of ({condition})",
                            value=value, source=sf.provenance))
        return out
    return generate


_PREMISE_REF = None


def _referenced_names(claims: list) -> set:
    """Every `assuming <name> holds / is proven` reference in a list
    of declared claim dicts, by cheap text scan (materialisation is a
    convenience; the adjudicator's own parse stays authoritative)."""
    import re
    global _PREMISE_REF
    if _PREMISE_REF is None:
        _PREMISE_REF = re.compile(
            r"assuming\s+([A-Za-z_]\w*(?:\.\w+)*(?:\s+and\s+"
            r"[A-Za-z_]\w*(?:\.\w+)*)*)\s+(?:is\s+proven|holds)")
    out: set = set()
    for c in claims or []:
        if isinstance(c, dict):
            text = c.get("statement") or c.get("law") or ""
        else:
            # a parsed Conjecture: the premise lives in `assuming`
            text = getattr(c, "assuming", "") or ""
        for m in _PREMISE_REF.finditer(text):
            for part in m.group(1).split(" and "):
                out.add(part.strip())
    return out


def materialize_referenced_entries(root: str, claims: list,
                                 premises: dict) -> bool:
    """Intent:
        Every compendium row a batch's premises reference, written into the
        verified store for its library key at verdict "declared":
        recorded, unestablished, addressable by the acceptance flow
        (`--as trusted`) and re-adjudicated by the ordinary sweep.
        Returns whether anything was written.

    Notes:
        Idempotent: a row already present under its key (declared,
        accepted, or reverified) is never rewritten.
    """
    import os

    from ..spec import verified_dir, write_yaml
    wrote = False
    for name in _referenced_names(claims):
        info = premises.get(name)
        if not (isinstance(info, dict) and info.get("row")):
            continue
        key, row, claimed = info["key"], info["row"], info["claimed"]
        path = os.path.join(verified_dir(root), f"{key}.yaml")
        import yaml
        entry: dict = {}
        if os.path.exists(path):
            entry = (yaml.safe_load(open(path)) or {}).get(key) or {}
        rows = entry.setdefault("claims", [])
        if any(r.get("name") == row.get("name") for r in rows):
            continue
        rows.append({
            "name": row.get("name"),
            "statement": row.get("statement"),
            "route": row.get("route", "best"),
            "verdict": "declared",
            "authored": "compendium",
            "meta": {"mathema.surface": "compendium",
                     "mathema.compendium": info.get("compendium", ""),
                     "mathema.compendium_claimed": claimed}})
        write_yaml(path, {key: entry},
                   header=f"library-compendium rows for {key}; declared until "
                          f"accepted as trusted or reverified by the sweep")
        wrote = True
    return wrote


def premise_state(claims: list, premises: dict) -> dict:
    """Intent:
        The freshness snapshot of a batch's EXTERNAL premises: every
        referenced name that resolves outside the batch, with the
        verdict and provenance it resolves to right now. A key whose
        snapshot moved (a compendium row accepted, a library row
        reverified) is stale even though its own code and claims are
        unchanged: the premise's status is part of what the record
        asserted.
    """
    out: dict = {}
    for name in sorted(_referenced_names(claims)):
        info = premises.get(name)
        if isinstance(info, dict) and info.get("verdict"):
            out[name] = f"{info.get('provenance', '')}={info['verdict']}"
        elif isinstance(info, dict) and (info.get("hint")
                                         or info.get("ambiguous")):
            out[name] = "unresolved"
    return out
