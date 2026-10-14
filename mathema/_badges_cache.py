# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A per-function cache of `mathema badges` results, under
`.mathema/cache/badges/` (the directory keeps its own `.gitignore`, so
it is never committed).

An entry holds what one function contributes to the badges (its
statement and covered-line counts, its intent and clarity, and the
warnings its analysis showed), or the centrality weights of one
population. It is found by a SHA-256 digest of what those numbers are
computed from:

- the environment (`environment_digest`): mathema's version, the
  contents of mathema's own source and of every other package loaded
  from outside both the installed library directories and the project
  root, the sampling seeds, the Python version and platform, every
  `MATHEMA_*` environment variable, the name and version of every
  installed distribution, the library claims the project knows,
  `README.md` (its intent is part of every function's intent context),
  `pyproject.toml`, `.mathema/index.yaml` and `.mathema/meta`;
- the function's reach (`Reach`): the function itself and everything it
  reaches, its static callees transitively and every function a reached
  verified record lists among its dependencies, each as its source text,
  file, first line, `form` hash, module docstring and the values of the
  module-level names it reads, with the verified record and the
  claims-file entry of each;
- for a function, whether the coverage pass ran, and, for that pass,
  whether the test report is fresh for its file and the lines the
  report says the tests executed in it; for the weights, the reach
  digest of every function in the population.

So an edit to one function computes that function and everything that
reaches it again, and nothing else. A function reached only at run time
(a call through a name the source does not bind statically) is not in
the reach, and an edit to it leaves its callers' entries in place;
`mathema badges --refresh` computes every function again. A code
object installed as a distribution, or part of mathema, ends the walk:
its version or the environment digest already covers it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

#: where the cache lives, under the project root
CACHE_DIR = os.path.join(".mathema", "cache", "badges")

#: the layout of an entry; a different layout is a different digest
_SCHEMA = "badges-cache@3"

#: directories a walk of the project root never enters
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "venv", "env",
                        "site-packages", "build", "dist"})

#: the longest value text a module-level name contributes to a reach
_VALUE_LIMIT = 4096


