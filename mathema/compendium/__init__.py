# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The compendium: claims about well-known libraries' functions.

A compendium file is an ordinary claims file whose keys are library
functions (`numpy.sqrt`) and which names the library and the version
range its claims apply to with two file-level fields:

    compendium: numpy
    versions: ">=1.24,<3"

    numpy.sqrt:
      claims:
        - name: is_defined
          statement: "x >= 0"
          note: "Principal square root; nan for a negative input."

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

from .._signatures import module_scope
import os
import sys
from typing import NamedTuple

from ..runtime_types import SEQUENCE_KINDS
from .._signatures import callable_signature


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


def _installed_version(package: str,
                       aliases: "tuple | list" = ()) -> "str | None":
    """Intent:
        The installed version of the library `package` names, `"*"` for
        the standard library, or None when it is not installed. Tried
        as a distribution name first, then each of `aliases` (a file's
        `aliases:`, such as `PyYAML` for `yaml`), then through the
        distributions `importlib.metadata.packages_distributions`
        reports for each of those names as an import name.
    """
    stdlib: frozenset = getattr(sys, "stdlib_module_names", frozenset())
    if package in ("math",) or package in stdlib:   # stdlib: always present
        return "*"
    asked = (package, tuple(aliases))
    if asked not in _VERSIONS:
        _VERSIONS[asked] = _distribution_version(package, aliases)
    return _VERSIONS[asked]


#: installed versions already looked up in this process, by the
#: `(package, aliases)` asked about
_VERSIONS: dict = {}


def _distribution_version(package: str, aliases) -> "str | None":
    """The installed version `_installed_version` reports for a library
    outside the standard library, looked up afresh."""
    from importlib import metadata
    names = [package, *[a for a in aliases if a != package]]
    for name in names:
        try:
            return metadata.version(name)
        except Exception:
            continue
    provided = _packages_distributions()
    if provided is None:
        return None
    for name in names:
        for dist in provided.get(name) or []:
            try:
                return metadata.version(dist)
            except Exception:
                continue
    return None


#: `importlib.metadata.packages_distributions()`, read once per process
#: (it walks every installed distribution's file list)
_PROVIDED: dict = {}


def _packages_distributions() -> "dict | None":
    """The import-name to distributions map of the installed packages,
    read once per process; None when it cannot be read."""
    if "map" not in _PROVIDED:
        from importlib import metadata
        try:
            _PROVIDED["map"] = metadata.packages_distributions()
        except Exception:
            _PROVIDED["map"] = None
    return _PROVIDED["map"]


def applicable_tag(library: str, versions: str = "*",
                   aliases: "tuple | list" = ()) -> "str | None":
    """Intent:
        The provenance tag a library claims file's rows carry
        (`compendium:numpy-2.2`, `compendium:math` for the standard
        library), or None when the file does not apply here: the
        library is not installed under its name or any of `aliases`,
        or its installed version is outside `versions`.
    """
    installed = _installed_version(library, aliases)
    if installed is None:
        return None
    if installed == "*":
        return f"compendium:{library}"
    if not _version_in_range(installed, str(versions)):
        return None
    return f"compendium:{library}-{'.'.join(installed.split('.')[:2])}"


class LibraryFields(NamedTuple):
    """The file-level fields of a compendium file: the library it is
    about (None for an ordinary claims file), the version range, and the
    other names the library goes by."""
    library: "str | None"
    versions: str
    aliases: tuple


def alias_key(key: str, library: str, aliases: "tuple | list") -> str:
    """Intent:
        `key` spelled under the library's own name: a key written under
        an alias prefix (`np.cbrt` with alias `np` of `numpy`) becomes
        the library's key (`numpy.cbrt`); any other key is unchanged.
    """
    for alias in aliases:
        if key == alias or key.startswith(alias + "."):
            return library + key[len(alias):]
    return key


#: the meta key marking a row whose own `versions:` range excludes the
#: installed library: adjudicated like any row, never used as a fact
OUTSIDE_VERSIONS = "mathema.outside_versions"


def mark_row_versions(data: dict, library: str,
                      aliases: "tuple | list" = ()) -> None:
    """Intent:
        Apply each row's own `versions:` range (it overrides the
        file's for that row): a row whose range excludes the installed
        library is marked with `OUTSIDE_VERSIONS` in its meta, naming
        the range. Such a row is still adjudicated when the project
        uses its function, and is never used as a fact (a derive guard,
        a sampling hint, a computation region).
    """
    installed = _installed_version(library, aliases)
    if installed is None or installed == "*":
        return
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        for row in entry.get("claims") or []:
            spec = row.get("versions") if isinstance(row, dict) else None
            if spec is None or _version_in_range(installed, str(spec)):
                continue
            row["meta"] = {**(row.get("meta") or {}),
                           OUTSIDE_VERSIONS: str(spec)}


