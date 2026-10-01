# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The strict examination of a function's effects, read from its source
without running it: what it writes outside the call, what hidden inputs
it reads, and what it does that cannot be read.

`examine(fn)` walks the body and every project function it reaches
(parsed once and cached; recursion and cycles are followed once), and
returns an `Effects`:

- a **write** is a store, a mutating method or a library call that
  changes something outside the call: an argument, a module-level value,
  a module attribute (`os.environ`, `sys.path`), the process (`os.chdir`,
  `print`), or the shared random generators (a draw from `random` or
  `numpy.random` at module level advances them);
- a **hidden read** is an input the arguments do not carry: the
  environment, the clock, the file system, a module-level value the
  module itself changes, a draw from a shared random generator;
- an **order-sensitive** call is a threaded reduction (a BLAS-backed
  `numpy.dot`, `@`, `numpy.linalg`), whose last bit is not known to be
  the same on every run: determinism cannot be decided past it;
- an **unknown** is anything the examination cannot read: a callee with
  no source and no purity entry, `getattr`, `setattr`, `exec`, `eval`,
  `globals()`, `__dict__`, a call of a function passed in, a method it
  has no entry for on an object from outside the call.

A local name bound to a parameter, a module-level value or a module
attribute (`ys = xs`, `e = os.environ`, `r = random`, an `import` inside
the body) is that same object, so a write through it is a write.
Arithmetic, comparisons and the other operators are read as pure: the
claim's domain fixes the argument types. Emitting a record on a standard
library logger is not a write; configuring logging is.

