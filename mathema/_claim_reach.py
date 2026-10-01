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

Every other name runs as written, in the same way as importing it and
calling it directly in the author's own code would. A binding into
third-party code whose effects mathema cannot establish carries a
warning naming it (`third_party_warning`); one into mathema itself, the
author's own project, or a function a trusted compendium covers carries
none.
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
    "sched", "pydoc", "pickletools", "zipapp", "imp",
    # every sympy function reads a string argument through sympify,
    # which evaluates it as Python
    "sympy",
})

#: dotted paths inside otherwise allowed packages that evaluate text as
#: code, load a pickle, read or write files, or reach an attribute by
#: name; a path equal to one of these, or below it, is refused
CODE_RUNNERS = frozenset({
    "operator.attrgetter", "operator.methodcaller", "operator.call",
    "_operator.attrgetter", "_operator.methodcaller", "_operator.call",
    "functools.singledispatch",
    "numpy.load", "numpy.save", "numpy.savez", "numpy.savez_compressed",
    "numpy.savetxt", "numpy.loadtxt", "numpy.genfromtxt",
    "numpy.fromfile", "numpy.memmap", "numpy.ndarray.tofile",
    "numpy.ndarray.dump", "numpy.f2py", "numpy.distutils",
    "numpy.lib.npyio", "numpy.lib.format",
    "numpy.ctypeslib", "numpy.DataSource", "numpy.lib._datasource",
    "pandas.eval", "pandas.read_pickle", "pandas.io",
    "pandas.core.computation", "scipy.io", "polars.io",
    "pandas.DataFrame.eval", "pandas.DataFrame.query",
    "pandas.DataFrame.to_pickle", "pandas.Series.to_pickle",
    "pandas.DataFrame.to_csv", "pandas.Series.to_csv",
    "sympy.sympify", "sympy.parse_expr", "sympy.parsing",
    "sympy.lambdify", "sympy.utilities.lambdify",
    "sympy.core.sympify", "sympy.printing.preview", "sympy.preview",
    "sympy.init_session", "sympy.interactive",
})