def row_pins(row: dict) -> dict:
    """Intent:
        The library parameters a row pins, `{parameter: value}`: each
        `let p be None/True/False` binding, and each `let p be <number>`
        whose name the statement never reads (`let axis be 1, dim(a) >=
        1`); a keyword argument of the same name (`std(a, ddof=1)`) is
        not a read. {} for a row that pins nothing or does not parse.
    """
    import re

    from ..conjecture import _single_point, claim
    try:
        cj = claim(str(row.get("statement") or row.get("law") or ""),
                   name=row.get("name"))
    except Exception:
        return {}
    pins = dict(getattr(cj, "param_pins", None) or {})
    text = " ".join(str(t) for t in (cj.lhs, cj.rhs, cj.assuming) if t)
    # a name followed by a single `=` is a keyword argument of a grammar
    # word (`std(a, ddof=1)`), not a read of that name
    named = set(re.findall(r"\b([A-Za-z_]\w*)\b(?!\s*=(?!=))", text))
    for name in sorted(cj.free_vars or ()):
        point = _single_point((cj.domain or {}).get(name))
        if point is not None and name not in named:
            pins[name] = (int(point) if isinstance(point, float)
                          and point.is_integer() else point)
    return pins


def row_is_fact(row: dict) -> bool:
    """Intent:
        Whether a library row states a fact about every call of its
        function: not outside its own `versions:` range, and not
        pinned to particular arguments (a pinned row speaks for the
        calls that pass them, so it is adjudicated but never registered
        as a region).
    """
    if (row.get("meta") or {}).get(OUTSIDE_VERSIONS):
        return False
    return not row_pins(row)


def pop_library_fields(data: dict) -> LibraryFields:
    """Intent:
        Remove the file-level `compendium`, `versions` and `aliases`
        fields from a parsed claims file and return them, re-keying a
        compendium file's entries written under an alias prefix to the
        library's own key (`alias_key`). An ordinary claims file keeps
        its keys.
    """
    library = data.pop("compendium", None)
    versions = str(data.pop("versions", "*"))
    aliases = tuple(str(a) for a in (data.pop("aliases", None) or ()))
    if library is not None and aliases:
        for key in list(data):
            renamed = alias_key(key, str(library), aliases)
            if renamed != key:
                data[renamed] = data.pop(key)
    return LibraryFields(library, versions, aliases)


def own_packages(root: str = ".") -> frozenset:
    """Intent:
        The top-level packages a project tree is the source of: every
        directory directly under `root` (or `root/src`) holding an
        `__init__.py`, and the distribution name its `pyproject.toml`
        declares, with `-` read as `_`.
    """
    import re
    names: set = set()
    for base in (root, os.path.join(root, "src")):
        try:
            entries = os.listdir(base)
        except OSError:
            continue
        for entry in entries:
            if entry.isidentifier() and os.path.isfile(
                    os.path.join(base, entry, "__init__.py")):
                names.add(entry)
    try:
        with open(os.path.join(root, "pyproject.toml"),
                  encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    section = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", text,
                        re.MULTILINE | re.DOTALL)
    if section:
        name = re.search(r"^name\s*=\s*[\"']([^\"']+)[\"']",
                         section.group(1), re.MULTILINE)
        if name:
            names.add(name.group(1).strip().replace("-", "_").lower())
    return frozenset(names)


def names_own_package(library: str, root: str = ".") -> bool:
    """Intent:
        Whether a claims file's `compendium: <library>` names the
        project's own package (`own_packages`): such a file states the
        project's own claims, not testimony about a library, and
        contributes nothing as a compendium file.
    """
    head = str(library).split(".")[0]
    return head in own_packages(root) or \
        head.replace("-", "_").lower() in own_packages(root)


