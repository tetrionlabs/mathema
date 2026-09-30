# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""State a function can change for the whole process, beyond its own
module's globals: the environment, the working directory, `sys.path`,
the global state of `random` and `numpy.random`, and logging's root
configuration.

`snapshot()` reads it, `changes(before, after)` names what differs,
and `restore(before)` puts it back, so a trial that observed a write
leaves the process as it found it. `os.putenv` and `os.unsetenv` change
the C environment only, which no Python read can see afterwards, so
`watching_putenv(fn)` records every call to them made while it is open.
`writer_calls(fn, facts)` is the structural reading: the call sites in
the body that resolve to one of these writers.
"""
from __future__ import annotations

import ast
import contextlib
import logging
import os
import random
import sys


def _numpy_random():
    """The `numpy.random` module when numpy is already imported, else
    None: a function that never imported numpy cannot have changed it."""
    np = sys.modules.get("numpy")
    return getattr(np, "random", None) if np is not None else None


def snapshot() -> dict:
    """Intent:
        The process-wide state, keyed by the name a witness gives it.
    """
    root = logging.getLogger()
    state = {
        "os.environ": dict(os.environ),
        "the working directory": os.getcwd(),
        "sys.path": list(sys.path),
        "the global state of random": random.getstate(),
        "logging's root configuration": (root.level, tuple(root.handlers),
                                          logging.root.manager.disable),
    }
    npr = _numpy_random()
    if npr is not None:
        state["the global state of numpy.random"] = npr.get_state()
    return state


def _same(name: str, a, b) -> bool:
    if name == "the global state of numpy.random":
        import numpy
        return (a[0] == b[0] and numpy.array_equal(a[1], b[1])
                and tuple(a[2:]) == tuple(b[2:]))
    return a == b


def _environ_change(a: dict, b: dict) -> str:
    set_ = sorted(k for k in b if a.get(k) != b[k])
    removed = sorted(k for k in a if k not in b)
    parts = [f"{k} set to {b[k]!r}" for k in set_[:3]]
    parts += [f"{k} removed" for k in removed[:3]]
    return ", ".join(parts)


def changes(before: dict, after: dict) -> list[str]:
    """Intent:
        One phrase per piece of process state that differs between two
        snapshots, naming it and, where it reads short, how it changed.
    """
    out = []
    for name, value in before.items():
        if name not in after or _same(name, value, after[name]):
            continue
        if name == "os.environ":
            out.append(f"os.environ ({_environ_change(value, after[name])})")
        elif name in ("the working directory", "sys.path"):
            out.append(f"{name} ({value!r} became {after[name]!r})"
                       if name == "the working directory" else name)
        else:
            out.append(name)
    for name in after:
        if name not in before and name == "the global state of numpy.random":
            out.append(name)
    return out


def restore(before: dict) -> None:
    """Intent:
        Put the process-wide state back as `before` read it.
    """
    if dict(os.environ) != before["os.environ"]:
        os.environ.clear()
        os.environ.update(before["os.environ"])
    if os.getcwd() != before["the working directory"]:
        os.chdir(before["the working directory"])
    if sys.path != before["sys.path"]:
        sys.path[:] = before["sys.path"]
    random.setstate(before["the global state of random"])
    level, handlers, disable = before["logging's root configuration"]
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = list(handlers)
    logging.disable(disable)
    npr = _numpy_random()
    if npr is not None and "the global state of numpy.random" in before:
        npr.set_state(before["the global state of numpy.random"])


@contextlib.contextmanager
def watching_putenv(fn):
    """Intent:
        Record every call to `os.putenv` and `os.unsetenv` made while
        open, however the function reaches them (`os.putenv(...)` or a
        name imported from os into its module), as `(writer, name)`
        pairs; each call still goes through.
    """
    from ._signatures import module_scope
    calls: list = []
    originals = {"putenv": os.putenv, "unsetenv": os.unsetenv}
    scope = module_scope(fn)
    rebound = {k: v for k, v in scope.items()
               if any(v is o for o in originals.values())}

    def recorder(label, original):
        def call(name, *rest):
            calls.append((f"os.{label}", name))
            return original(name, *rest)
        return call

    wrapped = {label: recorder(label, o) for label, o in originals.items()}
    try:
        for label, w in wrapped.items():
            setattr(os, label, w)
        for k, v in rebound.items():
            label = next(lbl for lbl, o in originals.items() if v is o)
            scope[k] = wrapped[label]
        yield calls
    finally:
        for label, o in originals.items():
            setattr(os, label, o)
        for k, v in rebound.items():
            scope[k] = v


def _writers() -> set:
    writers = {os.putenv, os.unsetenv, os.chdir, random.seed,
               random.setstate, logging.basicConfig, logging.disable}
    if hasattr(os, "fchdir"):
        writers.add(os.fchdir)
    return writers


def _draws_global_rng(obj) -> bool:
    """Whether `obj` is a method of the process-wide random generator
    (`random.random` and its siblings, `numpy.random.normal` and
    theirs), each of which advances that generator's state."""
    owner = getattr(obj, "__self__", None)
    if owner is None:
        return False
    if owner is getattr(random, "_inst", None):
        return True
    npr = _numpy_random()
    mtrand = getattr(npr, "mtrand", None) if npr is not None else None
    return owner is getattr(mtrand, "_rand", object())