def _file_digest(path: str) -> str:
    """Intent:
        The SHA-256 of a file's bytes, or `-` when it cannot be read.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return "-"
    return h.hexdigest()


def _installed_dirs() -> tuple:
    """Intent:
        The real paths of the standard library and installed-package
        directories of this interpreter.
    """
    import sysconfig
    paths = sysconfig.get_paths()
    dirs = {os.path.realpath(paths[name]) for name in
            ("stdlib", "platstdlib", "purelib", "platlib") if name in paths}
    return tuple(sorted(dirs))


def _walk(top: str, suffixes: "tuple | None") -> list:
    """Intent:
        Every file under `top` (only those ending in one of `suffixes`,
        or every file when None), skipping hidden directories and
        `_SKIP_DIRS`, as sorted real paths.
    """
    out = []
    for here, dirs, files in os.walk(top):
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith(".") and d not in _SKIP_DIRS)
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            if suffixes is None or name.endswith(suffixes):
                out.append(os.path.realpath(os.path.join(here, name)))
    return sorted(out)


def _distributions() -> list:
    """Intent:
        `(name, version)` of every installed distribution, sorted.
    """
    from importlib import metadata
    out = set()
    for dist in metadata.distributions():
        try:
            out.add((str(dist.metadata["Name"] or ""), str(dist.version)))
        except Exception:
            continue
    return sorted(out)


def _put(h, part) -> None:
    """Intent:
        Add `part` to the running digest `h` as canonical JSON, then a
        separator.
    """
    h.update(json.dumps(part, sort_keys=True, default=str).encode())
    h.update(b"\0")


def _under(path: str, dirs) -> bool:
    """Intent:
        Whether the real `path` is one of `dirs` or inside one of them.
    """
    return any(path == d or path.startswith(d + os.sep) for d in dirs)


def _tool_dirs(root: str) -> list:
    """Intent:
        The package directories whose code analyses the project rather
        than being analysed by it: mathema's own, and the top-level
        package of every loaded module that lives outside both the
        installed directories and `root`, as sorted real paths.
    """
    import mathema
    installed = _installed_dirs()
    real_root = os.path.realpath(root)
    tops = {os.path.realpath(d) for d in mathema.__path__}
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if not path or name in ("__main__", "__mp_main__"):
            continue
        real = os.path.realpath(path)
        if _under(real, installed) or _under(real, (real_root,)):
            continue
        top = sys.modules.get(name.split(".")[0])
        where = getattr(top, "__path__", None)
        if where:
            tops.update(os.path.realpath(d) for d in where)
        else:
            tops.add(real)
    return sorted(tops)


def environment_digest(root: str, library_keys) -> str:
    """Intent:
        The SHA-256 digest of everything every function's result in one
        badges run shares (see the module docstring): mathema and the
        other tool code, the interpreter, the environment, the installed
        distributions, the `library_keys` and the project-wide files.
    """
    import platform

    from . import __version__
    from ._sampling import _RNG_SEED
    from .equivalence import EQUIV_SEED
    h = hashlib.sha256()
    _put(h, [_SCHEMA, __version__, _RNG_SEED, EQUIV_SEED, sys.version,
             platform.platform(), platform.machine()])
    _put(h, sorted((k, v) for k, v in os.environ.items()
                   if k.startswith("MATHEMA_")))
    _put(h, _distributions())
    for top in _tool_dirs(root):
        files = _walk(top, None) if os.path.isdir(top) else [top]
        for path in files:
            _put(h, [path, _file_digest(path)])
    _put(h, sorted(library_keys))
    files = [os.path.join(root, name) for name in
             ("README.md", "pyproject.toml",
              os.path.join(".mathema", "index.yaml"))]
    meta = os.path.join(root, ".mathema", "meta")
    if os.path.isdir(meta):
        files += _walk(meta, None)
    for path in files:
        if os.path.isfile(path):
            _put(h, [os.path.relpath(os.path.realpath(path),
                                     os.path.realpath(root)),
                     _file_digest(path)])
    return h.hexdigest()


def _value_text(value) -> str:
    """Intent:
        A stable text for the value of a module-level name: its JSON
        when it is plain data (numbers, strings, booleans, None, and
        lists, tuples and string-keyed dicts of them) and no longer than
        `_VALUE_LIMIT`, its digest when longer, and otherwise its type's
        qualified name.
    """
    try:
        text = json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        kind = type(value)
        return f"<{kind.__module__}.{kind.__qualname__}>"
    if len(text) > _VALUE_LIMIT:
        return hashlib.sha256(text.encode()).hexdigest()
    return text


def _object_key(obj) -> "str | None":
    """Intent:
        `module.qualname` of a function or class, or None.
    """
    mod = getattr(obj, "__module__", None)
    qual = getattr(obj, "__qualname__", None)
    return f"{mod}.{qual}" if mod and qual else None


class Reach:
    """Intent:
        The reach of functions within one badges run: each function's
        code part and its direct reach are computed once and shared by
        every function that reaches it.
    """

    def __init__(self, root: str, verified: dict, declared: dict):
        self.root = os.path.realpath(root)
        self.verified = verified
        self.declared = declared
        self._ends = _installed_dirs() + tuple(_tool_dirs(root))
        self._parts: dict = {}
        self._edges: dict = {}

    def _source_file(self, obj) -> "str | None":
        """Intent:
            The real path of the file `obj` is defined in, or None.
        """
        import inspect
        try:
            path = inspect.getsourcefile(obj)
        except TypeError:
            return None
        return os.path.realpath(path) if path else None

    def _part(self, key: str, obj) -> dict:
        """Intent:
            The code part of `obj` (keyed `key`), and its direct reach
            recorded in `self._edges[key]`: the functions and classes
            its static dependencies name and every one its verified
            record lists among its dependencies.
        """
        import inspect

        from ._signatures import module_scope
        from .analysis import quiet_facts
        from .inventory import function_dependencies
        edges: dict = {}
        self._edges[key] = edges
        path = self._source_file(obj)
        if path is None:
            return {"key": key, "source": None}
        if _under(path, self._ends):
            return {"key": key, "outside": True}
        try:
            lines, first = inspect.getsourcelines(obj)
        except (OSError, TypeError):
            return {"key": key, "source": None}
        module = inspect.getmodule(obj)
        part = {"key": key, "line": first,
                "file": (os.path.relpath(path, self.root)
                         if _under(path, (self.root,)) else path),
                "source": hashlib.sha256("".join(lines).encode()).hexdigest(),
                "module_doc": getattr(module, "__doc__", None)}
        if inspect.isfunction(obj):
            facts = quiet_facts(obj)
            if facts is not None:
                scope = module_scope(obj)
                part["form"] = facts.form
                part["globals"] = sorted(
                    (name, _value_text(scope.get(name)))
                    for name in set(facts.global_vars))
                for dep in function_dependencies(obj, facts):
                    if dep.get("kind") in ("function", "class") \
                            and dep.get("key"):
                        edges[dep["key"]] = scope.get(dep.get("name"))
        entry = (self.verified.get(key) or {}).get("entry") or {}
        for dep in entry.get("dependencies") or ():
            if isinstance(dep, dict) and dep.get("key") \
                    and dep.get("kind", "function") in ("function", "class"):
                edges.setdefault(dep["key"], None)
        return part

    def _resolve(self, key: str, obj):
        """Intent:
            The object `key` names: `obj` when it is that object, else
            the importable function `key` resolves to, or None.
        """
        if obj is not None and _object_key(obj) == key:
            return obj
        from .conjecture import _resolve_func_ref
        try:
            return _resolve_func_ref(key)
        except Exception:
            return None

    def keys(self, key: str, fn) -> list:
        """Intent:
            Every key `fn` (keyed `key`) reaches, itself included,
            sorted.
        """
        seen = {key}
        todo = [(key, fn)]
        while todo:
            here, obj = todo.pop()
            if here not in self._parts:
                self._parts[here] = (self._part(here, obj) if obj is not None
                                     else {"key": here, "source": None})
            for nxt, nobj in self._edges.get(here, {}).items():
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append((nxt, self._resolve(nxt, nobj)))
        return sorted(seen)

    def digest(self, env: str, key: str, fn) -> str:
        """Intent:
            The SHA-256 digest of `fn`'s reach under the environment
            digest `env`: the code part, verified record and claims-file
            entry of every key it reaches.
        """
        h = hashlib.sha256()
        _put(h, [env, key])
        for k in self.keys(key, fn):
            _put(h, [self._parts[k], self.verified.get(k),
                     self.declared.get(k)])
        return h.hexdigest()


def function_digest(reach: str, implementation: bool, fresh: bool,
                    test_lines) -> str:
    """Intent:
        The digest one function's entry is stored under: its `reach`
        digest (`Reach.digest`), whether the coverage pass runs, and for
        that pass whether the test report is `fresh` for the function's
        file and the `test_lines` it executed there.
    """
    part = [reach, bool(implementation)]
    if implementation:
        part += [bool(fresh), sorted(test_lines)]
    return hashlib.sha256(json.dumps(part).encode()).hexdigest()


def weights_digest(env: str, reaches: dict) -> str:
    """Intent:
        The digest the run's centrality weights are stored under: the
        environment digest `env` and the reach digest of every function
        in the population, `{key: reach digest}`.
    """
    part = [env, "centrality", sorted(reaches.items())]
    return hashlib.sha256(json.dumps(part).encode()).hexdigest()


def _entry_path(root: str, digest: str) -> str:
    return os.path.join(root, CACHE_DIR, digest[:2], digest + ".json")


def read(root: str, digest: str) -> "dict | None":
    """Intent:
        The entry stored under `digest`, or None when there is none or
        it does not read as one.
    """
    try:
        with open(_entry_path(root, digest), encoding="utf-8") as fh:
            entry = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(entry, dict) or entry.get("digest") != digest:
        return None
    return entry


def write(root: str, digest: str, entry: dict) -> None:
    """Intent:
        Store `entry` under `digest`, replacing the file in one step;
        the cache directory is created with a `.gitignore` that ignores
        everything in it. A cache that cannot be written is left as it
        is.
    """
    base = os.path.join(root, CACHE_DIR)
    path = _entry_path(root, digest)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ignore = os.path.join(base, ".gitignore")
        if not os.path.exists(ignore):
            with open(ignore, "w", encoding="utf-8") as fh:
                fh.write("*\n")
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({**entry, "digest": digest}, fh, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        return