def own_package_compendium_files(root: str = ".") -> list:
    """Intent:
        The project claims files ignored because their `compendium:`
        names the project's own package, as `(path relative to root,
        library)` pairs.
    """
    from ..spec import claims_file_paths, read_claims_file
    own = own_packages(root)
    if not own:
        return []
    out: list = []
    for path in claims_file_paths(root, exclude=(_bundled_dir(),)):
        where = os.path.relpath(path, root)
        try:
            data = read_claims_file(path, where)
        except Exception:
            continue
        library = (data or {}).get("compendium")
        if isinstance(library, str) and names_own_package(library, root):
            out.append((where, library))
    return out


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
        (`numpy.sqrt`): `{"entry", "compendium", "versions", "source",
        "bundled"}`, where `entry` is the claims-file entry with its rows
        stamped as compendium testimony, `compendium` the library,
        `versions` the range the file declares, `source` the file it
        came from, and `bundled` whether that file ships with mathema.
        `root=None` reads the bundled files only.

    Notes:
        The bundled files are read first, then the project tree
        (`root`), with the discovery `spec.load_declared` uses; only
        files declaring `compendium:` count, and only when the library
        is importable at a version inside the file's range. A project
        file naming the project's own package (`names_own_package`)
        does not count. A later file shadows an earlier one per key,
        whole entry.

    Raises:
        spec.ClaimsFileError: a claims file that does not read.
    """
    from ..spec import (claims_file_paths, read_claims_file,
                        stamp_library_rows)
    bundled = _bundled_dir()
    paths = claims_file_paths(bundled)
    shipped = set(paths)
    if root is not None:
        paths += claims_file_paths(root, exclude=(bundled,))
    out: dict = {}
    for path in paths:
        where = _display_path(path, root or ".")
        data = read_claims_file(path, where)
        if not data or "compendium" not in data:
            continue
        library, versions, aliases = pop_library_fields(data)
        if path not in shipped and names_own_package(library, root or "."):
            # the project's own package: its claims, not a library's
            continue
        data.pop("grammar", None)
        tag = applicable_tag(library, versions, aliases)
        if tag is None:
            continue
        stamp_library_rows(data, tag)
        mark_row_versions(data, library, aliases)
        for key, entry in data.items():
            if isinstance(entry, dict) and not (entry.get("defines")
                                                and not entry.get("claims")):
                # a key that only defines its runtime's missing values
                # (`defines:`) has no function claims to register
                out[key] = {"entry": entry, "compendium": library,
                            "versions": versions, "source": where,
                            "bundled": path in shipped}
    return out


def compendium_functions(root: str = ".") -> dict:
    """Function key -> its applicable library claims entry, project
    files shadowing bundled ones."""
    return {key: info["entry"]
            for key, info in load_library_claims(root).items()}


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
    scope = dict(module_scope(fn))
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
            elif isinstance(node, ast.ImportFrom) and node.level:
                base = _relative_base(fn, node.level)
                if base is None:
                    continue
                module = f"{base}.{node.module}" if node.module else base
                for a in node.names:
                    origin[a.asname or a.name] = f"{module}.{a.name}"
    return origin


def _relative_base(fn, level: int) -> "str | None":
    """The package a relative import `level` dots deep resolves against
    inside `fn`'s module, or None when it cannot be told."""
    package = module_scope(fn).get("__package__")
    if not isinstance(package, str) or not package:
        return None
    parts = package.split(".")
    if level - 1 >= len(parts):
        return None
    return ".".join(parts[:len(parts) - (level - 1)])


def resolved_calls(fn, facts) -> list:
    """Intent:
        Every call `fn` makes whose name resolves through a name `fn`
        reaches (an import alias, a module-level function, a closure
        variable, a local or relative import), as the dotted key it
        calls, once each in first-seen order: `np.sqrt(x)` calls
        `numpy.sqrt`, a same-module helper `pkg.mod.helper`. A builtin,
        a method on a local value and any other name no alias explains
        are left out.
    """
    origin = _alias_origins(fn, facts)
    out: list = []
    for group in (getattr(facts, "call_groups", None) or {}).values():
        for name in group:
            head, dot, rest = name.partition(".")
            base = origin.get(head)
            if base is None:
                continue
            key = f"{base}.{rest}" if dot else base
            if key not in out:
                out.append(key)
    return out


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


def _region_texts(entry: dict, families) -> list:
    """Intent:
        Each restriction row of one of `families` (`is_defined`,
        `is_overflow_safe`) in `entry`, as the relation texts its
        region conjoins (`-1 <= x <= 1` reads as `["-1 <= x", "x <=
        1"]`), parsed by the claim grammar. A bare row
        (`is_defined(f)`) states no region and contributes nothing.
    """
    from ..conjecture import InvalidConjecture, claim, region_row_kind
    out: list = []
    for row in entry.get("claims") or []:
        kind = region_row_kind(row.get("name", ""))
        if kind is None or kind not in families or not row_is_fact(row):
            continue
        try:
            cj = claim(str(row.get("statement") or row.get("law") or ""),
                       name=row.get("name"))
        except (InvalidConjecture, ValueError):
            continue
        if cj.relation == kind:
            continue
        links = cj.links or [(cj.lhs, cj.relation, cj.rhs)]
        out.append([f"{lhs} {rel} {rhs}" for lhs, rel, rhs in links
                    if rhs])
    return out