#: in the libraries a claim commonly binds, a function of one of these
#: names reads or writes files (`pandas.read_csv`,
#: `pandas.DataFrame.to_parquet`, `polars.DataFrame.write_csv`)
_IO_LIBRARIES = frozenset({"numpy", "pandas", "polars", "scipy"})
_IO_PREFIXES = ("read_", "write_", "scan_", "sink_")
_IO_NAMES = frozenset({
    "to_csv", "to_excel", "to_json", "to_parquet", "to_hdf", "to_sql",
    "to_feather", "to_stata", "to_html", "to_latex", "to_markdown",
    "to_string", "to_xml", "to_orc", "to_clipboard", "to_pickle",
    "load", "save", "dump", "tofile", "fromfile", "loadtxt", "savetxt",
    "genfromtxt", "memmap", "fromregex",
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
    last = parts[-1]
    if parts[0] in _IO_LIBRARIES and len(parts) > 1 and (
            last in _IO_NAMES or last.startswith(_IO_PREFIXES)):
        return (f"`{path}` reaches the system: {last} reads or writes "
                f"files, which a claim may not name")
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
    module = _own_module(target)
    if _top(module) in SYSTEM_MODULES or _below(module, CODE_RUNNERS):
        return (f"`{path}` reaches the system: it comes from the module "
                f"{_shown(module)!r}, which a claim may not name")
    name = getattr(target, "__name__", None)
    if (isinstance(name, str) and _top(module) in _IO_LIBRARIES
            and (name in _IO_NAMES or name.startswith(_IO_PREFIXES))):
        return (f"`{path}` reaches the system: {name} reads or writes "
                f"files, which a claim may not name")
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


#: libraries every function of which has effects mathema establishes:
#: none beyond computing a value from its arguments
_PURE_MODULES = frozenset({"math", "cmath", "statistics"})

#: numpy functions whose effects mathema establishes, called without
#: `out=`: they compute a new value from their arguments and write
#: neither an argument nor process-wide state. Every numpy ufunc is
#: established the same way.
NUMPY_ESTABLISHED = frozenset({
    "abs", "absolute", "all", "allclose", "amax", "amin", "any", "arange",
    "argmax", "argmin", "argsort", "around", "array", "array_equal",
    "asarray", "average", "clip", "concatenate", "convolve", "corrcoef",
    "correlate", "count_nonzero", "cov", "cross", "cumprod", "cumsum",
    "diag", "diagonal", "diff", "dot", "empty_like", "eye", "flip", "full",
    "full_like", "gradient", "hstack", "identity", "inner", "interp",
    "isclose", "kron", "linspace", "logspace", "matmul", "max", "mean",
    "median", "min", "nanmax", "nanmean", "nanmedian", "nanmin",
    "nanpercentile", "nanprod", "nanquantile", "nanstd", "nansum",
    "nanvar", "ones", "ones_like", "outer", "percentile", "polyval",
    "prod", "ptp", "quantile", "ravel", "reshape", "round", "sort",
    "squeeze", "stack", "std", "sum", "tensordot", "trace", "transpose",
    "tril", "triu", "unique", "var", "vdot", "vstack", "where", "zeros",
    "zeros_like",
    "linalg.cholesky", "linalg.cond", "linalg.det", "linalg.eig",
    "linalg.eigh", "linalg.eigvals", "linalg.eigvalsh", "linalg.inv",
    "linalg.lstsq", "linalg.matrix_power", "linalg.matrix_rank",
    "linalg.norm", "linalg.pinv", "linalg.qr", "linalg.slogdet",
    "linalg.solve", "linalg.svd",
})


def _numpy_established(obj) -> bool:
    """Intent:
        Whether `obj` is a numpy ufunc or one of the functions
        `NUMPY_ESTABLISHED` names, by identity, so an alias resolves
        the same way.
    """
    numpy = sys.modules.get("numpy")
    if numpy is None:
        return False
    if isinstance(obj, numpy.ufunc):
        return True
    for name in NUMPY_ESTABLISHED:
        target = numpy
        for attr in name.split("."):
            target = getattr(target, attr, None)
        if target is not None and target is obj:
            return True
    return False


def purity_established(obj, path: str, root: str = ".") -> bool:
    """Intent:
        Whether mathema can establish the effects of the function a
        claim names, that it does nothing beyond computing a value from
        its arguments: a function of math, cmath or statistics, a numpy
        ufunc or a function `NUMPY_ESTABLISHED` names, or a function a
        trusted compendium covers (`trusted_compendium_key`).
    """
    module = _module_of(obj, path)
    if _top(module) in _PURE_MODULES:
        return True
    if _numpy_established(obj):
        return True
    return trusted_compendium_key(obj, path, root)


def trusted_compendium_key(obj, path: str, root: str = ".") -> bool:
    """Intent:
        Whether the function is a key of a trusted compendium: a
        bundled compendium (mathema's own), or a project or dependency
        compendium every row of whose entry for the key the project has
        accepted as trusted (`mathema accept <key> <row> --as trusted`),
        the acceptance not gone stale.
    """
    from .compendium import library_key_of, load_library_claims
    from .spec import load_verified
    try:
        library = load_library_claims(root)
    except Exception:
        return False
    key = path if path in library else None
    if key is None:
        try:
            key = library_key_of(obj)
        except Exception:
            key = None
    info = library.get(key) if key else None
    if info is None:
        return False
    if info.get("bundled"):
        return True
    names = {c.get("name") for c in (info.get("entry") or {}).get("claims")
             or [] if c.get("name")}
    if not names:
        return False
    recorded = {c.get("name"): c for c in
                ((load_verified(root).get(key) or {}).get("entry") or {})
                .get("claims") or []}
    for name in names:
        accepted = (recorded.get(name) or {}).get("accepted") or {}
        if accepted.get("as") != "trusted" or accepted.get("stale"):
            return False
    return True


def _own_module(obj) -> str:
    """Intent:
        The module an object says it belongs to: its `__module__`, else
        the module of the class a method descriptor belongs to
        (`numpy.ndarray.fill` belongs to numpy), else its type's.
    """
    module = getattr(obj, "__module__", None)
    if isinstance(module, str):
        return module
    owner = getattr(obj, "__objclass__", None)
    if owner is not None and isinstance(getattr(owner, "__module__", None),
                                        str):
        return owner.__module__
    return getattr(type(obj), "__module__", "") or ""


def _module_of(obj, path: str) -> str:
    """Intent:
        The module a named function belongs to: its own `__module__`,
        except a wrapper mathema builds around a library method (a
        receiver form of `pandas.Series.mean`), which belongs to the
        library its path names.
    """
    module = _own_module(obj)
    if _top(module) == "mathema" and path and _top(path) != "mathema":
        return path.rsplit(".", 1)[0]
    return module


def _library_file(path: str) -> bool:
    """Intent:
        Whether a source file belongs to an installed library or the
        standard library rather than to a project's own tree.
    """
    import sysconfig
    parts = path.replace("\\", "/").split("/")
    if "site-packages" in parts or "dist-packages" in parts:
        return True
    roots = {sysconfig.get_paths().get(k) for k in ("stdlib", "platstdlib")}
    return any(r and os_path_within(path, r) for r in roots)


def os_path_within(path: str, root: str) -> bool:
    """Whether `path` lies inside the directory `root`."""
    import os
    try:
        return os.path.commonpath([os.path.realpath(path),
                                   os.path.realpath(root)]) \
            == os.path.realpath(root)
    except ValueError:
        return False


def declared_packages(root: str = ".") -> frozenset:
    """Intent:
        The top-level packages a project's pyproject.toml declares as
        its own: the project name (with `-` read as `_`), setuptools'
        `packages`, poetry's `packages` includes and hatch's wheel
        `packages`. Empty when there is no readable pyproject.toml.
    """
    import os
    try:
        import tomllib
    except ImportError:
        return frozenset()
    try:
        with open(os.path.join(root, "pyproject.toml"), "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, ValueError):
        return frozenset()
    out: set = set()
    name = (data.get("project") or {}).get("name")
    if isinstance(name, str):
        out.add(name.replace("-", "_").replace(".", "_"))
    tool = data.get("tool") or {}
    packages = (tool.get("setuptools") or {}).get("packages")
    if isinstance(packages, list):
        out.update(_top(p) for p in packages if isinstance(p, str))
    for item in (tool.get("poetry") or {}).get("packages") or []:
        if isinstance(item, dict) and isinstance(item.get("include"), str):
            out.add(_top(item["include"]))
    hatch = (((tool.get("hatch") or {}).get("build") or {})
             .get("targets") or {}).get("wheel") or {}
    for item in hatch.get("packages") or []:
        if isinstance(item, str):
            out.add(item.rstrip("/").rsplit("/", 1)[-1])
    return frozenset(out)


def is_project_code(obj, own_module: str = "", path: str = "",
                    root: str = ".") -> bool:
    """Intent:
        Whether the function a claim names is mathema itself or the
        author's own project: its module is mathema's, or its top-level
        package is the top-level package of the function under test
        (`own_module`) or one the project's pyproject.toml declares
        (`declared_packages`), and its source is not an installed
        library's.
    """
    module = _module_of(obj, path)
    if _top(module) == "mathema":
        return True
    own = {_top(own_module)} if own_module else set()
    if _top(module) not in (own | declared_packages(root)) - {"builtins"}:
        return False
    mod = sys.modules.get(module)
    source = getattr(mod, "__file__", None) or ""
    return not (source and _library_file(source))


def third_party_warning(binding: str, obj, path: str,
                        own_module: str = "", root: str = ".",
                        writes_argument: bool = False) -> "str | None":
    """Intent:
        The warning a claim's result carries for one binding (`let g =
        json.dumps`) into third-party code whose effects mathema cannot
        establish, or None for mathema itself, the author's own
        project, and a function whose effects are established.
        `writes_argument` (the claim passes `out=`) means its effects
        are not established whatever the function.
    """
    if obj is None or is_project_code(obj, own_module, path, root):
        return None
    if not writes_argument and purity_established(obj, path, root):
        return None
    return (f"{binding} calls third-party code whose effects mathema "
            f"cannot establish, in the same way as importing it and "
            f"calling it directly would")


def call_writes_argument(obj, n_positional: int, keywords) -> bool:
    """Intent:
        Whether one call of `obj` with `n_positional` positional
        arguments and the keyword names `keywords` passes a value to an
        output parameter (`out`), however it is passed: a numpy ufunc
        takes its outputs after its `nin` inputs, any other function is
        bound to its signature. A call that cannot be bound counts as
        writing.
    """
    import inspect
    keywords = set(keywords)
    if "out" in keywords:
        return True
    numpy = sys.modules.get("numpy")
    if numpy is not None and isinstance(obj, numpy.ufunc):
        return n_positional > obj.nin
    try:
        signature = inspect.signature(obj)
    except (TypeError, ValueError):
        return True
    try:
        bound = signature.bind_partial(*range(n_positional),
                                       **dict.fromkeys(keywords))
    except TypeError:
        return True
    return "out" in bound.arguments