A generator passed in (`seed_parameter`) is the caller's: a draw from it
is neither a write nor a hidden read here.
"""
from __future__ import annotations

import ast
import builtins
import inspect
import os
import re
import sys
import sysconfig
import textwrap
import types
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Site:
    """One thing the examination found: its kind ("write",
    "hidden_read", "unknown") and the sentence a witness or a note
    shows."""
    kind: str
    text: str


#: marks a label for an object that may come from outside the call
_MAYBE = "\u2063"


@dataclass
class Effects:
    """What a function's body, with the project functions it reaches,
    writes, reads from outside its arguments, and does that cannot be
    read."""
    writes: list = field(default_factory=list)
    hidden_reads: list = field(default_factory=list)
    order_sensitive: list = field(default_factory=list)
    unknowns: list = field(default_factory=list)
    #: module-level names written, as (module, name)
    module_writes: set = field(default_factory=set)
    #: module-level names read whose value other code can change
    module_reads: set = field(default_factory=set)
    #: per site, the branch conditions that enclose it in the examined
    #: function, as (condition source, True for its body, False for its
    #: else), outermost first; a site in a project function it calls
    #: carries the conditions around that call
    guards: dict = field(default_factory=dict)
    #: the branch conditions around the statement being examined
    branch: tuple = ()
    #: writes the function makes to one of its own parameters, as
    #: (parameter, site): a caller decides whether what it passes there
    #: is its own object or one from outside the call
    arg_writes: list = field(default_factory=list)
    #: what the function's result may be: origins in the function's own
    #: terms, ("param", p) for a parameter it hands back, an outside
    #: value, or ("fresh",); `returns_exact` when every return hands
    #: back the same one
    returns: list = field(default_factory=list)
    returns_exact: bool = False
    #: assumptions a proof from this examination rests on
    assumes: set = field(default_factory=set)

    def add(self, site: Site) -> None:
        if _MAYBE in site.text:
            # a write through an object that may or may not come from
            # outside the call cannot be attributed: it is unknown
            site = Site("unknown" if site.kind == "write" else site.kind,
                        site.text.replace(_MAYBE, ""))
        bucket = {"write": self.writes, "hidden_read": self.hidden_reads,
                  "order": self.order_sensitive,
                  "unknown": self.unknowns}[site.kind]
        if site not in bucket:
            bucket.append(site)
            self.guards[site] = self.branch
        elif not self.branch:
            # reached outside every branch as well
            self.guards[site] = ()

    def merge(self, other: "Effects") -> None:
        for site in (*other.writes, *other.hidden_reads,
                     *other.order_sensitive, *other.unknowns):
            self.add(site)
        self.module_writes |= other.module_writes
        self.module_reads |= other.module_reads
        self.assumes |= other.assumes

    def settle(self) -> None:
        """A module-level value both read and written in the call is a
        hidden read: the next call sees what this one left there."""
        for module, name, text in sorted(self.module_reads):
            if (module, name) in self.module_writes:
                self.unknowns = [u for u in self.unknowns if u.text != text]
                self.add(Site("hidden_read", text.replace(
                    ", a value other code can change",
                    ", which the call also changes")))


# --- the purity table --------------------------------------------------------

_PURE_BUILTINS = frozenset({
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "complex", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "hasattr", "hex", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next", "oct",
    "ord", "pow", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "type", "zip", "object", "super",
    "NotImplemented", "Ellipsis", "ValueError", "TypeError", "KeyError",
    "IndexError", "ZeroDivisionError", "ArithmeticError", "OverflowError",
    "RuntimeError", "Exception", "StopIteration", "AttributeError",
    "NotImplementedError", "AssertionError", "LookupError", "property",
    "staticmethod", "classmethod",
})
_UNREADABLE_BUILTINS = {
    "getattr": "getattr", "setattr": "setattr", "delattr": "delattr",
    "exec": "exec", "eval": "eval", "globals": "globals()",
    "vars": "vars()", "locals": "locals()", "__import__": "__import__",
    "compile": "compile",
}
_WRITING_BUILTINS = {"print": "writes to standard output",
                     "input": "reads standard input"}

#: library functions by dotted name: "pure", "read" (a hidden read),
#: "write", or "draw" (a draw from a shared generator: a read and a write)
_LIBRARY = {
    "time.time": "read", "time.time_ns": "read", "time.monotonic": "read",
    "time.monotonic_ns": "read", "time.perf_counter": "read",
    "time.perf_counter_ns": "read", "time.process_time": "read",
    "time.localtime": "read", "time.gmtime": "read", "time.ctime": "read",
    "time.strftime": "read", "time.sleep": "pure",
    "datetime.datetime.now": "read", "datetime.datetime.today": "read",
    "datetime.datetime.utcnow": "read", "datetime.date.today": "read",
    "os.getenv": "read", "os.getcwd": "read", "os.listdir": "read",
    "os.urandom": "read", "os.path.exists": "read", "os.path.isfile": "read",
    "os.path.isdir": "read", "os.path.getsize": "read",
    "os.path.join": "pure", "os.path.basename": "pure",
    "os.path.dirname": "pure", "os.path.splitext": "pure",
    "os.path.split": "pure", "os.path.normpath": "pure",
    "os.chdir": "write", "os.putenv": "write", "os.unsetenv": "write",
    "os.mkdir": "write", "os.makedirs": "write", "os.remove": "write",
    "os.rename": "write", "os.rmdir": "write", "os.umask": "write",
    "os.system": "write", "sys.exit": "write",
    "sys.setrecursionlimit": "write", "sys.getrecursionlimit": "read",
    "random.seed": "write", "random.setstate": "write",
    "random.getstate": "read", "random.Random": "seeded",
    "random.SystemRandom": "read", "uuid.uuid1": "read",
    "uuid.uuid4": "read", "os.getpid": "read",
    "warnings.simplefilter": "write", "warnings.filterwarnings": "write",
    "warnings.warn": "write",
    "logging.basicConfig": "write", "logging.disable": "write",
    "logging.getLogger": "pure",
    "numpy.random.default_rng": "seeded", "numpy.random.RandomState": "seeded",
    "numpy.random.Generator": "pure", "numpy.random.seed": "write",
    "numpy.random.set_state": "write", "numpy.random.get_state": "read",
    "numpy.seterr": "write", "numpy.set_printoptions": "write",
    "numpy.save": "write", "numpy.savetxt": "write", "numpy.load": "read",
    "numpy.loadtxt": "read",
    "numpy.dot": "threaded", "numpy.matmul": "threaded",
    "numpy.vdot": "threaded", "numpy.inner": "threaded",
    "numpy.tensordot": "threaded", "numpy.einsum": "threaded",
    "numpy.copyto": "writes_first", "numpy.put": "writes_first",
    "numpy.place": "writes_first", "numpy.putmask": "writes_first",
    "numpy.fill_diagonal": "writes_first",
    "numpy.put_along_axis": "writes_first",
}
#: numpy submodules whose functions run threaded reductions
_THREADED_MODULES = frozenset({"numpy.linalg"})
#: library functions that return an object other code shares
_SHARED_RESULTS = frozenset({"logging.getLogger", "decimal.getcontext",
                             "sys.modules.get"})
#: whole modules whose functions are pure, by module name
_PURE_MODULES = frozenset({"math", "cmath", "operator", "functools",
                           "itertools", "statistics", "fractions",
                           "decimal", "numbers", "copy", "string",
                           "re", "json", "collections", "typing",
                           "dataclasses", "bisect", "heapq", "abc",
                           "enum", "textwrap"})
#: modules whose functions read fresh entropy or the system
_ENTROPY_MODULES = frozenset({"secrets"})
#: modules whose module-level functions draw from a shared generator
_DRAW_MODULES = frozenset({"random", "numpy.random"})

#: method names that change the object they are called on
_MUTATING_METHODS = frozenset({
    "append", "extend", "insert", "pop", "remove", "clear", "sort",
    "reverse", "update", "setdefault", "popitem", "add", "discard",
    "difference_update", "intersection_update",
    "symmetric_difference_update", "fill", "resize", "put", "itemset",
    "setflags", "partition", "shuffle", "__setitem__", "__delitem__",
    "setLevel", "addHandler", "removeHandler", "addFilter", "removeFilter",
    "setFormatter", "seed", "set_state", "setstate", "write", "writelines",
    "close", "flush", "send", "drop_duplicates_inplace", "scatter", "set",
})
#: method names that read and do not change the object, on any type the
#: claim's domain admits (numbers, strings, containers, arrays, frames)
_READING_METHODS = frozenset({
    "copy", "count", "index", "keys", "values", "items", "get",
    "startswith", "endswith", "lower", "upper", "strip", "lstrip",
    "rstrip", "split", "rsplit", "join", "replace", "find", "rfind",
    "format", "encode", "decode", "isdigit", "isalpha", "isspace",
    "title", "capitalize", "casefold", "zfill", "splitlines", "partition_",
    "is_integer", "conjugate", "real", "imag", "bit_length", "hex",
    "as_integer_ratio", "union", "intersection", "difference",
    "symmetric_difference", "issubset", "issuperset", "isdisjoint",
    "sum", "mean", "std", "var", "min", "max", "prod", "cumsum",
    "cumprod", "argmax", "argmin", "argsort", "any", "all", "round",
    "reshape", "ravel", "flatten", "transpose", "T", "astype", "tolist",
    "dot", "clip", "nonzero", "squeeze", "item", "trace", "diagonal",
    "median", "quantile", "pct_change", "shift", "diff", "rolling",
    "ewm", "expanding", "abs", "isna", "notna", "isnull", "notnull",
    "dropna", "fillna", "head", "tail", "to_numpy", "to_list", "unique",
    "nunique", "value_counts", "groupby", "agg", "aggregate", "describe",
    "sort_values", "sort_index", "reset_index", "set_index", "rename",
    "iloc", "loc", "at", "iat", "shape", "size", "ndim", "dtype", "dtypes",
    "columns", "index", "empty", "sem", "skew", "kurt", "cov", "corr",
    "between", "where", "mask", "duplicated", "drop", "drop_duplicates",
    "assign", "merge", "join_", "concat", "pipe", "map_", "idxmax",
    "idxmin", "first", "last", "nlargest", "nsmallest", "rank",
    "cummax", "cummin", "mode", "apply", "map", "standard_normal",
    "random", "normal", "uniform", "integers", "choice", "gauss",
    "randint", "random_sample", "logpdf", "pdf", "cdf",
    "bit_count", "debug", "info", "warning", "error", "exception",
    "critical", "log", "fatal", "warn", "isEnabledFor", "getEffectiveLevel",
    "hexdigest", "digest",
})
#: draws, on a generator object: reading methods that advance it
_DRAW_METHODS = frozenset({
    "random", "uniform", "gauss", "normalvariate", "choice", "choices",
    "sample", "shuffle", "randint", "randrange", "getrandbits",
    "standard_normal", "normal", "integers", "random_sample", "rand",
    "randn", "permutation", "exponential", "poisson", "binomial",
    "beta", "gamma", "lognormal", "triangular", "betavariate",
    "expovariate", "gammavariate", "lognormvariate", "vonmisesvariate",
    "paretovariate", "weibullvariate",
})
_EMIT_METHODS = frozenset({"debug", "info", "warning", "warn", "error",
                           "exception", "critical", "fatal", "log"})


def _draws_shared_generator(obj) -> bool:
    """Whether `obj` is a method of the process-wide generator of
    `random` or of `numpy.random`'s legacy global state."""
    owner = getattr(obj, "__self__", None)
    if owner is None:
        return False
    stdlib = sys.modules.get("random")
    if stdlib is not None and owner is getattr(stdlib, "_inst", None):
        return True
    mtrand = getattr(sys.modules.get("numpy.random"), "mtrand", None)
    return mtrand is not None and owner is getattr(mtrand, "_rand", None)


def _installed_paths() -> tuple:
    paths = set()
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        found = sysconfig.get_paths().get(key)
        if found:
            paths.add(os.path.abspath(found))
    return tuple(paths)


_INSTALLED = _installed_paths()


def _project_source(fn) -> "ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | None":
    """The parsed definition of a project function (Python source outside
    the standard library and the installed packages), or None."""
    code = getattr(fn, "__code__", None)
    if code is None:
        return None
    path = os.path.abspath(code.co_filename)
    if any(path.startswith(p + os.sep) for p in _INSTALLED):
        return None
    try:
        # the code object's own source: the function's would follow
        # __wrapped__ past a decorator's wrapper
        source = textwrap.dedent(inspect.getsource(code))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda)):
            return node
    return None