def _is_defined_region_texts(entry: dict) -> list:
    """The `is_defined` restriction rows' regions, see `_region_texts`."""
    return _region_texts(entry, ("is_defined",))


#: what is registered: the root the library claims were installed for
#: (`BUNDLED` for the bundled layer alone, None for nothing), and the
#: `(key, builder)` rows it added to the partiality registry
_INSTALLED: dict = {"root": None, "rows": []}
#: the computation stratum of the registered library claims (P9): per
#: key, the rows that state a fact about the computation rather than the
#: mathematics, each `{"family", "name", "params", "region", "texts",
#: "exception", "source"}`. For a computation-safety family in
#: restriction form (`is_overflow_safe`) `region` is where the
#: computation is safe in that respect and `exception` is None; for a
#: `raises` row whose type is a machine failure, `family` is "raises",
#: `region` is where the call raises and `exception` names the type.
#: Read by the hazard generator, `is_compendium_safe`'s diagnosis, the
#: `is_defined` probe's reach on a library key and the float companion's
#: sketch; never by the derive route.
_COMPUTATION: dict = {}
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
    from ..conjecture import _resolve_func_ref
    fn = _resolve_func_ref(key)
    try:
        sig = callable_signature(fn) if fn is not None else None
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


class _RowRegion(NamedTuple):
    """One library row's region, typed by stratum (P9). `params` are the
    call's parameter names in call order and `texts` the relation texts
    the row conjoins. On the mathematics stratum `region` is where the
    call FAILS and `label` is `NO_VALUE` (an `is_defined` row, the
    complement of its stated region) or the exception name of a
    `raises` row. On the computation stratum `label` is the family name
    and `region` the stated region where the computation is safe in
    that respect (`is_overflow_safe`), or the exception name and the
    region where the call raises it (a machine-failure `raises` row).
    `applies_to` names the arguments the region speaks for: `"real"`
    for a region stated with an ordering (`x >= 0` has no complex
    reading), `"complex"` for a row over C (`for x in C \\ {0},
    is_defined(f)`), `"all"` otherwise (`x2 != 0`)."""
    params: list
    region: object
    label: str
    stratum: str
    texts: list
    applies_to: str = "all"


def _machine_failure_types() -> frozenset:
    """The exception names whose raise is the machine giving out rather
    than the mathematics or the author's contract: the types
    `conjecture._MACHINE_FAILURE_CAUSES` classifies, and numpy's
    FloatingPointError."""
    from ..conjecture import _MACHINE_FAILURE_CAUSES
    return frozenset(t.__name__ for t in _MACHINE_FAILURE_CAUSES) | {
        "FloatingPointError"}


def _row_region(key: str, row: dict) -> "_RowRegion | None":
    """Intent:
        One library row's region, typed by stratum: a `_RowRegion` (see
        there), or None for a row that states no region (a value claim,
        the bare `is_defined(f)`). An `is_defined` restriction row and a
        `raises(f(...), Exc)` row with an ordinary type are mathematics
        (a partiality guard); a computation-safety family in
        restriction form (`is_overflow_safe`) and a `raises` row whose
        type is a machine failure (OverflowError, MemoryError,
        RecursionError, FloatingPointError) are computation. The
        statement is read by the claim grammar itself.

    Raises:
        _Unbuildable: the region cannot be stated over the call's
            scalar arguments (`"shape"` when it reads an array's shape
            or a matrix, otherwise the reason).
    """
    import sympy

    from ..conjecture import (REGION_ROW_STRATA, _parse_assuming_relation,
                              claim, region_row_kind)
    from ..domain import bound_to_sympy_set
    from ..symbolic._partiality import NO_VALUE
    name = str(row.get("name") or "")
    text = str(row.get("statement") or row.get("law") or "")
    try:
        cj = claim(text, name=name or None)
    except Exception as e:
        raise _Unbuildable(f"the statement does not parse ({e})") from None
    kind = region_row_kind(name)
    if cj.relation == "is_defined":
        # the bare form (`is_defined(f)`): totality over its domain.
        # Over C less some points, those points have no value at a
        # complex argument; anything else states no region
        return _complex_row_region(key, cj)
    if kind is not None and cj.relation == kind:
        return None
    if kind is not None and cj.relation != "raises":
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
        texts = [f"{lhs} {rel} {rhs}" for lhs, rel, rhs in links]
        if REGION_ROW_STRATA[kind] == "computation":
            return _RowRegion(params, region, kind, "computation", texts)
        ordering = any(rel in ("<", "<=", ">", ">=") for _l, rel, _r in links)
        return _RowRegion(params, sympy.Not(region).to_nnf(), NO_VALUE,
                          "mathematics", texts,
                          "real" if ordering else "all")
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
    exc_name = str(cj.rhs).strip()
    stratum = ("computation"
               if exc_name.rsplit(".", 1)[-1] in _machine_failure_types()
               else "mathematics")
    texts = [str(rel) for rel in parts]
    return _RowRegion(params, sympy.And(*parts), exc_name, stratum, texts)


