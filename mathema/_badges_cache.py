# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A per-function cache of `mathema badges` results, under
`.mathema/cache/badges/` (the directory keeps its own `.gitignore`, so
it is never committed).

An entry holds what one function contributes to the badges (its
statement and covered-line counts, its intent and clarity, and the
warnings its analysis showed), or the centrality weights of one
population. It is found by a SHA-256 digest of everything those numbers
are computed from:

- the run's fingerprint (`run_fingerprint`): mathema's version and
  sampling seeds, the Python version and platform, every `MATHEMA_*`
  environment variable, the name and version of every installed
  distribution, the contents of every source file of every package
  loaded from outside the installed library directories and of every
  project file under the root, and the contents of the store (the
  verified records, `.mathema/meta`, `.mathema/index.yaml`, every
  claims file, the root `README.md` and `pyproject.toml`);
- for a function, its key, whether the coverage pass ran, and, for
  that pass, whether the test report is fresh for its file and the
  lines the report says the tests executed in it; for the weights, the
  keys of the population.

An entry is used only when that digest matches exactly, so any change
to the code, the store or the environment computes the function again.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

#: where the cache lives, under the project root
CACHE_DIR = os.path.join(".mathema", "cache", "badges")

#: the layout of an entry; a different layout is a different digest
_SCHEMA = "badges-cache@1"

#: directories a walk of the project root never enters
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "venv", "env",
                        "site-packages", "build", "dist"})

#: the project files under the root that a walk hashes, by suffix
_ROOT_SUFFIXES = (".py", ".pyi", ".pyx", ".so", ".pyd", ".yaml", ".yml",
                  ".toml", ".cfg", ".ini")


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


def _code_files(root: str) -> list:
    """Intent:
        The source files the run's code is read from: every file of the
        top-level package of each loaded module that lives outside the
        installed directories (a lone module counts as its own file;
        the script the process was started with is not one of them),
        and the project files under `root` (`_ROOT_SUFFIXES`).
    """
    installed = _installed_dirs()
    tops: set = set()
    files: set = set()
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if not path or name in ("__main__", "__mp_main__"):
            continue
        real = os.path.realpath(path)
        if real.startswith(installed):
            continue
        top = sys.modules.get(name.split(".")[0])
        for where in getattr(top, "__path__", None) or ():
            tops.add(os.path.realpath(where))
        if getattr(top, "__path__", None) is None:
            files.add(real)
    for where in sorted(tops):
        if os.path.isdir(where) and not where.startswith(installed):
            files.update(_walk(where, None))
    files.update(_walk(root, _ROOT_SUFFIXES))
    return sorted(files)


def _store_files(root: str) -> list:
    """Intent:
        The store and configuration files a badges run reads under
        `root`: the verified records, `.mathema/meta`,
        `.mathema/index.yaml`, every claims file, `README.md` and
        `pyproject.toml`.
    """
    from .spec import claims_file_paths, verified_dir
    files: set = set()
    for where in (verified_dir(root), os.path.join(root, ".mathema", "meta")):
        if os.path.isdir(where):
            files.update(_walk(where, None))
    for name in (os.path.join(".mathema", "index.yaml"), "README.md",
                 "pyproject.toml"):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            files.add(os.path.realpath(path))
    files.update(os.path.realpath(p) for p in claims_file_paths(root))
    return sorted(files)


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


def run_fingerprint(root: str) -> str:
    """Intent:
        The SHA-256 digest of everything shared by every function of
        one badges run (see the module docstring).
    """
    import platform

    from . import __version__
    from ._sampling import _RNG_SEED
    from .equivalence import EQUIV_SEED
    h = hashlib.sha256()

    def put(part) -> None:
        h.update(json.dumps(part, sort_keys=True, default=str).encode())
        h.update(b"\0")

    put([_SCHEMA, __version__, _RNG_SEED, EQUIV_SEED, sys.version,
         platform.platform(), platform.machine()])
    put(sorted((k, v) for k, v in os.environ.items()
               if k.startswith("MATHEMA_")))
    put(_distributions())
    for path in _code_files(root):
        put([path, _file_digest(path)])
    put("store")
    for path in _store_files(root):
        put([os.path.relpath(path, os.path.realpath(root)),
             _file_digest(path)])
    return h.hexdigest()


def function_digest(fingerprint: str, key: str, implementation: bool,
                    fresh: bool, test_lines) -> str:
    """Intent:
        The digest one function's entry is stored under: the run's
        `fingerprint`, the function's `key`, whether the coverage pass
        runs, and for that pass whether the test report is `fresh` for
        the function's file and the `test_lines` it executed there.
    """
    part = [fingerprint, key, bool(implementation)]
    if implementation:
        part += [bool(fresh), sorted(test_lines)]
    return hashlib.sha256(json.dumps(part).encode()).hexdigest()


def weights_digest(fingerprint: str, keys) -> str:
    """Intent:
        The digest the run's centrality weights are stored under: the
        run's `fingerprint` and the population's `keys`.
    """
    part = [fingerprint, "centrality", sorted(keys)]
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
