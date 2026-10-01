# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a claim's text may name: a denylist of modules and functions
that reach the system.

A claim names functions by dotted path (`let g = numpy.mean`) and by
bare call name resolved from the function's module. Either way the
named function runs during adjudication, so a name that reaches the
operating system (a process, a file, a socket, the interpreter itself)
would run whatever the claim's text passes it. This module refuses
those names: a module on the denylist, a function that evaluates text
as code or loads a pickle, and anything reached through an allowed
module's attributes (`logging.os.system`, a project module's
`from os import system`).

The denylist is a list, not an isolation boundary: a project function
a claim names runs with the claim's arguments like any other call.
"""
from __future__ import annotations

import sys

#: top-level modules whose functions reach the operating system, the
#: interpreter or the network; a claim may name nothing inside them
SYSTEM_MODULES = frozenset({
    "os", "posix", "nt", "posixpath", "ntpath", "sys", "subprocess",
    "_posixsubprocess", "builtins", "shutil", "socket", "_socket",
    "socketserver", "ssl", "select", "selectors", "importlib", "_imp",
    "_frozen_importlib", "_frozen_importlib_external", "zipimport",
    "pkgutil", "runpy", "site", "sysconfig", "pathlib", "io", "_io",
    "codecs", "fileinput", "linecache", "ctypes", "_ctypes",
    "multiprocessing", "_multiprocessing", "concurrent", "threading",
    "_thread", "signal", "_signal", "pickle", "_pickle", "shelve",
    "dbm", "marshal", "copyreg", "code", "codeop", "compileall",
    "py_compile", "pty", "tty", "termios", "fcntl", "resource", "mmap",
    "tempfile", "glob", "fnmatch", "webbrowser", "antigravity", "this",
    "urllib", "http", "ftplib", "smtplib", "poplib", "imaplib",
    "nntplib", "telnetlib", "xmlrpc", "asyncio", "_asyncio", "gc",
    "inspect", "types", "logging", "timeit", "doctest", "pdb", "bdb",
    "trace", "profile", "cProfile", "atexit", "faulthandler", "zipfile",
    "tarfile", "sqlite3", "platform", "getpass", "pwd", "grp", "tkinter",
    "turtle", "ensurepip", "venv", "distutils", "setuptools", "pip",
    "sched",
})

#: dotted paths inside otherwise allowed packages that evaluate text as
#: code, load a pickle, read or write files, or reach an attribute by
#: name; a path equal to one of these, or below it, is refused
CODE_RUNNERS = frozenset({
    "operator.attrgetter", "operator.methodcaller", "_operator",
    "functools.singledispatch",
    "numpy.load", "numpy.save", "numpy.savez", "numpy.savez_compressed",
    "numpy.savetxt", "numpy.loadtxt", "numpy.genfromtxt",
    "numpy.fromfile", "numpy.memmap", "numpy.ndarray.tofile",
    "numpy.ndarray.dump", "numpy.f2py", "numpy.distutils",
    "numpy.lib.npyio", "numpy.lib.format",
    "pandas.eval", "pandas.read_pickle", "pandas.io",
    "pandas.DataFrame.eval", "pandas.DataFrame.query",
    "pandas.DataFrame.to_pickle", "pandas.Series.to_pickle",
    "pandas.DataFrame.to_csv", "pandas.Series.to_csv",
    "sympy.sympify", "sympy.parse_expr", "sympy.parsing",
    "sympy.lambdify", "sympy.utilities.lambdify",
    "sympy.core.sympify", "sympy.printing.preview", "sympy.preview",
    "sympy.init_session", "sympy.interactive",
})

#: the builtins that run text or reach objects by name, refused by
#: identity however a module exposes them
_RUNNER_BUILTINS = ("eval", "exec", "compile", "open", "input",
                    "breakpoint", "__import__", "getattr", "setattr",
                    "delattr", "globals", "locals", "vars")


class SystemReach(Exception):
    """A name in a claim's text reaches the system; the message names
    the module or the function."""


#: the public module a private implementation module belongs to, as a
#: refusal names it
_PUBLIC_NAME = {
    "posix": "os", "nt": "os", "posixpath": "os", "ntpath": "os",
    "_io": "io", "_socket": "socket", "_thread": "threading",
    "_signal": "signal", "_pickle": "pickle", "_ctypes": "ctypes",
    "_posixsubprocess": "subprocess", "_multiprocessing": "multiprocessing",
    "_asyncio": "asyncio", "_imp": "importlib",
    "_frozen_importlib": "importlib",
    "_frozen_importlib_external": "importlib", "_operator": "operator",
}


def _top(name: str) -> str:
    return name.split(".", 1)[0]


def _shown(module: str) -> str:
    """The module name a refusal shows: the public module for a private
    implementation module (`posix` is shown as `os`)."""
    top = _top(module)
    return _PUBLIC_NAME.get(top, top)


def _below(path: str, prefixes) -> "str | None":
    """Intent:
        The entry of `prefixes` that `path` equals or lies below, or
        None.
    """
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "."):
            return prefix
    return None


def path_refusal(path: str) -> "str | None":
    """Intent:
        Why a dotted path written in a claim's text reaches the system,
        or None when its text alone shows nothing: a dunder segment,
        a first segment on the module denylist, or a path at or below
        a function that runs text as code.
    """
    parts = path.split(".")
    dunder = next((p for p in parts if p.startswith("__")), None)
    if dunder is not None:
        return (f"`{path}` reads the attribute {dunder!r}, which a claim "
                f"may not name")
    if parts[0] in SYSTEM_MODULES:
        return (f"`{path}` reaches the system through the module "
                f"{parts[0]!r}, which a claim may not name")
    runner = _below(path, CODE_RUNNERS)
    if runner is not None:
        return (f"`{path}` reaches the system: {runner} runs text as code "
                f"or reads and writes files, which a claim may not name")
    return None


def _runner_objects() -> list:
    """Intent:
        The live objects the denylisted paths name, for the packages
        already imported; a package not yet imported has none to
        compare against.
    """
    import builtins
    out = [getattr(builtins, name) for name in _RUNNER_BUILTINS
           if hasattr(builtins, name)]
    for path in CODE_RUNNERS:
        parts = path.split(".")
        obj = sys.modules.get(parts[0])
        for attr in parts[1:]:
            if obj is None:
                break
            obj = getattr(obj, attr, None)
        if obj is not None:
            out.append(obj)
    return out


def object_refusal(obj, path: str) -> "str | None":
    """Intent:
        Why the object a claim's name resolved to reaches the system,
        or None: a module on the denylist, an object one of the
        denylisted functions is, or a function defined in a denylisted
        module (`from os import system` re-exported by a project
        module).
    """
    import types
    if isinstance(obj, types.ModuleType):
        name = getattr(obj, "__name__", "") or ""
        if _top(name) in SYSTEM_MODULES or _below(name, CODE_RUNNERS):
            return (f"`{path}` reaches the system through the module "
                    f"{_shown(name)!r}, which a claim may not name")
        return None
    for runner in _runner_objects():
        if obj is runner:
            owner = _shown(getattr(obj, "__module__", None) or "builtins")
            shown = getattr(obj, "__qualname__", None) or repr(obj)
            return (f"`{path}` reaches the system: it is {owner}.{shown}, "
                    f"which runs text as code or reaches the files, which "
                    f"a claim may not name")
    target = getattr(obj, "__func__", obj)
    module = getattr(target, "__module__", None)
    if not isinstance(module, str):
        module = getattr(type(target), "__module__", "") or ""
    if _top(module) in SYSTEM_MODULES:
        return (f"`{path}` reaches the system: it comes from the module "
                f"{_shown(module)!r}, which a claim may not name")
    owner = getattr(obj, "__self__", None)
    if isinstance(owner, types.ModuleType):
        return object_refusal(owner, path)
    return None


def walk_refusal(path: str, root: str = ".") -> "str | None":
    """Intent:
        Why a dotted path reaches the system once resolved: the text
        check, then every object along the walk from the longest
        importable prefix (an allowed module's attribute that is a
        denylisted module, `logging.os`), then the object it names.
        None when nothing on the way reaches the system or the path
        does not resolve.
    """
    import inspect

    said = path_refusal(path)
    if said is not None:
        return said
    from .targets import TargetError, _import_module
    parts = path.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        try:
            obj = _import_module(".".join(parts[:cut]), root)
        except TargetError:
            continue
        except Exception:
            return None
        said = object_refusal(obj, path)
        if said is not None:
            return said
        for attr in parts[cut:]:
            obj = inspect.getattr_static(obj, attr, None)
            if obj is None:
                return None
            if isinstance(obj, (staticmethod, classmethod)):
                obj = obj.__func__
            said = object_refusal(obj, path)
            if said is not None:
                return said
        return None
    return None


def refuse_path(path: str) -> None:
    """Intent:
        Refuse a dotted path written in a claim's text whose text alone
        reaches the system.

    Raises:
        SystemReach: the path reaches the system.
    """
    said = path_refusal(path)
    if said is not None:
        raise SystemReach(said)