def _complex_row_region(key: str, cj) -> "_RowRegion | None":
    """Intent:
        The region a bare `is_defined(f)` row over C states: the points
        its domain excludes (`for x in C \\ {0}, is_defined(f)`), where
        the call has no value at a complex argument, as a mathematics
        guard that applies to complex arguments only. None for a row
        whose domain binds nothing in C or excludes nothing.
    """
    import sympy

    from ..symbolic._partiality import NO_VALUE
    parts = []
    names = []
    for p, bound in (cj.domain or {}).items():
        if getattr(bound, "base_type", None) != "C" and bound != "C":
            continue
        excluded = sorted((v for v in getattr(bound, "excluded", ())
                           if isinstance(v, (int, float, complex))
                           and not isinstance(v, bool)),
                          key=lambda v: (complex(v).real, complex(v).imag))
        if excluded:
            names.append(p)
            parts.append((p, excluded))
    if not parts:
        return None
    params = _signature_params(key, names)
    env = {p: sympy.Symbol(p, real=True) for p in params}
    stray = [p for p in names if p not in env]
    if stray:
        raise _Unbuildable(f"{', '.join(stray)} is not a parameter of {key}")
    region = sympy.Or(*[sympy.Eq(env[p], sympy.sympify(v))
                        for p, excluded in parts for v in excluded])
    texts = [f"{p} != {v}" for p, excluded in parts for v in excluded]
    return _RowRegion(params, region, NO_VALUE, "mathematics", texts,
                      "complex")


def _names_in(text: str) -> list:
    """The identifiers a relation text reads that are not calls."""
    import re
    return [m.group(1) for m in re.finditer(
        r"\b([A-Za-z_]\w*)\b(?!\s*\()", str(text))
        if m.group(1) not in ("and", "or", "not", "in", "for", "assuming",
                              "inf", "oo", "pi", "e", "E")]


def _builder(params: list, region, applies_to: str = "all"):
    """The callable the partiality registry takes: the call's
    positional arguments (sympy expressions) substituted for the row's
    parameter symbols. Its `applies_to` attribute names the arguments
    the region speaks for (`_RowRegion.applies_to`), read by the
    partiality walk."""
    import sympy
    syms = [sympy.Symbol(p, real=True) for p in params]
    needed = {i for i, s in enumerate(syms) if s in region.free_symbols}

    def build(*args):
        if needed and max(needed) >= len(args):
            return sympy.false
        return region.subs({syms[i]: args[i] for i in needed},
                           simultaneous=True)
    build.applies_to = applies_to  # type: ignore[attr-defined]
    return build


def _row_source(info: dict) -> str:
    """The provenance a key's rows carry: the `mathema.compendium` tag a
    row states, else `compendium:<library>` from the file."""
    return str(next(
        ((r.get("meta") or {}).get("mathema.compendium")
         for r in info["entry"].get("claims") or []
         if (r.get("meta") or {}).get("mathema.compendium")),
        f"compendium:{info['compendium']}"))