def _project_class(cls) -> bool:
    """Whether a class is defined in project source, outside the
    standard library and the installed packages."""
    module = sys.modules.get(getattr(cls, "__module__", "") or "")
    path = getattr(module, "__file__", None)
    if not path:
        return False
    path = os.path.abspath(path)
    return not any(path.startswith(p + os.sep) for p in _INSTALLED)


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
    """`module.name` for a function, class or module reached by name."""
    if isinstance(obj, types.ModuleType):
        return obj.__name__
    if _draws_shared_generator(obj):
        owner = obj.__self__
        stdlib = sys.modules.get("random")
        base = ("random" if stdlib is not None
                and owner is getattr(stdlib, "_inst", None) else "numpy.random")
        return f"{base}.{getattr(obj, '__name__', '')}"
    module = getattr(obj, "__module__", None) or ""
    name = getattr(obj, "__qualname__", None) or getattr(obj, "__name__", "")
    if module in ("posix", "nt"):
        module = "os"
    if module == "builtins":
        return name
    if module.startswith("numpy.random"):
        module = "numpy.random"
    elif module.startswith("numpy.linalg"):
        module = "numpy.linalg"
    elif module.startswith("numpy"):
        module = "numpy"
    if obj is os.environ:
        return "os.environ"
    return f"{module}.{name}" if module and name else None


def _immutable(value) -> bool:
    if isinstance(value, (int, float, complex, str, bytes, bool,
                          type(None), range, frozenset)):
        return True
    if isinstance(value, tuple):
        return all(_immutable(v) for v in value)
    return False


_CACHE: dict = {}


#: library functions that hand back their first argument itself when
#: it is already what they would make (an array of the asked type)
_ALIASING = frozenset({
    "numpy.asarray", "numpy.asanyarray", "numpy.ascontiguousarray",
    "numpy.asfortranarray", "numpy.atleast_1d", "numpy.atleast_2d",
    "numpy.atleast_3d", "numpy.ravel", "numpy.reshape", "numpy.squeeze",
    "numpy.transpose", "numpy.asarray_chkfinite", "numpy.ndarray.view",
})


def _returns_its_argument(qualified: str, node: ast.Call) -> bool:
    """Whether a call of `qualified` may return its first argument
    itself: an aliasing numpy function, or `numpy.array` asked not to
    copy."""
    if qualified in _ALIASING:
        return True
    if qualified == "numpy.array":
        return any(k.arg == "copy" and not (
            isinstance(k.value, ast.Constant) and k.value.value is True)
            for k in node.keywords)
    return False


def _joined(*origins: dict) -> dict:
    """The origins of names after paths that may each have run: a name
    fresh on one path and from outside on another is from outside; two
    different outside origins leave it one that may be either."""
    out: dict = {}
    for name in set().union(*origins):
        seen = [o[name] for o in origins if name in o]
        outside = [o for o in seen if o[0] != "fresh"]
        if not outside:
            out[name] = seen[0]
        elif all(o == outside[0] for o in outside):
            out[name] = outside[0]
        else:
            out[name] = ("may", tuple(dict.fromkeys(outside)))
    return out


