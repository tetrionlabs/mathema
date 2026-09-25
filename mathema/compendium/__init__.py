# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The compendium: claims about well-known libraries' functions.

A compendium file is an ordinary claims file whose keys are library
functions (`numpy.sqrt`) and which names the library and the version
range its claims apply to with two file-level fields:

    compendium: numpy
    versions: ">=1.24,<3"

    numpy.sqrt:
      intent: "Principal square root; nan for a negative input."
      claims:
        - name: is_defined
          statement: "x >= 0"

mathema bundles such files for `math` and `numpy` beside this module;
a project states its own wherever its ordinary claims files live
(`claims/numpy.claims.yaml`), and a project file shadows a bundled one
per function key. A file applies only when the library is importable
and its installed version is inside `versions` (`"*"`, `">=X"` or
`">=X,<Y"`; the standard library counts as `"*"`); otherwise it
contributes nothing, rather than stale facts.

Three consumption paths:

- Definedness regions (`is_defined` rows) feed the hazard generator:
  their boundary values become sampling hints for every numeric
  parameter of a function that calls a covered function.
- Rows are premises a caller's claim may rest on (`assuming
  numpy.clip.clip_lower holds, ...`). A compendium row is testimony
  until `mathema verify` adjudicates it against the installed library,
  or a person accepts it (`mathema accept <key> <name> --as trusted`);
  until then a premise resting on it stays `unknown` and its note
  names both paths.
- `mathema compendium export <library>` writes a library's own
  verified claims back out in this shape.
"""
from __future__ import annotations

import os
import sys


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


def valid_version_range(spec: str) -> bool:
    """Intent:
        Whether `spec` is a range `_version_in_range` reads: `"*"`,
        `">=X"`, `"<Y"` or `">=X,<Y"`, each version a dotted run of
        whole numbers.
    """
    import re
    text = spec.strip()
    if text == "*":
        return True
    parts = [p.strip() for p in text.split(",")]
    if len(parts) > 2:
        return False
    version = r"\d+(?:\.\d+){0,2}"
    return all(re.fullmatch(rf"(?:>=|<)\s*{version}", p) for p in parts)


def _installed_version(package: str) -> "str | None":
    stdlib: frozenset = getattr(sys, "stdlib_module_names", frozenset())
    if package in ("math",) or package in stdlib:   # stdlib: always present
        return "*"
    try:
        from importlib import metadata
        return metadata.version(package)
    except Exception:
        return None


def applicable_tag(library: str, versions: str = "*") -> "str | None":
    """Intent:
        The provenance tag a library claims file's rows carry
        (`compendium:numpy-2.2`, `compendium:math` for the standard
        library), or None when the file does not apply here: the
        library is not importable, or its installed version is outside
        `versions`.
    """
    installed = _installed_version(library)
    if installed is None:
        return None
    if installed == "*":
        return f"compendium:{library}"
    if not _version_in_range(installed, str(versions)):
        return None
    return f"compendium:{library}-{'.'.join(installed.split('.')[:2])}"


def _bundled_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _display_path(path: str, root: str) -> str:
    """A bundled file as `mathema/compendium/...`, a project file
    relative to the project root."""
    bundled = os.path.realpath(_bundled_dir())
    real = os.path.realpath(path)
    if real.startswith(bundled + os.sep):
        return os.path.join("mathema", "compendium",
                            os.path.relpath(real, bundled))
    return os.path.relpath(path, root)


def load_library_claims(root: "str | None" = ".") -> dict:
    """Intent:
        Every applicable library claim entry, keyed by dotted function
        (`numpy.sqrt`): `{"entry", "compendium", "versions", "source"}`,
        where `entry` is the claims-file entry with its rows stamped as
        compendium testimony, `compendium` the library, `versions` the
        range the file declares, and `source` the file it came from.
        `root=None` reads the bundled files only.

    Notes:
        The bundled files are read first, then the project tree
        (`root`), with the discovery `spec.load_declared` uses; only
        files declaring `compendium:` count, and only when the library
        is importable at a version inside the file's range. A later
        file shadows an earlier one per key, whole entry.

    Raises:
        spec.ClaimsFileError: a claims file that does not read.
    """
    from ..spec import (claims_file_paths, read_claims_file,
                        stamp_library_rows)
    bundled = _bundled_dir()
    paths = claims_file_paths(bundled)
    if root is not None:
        paths += claims_file_paths(root, exclude=(bundled,))
    out: dict = {}
    for path in paths:
        where = _display_path(path, root or ".")
        data = read_claims_file(path, where)
        if not data or "compendium" not in data:
            continue
        library = data.pop("compendium")
        versions = str(data.pop("versions", "*"))
        data.pop("grammar", None)
        tag = applicable_tag(library, versions)
        if tag is None:
            continue
        stamp_library_rows(data, tag)
        for key, entry in data.items():
            if isinstance(entry, dict):
                out[key] = {"entry": entry, "compendium": library,
                            "versions": versions, "source": where}
    return out


def compendium_functions(root: str = ".") -> dict:
    """Function key -> its applicable library claims entry, project
    files shadowing bundled ones."""
    return {key: info["entry"]
            for key, info in load_library_claims(root).items()}


def _covered_by_library(root: str = ".") -> dict:
    """`{root_library: {covered short function name, ...}}` from the
    applicable library claims files (`numpy` -> {`sqrt`, `inv`,
    `clip`, ...}); a key counts as covered whatever rows it states."""
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
    only locally, never in __globals__) AND from-imports. A chained
    call (`np.linalg.norm`) resolves through its first name."""
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
        alias, dot, _rest = name.partition(".")
        short = name.rsplit(".", 1)[-1]
        if dot:                                   # a dotted call, np.arcsin
            out.append((alias_root.get(alias), short))
        else:                                     # a bare call, arcsin
            out.append((alias_root.get(name), name))
    return out


def _alias_origins(fn, facts) -> dict:
    """Intent:
        Every name `fn` can reach a module or a module's function
        through, mapped to its dotted origin: module-level globals,
        names it closes over, the function's own local imports, and
        from-imports (`from
        numpy import arcsin` maps `arcsin` to `numpy.arcsin`).
    """
    import ast
    import types
    import inspect
    origin: dict = {}
    scope = dict(getattr(fn, "__globals__", {}) or {})
    try:
        scope.update(inspect.getclosurevars(fn).nonlocals)
    except (TypeError, ValueError):
        pass
    for name, obj in scope.items():
        if isinstance(obj, types.ModuleType):
            origin[name] = obj.__name__
        elif callable(obj):
            mod = getattr(obj, "__module__", None)
            short = getattr(obj, "__name__", None)
            if isinstance(mod, str) and isinstance(short, str):
                origin[name] = f"{mod}.{short}"
    tree = getattr(facts, "tree", None)
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        origin[a.asname] = a.name
                    else:
                        head = a.name.split(".")[0]
                        origin[head] = head
            elif isinstance(node, ast.ImportFrom) and node.module \
                    and not node.level:
                for a in node.names:
                    origin[a.asname or a.name] = f"{node.module}.{a.name}"
    return origin


def _resolve_called_keys(fn, facts) -> list:
    """Intent:
        Every call `fn` makes, as the dotted key it resolves to
        through fn's import aliases: `np.linalg.norm(v)` calls
        `numpy.linalg.norm`, a bare `arcsin` from `from numpy import
        arcsin` calls `numpy.arcsin`. A name no alias explains stays
        as written.

    Notes:
        The resolved key keeps the spelling the caller used past the
        module alias (`np.linalg.norm` is `numpy.linalg.norm`, never
        the defining module's `numpy.linalg._linalg.norm`), which is
        the spelling a compendium key uses.
    """
    origin = _alias_origins(fn, facts)
    out: list = []
    for group in (getattr(facts, "call_groups", None) or {}).values():
        for name in group:
            head, dot, rest = name.partition(".")
            base = origin.get(head)
            key = name if base is None else (
                f"{base}.{rest}" if dot else base)
            if key not in out:
                out.append(key)
    return out


def library_keys_called(fn, facts, root: str = ".",
                        library_claims: "dict | None" = None) -> set:
    """Intent:
        The library claim keys `fn` calls (`np.sqrt(x)` calls
        `numpy.sqrt`), resolved through its import aliases.
    """
    keys = set(library_claims if library_claims is not None
               else load_library_claims(root))
    return {key for key in _resolve_called_keys(fn, facts) if key in keys}


def libraries_called(fn, facts, root: str = ".") -> set:
    """The set of libraries whose COMPENDIUM-COVERED functions `fn`
    calls, resolving import aliases through fn's own globals so
    `np.sqrt` counts as `numpy.sqrt`. This is what is_compendium_safe is
    suggested and adjudicated for: a function that never touches a
    covered library function has nothing to check."""
    stdlib: frozenset = getattr(sys, "stdlib_module_names", frozenset())
    # stdlib (math) is is_builtin_safe's domain; is_compendium_safe
    # covers THIRD-PARTY libraries (numpy, ...) only
    return {key.split(".")[0] for key in library_keys_called(fn, facts, root)
            if key.split(".")[0] not in stdlib}


def hazard_call_sites(fn, facts, root: str = ".") -> tuple:
    """`(covered, uncovered)` counts of `fn`'s calls into external
    (non-stdlib) libraries, split by whether a compendium exists for the
    library at all. A covered call is a REDUCIBLE hazard,
    `is_compendium_safe` samples the callee's known nan/raise regions and
    can clear it; an uncovered call is a black box, no model of where it
    fails exists, so nothing can clear it. The clarity metric charges the
    two differently for exactly this reason."""
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


def is_library_record(entry: dict) -> bool:
    """Intent:
        Whether a verified record holds library claims only: every row
        a person or a claims file stated is compendium testimony, the
        rows mathema generates for every function (the built-in
        battery, `dependencies_current`) aside, and there is at least
        one.
    """
    stated = [r for r in (entry or {}).get("claims") or []
              if isinstance(r, dict)
              and (r.get("meta") or {}).get("mathema.surface")
              not in ("builtin", "mathema")]
    return bool(stated) and all(
        (r.get("meta") or {}).get("mathema.surface") == "compendium"
        for r in stated)


def premise_names(root: str = ".") -> dict:
    """Backward wrapper over `external_premises`: name -> the hint
    entry's text, for callers that only render notes."""
    out = {}
    for name, info in external_premises(root).items():
        if isinstance(info, dict) and info.get("hint"):
            out[name] = info["hint"]
    return out


#: verdicts that leave a compendium row unsettled here: never
#: adjudicated, or adjudicated without reaching a verdict
_UNSETTLED = ("declared", "unknown", "skipped")


def external_premises(root: str = ".", verified: "dict | None" = None,
                      library_claims: "dict | None" = None) -> dict:
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
        name two compendium entries share; {"hint": text, "key",
        "claimed"} is a compendium row not settled here (only stated in
        a library claims file, or verified without a verdict:
        declared, unknown, skipped), which satisfies nothing and
        explains itself.
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
            from_compendium = meta.get("mathema.surface") == "compendium"
            unsettled = str(verdict).split(":", 1)[0] in _UNSETTLED
            if unsettled and (comp_tag or from_compendium):
                hint = {"hint": _compendium_hint(
                            comp_tag or "a compendium", name, key, verdict),
                        "key": key,
                        "claimed": meta.get("mathema.compendium_claimed",
                                            "holds")}
                out[f"{key}.{name}"] = hint
                if from_compendium:
                    put_bare(name, dict(hint))
                continue
            if verdict == "declared":
                continue
            resolved = {"verdict": verdict, "key": key,
                        "provenance": (f"{comp_tag}/{name}" if comp_tag
                                       else f"{key}/{name}")}
            out[f"{key}.{name}"] = resolved
            if from_compendium:
                put_bare(name, dict(resolved))

    # library rows the verified store does not hold: hints, both spellings
    if library_claims is None:
        library_claims = load_library_claims(root)
    for key, info in library_claims.items():
        for c in info["entry"].get("claims") or []:
            name = c.get("name")
            if not name or f"{key}.{name}" in out:
                continue
            meta = c.get("meta") or {}
            tag = meta.get("mathema.compendium", "")
            hint = {"hint": _compendium_hint(tag, name, key),
                    "key": key,
                    "claimed": meta.get("mathema.compendium_claimed",
                                        "holds"),
                    "compendium": tag}
            out[f"{key}.{name}"] = hint
            put_bare(name, dict(hint))
    return out


def _compendium_hint(tag: str, name: str, key: str,
                     verdict: "str | None" = None) -> str:
    standing = (f"mathema verify recorded it {verdict} against the "
                f"installed library" if verdict and verdict != "declared"
                else "a compendium verdict is never trusted silently")
    return (f"{tag} declares {name!r} for {key}; {standing}: accept it "
            f"(mathema accept {key} {name} --as trusted) or let "
            f"mathema verify adjudicate it against the installed "
            f"library")


def _is_defined_region_texts(entry: dict) -> list:
    """Intent:
        Each `is_defined` restriction row's region as the relation
        texts it conjoins (`-1 <= x <= 1` reads as `["-1 <= x",
        "x <= 1"]`), parsed by the claim grammar.
    """
    from ..conjecture import InvalidConjecture, claim
    out: list = []
    for row in entry.get("claims") or []:
        if str(row.get("name", "")).split("[", 1)[0] != "is_defined":
            continue
        try:
            cj = claim(str(row.get("statement") or row.get("law") or ""),
                       name=row.get("name"))
        except (InvalidConjecture, ValueError):
            continue
        links = cj.links or [(cj.lhs, cj.relation, cj.rhs)]
        out.append([f"{lhs} {rel} {rhs}" for lhs, rel, rhs in links
                    if rhs])
    return out


#: what is registered: the root the library claims were installed for
#: (`BUNDLED` for the bundled layer alone, None for nothing), and the
#: `(key, builder)` rows it added to the partiality registry
_INSTALLED: dict = {"root": None, "rows": []}
#: the `_INSTALLED` root of the bundled layer alone
BUNDLED = "<bundled>"
#: the rows already reported as unbuildable, so each is reported once
_REPORTED: set = set()

#: region functions a row may read that are facts about an array's shape
#: or a matrix, not a scalar region over the call's arguments
_SHAPE_FUNCTIONS = ("dim", "det", "rows", "cols", "len")


class _Unbuildable(Exception):
    """A library row whose region cannot be stated over the call's
    scalar arguments; the message says why."""


def _signature_params(key: str, used: list) -> list:
    """Intent:
        The positional parameter names of the function `key` names, in
        call order (`inspect.signature`); when the function has no
        readable signature, the one name the row itself uses.

    Raises:
        _Unbuildable: no signature and not exactly one name in use.
    """
    import inspect

    from ..conjecture import _resolve_func_ref
    fn = _resolve_func_ref(key)
    try:
        sig = inspect.signature(fn) if fn is not None else None
    except (TypeError, ValueError):
        sig = None
    if sig is not None:
        return [n for n, p in sig.parameters.items()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if len(used) == 1:
        return list(used)
    raise _Unbuildable("the function has no readable signature to place "
                       "the row's parameters in call order")


def _side_to_sympy(text: str, env: dict):
    """One relation side as a sympy expression over `env`'s symbols,
    read the way the claim grammar reads it."""
    import ast
    import re

    from ..grammar import normalize
    from ..symbolic._base import NotSymbolic, _expr_to_sympy
    src = normalize(str(text))
    if re.search(rf"\b(?:{'|'.join(_SHAPE_FUNCTIONS)})\s*\(", src):
        raise _Unbuildable("shape")
    try:
        value = _expr_to_sympy(ast.parse(src, mode="eval").body, dict(env))
    except (NotSymbolic, SyntaxError) as e:
        raise _Unbuildable(f"{text!r} does not lift ({e})") from None
    if isinstance(value, tuple):
        raise _Unbuildable(f"{text!r} is not a single value")
    return value


def _relation(lhs: str, rel: str, rhs: str, env: dict):
    import sympy
    ops = {"<": sympy.Lt, "<=": sympy.Le, ">": sympy.Gt, ">=": sympy.Ge,
           "==": sympy.Eq, "!=": sympy.Ne}
    if rel not in ops:
        raise _Unbuildable(f"relation {rel!r} is not a region")
    return ops[rel](_side_to_sympy(lhs, env), _side_to_sympy(rhs, env))


def _row_region(key: str, row: dict) -> "tuple | None":
    """Intent:
        One library row as a partiality guard: `(parameter names in call
        order, region, label)`, where the region is where the call
        fails and the label is `NO_VALUE` for an `is_defined` row (the
        complement of its stated region) or the exception name of a
        `raises(f(...), Exc)` row (its `for` domain and `assuming`
        premise conjoined). None for a row that states no region.
        The statement is read by the claim grammar itself.

    Raises:
        _Unbuildable: the region cannot be stated over the call's
            scalar arguments (`"shape"` when it reads an array's shape
            or a matrix, otherwise the reason).
    """
    import sympy

    from ..conjecture import _parse_assuming_relation, claim
    from ..domain import bound_to_sympy_set
    from ..symbolic._partiality import NO_VALUE
    name = str(row.get("name") or "")
    text = str(row.get("statement") or row.get("law") or "")
    try:
        cj = claim(text, name=name or None)
    except Exception as e:
        raise _Unbuildable(f"the statement does not parse ({e})") from None
    if name.split("[", 1)[0] == "is_defined" and cj.relation != "raises":
        links = cj.links or [(cj.lhs, cj.relation, cj.rhs)]
        used = sorted({n for lhs, _r, rhs in links
                       for n in _names_in(f"{lhs} {rhs}")})
        params = _signature_params(key, used)
        env = {p: sympy.Symbol(p, real=True) for p in params}
        stray = [n for n in used if n not in env]
        if stray:
            raise _Unbuildable(f"{', '.join(stray)} is not a parameter of "
                               f"{key}")
        region = sympy.And(*[_relation(lhs, rel, rhs, env)
                             for lhs, rel, rhs in links])
        return params, sympy.Not(region).to_nnf(), NO_VALUE
    if cj.relation != "raises" or not cj.rhs:
        return None
    used = sorted(set(cj.domain) | set(_names_in(cj.assuming or ""))
                  | set(_names_in(cj.lhs)) - {"f"})
    params = _signature_params(key, used)
    env = {p: sympy.Symbol(p, real=True) for p in params}
    parts = []
    for p, bound in (cj.domain or {}).items():
        if p not in env:
            raise _Unbuildable(f"{p} is not a parameter of {key}")
        if getattr(bound, "dims", None):
            raise _Unbuildable("shape")
        parts.append(bound_to_sympy_set(bound).as_relational(env[p]))
    premise = (cj.assuming or "").strip()
    if premise.startswith("assuming"):
        premise = premise[len("assuming"):].strip()
    for conjunct in filter(None, (c.strip() for c in premise.split(" and "))):
        rel = _parse_assuming_relation(conjunct)
        if rel is None:
            raise _Unbuildable(f"premise {conjunct!r} is not a relation")
        parts.append(_relation(rel.lhs, rel.relation, rel.rhs, env))
    return params, sympy.And(*parts), str(cj.rhs).strip()


def _names_in(text: str) -> list:
    """The identifiers a relation text reads that are not calls."""
    import re
    return [m.group(1) for m in re.finditer(
        r"\b([A-Za-z_]\w*)\b(?!\s*\()", str(text))
        if m.group(1) not in ("and", "or", "not", "in", "for", "assuming",
                              "inf", "oo", "pi", "e", "E")]


def _builder(params: list, region):
    """The callable the partiality registry takes: the call's
    positional arguments (sympy expressions) substituted for the row's
    parameter symbols."""
    import sympy
    syms = [sympy.Symbol(p, real=True) for p in params]
    needed = {i for i, s in enumerate(syms) if s in region.free_symbols}

    def build(*args):
        if needed and max(needed) >= len(args):
            return sympy.false
        return region.subs({syms[i]: args[i] for i in needed},
                           simultaneous=True)
    return build


def register_library_claims(root: "str | None" = ".") -> list:
    """Intent:
        Register every applicable library row's region as a partiality
        guard (`load_library_claims`): an `is_defined` row registers
        the complement of its region as `NO_VALUE`, a `raises(f(...),
        Exc)` row its domain and premise as `Exc`. `root=None` registers
        the bundled files alone. Idempotent per root: the same root
        again is a no-op, a different root replaces the rows the
        previous one registered. Returns the `(key, row name)` pairs
        registered.

    Notes:
        A row that reads an array's shape or a matrix (`dim(a) >= 1`,
        `det(a) != 0`) states no scalar region and is left to the
        hazard generator; any other row whose region cannot be built is
        reported once with `warnings.warn`, naming the key and the row.
    """
    import warnings

    from ..symbolic._partiality import register_raises_when
    marker = BUNDLED if root is None else os.path.abspath(root)
    if _INSTALLED["root"] == marker:
        return list(_INSTALLED.get("names", []))
    uninstall()
    library_claims = load_library_claims(root)
    rows: list = []
    names: list = []
    for key, info in sorted(library_claims.items()):
        for row in info["entry"].get("claims") or []:
            try:
                built = _row_region(key, row)
            except _Unbuildable as e:
                reason = str(e)
                label = (key, str(row.get("name")), reason)
                if reason != "shape" and label not in _REPORTED:
                    _REPORTED.add(label)
                    warnings.warn(
                        f"mathema: compendium row {row.get('name')!r} of "
                        f"{key} ({info['source']}) registers no region: "
                        f"{reason}", stacklevel=2)
                continue
            if built is None:
                continue
            params, region, label_text = built
            build = _builder(params, region)
            register_raises_when(key, build, label_text)
            rows.append((key, build))
            names.append((key, str(row.get("name"))))
    _INSTALLED.update(root=marker, rows=rows, names=names)
    from ..hazards import register_hazard_generator
    register_hazard_generator("compendium",
                              _boundary_generator(library_claims))
    return names


def install(root: str = ".") -> None:
    """Register the applicable library claims' automatic facts for
    `root`, the bundled files with the project's own on top:
    partiality guards (`register_library_claims`) and the
    boundary-hazard generator. Called by the joins (`verify`,
    `write_spec`, `mathema check`, the MCP surfaces); `check()` itself
    reads no project file and applies the bundled layer alone
    (`ensure_bundled`)."""
    register_library_claims(root)


def ensure_bundled() -> None:
    """Intent:
        Register the bundled library claims when no library claims are
        registered, so every adjudication knows what mathema ships about
        `math` and `numpy`; a project layer installed by `install(root)`
        already contains them and is left as it is. Reads only files
        inside the mathema package.
    """
    if _INSTALLED["root"] is None:
        register_library_claims(None)


def uninstall(root: "str | None" = None) -> None:
    """Remove what `install` registered (for `root`, when given and it
    is the installed one; otherwise whatever is installed)."""
    from ..symbolic._partiality import unregister_lemmas
    if root is not None and _INSTALLED["root"] != os.path.abspath(root):
        return
    for key, build in _INSTALLED["rows"]:
        unregister_lemmas(key, [build])
    _INSTALLED.update(root=None, rows=[], names=[])
    from ..hazards import _GENERATORS
    _GENERATORS.pop("compendium", None)


def _boundaries(condition) -> list:
    """Intent:
        The numeric boundary values of a single-variable relation (a
        sympy relation, or its text), solved over a real variable
        under the fast wall-clock cap: `x < c` gives `c`, `abs(x) > 1`
        gives `-1` and `1`; [] for anything richer or unsolved.
    """
    import sympy

    from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    try:
        rel = (sympy.sympify(condition) if isinstance(condition, str)
               else condition)
    except Exception:
        return []
    if not isinstance(rel, sympy.core.relational.Relational):
        return []
    diff = rel.lhs - rel.rhs
    free = list(diff.free_symbols)
    if len(free) != 1:
        return []
    var = sympy.Symbol(free[0].name, real=True)
    diff = diff.subs(free[0], var)
    try:
        roots = _with_timeout(lambda: sympy.solve(sympy.Eq(diff, 0), var),
                              FAST_TIMEOUT_SECONDS)
    except Exception:
        return []
    out = []
    for r in roots:
        try:
            out.append(float(r))
        except Exception:
            continue
    return sorted(out)


def _boundary_generator(library_claims: dict):
    """Hazard points for callers of covered functions: each covered
    region's boundary value, offered on every numeric parameter of
    the caller. Coarse on purpose (the covered call's argument is often an
    expression over the caller's parameters, not one of them), and a
    wrong hint costs one sample."""
    def generate(fn, facts, domain):
        import re

        from ..hazards import HazardPoint
        out = []
        for key in sorted(library_keys_called(
                fn, facts, library_claims=library_claims)):
            info = library_claims[key]
            source = next(
                ((r.get("meta") or {}).get("mathema.compendium")
                 for r in info["entry"].get("claims") or []
                 if (r.get("meta") or {}).get("mathema.compendium")),
                f"compendium:{info['compendium']}")
            for region in _is_defined_region_texts(info["entry"]):
                for condition in region:
                    if re.search(r"\bdim\s*\(", condition):
                        # outside `dim(a) >= 1` is the empty sequence
                        for param in getattr(facts, "params", ()):
                            if (getattr(facts, "param_kinds", None) or {}
                                    ).get(param) == "sequence":
                                out.append(HazardPoint(
                                    kind="compendium", param=param,
                                    at=f"{key}: empty sequence, outside "
                                       f"({condition})",
                                    value=None, source=source))
                        continue
                    for value in _boundaries(condition):
                        for param in getattr(facts, "params", ()):
                            out.append(HazardPoint(
                                kind="compendium", param=param,
                                at=f"{key}: boundary of ({condition})",
                                value=value, source=source))
        return out
    return generate


_PREMISE_REF = None


def _referenced_names(claims: list) -> set:
    """Every `assuming <name> holds / is proven` reference in a list
    of declared claim dicts or parsed Conjectures, by cheap text scan
    (the adjudicator's own parse stays authoritative)."""
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