def register_library_claims(root: "str | None" = ".") -> list:
    """Intent:
        Register every applicable library row's region by stratum
        (`load_library_claims`, `_row_region`). Mathematics rows become
        partiality guards: an `is_defined` row registers the complement
        of its region as `NO_VALUE`, a `raises(f(...), Exc)` row with an
        ordinary type its domain and premise as `Exc`. Computation rows
        (a computation-safety family in restriction form, a `raises`
        row with a machine-failure type) go to `_COMPUTATION`, read by
        `computation_region`. `root=None` registers the bundled files
        alone. Idempotent per root: the same root again is a no-op, a
        different root replaces the rows the previous one registered.
        Returns the `(key, row name)` pairs registered.

    Notes:
        A row that reads an array's shape or a matrix (`dim(a) >= 1`,
        `det(a) != 0`) states no scalar region and is left to the
        hazard generator. Any other row whose region cannot be built
        registers nothing: a row of a project file is reported once per
        process with `warnings.warn`, naming the key and the row; a
        bundled row is not warned about, and `mathema compendium status`
        names it beside its function (`status.compendium_status`).
    """
    import warnings

    from ..conjecture import REGION_ROW_STRATA
    from ..symbolic._partiality import register_raises_when
    marker = BUNDLED if root is None else os.path.abspath(root)
    if _INSTALLED["root"] == marker:
        return list(_INSTALLED.get("names", []))
    uninstall()
    library_claims = load_library_claims(root)
    apply_definitions(root)
    rows: list = []
    names: list = []
    defined: set = set()
    from ..conjecture import region_row_kind
    for key, info in sorted(library_claims.items()):
        for row in info["entry"].get("claims") or []:
            if not row_is_fact(row):
                continue
            try:
                built = _row_region(key, row)
            except _Unbuildable as e:
                reason = str(e)
                label = (key, str(row.get("name")), reason)
                if (reason != "shape" and not info.get("bundled")
                        and label not in _REPORTED):
                    _REPORTED.add(label)
                    warnings.warn(
                        f"mathema: compendium row {row.get('name')!r} of "
                        f"{key} ({info['source']}) registers no region: "
                        f"{reason}", stacklevel=2)
                continue
            if region_row_kind(str(row.get("name") or "")) == "is_defined" \
                    and (built is not None or _states_totality(row)):
                defined.add(key)
            if built is None:
                continue
            if built.stratum == "computation":
                is_family = built.label in REGION_ROW_STRATA
                free = {str(s) for s in built.region.free_symbols}
                _COMPUTATION.setdefault(key, []).append({
                    "family": built.label if is_family else "raises",
                    "name": str(row.get("name")),
                    "params": [p for p in built.params if p in free],
                    "region": built.region,
                    "texts": list(built.texts),
                    "exception": None if is_family else built.label,
                    "source": _row_source(info)})
                names.append((key, str(row.get("name"))))
                continue
            build = _builder(built.params, built.region, built.applies_to)
            register_raises_when(key, build, built.label)
            rows.append((key, build))
            names.append((key, str(row.get("name"))))
    _INSTALLED.update(root=marker, rows=rows, names=names,
                      keys=frozenset(library_claims), objects=None,
                      defined=frozenset(defined))
    from ..hazards import register_hazard_generator
    register_hazard_generator("compendium",
                              _boundary_generator(library_claims))
    return names


def _states_totality(row: dict) -> bool:
    """Whether a library row is the bare `is_defined(f)` with no domain:
    the function has a value at every argument."""
    from ..conjecture import claim
    try:
        cj = claim(str(row.get("statement") or row.get("law") or ""),
                   name=row.get("name") or None)
    except Exception:
        return False
    return cj.relation == "is_defined" and not cj.domain


def defined_keys() -> frozenset:
    """The registered library claim keys whose files state an
    `is_defined` row (bare or a region): where each is defined is a
    stated fact."""
    return _INSTALLED.get("defined") or frozenset()


def install(root: str = ".") -> None:
    """Register the applicable library claims' automatic facts for
    `root`, the bundled files with the project's own on top:
    partiality guards (`register_library_claims`) and the
    boundary-hazard generator. Called by the joins (`verify`,
    `write_spec`, `mathema check`, the MCP surfaces); `check()` itself
    reads no project file and applies the bundled layer alone
    (`ensure_bundled`)."""
    register_library_claims(root)


def library_key_of(fn) -> "str | None":
    """Intent:
        The library claim key `fn` is (`numpy.mean` for `np.mean`),
        among the keys the registered library claims files state, or
        None for any other callable (a project's own function
        included). The wrappers mathema itself calls a function through
        (a runtime type realiser, a premise guard) are the function
        they wrap.
    """
    keys = _INSTALLED.get("keys") or frozenset()
    if not keys:
        return None
    fn = _engine_unwrapped(fn)
    from ..conjecture import _resolve_func_ref

    def resolved() -> dict:
        out: dict = {}
        for key in sorted(keys):
            try:
                obj = _resolve_func_ref(key)
            except Exception:
                obj = None
            if obj is not None:
                out.setdefault(id(obj), (obj, key))
        return out

    objects = _INSTALLED.get("objects")
    if objects is None:
        objects = _INSTALLED["objects"] = resolved()
    found = objects.get(id(fn))
    if found is not None and found[0] is fn:
        return found[1]
    # a module imported again since the map was built holds new
    # function objects: the function's own dotted name, when it is a
    # key that resolves to this very object, still identifies it
    name = f"{getattr(fn, '__module__', '')}.{getattr(fn, '__qualname__', '')}"
    if name in keys:
        try:
            if _resolve_func_ref(name) is fn:
                _INSTALLED["objects"] = resolved()
                return name
        except Exception:
            return None
    return None