def _argument_for(fn, node: ast.Call, param: str, bound=None,
                  constructing: bool = False):
    """The expression a call passes for `param` of `fn`, `bound` for a
    method's first parameter, or None when the call's arguments cannot
    be matched (a starred argument or a `**` mapping)."""
    if any(isinstance(a, ast.Starred) for a in node.args) or any(
            k.arg is None for k in node.keywords):
        return None
    try:
        names = list(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return None
    if bound is not None or constructing:
        if names and names[0] == param:
            return bound
        names = names[1:]
    for keyword in node.keywords:
        if keyword.arg == param:
            return keyword.value
    if param in names and names.index(param) < len(node.args):
        return node.args[names.index(param)]
    try:
        default = inspect.signature(fn).parameters[param].default
    except (TypeError, ValueError, KeyError):
        return None
    if default is inspect.Parameter.empty or _immutable(default):
        return ast.Constant(None)
    # a mutable default is one object every call shares
    return "default"


def _closure_ids(fn) -> tuple:
    """The identities of the values a function closes over: one wrapper
    code shared by many decorated functions is a different function
    for each."""
    out = []
    for cell in getattr(fn, "__closure__", None) or ():
        try:
            out.append(id(cell.cell_contents))
        except ValueError:
            out.append(None)
    return tuple(out)


_MATHEMA_DIR = os.path.dirname(os.path.abspath(__file__))


def _unwrapped(fn):
    """`fn`, or the function a mathema guard decorator wraps: those
    wrappers only check arguments and results, and every other
    decorator's wrapper is examined as the function it is."""
    while True:
        code = getattr(fn, "__code__", None)
        inner = getattr(fn, "__wrapped__", None)
        if inner is None or code is None or not os.path.abspath(
                code.co_filename).startswith(_MATHEMA_DIR + os.sep):
            return fn
        fn = inner


def examine(fn, generator: "str | None" = None,
            constructing: bool = False) -> Effects:
    """Intent:
        The effects of calling `fn`, read from its source and the source
        of every project function it reaches, cached per function.
        `generator` names a parameter that passes in a random generator
        the caller owns, whose draws are neither writes nor hidden reads.
        `constructing` reads `fn` as a class's `__init__`, whose first
        parameter is the object being made.
    """
    key = (getattr(fn, "__code__", fn), _closure_ids(fn), generator,
           constructing)
    if key in _CACHE:
        return _CACHE[key]
    _CACHE[key] = Effects()      # a cycle reaching fn again adds nothing
    found = _Examiner(fn, generator, constructing).run()
    _CACHE[key] = found
    return found


def _own_statements(tree):
    """Every node of a function's body outside the functions and
    classes defined in it."""
    stack = list(tree.body) if isinstance(tree.body, list) else []
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


def _own_returns(tree) -> list:
    return [n for n in _own_statements(tree) if isinstance(n, ast.Return)]


#: method names whose result is part of the object they are called on
_PART_METHODS = frozenset({
    "values", "items", "keys", "get", "__getitem__", "view", "reshape",
    "ravel", "transpose", "squeeze", "setdefault", "pop", "popitem",
    "__iter__", "__next__", "swapaxes", "real", "imag", "diagonal",
})


def _set_of_text(node) -> bool:
    """Whether `node` builds a set or frozenset holding text: a set
    display or comprehension with a string element, or set()/
    frozenset() of a display or a string holding one."""
    def textual(n) -> bool:
        return isinstance(n, ast.Constant) and isinstance(
            n.value, (str, bytes))
    if isinstance(node, ast.Set):
        return any(textual(e) for e in node.elts)
    if isinstance(node, ast.SetComp):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in ("set", "frozenset") and node.args:
        arg = node.args[0]
        if textual(arg):
            return True
        if isinstance(arg, (ast.List, ast.Tuple, ast.Set)):
            return any(textual(e) for e in arg.elts)
        return isinstance(arg, (ast.ListComp, ast.GeneratorExp, ast.SetComp))
    return False


#: calls whose result depends on the order their argument iterates in
_ORDERED_CONSUMERS = frozenset({"iter", "list", "tuple", "enumerate",
                                "next", "zip", "map", "filter", "reversed"})


class _Examiner:
    """One function's examination (see `examine`)."""

    def __init__(self, fn, generator, constructing: bool = False):
        self.constructing = constructing
        self.fn = _unwrapped(fn)
        self.name = getattr(self.fn, "__name__", "f")
        self.generator = generator
        self.effects = Effects()
        self.scope = dict(getattr(self.fn, "__globals__", {}) or {})
        try:
            # the values a nested function closes over read like globals
            self.scope.update(inspect.getclosurevars(self.fn).nonlocals)
        except (TypeError, ValueError):
            pass
        self.module = self.scope.get("__name__", "")
        self.origin: dict = {}      # local name -> ("param", p) | ("global", n)
                                    # | ("value", obj, dotted) | ("fresh",)

    # entry

    def run(self) -> Effects:
        tree = _project_source(self.fn)
        if tree is None:
            self.effects.add(Site("unknown", f"{self.name} has no Python "
                                  f"source mathema can read"))
            return self.effects
        args = tree.args
        params = [a.arg for a in (*args.posonlyargs, *args.args,
                                  *args.kwonlyargs)]
        if args.vararg:
            params.append(args.vararg.arg)
        if args.kwarg:
            params.append(args.kwarg.arg)
        for p in params:
            self.origin[p] = ("param", p)
        if self.constructing and params:
            self.origin[params[0]] = ("fresh",)
        self.declared_global = {n for node in ast.walk(tree)
                                if isinstance(node, ast.Global)
                                for n in node.names}
        self.declared_nonlocal = {n for node in _own_statements(tree)
                                  if isinstance(node, ast.Nonlocal)
                                  for n in node.names}
        self.params = params
        self.text_sets: set = set()
        for p in params:
            try:
                note = str(inspect.signature(self.fn).parameters[p].annotation)
            except (TypeError, ValueError, KeyError):
                note = ""
            if re.search(r"(?:set|Set|frozenset|FrozenSet)\[(?:str|bytes)\]",
                         note):
                self.text_sets.add(p)
        body = tree.body if isinstance(tree.body, list) else [tree.body]
        for stmt in body:
            self.visit(stmt)
        self.effects.settle()
        returned = [self._origin_of(r.value) if r.value is not None
                    else ("fresh",) for r in _own_returns(tree)] if \
            isinstance(tree.body, list) else [self._origin_of(tree.body)]
        self.effects.returns = [o for o in returned if o[0] != "fresh"]
        self.effects.returns_exact = bool(returned) and all(
            o == returned[0] for o in returned) and returned[0][0] != "fresh"
        own = f"{self.name} "
        for site in self.effects.writes:
            if not site.text.startswith(own):
                continue
            for p in params:
                if re.search(rf"its argument {re.escape(p)}\b", site.text):
                    self.effects.arg_writes.append((p, site))
                    break
        return self.effects

    # what a name or expression is

    def _origin_of(self, node):
        """Where the value of `node` comes from: a parameter, a
        module-level value, a library object, or fresh (made in the call)."""
        if isinstance(node, ast.Name):
            if node.id in self.origin:
                return self.origin[node.id]
            if node.id in self.scope:
                value = self.scope[node.id]
                return ("value", value, node.id)
            if hasattr(builtins, node.id):
                return ("value", getattr(builtins, node.id), node.id)
            return ("unresolved", node.id)
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            base = self._origin_of(node.value)
            if base[0] == "value" and isinstance(node, ast.Attribute):
                try:
                    obj = getattr(base[1], node.attr)
                except Exception:
                    return ("value", None, f"{base[2]}.{node.attr}")
                return ("value", obj, f"{base[2]}.{node.attr}")
            if base[0] == "value" and isinstance(node, ast.Subscript):
                return ("value", None, f"{base[2]}[...]")
            if base[0] == "holds":
                return ("may", base[1])
            return base
        if isinstance(node, ast.Call):
            return self._call_origin(node)
        if isinstance(node, ast.NamedExpr):
            return self._origin_of(node.value)
        if isinstance(node, ast.Lambda):
            return ("local_fn",)
        if isinstance(node, ast.IfExp):
            return _joined({"v": self._origin_of(node.body)},
                           {"v": self._origin_of(node.orelse)})["v"]
        if isinstance(node, ast.BoolOp):
            return _joined(*({"v": self._origin_of(v)}
                             for v in node.values))["v"]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            parts = node.values if isinstance(node, ast.Dict) else node.elts
            held = tuple(dict.fromkeys(
                o for o in (self._origin_of(e) for e in parts if e is not None)
                if self._outside(o) is not None))
            return ("holds", held) if held else ("fresh",)
        return ("fresh",)

    def _part_of(self, origin):
        """The origin of an element or a part of an object of `origin`:
        a part of an object from outside the call is outside it too, a
        part of a fresh container holding outside objects may be one."""
        if origin[0] == "holds":
            return ("may", origin[1])
        if origin[0] in ("param", "global", "element"):
            return ("element", origin) if origin[0] != "element" else origin
        if origin[0] == "value" and self._outside(origin) is not None:
            return ("element", origin)
        if origin[0] == "may":
            return origin
        return ("fresh",)

    def _call_origin(self, node: ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            owner = self._origin_of(func.value)
            if not (owner[0] == "value" and isinstance(
                    owner[1], (types.ModuleType, type))):
                if func.attr in ("reshape", "ravel", "view", "T", "transpose",
                                 "squeeze", "__getitem__", "__iter__"):
                    return owner
                if func.attr in _PART_METHODS:
                    return self._part_of(owner)
        callee = self._origin_of(func)
        if callee[0] == "value" and isinstance(callee[1], types.FunctionType) \
                and _project_source(callee[1]) is not None:
            return self._returned(callee[1], node)
        if callee[0] == "value" and _qualified(callee[1]) in _SHARED_RESULTS:
            # the call returns an object other code holds too
            return ("value", None, self._shown(node))
        if callee[0] == "value" and node.args and _returns_its_argument(
                _qualified(callee[1]) or "", node):
            # an array already of the asked type comes back as itself
            return self._origin_of(node.args[0])
        return ("fresh",)

    def _returned(self, fn, node: ast.Call):
        """The origin of what a call of project function `fn` returns:
        the argument passed for a parameter it hands back, an outside
        value it hands back, else fresh."""
        found = examine(fn)
        mapped = []
        for origin in found.returns:
            if origin[0] == "param":
                arg = _argument_for(fn, node, origin[1])
                if arg is None or arg == "default":
                    mapped.append(("opaque", f"what {fn.__name__} returns"))
                else:
                    mapped.append(self._origin_of(arg))
            elif origin[0] in ("value", "global"):
                mapped.append(origin)
            else:
                mapped.append(("opaque", f"what {fn.__name__} returns"))
        outside = [o for o in mapped if self._outside(o) is not None]
        if not outside:
            return ("fresh",)
        if found.returns_exact and len(outside) == 1:
            return outside[0]
        return ("may", tuple(dict.fromkeys(outside)))

    def _shown(self, node) -> str:
        try:
            return ast.unparse(node)
        except Exception:
            return "an expression"

    def _outside(self, origin) -> "str | None":
        """What a write through an object of this origin changes, or None
        for an object made in the call."""
        kind = origin[0]
        if kind == "element":
            inner = self._outside(origin[1])
            if inner is None:
                return None
            if inner.startswith(_MAYBE):
                return inner
            return f"an element of {inner}"
        if kind == "may":
            labels = [lab for lab in (self._outside(o) for o in origin[1])
                      if lab is not None]
            if not labels:
                return None
            return (_MAYBE + "an object that may be "
                    + " or ".join(dict.fromkeys(
                        lab.replace(_MAYBE, "").replace(
                            "an object that may be ", "") for lab in labels)))
        if kind == "opaque":
            return _MAYBE + origin[1]
        if kind == "param":
            if origin[1] == self.generator:
                return None
            if self._shared_default(origin[1]):
                return (f"its argument {origin[1]}, whose default every "
                        f"call that leaves it out shares")
            return f"its argument {origin[1]}"
        if kind == "global":
            return f"the module-level {origin[1]}"
        if kind == "value":
            value, shown = origin[1], origin[2]
            if isinstance(value, type) and not shown.endswith("]") and \
                    _project_class(value):
                return f"the class {shown}"
            if isinstance(value, (types.FunctionType, types.BuiltinFunctionType,
                                  type)) and not shown.endswith("]"):
                return None
            if shown.startswith("os.environ"):
                return "os.environ"
            if isinstance(value, types.ModuleType):
                return f"the module {shown}"
            if "." not in shown and "[" not in shown:
                return f"the module-level {shown}"
            return shown
        return None

    # statements

    def visit(self, node) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self._bind_import(node)
            return
        if isinstance(node, ast.Assign):
            if not (isinstance(node.value, (ast.Name, ast.Attribute))
                    and _dotted(node.value) is not None):
                # binding a name to an object is not a read of it
                self.expr(node.value)
            for target in node.targets:
                self._store(target, node.value)
            return
        if isinstance(node, ast.AnnAssign):
            if node.value is not None:
                self.expr(node.value)
                self._store(node.target, node.value)
            return
        if isinstance(node, ast.AugAssign):
            self.expr(node.value)
            self._augmented(node)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._nested(node.name, node.args, node.body)
            self.origin[node.name] = ("local_fn",)
            return
        if isinstance(node, ast.Delete):
            for target in node.targets:
                if isinstance(target, (ast.Subscript, ast.Attribute)):
                    self._write_through(target, f"del {self._shown(target)}")
            return
        if isinstance(node, ast.If):
            self.expr(node.test)
            test = ast.unparse(node.test)
            outer = self.effects.branch
            before = dict(self.origin)
            after = []
            for taken, stmts in ((True, node.body), (False, node.orelse)):
                self.origin = dict(before)
                self.effects.branch = (*outer, (test, taken))
                for stmt in stmts:
                    self.visit(stmt)
                after.append(self.origin)
            self.effects.branch = outer
            self.origin = _joined(*after)
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self.expr(node.iter)
            self._iterated(node.iter)
            before = dict(self.origin)
            self._bind(node.target, self._part_of(self._origin_of(node.iter)))
            for stmt in (*node.body, *node.body, *node.orelse):
                # twice: a name the body rebinds late is what an early
                # statement sees on the next pass
                self.visit(stmt)
            self.origin = _joined(before, self.origin)
            return
        if isinstance(node, ast.While):
            self.expr(node.test)
            before = dict(self.origin)
            for stmt in (*node.body, *node.body, *node.orelse):
                self.visit(stmt)
            self.origin = _joined(before, self.origin)
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                self.expr(item.context_expr)
                if item.optional_vars is not None:
                    self._bind(item.optional_vars,
                               self._entered(item.context_expr))
            for stmt in node.body:
                self.visit(stmt)
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                self.visit(child)
            elif isinstance(child, ast.expr):
                self.expr(child)
            elif isinstance(child, ast.excepthandler):
                for stmt in child.body:
                    self.visit(stmt)
            else:
                for sub in ast.iter_child_nodes(child):
                    if isinstance(sub, ast.stmt):
                        self.visit(sub)
                    elif isinstance(sub, ast.expr):
                        self.expr(sub)

    def _bind_import(self, node) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = sys.modules.get(alias.name)
                top = alias.asname or alias.name.split(".")[0]
                value = module if alias.asname else sys.modules.get(
                    alias.name.split(".")[0], module)
                self.origin[top] = ("value", value, alias.name if alias.asname
                                    else alias.name.split(".")[0])
            return
        module = sys.modules.get(node.module or "")
        for alias in node.names:
            value = getattr(module, alias.name, None) if module else None
            if value is None:
                value = sys.modules.get(f"{node.module}.{alias.name}")
            self.origin[alias.asname or alias.name] = (
                "value", value, f"{node.module}.{alias.name}")

    def _nested(self, name: str, args, body) -> None:
        """Examine a function or lambda defined in the body where it
        stands: its parameters receive whatever a caller passes, and
        the names it binds are its own."""
        before = dict(self.origin)
        for a in (*args.posonlyargs, *args.args, *args.kwonlyargs,
                  *([args.vararg] if args.vararg else []),
                  *([args.kwarg] if args.kwarg else [])):
            self.origin[a.arg] = ("opaque", f"an argument passed to {name}")
        for default in (*args.defaults, *args.kw_defaults):
            if default is not None:
                self.expr(default)
        if isinstance(body, list):
            for stmt in body:
                self.visit(stmt)
        else:
            self.expr(body)
        self.origin = before

    def _entered(self, node):
        """The origin of what `with node as name` binds: the object
        itself for one from outside the call, what a project context
        manager yields (which mathema does not follow), else fresh."""
        if isinstance(node, ast.Call):
            callee = self._origin_of(node.func)
            if callee[0] == "value" and (
                    isinstance(callee[1], types.FunctionType)
                    and _project_source(callee[1]) is not None
                    or isinstance(callee[1], type)
                    and _project_class(callee[1])):
                return ("opaque", f"what {self._shown(node)} yields")
            return ("fresh",)
        origin = self._origin_of(node)
        return origin if self._outside(origin) is not None else ("fresh",)

    def _iterated(self, node) -> None:
        """An iteration of `node` whose order reaches the result: a set
        of strings iterates in an order that changes from one process
        to the next."""
        if _set_of_text(node) or isinstance(node, ast.Name) and \
                node.id in self.text_sets:
            self.effects.add(Site("order", f"{self.name} iterates "
                                  f"{self._shown(node)}: the iteration order "
                                  f"of a set of strings varies across "
                                  f"processes"))

    def _bind(self, target, origin) -> None:
        if isinstance(target, ast.Name) and target.id in \
                self.declared_nonlocal:
            self.effects.add(Site("write", f"{self.name} rebinds "
                                  f"{target.id}, a variable of the function "
                                  f"that encloses it"))
            return
        if isinstance(target, ast.Name):
            if target.id in self.declared_global:
                self.effects.module_writes.add((self.module, target.id))
                self.effects.add(Site("write", f"{self.name} rebinds the "
                                      f"module-level {target.id}"))
                return
            self.origin[target.id] = origin
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._bind(element.value if isinstance(element, ast.Starred)
                           else element, self._part_of(origin))

    def _target_parts(self, target) -> None:
        """Read the expressions inside an assignment target (an index, a
        call in the chain), never the stored-to object itself."""
        node = target
        while isinstance(node, (ast.Subscript, ast.Attribute)):
            if isinstance(node, ast.Subscript):
                self.expr(node.slice)
            node = node.value
        if not isinstance(node, ast.Name):
            self.expr(node)

    def _store(self, target, value) -> None:
        if isinstance(target, (ast.Subscript, ast.Attribute)):
            self._target_parts(target)
            self._write_through(target, f"{self._shown(target)} = ...")
            return
        if isinstance(target, ast.Name):
            if _set_of_text(value) or isinstance(value, ast.Name) and \
                    value.id in self.text_sets:
                self.text_sets.add(target.id)
            else:
                self.text_sets.discard(target.id)
            self._bind(target, self._origin_of(value))
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(
                    value.elts) == len(target.elts) and not any(
                    isinstance(e, ast.Starred)
                    for e in (*value.elts, *target.elts)):
                for element, part in zip(target.elts, value.elts):
                    self._store(element, part)
                return
            for element in target.elts:
                inner = element.value if isinstance(
                    element, ast.Starred) else element
                if isinstance(inner, ast.Name):
                    self._bind(inner, self._part_of(self._origin_of(value)))
                else:
                    self._store(inner, ast.Constant(None))

    def _augmented(self, node: ast.AugAssign) -> None:
        target = node.target
        if isinstance(target, (ast.Subscript, ast.Attribute)):
            self._target_parts(target)
            root = target
            while isinstance(root, (ast.Subscript, ast.Attribute)):
                root = root.value
            if isinstance(root, ast.Name):
                self._load(root)          # x[i] += 1 reads x[i] first
            self._write_through(target, self._shown(node))
            return
        if isinstance(target, ast.Name):
            if target.id in self.declared_global:
                self.effects.add(Site("write", f"{self.name} rebinds the "
                                      f"module-level {target.id}"))
                return
            if target.id in self.declared_nonlocal:
                self._bind(target, ("fresh",))
                return
            origin = self.origin.get(target.id)
            if origin and origin[0] == "param" and isinstance(
                    node.op, (ast.Add, ast.Mult, ast.BitOr)) and \
                    self._mutable_param(origin[1]):
                self.effects.add(Site("write", f"{self.name} changes its "
                                      f"argument {origin[1]} in place "
                                      f"({self._shown(node)})"))
            else:
                self.origin[target.id] = ("fresh",)

    def _shared_default(self, name: str) -> bool:
        """Whether parameter `name` defaults to one mutable object."""
        try:
            default = inspect.signature(self.fn).parameters[name].default
        except (TypeError, ValueError, KeyError):
            return False
        return default is not inspect.Parameter.empty and \
            not _immutable(default)

    def _mutable_param(self, name: str) -> bool:
        annotation = None
        try:
            annotation = inspect.signature(self.fn).parameters[name].annotation
        except (TypeError, ValueError, KeyError):
            pass
        if annotation in (int, float, complex, str, bool, bytes, tuple):
            return False
        text = str(annotation)
        return not any(word in text for word in ("float", "int", "str",
                                                 "complex", "tuple"))

    def _note_module_write(self, origin) -> None:
        if origin[0] == "value" and "." not in origin[2] \
                and "[" not in origin[2]:
            self.effects.module_writes.add((self.module, origin[2]))

    def _write_through(self, target, shown: str) -> None:
        origin = self._origin_of(target.value if isinstance(
            target, (ast.Subscript, ast.Attribute)) else target)
        self._note_module_write(origin)
        changed = self._outside(origin)
        if origin[0] == "unresolved":
            self.effects.add(Site("unknown", f"{self.name} writes through "
                                  f"{origin[1]}, a name mathema cannot "
                                  f"resolve"))
        elif changed is not None:
            self.effects.add(Site("write", f"{self.name} changes {changed} "
                                  f"({shown})"))

    # expressions

    def expr(self, node) -> None:
        if isinstance(node, ast.Lambda):
            self._nested("a lambda", node.args, node.body)
            return
        if isinstance(node, ast.Call):
            self.call(node)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            self._load(node)
            return
        if isinstance(node, ast.Attribute):
            if node.attr == "__dict__":
                self.effects.add(Site("unknown", f"{self.name} reads "
                                      f"{self._shown(node)}"))
            origin = self._origin_of(node)
            if origin[0] == "value" and origin[2] == "os.environ":
                self.effects.add(Site("hidden_read", f"{self.name} reads "
                                      f"os.environ"))
                return
            self.expr(node.value)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp,
                             ast.DictComp)):
            before = dict(self.origin)
            for gen in node.generators:
                self.expr(gen.iter)
                if not isinstance(node, ast.SetComp):
                    self._iterated(gen.iter)
                self._bind(gen.target, self._part_of(
                    self._origin_of(gen.iter)))
                for cond in gen.ifs:
                    self.expr(cond)
            if isinstance(node, ast.DictComp):
                self.expr(node.key)
                self.expr(node.value)
            else:
                self.expr(node.elt)
            self.origin = before
            return
        if isinstance(node, ast.NamedExpr):
            self.expr(node.value)
            self._bind(node.target, self._origin_of(node.value))
            return
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.MatMult):
            self.effects.add(Site("order", f"{self.name} computes "
                                  f"{self._shown(node)}, a threaded reduction "
                                  f"whose last bit is not known to be the "
                                  f"same on every run"))
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self.expr(child)
            elif isinstance(child, ast.comprehension):
                self.expr(child.iter)

    def _load(self, node: ast.Name) -> None:
        if node.id in self.origin:
            origin = self.origin[node.id]
            if origin[0] == "value":
                self._read_value(origin[1], origin[2])
            return
        if node.id in self.scope:
            self._read_value(self.scope[node.id], node.id)
            return
        if hasattr(builtins, node.id):
            return
        self.effects.add(Site("unknown", f"{self.name} uses {node.id}, a "
                              f"name mathema cannot resolve"))

    def _read_value(self, value, shown: str) -> None:
        """A read of a value from outside the call: the environment is a
        hidden read, a module, function, class, constant or logger is
        not, and any other module-level value is one other code can
        change."""
        import logging
        if value is os.environ or shown.startswith("os.environ"):
            self.effects.add(Site("hidden_read", f"{self.name} reads "
                                  f"os.environ"))
            return
        if isinstance(value, (types.ModuleType, type)) or callable(value):
            if isinstance(value, types.FunctionType):
                self._reach(value)
            return
        if _immutable(value) or isinstance(
                value, (logging.Logger, logging.LoggerAdapter)):
            return
        if "." in shown or "[" in shown:
            return          # an attribute of a module, judged where called
        if shown in self.declared_global:
            self.effects.add(Site("hidden_read", f"{self.name} reads the "
                                  f"module-level {shown}, which it also "
                                  f"changes"))
            return
        text = (f"{self.name} reads the module-level {shown}, a value "
                f"other code can change")
        self.effects.module_reads.add((self.module, shown, text))
        self.effects.add(Site("unknown", text))

    def _reach(self, fn, node: "ast.Call | None" = None,
               bound=None, constructing: bool = False) -> None:
        """Examine a project function this body reaches, and merge it.
        At a call (`node`), a write the callee makes to one of its own
        parameters is a write here only when the argument passed there
        is not an object this call made; `bound` is the expression a
        method is called on, the first parameter of the callee."""
        if _project_source(fn) is None:
            self._library(fn, _qualified(fn) or getattr(fn, "__name__", "?"),
                          None)
            return
        found = examine(fn, constructing=constructing)
        if node is None:
            self.effects.merge(found)
            return
        passed = {site for _p, site in found.arg_writes}
        for site in (*found.writes, *found.hidden_reads,
                     *found.order_sensitive, *found.unknowns):
            if site not in passed:
                self.effects.add(site)
        self.effects.module_writes |= found.module_writes
        self.effects.assumes |= found.assumes
        self.effects.module_reads |= found.module_reads
        callee = getattr(fn, "__name__", "f")
        for p, site in found.arg_writes:
            arg = _argument_for(fn, node, p, bound, constructing)
            if arg is None:
                self.effects.add(Site("unknown", f"{self.name} calls "
                                      f"{callee} with arguments mathema "
                                      f"cannot match to its parameters, "
                                      f"and {site.text}"))
                continue
            if arg == "default":
                self.effects.add(Site("write", f"{self.name} calls {callee} "
                                      f"without {p}, and {site.text}, the "
                                      f"default every call shares"))
                continue
            changed = self._outside(self._origin_of(arg))
            if changed is not None:
                self._note_module_write(self._origin_of(arg))
                self.effects.add(Site("write", f"{self.name} passes "
                                      f"{changed} to {callee}, and "
                                      f"{site.text}"))

    def call(self, node: ast.Call) -> None:
        for arg in node.args:
            self.expr(arg)
        for keyword in node.keywords:
            self.expr(keyword.value)
        func = node.func
        if isinstance(func, ast.Name) and func.id in _ORDERED_CONSUMERS \
                and node.args and func.id not in self.origin:
            self._iterated(node.args[0])
        if isinstance(func, ast.Attribute) and func.attr in ("join", "pop") \
                and (node.args or func.attr == "pop"):
            self._iterated(node.args[0] if func.attr == "join"
                           else func.value)
        if isinstance(func, ast.Name):
            name = func.id
            if name in self.origin:
                origin = self.origin[name]
                if origin[0] == "param":
                    if origin[1] != self.generator:
                        self.effects.add(Site("unknown", f"{self.name} calls "
                                              f"its argument {name}"))
                    return
                if origin[0] == "value":
                    self._callee(origin[1], origin[2], node)
                    return
                if origin[0] != "local_fn":
                    self.effects.add(Site("unknown", f"{self.name} calls "
                                          f"{name}, an object mathema cannot "
                                          f"follow"))
                return
            if name in ("hash", "id") and name not in self.scope:
                self.effects.add(Site("order", f"{self.name} calls {name}(), "
                                      f"whose value for a string, bytes or an "
                                      f"object varies across processes"))
                return
            if name in _UNREADABLE_BUILTINS and name not in self.scope:
                self.effects.add(Site("unknown", f"{self.name} calls "
                                      f"{_UNREADABLE_BUILTINS[name]}, which "
                                      f"mathema cannot read"))
                return
            if name in _WRITING_BUILTINS and name not in self.scope:
                kind = "write" if name == "print" else "hidden_read"
                self.effects.add(Site(kind, f"{self.name} calls {name}(), "
                                      f"which {_WRITING_BUILTINS[name]}"))
                return
            if name == "open" and name not in self.scope:
                self._open(node)
                return
            if name in self.scope:
                self._callee(self.scope[name], name, node)
                return
            if name in _PURE_BUILTINS:
                return
            if hasattr(builtins, name):
                self.effects.add(Site("unknown", f"{self.name} calls "
                                      f"{name}, which mathema has no entry "
                                      f"for"))
                return
            self.effects.add(Site("unknown", f"{self.name} calls {name}, a "
                                  f"name mathema cannot resolve"))
            return
        if isinstance(func, ast.Attribute):
            self.expr(func.value)
            owner = self._origin_of(func.value)
            if owner[0] == "value" and isinstance(
                    owner[1], (types.ModuleType, type)):
                try:
                    callee = getattr(owner[1], func.attr)
                except Exception:
                    callee = None
                if callee is not None:
                    self._callee(callee, f"{owner[2]}.{func.attr}", node,
                                 owner=owner)
                    return
            self._method(owner, func.attr, node)
            return
        self.expr(func)
        self.effects.add(Site("unknown", f"{self.name} calls "
                              f"{self._shown(func)}, which mathema cannot "
                              f"read"))

    def _seedless_draw(self, owner, method: str, node: ast.Call) -> None:
        """A table or series method that draws at random when no seed is
        given: pandas `sample` (`random_state`), polars `sample` and
        `shuffle` (`seed`), and a rank that breaks ties at random."""
        seeded = any(k.arg in ("random_state", "seed") and not (
            isinstance(k.value, ast.Constant) and k.value.value is None)
            for k in node.keywords)
        if seeded or owner[0] == "param" and owner[1] == self.generator:
            return
        if method == "rank" and any(
                k.arg == "method" and isinstance(k.value, ast.Constant)
                and k.value.value == "random" for k in node.keywords):
            self.effects.add(Site("hidden_read", f"{self.name} ranks ties "
                                  f"at random with no seed "
                                  f"({self._shown(node)})"))
            return
        if method == "sample" and owner[0] != "value":
            self.effects.add(Site("unknown", f"{self.name} calls "
                                  f"{self._shown(node.func)} with no seed, "
                                  f"which draws from a shared random "
                                  f"generator when {self._shown(node.func.value)}"
                                  f" is a table or a series"))

    def _open(self, node: ast.Call) -> None:
        mode = node.args[1] if len(node.args) > 1 else next(
            (k.value for k in node.keywords if k.arg == "mode"), None)
        text = mode.value if isinstance(mode, ast.Constant) else "r"
        if not isinstance(text, str) or any(c in text for c in "wax+"):
            self.effects.add(Site("write", f"{self.name} opens a file for "
                                  f"writing"))
        else:
            self.effects.add(Site("hidden_read", f"{self.name} reads a "
                                  f"file"))

    def _callee(self, obj, shown: str, node: ast.Call, owner=None) -> None:
        if isinstance(obj, types.FunctionType):
            self._reach(obj, node)
            self._out_keyword(node)
            return
        if isinstance(obj, type) and not issubclass(obj, BaseException) and \
                _project_source(getattr(obj, "__init__", None)) is not None:
            # a project class: constructing it runs its __init__
            self._reach(obj.__init__, node, constructing=True)
            return
        if isinstance(obj, type) and getattr(obj, "__init__", None) is \
                object.__init__ and obj.__module__ not in ("builtins",):
            return
        if isinstance(obj, types.MethodType) and isinstance(
                getattr(obj, "__func__", None), types.FunctionType) and \
                _project_source(obj.__func__) is not None:
            self._reach(obj.__func__, node,
                        bound=node.func.value if isinstance(
                            node.func, ast.Attribute) else None)
            return
        self._library(obj, _qualified(obj) or shown, node, shown=shown,
                      owner=owner)

    def _out_keyword(self, node) -> None:
        if node is None:
            return
        for keyword in node.keywords:
            if keyword.arg == "out":
                changed = self._outside(self._origin_of(keyword.value))
                if changed is not None:
                    self.effects.add(Site("write", f"{self.name} writes "
                                          f"its result into {changed} "
                                          f"(out=)"))
            if keyword.arg == "overwrite_input" and node.args and not (
                    isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False):
                changed = self._outside(self._origin_of(node.args[0]))
                if changed is not None:
                    self.effects.add(Site("write", f"{self.name} lets "
                                          f"{self._shown(node.func)} reorder "
                                          f"{changed} (overwrite_input=True)"))
            if keyword.arg in ("inplace", "in_place") and not (
                    isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False):
                origin = self._origin_of(node.func.value) if isinstance(
                    node.func, ast.Attribute) else ("fresh",)
                changed = self._outside(origin)
                if changed is not None:
                    self.effects.add(Site("write", f"{self.name} changes "
                                          f"{changed} in place "
                                          f"({keyword.arg}=True)"))

    def _library(self, obj, qualified: str, node, shown: "str | None" = None,
                 owner=None) -> None:
        import logging
        self._out_keyword(node)
        entry = _LIBRARY.get(qualified)
        module = qualified.rsplit(".", 1)[0] if "." in qualified else ""
        if entry is None and isinstance(obj, type) and issubclass(
                obj, BaseException):
            return
        if entry is None and owner is not None and isinstance(
                owner[1], (logging.Logger, logging.LoggerAdapter)):
            method = qualified.rsplit(".", 1)[-1]
            if method in _EMIT_METHODS:
                self._emission(owner[1], method)
                return
            entry = "write" if method in _MUTATING_METHODS else None
        if entry is None and _draws_shared_generator(obj):
            entry = "draw"
        if entry is None:
            if module in _DRAW_MODULES:
                entry = "draw"
            elif module in _THREADED_MODULES:
                entry = "threaded"
            elif module in _ENTROPY_MODULES:
                entry = "read"
            elif module in _PURE_MODULES or module.split(".")[0] in \
                    _PURE_MODULES:
                entry = "pure"
            elif module == "numpy" or (module.startswith("numpy.")
                                       and not module.startswith("numpy.random")):
                entry = "pure"
            elif module == "builtins" or qualified in _PURE_BUILTINS:
                entry = "pure"
        if module == "numpy" or module.startswith("numpy."):
            # every numpy ufunc reads the floating-point error state
            # np.seterr sets: under all="raise", np.log(0) raises
            self.effects.assumes.add("numpy's default error state")
        name = qualified if "." in qualified else (shown or qualified)
        if qualified.rsplit(".", 1)[-1] in ("shuffle",) and node is not None \
                and node.args:
            changed = self._outside(self._origin_of(node.args[0]))
            if changed is not None:
                self.effects.add(Site("write", f"{self.name} changes "
                                      f"{changed} ({self._shown(node)})"))
        if entry == "writes_first":
            changed = (self._outside(self._origin_of(node.args[0]))
                       if node is not None and node.args else None)
            if changed is not None:
                self.effects.add(Site("write", f"{self.name} changes "
                                      f"{changed} ({self._shown(node)})"))
            return
        if entry == "pure":
            return
        if entry == "seeded":
            if node is not None and not node.args and not node.keywords:
                self.effects.add(Site("hidden_read", f"{self.name} calls "
                                      f"{name}() with no seed, which reads "
                                      f"fresh entropy"))
            return
        if entry == "threaded":
            self.effects.add(Site("order", f"{self.name} calls {name}, a "
                                  f"threaded reduction whose last bit is not "
                                  f"known to be the same on every run"))
            return
        if entry == "read":
            self.effects.add(Site("hidden_read", f"{self.name} calls {name}, "
                                  f"which reads an input its arguments do "
                                  f"not carry"))
            return
        if entry == "write":
            self.effects.add(Site("write", f"{self.name} calls {name}, which "
                                  f"changes process-wide state"))
            return
        if entry == "draw":
            self.effects.add(Site("hidden_read", f"{self.name} draws from the "
                                  f"shared random generator ({name})"))
            self.effects.add(Site("write", f"{self.name} advances the shared "
                                  f"random generator ({name})"))
            return
        self.effects.add(Site("unknown", f"{self.name} calls {name}, which "
                              f"mathema has no purity entry for"))

    def _emission(self, logger, method: str) -> None:
        """A log record emitted on `logger`: the standard library's own
        logging code changes nothing; an override of the emission path
        on the logger's class, or a handler, filter or formatter it
        reaches, is examined when it is project code and unknown
        otherwise."""
        import logging
        base = (logging.LoggerAdapter if isinstance(logger, logging.LoggerAdapter)
                else logging.Logger)
        path = ((method, "process", "log", "isEnabledFor")
                if base is logging.LoggerAdapter else
                (method, "_log", "handle", "callHandlers", "makeRecord",
                 "isEnabledFor", "filter"))
        for name in path:
            attr = getattr(type(logger), name, None)
            if attr is not None and attr is not getattr(base, name, None):
                self._user_logging_code(attr, f"{type(logger).__name__}.{name}")
        if base is logging.LoggerAdapter:
            self._emission(logger.logger, "log")
            return
        current = logger
        while current is not None:
            for item in (*getattr(current, "filters", ()),
                         *getattr(current, "handlers", ())):
                self._logging_part(item)
                for nested in (*getattr(item, "filters", ()),
                               getattr(item, "formatter", None)):
                    if nested is not None:
                        self._logging_part(nested)
            if not getattr(current, "propagate", False):
                break
            current = current.parent

    def _logging_part(self, part) -> None:
        if type(part).__module__.split(".")[0] == "logging":
            return
        for name in ("emit", "handle", "filter", "format"):
            attr = getattr(type(part), name, None)
            if attr is not None and getattr(attr, "__module__", "").split(
                    ".")[0] != "logging":
                self._user_logging_code(attr, f"{type(part).__name__}.{name}")

    def _user_logging_code(self, attr, shown: str) -> None:
        if isinstance(attr, types.FunctionType) and \
                _project_source(attr) is not None:
            self.effects.merge(examine(attr))
            return
        self.effects.add(Site("unknown", f"{self.name} emits a log record "
                              f"that reaches {shown}, which mathema cannot "
                              f"read"))

    def _method(self, owner, method: str, node: ast.Call) -> None:
        import logging
        self._out_keyword(node)
        self._seedless_draw(owner, method, node)
        if owner[0] == "fresh":
            return
        if owner[0] == "value" and isinstance(
                owner[1], (logging.Logger, logging.LoggerAdapter)):
            if method in _EMIT_METHODS:
                self._emission(owner[1], method)
            elif method in _MUTATING_METHODS:
                self.effects.add(Site("write", f"{self.name} changes "
                                      f"{owner[2]} ({self._shown(node)})"))
            elif method not in _READING_METHODS:
                self.effects.add(Site("unknown", f"{self.name} calls "
                                      f"{self._shown(node.func)}, a method "
                                      f"mathema has no entry for"))
            return
        if owner[0] == "value" and _draws_shared_generator(
                getattr(owner[1], method, None)):
            self._library(getattr(owner[1], method), f"{owner[2]}.{method}",
                          node, shown=f"{owner[2]}.{method}")
            return
        if owner[0] == "param" and owner[1] == self.generator:
            return
        if owner[0] == "unresolved":
            self.effects.add(Site("unknown", f"{self.name} calls "
                                  f"{owner[1]}.{method}, a name mathema "
                                  f"cannot resolve"))
            return
        changed = self._outside(owner)
        if changed is None:
            return
        if method in _MUTATING_METHODS:
            self._note_module_write(owner)
            self.effects.add(Site("write", f"{self.name} changes {changed} "
                                  f"({self._shown(node)})"))
            return
        if method in ("sample", "shuffle") and any(
                k.arg in ("random_state", "seed") for k in node.keywords):
            return
        if method in _DRAW_METHODS and owner[0] == "param":
            self.effects.add(Site("write", f"{self.name} advances "
                                  f"{changed}, a generator it does not own "
                                  f"({self._shown(node)})"))
            return
        if method == "dot":
            self.effects.add(Site("order", f"{self.name} calls "
                                  f"{self._shown(node.func)}, a threaded "
                                  f"reduction whose last bit is not known to "
                                  f"be the same on every run"))
            return
        if method in _READING_METHODS:
            return
        self.effects.add(Site("unknown", f"{self.name} calls "
                              f"{self._shown(node.func)} on {changed}, a "
                              f"method mathema has no entry for"))