def writer_calls(fn, facts) -> list[str]:
    """Intent:
        The bare-name calls in the body that resolve, through the
        function's module, to a writer of process-wide state (os.putenv,
        os.chdir, random.seed, a draw from the global generator, ...),
        by the name the body calls. An attribute call (`os.putenv`) is
        already an external write site for `hazards._state_writes`.
    """
    from ._signatures import module_scope
    tree = getattr(facts, "tree", None)
    if tree is None:
        return []
    scope = module_scope(fn)
    writers = _writers()
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        obj = scope.get(node.func.id)
        if obj is None:
            continue
        try:
            hit = obj in writers or _draws_global_rng(obj)
        except TypeError:
            hit = False
        if hit and node.func.id not in found:
            found.append(node.func.id)
    return found


#: reads of inputs outside the arguments that change slowly enough that
#: two back-to-back calls agree: the clock, the environment, a file
_HIDDEN_READ_CALLS = {
    "time.time", "time.time_ns", "time.monotonic", "time.monotonic_ns",
    "time.perf_counter", "time.perf_counter_ns", "time.localtime",
    "time.gmtime", "time.ctime", "time.strftime",
    "datetime.now", "datetime.today", "datetime.utcnow", "date.today",
    "datetime.datetime.now", "datetime.datetime.today",
    "datetime.datetime.utcnow", "datetime.date.today",
    "os.getenv", "os.getcwd", "open", "io.open",
}


#: the os.environ methods that only write it
_ENVIRON_WRITERS = frozenset({"update", "clear", "__setitem__", "__delitem__"})


def _dotted(node) -> "str | None":
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _qualified(obj) -> "str | None":
    """The `module.name` of a function or builtin reached through a
    bare name, or None."""
    module = getattr(obj, "__module__", None) or ""
    name = getattr(obj, "__qualname__", None) or getattr(obj, "__name__", "")
    if obj is os.environ:
        return "os.environ"
    if module in ("posix", "nt"):
        module = "os"
    if module == "builtins":
        return name
    return f"{module}.{name}" if module and name else None


def hidden_reads(fn, facts) -> list[str]:
    """Intent:
        The inputs outside its arguments the body reads that two
        back-to-back calls cannot see change: the clock (`time.time`,
        `datetime.now`, ...), the environment (`os.environ`,
        `os.getenv`), the working directory and files (`open`), by the
        name mathema resolves them to, in the order first read.
    """
    from ._signatures import module_scope
    tree = getattr(facts, "tree", None)
    if tree is None:
        return []
    scope = module_scope(fn)
    found: list = []
    # a store into the environment (`os.environ[k] = v`, `del
    # os.environ[k]`, `os.environ.update(...)`) writes it, it reads
    # nothing
    written = {id(n.value) for n in ast.walk(tree)
               if isinstance(n, ast.Subscript)
               and isinstance(n.ctx, (ast.Store, ast.Del))}
    written |= {id(n.func.value) for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in _ENVIRON_WRITERS}

    def add(name):
        if name not in found:
            found.append(name)

    for node in ast.walk(tree):
        if id(node) in written:
            continue
        dotted = _dotted(node) if isinstance(node, (ast.Attribute, ast.Name)) else None
        if dotted is None:
            continue
        head, _, rest = dotted.partition(".")
        target = scope.get(head)
        if target is None:
            continue
        if isinstance(node, ast.Name):
            resolved = _qualified(target)
        else:
            base = getattr(target, "__name__", None) if isinstance(
                target, type(os)) else _qualified(target)
            resolved = f"{base}.{rest}" if base else None
        if resolved is None:
            continue
        if resolved == "os.environ" or (
                resolved.startswith("os.environ.")
                and resolved.rsplit(".", 1)[-1] not in _ENVIRON_WRITERS):
            add("os.environ")
        elif isinstance(node, ast.Attribute) or isinstance(
                getattr(node, "ctx", None), ast.Load):
            if resolved in _HIDDEN_READ_CALLS:
                add(resolved)
    return found