def _engine_unwrapped(fn):
    """`fn` without the wrappers mathema calls a function through: a
    runtime type realiser (`runtime_types._Realising`) and a premise
    guard (`_premises._Guarded`), at any depth. A wrapper anyone else
    wrote is left in place."""
    from .._premises import _Guarded
    from ..runtime_types import _Realising
    while isinstance(fn, (_Realising, _Guarded)):
        fn = (fn.__dict__["_fn"] if isinstance(fn, _Realising)
              else fn.__wrapped__)
    return fn


def _entry_definitions(key: str, entry: dict, source: str) -> list:
    """Intent:
        The definition rows a claims-file entry states under `defines:`,
        each a `runtime_types.Definition`, in order. A row is the text
        `<word> := {<members>}` or a record of one (`definition:`).
    """
    from ..grammar import parse_definition
    from ..runtime_types import Definition
    out = []
    for row in entry.get("defines") or []:
        text = row.get("definition") if isinstance(row, dict) else row
        word, members, extends = parse_definition(str(text))
        out.append(Definition(key, word, members, extends, str(text), source))
    return out


def load_definitions(root: "str | None" = ".") -> dict:
    """Intent:
        Every definition row the claims files state, by layer:
        `{"bundled": [...], "compendium": [...], "claims": [...]}`, the
        bundled compendium files first, then a project's compendium
        files, then its ordinary claims files. `root=None` reads the
        bundled files only. A bundled or project compendium file counts
        only when its library applies, as its claims do.

    Raises:
        spec.ClaimsFileError: a claims file that does not read, a
            definition row that does not parse, or a spelling its key's
            runtime type cannot realise.
    """
    from ..spec import claims_file_paths, read_claims_file
    bundled = _bundled_dir()
    out: dict = {"bundled": [], "compendium": [], "claims": []}
    paths = [(p, True) for p in claims_file_paths(bundled)]
    if root is not None:
        paths += [(p, False) for p in claims_file_paths(root, exclude=(bundled,))]
    for path, shipped in paths:
        where = _display_path(path, root or ".")
        data = read_claims_file(path, where)
        if not data:
            continue
        rows: list = []
        for key, entry in data.items():
            if isinstance(entry, dict) and entry.get("defines"):
                origin = (f"compendium {data['compendium']}"
                          + (", bundled" if shipped else f", {where}")
                          if "compendium" in data else f"claims file {where}")
                rows.extend(_entry_definitions(key, entry, origin))
        if not rows:
            continue
        if "compendium" in data:
            library, versions, aliases = pop_library_fields(dict(data))
            if applicable_tag(library, versions, aliases) is None:
                continue
            out["bundled" if shipped else "compendium"].extend(rows)
        else:
            out["claims"].extend(rows)
    return out


def apply_definitions(root: "str | None" = ".") -> list:
    """Register every definition row `load_definitions(root)` finds, layer
    by layer, and return them in the order they apply."""
    from ..runtime_types import set_definitions
    layers = load_definitions(root)
    for layer, rows in layers.items():
        set_definitions(layer, rows)
    return [row for layer in ("bundled", "compendium", "claims")
            for row in layers[layer]]


