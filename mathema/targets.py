# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The one target resolver: any spelling of "which function(s)" that a
mathema command accepts resolves here, to live callables keyed by their
canonical dotted name (`module.qualname`, the same shape the
declared/verified stores use).

Accepted spellings:

- ``pkg`` / ``pkg.mod``, an importable package or module; a package
  is walked into every submodule.
- ``pkg.mod.fn`` / ``pkg.mod.Class.method``; one function or method,
  found by importing the longest importable prefix and walking
  attributes for the rest.
- ``pkg.mod:fn`` / ``pkg.mod:Class.method``, the explicit one-function
  form; ``pkg:name`` also matches ``name`` anywhere under ``pkg`` when
  that suffix is unique.
- ``path/to/file.py`` / ``path/to/file.py:fn``, a file, imported
  under its real dotted name with full package context (the package
  root is found by walking up through ``__init__.py`` directories), so
  relative imports inside the target work and the loaded functions key
  identically to normally-imported ones.

Every command and programmatic surface resolves through `resolve` /
`resolve_function`; a target that cannot be resolved raises
`TargetError` with a printable message (CLI exit 2).
"""
from __future__ import annotations

import contextlib
import importlib
import inspect
import os
import sys
from dataclasses import dataclass, field
from typing import Callable


class TargetError(Exception):
    """A target string that cannot be resolved to any function. The
    message is written to be printed as-is to a CLI user."""


@dataclass
class Target:
    """One resolved target: `kind` is "package", "module", or
    "function"; `functions` maps each canonical dotted key to its live
    callable; `module_name` is the dotted module actually imported (or
    None for a package walk); `skipped` lists `(submodule, error)`
    pairs for package submodules that failed to import."""
    kind: str
    functions: dict[str, Callable]
    module_name: str | None
    root: str
    skipped: list = field(default_factory=list)


def _is_pathlike(spelling: str) -> bool:
    """Intent:
        Classify the module half of a target as a filesystem path
        rather than a dotted importable name, mirroring the checks
        audit's discovery applies before rejecting a path.
    """
    return ("/" in spelling or os.sep in spelling or spelling.endswith(".py")
            or spelling.startswith(("~", ".")))


def _dotted_name_for_file(path: str) -> tuple[str, str]:
    """Intent:
        The real dotted module name `path` would have if imported
        normally, and the sys.path root that makes that import work:
        walk up through directories containing `__init__.py` to the
        package root. A file in no package at all imports under its
        bare stem with its own directory as the root.

    Raises:
        TargetError: the file does not exist, is not a `.py` file, or
            its own name is not a valid module name.
    """
    full = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(full):
        raise TargetError(f"no such file: {path}")
    if not full.endswith(".py"):
        raise TargetError(f"{path!r} is not a .py file")
    stem = os.path.basename(full)[:-len(".py")]
    if not stem.isidentifier():
        raise TargetError(
            f"{path!r} cannot be imported: {stem!r} is not a valid "
            f"module name")
    parts = [stem]
    d = os.path.dirname(full)
    while os.path.isfile(os.path.join(d, "__init__.py")):
        seg = os.path.basename(d)
        if not seg.isidentifier():
            break
        parts.insert(0, seg)
        d = os.path.dirname(d)
    return ".".join(parts), d


@contextlib.contextmanager
def _root_on_path(root: str):
    """Intent:
        Temporarily put `root` first on sys.path for an import, unless
        it is already present. Imported modules stay usable after
        removal; sys.modules keeps them alive.
    """
    root_abs = os.path.abspath(root)
    inserted = root_abs not in sys.path
    if inserted:
        sys.path.insert(0, root_abs)
    try:
        yield
    finally:
        if inserted and root_abs in sys.path:
            sys.path.remove(root_abs)


def _import_module(dotted: str, root: str):
    """Intent:
        `importlib.import_module` under `_root_on_path`, converting any
        import-time failure (not just ImportError, a target module
        can crash at import with anything) into a printable
        TargetError.
    """
    with _root_on_path(root):
        try:
            return importlib.import_module(dotted)
        except Exception as e:
            raise TargetError(
                f"could not import {dotted!r}: {type(e).__name__}: {e}") from e


def _prefix_walk(dotted: str, root: str):
    """Intent:
        Resolve a fully dotted reference (`pkg.mod.fn`,
        `pkg.mod.Class.method`) by importing the longest importable
        prefix and walking attributes for the remainder. Returns
        `(module, qualname, obj)` or None when no prefix imports or
        the attribute walk dead-ends. A staticmethod is unwrapped to
        its plain function.
    """
    parts = dotted.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        mod_name = ".".join(parts[:cut])
        try:
            mod = _import_module(mod_name, root)
        except TargetError:
            continue
        obj: object = mod
        for attr in parts[cut:]:
            obj = inspect.getattr_static(obj, attr, None)
            if obj is None:
                return None
        if isinstance(obj, staticmethod):
            obj = obj.__func__
        return mod, ".".join(parts[cut:]), obj
    return None


def resolve(target: str, root: str = ".", *,
            skipped: list | None = None) -> Target:
    """Resolve a target spelling to its functions, keyed by canonical
    dotted name. See the module docstring for the accepted spellings.
    `skipped`, when given, collects `(submodule, error)` pairs for
    package submodules that failed to import (also carried on the
    returned Target).

    Raises:
        TargetError: nothing resolvable at this spelling; the message
            is printable as-is.
    """
    from .audit import DiscoveryError, discover

    skipped = skipped if skipped is not None else []
    mod_part, _, qual_part = target.partition(":")

    if ":" in target and not _is_pathlike(mod_part):
        # a language-tagged key (`ts:src/ema.ts#ema`): a registered
        # resolver turns it into a Target of callable proxies; None
        # means "not mine" and resolution falls through to the
        # ordinary import path unchanged
        from ._target_resolvers import get_resolver
        resolver = get_resolver(mod_part)
        if resolver is not None:
            resolved = resolver(target, root)
            if resolved is not None:
                return resolved

    if _is_pathlike(mod_part):
        dotted, root = _dotted_name_for_file(mod_part)
        # a cached module under this dotted name that came from a
        # DIFFERENT file (two scratch scripts both named m.py, say)
        # would be returned instead of importing the requested one,
        # evict it, and its submodules, so the import is really this
        # file
        full = os.path.abspath(os.path.expanduser(mod_part))
        cached = sys.modules.get(dotted)
        if cached is not None and os.path.abspath(
                getattr(cached, "__file__", "") or "") != full:
            for name in [dotted] + [k for k in list(sys.modules)
                                    if k.startswith(dotted + ".")]:
                sys.modules.pop(name, None)
        _import_module(dotted, root)
        target = f"{dotted}:{qual_part}" if qual_part else dotted
        mod_part = dotted

    colon = ":" in target
    with _root_on_path(root):
        try:
            found = discover([target], skipped=skipped)
        except DiscoveryError as e:
            if not colon:
                walked = _prefix_walk(mod_part, root)
                if walked is not None:
                    return _walked_target(walked, target, root, skipped)
            if "#" in qual_part and "." not in mod_part:
                # the tagged-key shape with nothing registered to serve
                # it: name the remedy, not the bogus module import
                raise TargetError(
                    f"no target resolver is registered for "
                    f"{mod_part + ':'!r}; install the adaptor package "
                    f"providing it, or check the tag spelling "
                    f"(registered resolvers come from the "
                    f"{'mathema.target_resolvers'!r} entry-point "
                    f"group)") from e
            raise TargetError(str(e)) from e
        if colon and found:
            return Target("function", found, mod_part, root, skipped)
        if not colon:
            # a module or package resolves even with zero functions;
            # the caller decides whether an empty population is an error
            mod = sys.modules.get(target)
            kind = ("package" if mod is not None and hasattr(mod, "__path__")
                    else "module")
            return Target(kind, found, target if kind == "module" else None,
                          root, skipped)
        if "." not in qual_part:
            # bare-suffix search: `pkg:name` matches `name` anywhere
            # under the package when that suffix is unique
            wider = discover([mod_part], skipped=skipped)
            hits = {k: v for k, v in wider.items()
                    if k.rsplit(".", 1)[-1] == qual_part}
            if len(hits) == 1:
                return Target("function", hits, None, root, skipped)
            if len(hits) > 1:
                names = ", ".join(sorted(hits)[:10])
                raise TargetError(
                    f"{qual_part!r} is ambiguous under {mod_part!r}: {names}")
        what = qual_part or target
        hint = ""
        try:
            pool = discover([mod_part], skipped=list(skipped))
        except Exception:
            pool = {}
        if pool:
            import difflib
            leaf = what.rsplit(".", 1)[-1]
            close = set(difflib.get_close_matches(
                leaf, {k.rsplit(".", 1)[-1] for k in pool}, n=3, cutoff=0.6))
            matches = [k for k in sorted(pool)
                       if k.rsplit(".", 1)[-1] in close]
            if matches:
                hint = "; did you mean: " + ", ".join(matches[:3]) + "?"
        raise TargetError(
            f"no function named {what!r} found under {mod_part!r}{hint}")


def _walked_target(walked, target: str, root: str, skipped: list) -> Target:
    """Intent:
        Package a `_prefix_walk` hit as a Target, rejecting anything
        that is not a plain function or method with a message naming
        what the reference actually is.

    Raises:
        TargetError: the reference names a class, a non-callable, or a
            callable with no signature to adjudicate.
    """
    mod, qual, obj = walked
    if inspect.isclass(obj):
        raise TargetError(
            f"{target!r} names a class, target one of its methods "
            f"({target}.method) or the whole module ({mod.__name__})")
    if not callable(obj):
        raise TargetError(
            f"{target!r} names a {type(obj).__name__}, not a function")
    return Target("function", {f"{mod.__name__}.{qual}": obj},
                  mod.__name__, root, skipped)


def resolve_function(target: str, root: str = ".") -> tuple[str, Callable]:
    """Resolve a target that must name exactly one function, returning
    `(key, fn)`.

    Raises:
        TargetError: the target resolves to nothing, or to more than
            one function (the message lists candidates).
    """
    t = resolve(target, root)
    if len(t.functions) == 1:
        return next(iter(t.functions.items()))
    names = ", ".join(sorted(t.functions)[:10])
    more = "" if len(t.functions) <= 10 else f" (+{len(t.functions) - 10} more)"
    raise TargetError(
        f"{target!r} names {len(t.functions)} functions, not one: "
        f"{names}{more}. Narrow it with `module:function`.")