def definition_records(rows=None) -> list:
    """Intent:
        The record of each definition row in force: `{key, definition,
        verdict, route, source, members}`, the verdict `trusted` and the
        route `axiom` (a definition is taken at face value, never
        adjudicated), `members` the spellings the row's word stands for
        on its key once every layer up to it has applied.
    """
    from ..runtime_types import definitions, members
    out = []
    for row in rows if rows is not None else definitions():
        out.append({"key": row.key, "definition": row.text,
                    "verdict": "trusted", "route": "axiom",
                    "source": row.source,
                    "members": list(members(row.key, row.word))})
    return out


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
    is the installed one; otherwise whatever is installed): the
    partiality guards, the computation rows and the hazard generator."""
    from ..symbolic._partiality import unregister_lemmas
    if root is not None and _INSTALLED["root"] != os.path.abspath(root):
        return
    for key, build in _INSTALLED["rows"]:
        unregister_lemmas(key, [build])
    _INSTALLED.update(root=None, rows=[], names=[], keys=frozenset(),
                      objects=None, defined=frozenset())
    _COMPUTATION.clear()
    from ..runtime_types import set_definitions
    for layer in ("bundled", "compendium", "claims"):
        set_definitions(layer, ())
    from ..hazards import _GENERATORS
    _GENERATORS.pop("compendium", None)


def computation_region(key: str, family: "str | None" = None) -> list:
    """Intent:
        The registered computation rows of a library key (see
        `_COMPUTATION`), every one or those of one `family`
        (`"is_overflow_safe"`, `"raises"`); [] when the key states
        none.
    """
    rows = _COMPUTATION.get(key) or []
    return [dict(r) for r in rows if family is None or r["family"] == family]


def computation_diagnosis(fn, facts, point: "dict | None" = None) -> "str | None":
    """Intent:
        One sentence naming the computation region of a covered call
        `fn` makes, for a failure at `point` (the caller's parameter
        values): "the covered call numpy.exp is overflow-safe only for
        x <= 709.78, and x = 1000 lies outside it" when the region
        reads over the caller's own parameters and the point is
        outside it; the same sentence without the point when the
        region cannot be evaluated at it (the call's argument is an
        expression over the caller's parameters); None when no covered
        call states a computation region, or the point is inside every
        region that can be evaluated (the failure is not this call's).
    """
    import sympy
    keys = sorted(k for k in _resolve_called_keys(fn, facts)
                  if k in _COMPUTATION)
    for key in keys:
        for row in computation_region(key, "is_overflow_safe"):
            texts = " and ".join(row["texts"])
            sentence = (f"the covered call {key} is overflow-safe only for "
                        f"{texts}")
            values = {p: (point or {}).get(p) for p in row["params"]}
            if any(not isinstance(v, (int, float)) or isinstance(v, bool)
                   for v in values.values()):
                return sentence
            try:
                inside = row["region"].subs(
                    {sympy.Symbol(p, real=True): v for p, v in values.items()})
            except Exception:
                return sentence
            if inside == sympy.true:
                continue
            if inside == sympy.false:
                at = ", ".join(f"{p} = {v:g}" for p, v in values.items())
                return f"{sentence}, and {at} lies outside it"
            return sentence
    return None


def _dotted_call_name(node) -> "str | None":
    """The dotted name a call is written with (`np.exp`, `exp`), or
    None for a call through anything but names and attributes."""
    import ast
    parts: list = []
    f = node.func
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if not isinstance(f, ast.Name):
        return None
    parts.append(f.id)
    return ".".join(reversed(parts))


def _call_argument(node, position: int, name: str):
    """The argument expression a call passes for the parameter at
    `position` named `name`, or None when the call passes none."""
    if position < len(node.args):
        return node.args[position]
    return next((k.value for k in node.keywords if k.arg == name), None)


def computation_edges(fn, facts) -> list:
    """Intent:
        The edges of every covered call's overflow-safe region that `fn`
        passes one of its own parameters to directly, in the caller's
        terms: `(param, value, key, above)`; for `np.exp(x)` it is
        `("x", 709.78..., "numpy.exp", True)`, `above` saying the call
        stops being overflow-safe past the value rather than below it.
        A call whose argument is an expression is left out, since the
        row's edge is then not an edge in the caller's parameter.
    """
    import ast

    import sympy
    tree = getattr(facts, "tree", None)
    if tree is None:
        return []
    params = set(getattr(facts, "params", ()) or ())
    origin = _alias_origins(fn, facts)
    out: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_call_name(node)
        if name is None:
            continue
        head, dot, rest = name.partition(".")
        base = origin.get(head)
        key = name if base is None else (f"{base}.{rest}" if dot else base)
        for row in computation_region(key, "is_overflow_safe"):
            positions = {p: i for i, p in enumerate(row["params"])}
            for condition in row["texts"]:
                try:
                    rel = sympy.sympify(condition)
                    (sym,) = rel.free_symbols
                except Exception:
                    continue
                if sym.name not in positions:
                    continue
                arg = _call_argument(node, positions[sym.name], sym.name)
                if not (isinstance(arg, ast.Name) and arg.id in params):
                    continue
                for value in _boundaries(rel):
                    above = rel.subs(sym, value + 1) == sympy.false
                    edge = (arg.id, value, key, bool(above))
                    if edge not in out:
                        out.append(edge)
    return out


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
    region's boundary value (an `is_defined` region and an
    `is_overflow_safe` region alike), offered on every numeric
    parameter of the caller. Coarse on purpose (the covered call's
    argument is often an expression over the caller's parameters, not
    one of them), and a wrong hint costs one sample."""
    def generate(fn, facts, domain):
        import re

        from ..conjecture import REGION_ROW_STRATA
        from ..hazards import HazardPoint
        out = []
        for key in sorted(library_keys_called(
                fn, facts, library_claims=library_claims)):
            info = library_claims[key]
            source = _row_source(info)
            for region in _region_texts(info["entry"],
                                        tuple(REGION_ROW_STRATA)):
                for condition in region:
                    if re.search(r"\bdim\s*\(", condition):
                        # outside `dim(a) >= 1` is the empty sequence
                        for param in getattr(facts, "params", ()):
                            if (getattr(facts, "param_kinds", None) or {}
                                    ).get(param) in SEQUENCE_KINDS:
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
