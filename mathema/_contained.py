# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness call made in a child process. A fresh interpreter imports
the function's module, calls the function at the points it is handed,
looks at the module-level values before and after each call, and prints
what it saw as one line of JSON. The checking process calls nothing and
its own module values stay as they were.

The child gets the checking process's `sys.path`, working directory and
environment, so the module it imports is the file the function came
from; it is checked to be. The module is imported once in each child,
afresh: what the child sees is what a new import of the module does.
The points travel to the child pickled; the child answers in JSON only,
and no answer holds a value the child observed: a changed value is
named and described by its size and by its type when that is a listed
built-in or standard-library type (`described`), so nothing the called
code makes is unpickled here or shown.

Two values are compared by a structural snapshot (`snapshot`) that
depends on what they hold and never on which object they are; a value
that cannot be read that way is reported as not compared, and is no
witness.
"""
from __future__ import annotations

import base64
import json
import os
import pickle
import subprocess
import sys

from ._timeout import EXTENSIVE_TIMEOUT_SECONDS

# :draft a run's limit is a budget of work; until work is counted, this
# wall clock, start-up and import included, is the failsafe that stops
# a child that does not finish
FAILSAFE_WALL_CLOCK_SECONDS = EXTENSIVE_TIMEOUT_SECONDS

#: the longest name the child sends back
SHOWN = 60

# :draft how deep a value is read for comparison, and how many values
# one snapshot may hold: a budget of work, counted in values read
SNAPSHOT_DEPTH = 8
SNAPSHOT_VALUES = 1_000_000

_BOOTSTRAP = (
    "import sys, json\n"
    "request = json.loads(sys.stdin.read())\n"
    "sys.path[:] = request['sys_path']\n"
    "from mathema._contained import _child\n"
    "_child(request)\n")


def not_importable(fn) -> "str | None":
    """Intent:
        Why no child process can import `fn`, or None when one can: the
        child reaches a function as an attribute path of a module that
        was loaded from a file.
    """
    module = getattr(fn, "__module__", None)
    qualname = getattr(fn, "__qualname__", None)
    if not module or not qualname:
        return "it has no module or no name"
    if module == "__main__":
        return "it is defined in `__main__`"
    if "<locals>" in qualname:
        return "it is defined inside another function"
    if "<lambda>" in qualname:
        return "it is a lambda"
    loaded = sys.modules.get(module)
    path = getattr(loaded, "__file__", None)
    if loaded is None or not path or not os.path.isfile(path):
        return f"its module {module} was not loaded from a file"
    found = loaded
    for part in qualname.split("."):
        found = getattr(found, part, None)
    if found is not fn:
        return "its module and name lead to another object"  # :draft
    return None


class NotCompared(Exception):
    """A value `snapshot` cannot read; the text says why."""


_ABSENT = ("not set",)

# :draft how many items a container holds before it is kept as its
# length and a digest of its items' snapshots
DIGESTED = 4096


def _listed_types() -> list:
    """The built-in and standard-library types a row names, each with
    the name it is given. Any other type is named "an object"."""
    import array
    import collections
    import datetime
    import decimal
    import fractions
    import re
    import types
    return [
        (bool, "bool"), (int, "int"), (float, "float"),
        (complex, "complex"), (str, "str"), (bytes, "bytes"),
        (bytearray, "bytearray"), (list, "list"), (tuple, "tuple"),
        (dict, "dict"), (set, "set"), (frozenset, "frozenset"),
        (range, "range"), (slice, "slice"), (type, "type"),
        (types.ModuleType, "module"), (types.FunctionType, "function"),
        (types.BuiltinFunctionType, "built-in function"),
        (types.MethodType, "method"), (types.GeneratorType, "generator"),
        (collections.deque, "deque"),
        (collections.OrderedDict, "OrderedDict"),
        (collections.defaultdict, "defaultdict"),
        (collections.Counter, "Counter"), (decimal.Decimal, "Decimal"),
        (fractions.Fraction, "Fraction"), (datetime.date, "date"),
        (datetime.datetime, "datetime"), (datetime.time, "time"),
        (datetime.timedelta, "timedelta"), (array.array, "array"),
        (re.Pattern, "Pattern"),
        (BaseException, "BaseException"), (Exception, "Exception"),
        (ArithmeticError, "ArithmeticError"),
        (AssertionError, "AssertionError"),
        (AttributeError, "AttributeError"), (EOFError, "EOFError"),
        (FileNotFoundError, "FileNotFoundError"),
        (ImportError, "ImportError"), (IndexError, "IndexError"),
        (KeyError, "KeyError"), (KeyboardInterrupt, "KeyboardInterrupt"),
        (LookupError, "LookupError"), (MemoryError, "MemoryError"),
        (ModuleNotFoundError, "ModuleNotFoundError"),
        (NameError, "NameError"),
        (NotImplementedError, "NotImplementedError"),
        (OSError, "OSError"), (OverflowError, "OverflowError"),
        (PermissionError, "PermissionError"),
        (RecursionError, "RecursionError"), (RuntimeError, "RuntimeError"),
        (StopIteration, "StopIteration"), (SyntaxError, "SyntaxError"),
        (SystemExit, "SystemExit"), (TimeoutError, "TimeoutError"),
        (TypeError, "TypeError"), (UnicodeError, "UnicodeError"),
        (ValueError, "ValueError"),
        (ZeroDivisionError, "ZeroDivisionError"),
        (pickle.PicklingError, "PicklingError"),
        (subprocess.SubprocessError, "SubprocessError"),
    ]


_LISTED = {id(kind): name for kind, name in _listed_types()}
#: the listed types themselves, which keep their ids in use
_LISTED_KINDS = tuple(kind for kind, _name in _listed_types())


def listed_name(kind) -> "str | None":
    """Intent:
        The name a row gives the type `kind`: its name from the fixed
        list of built-in and standard-library types (`_listed_types`),
        found by identity, or None for any other type. Nothing of
        `kind` is read but which object it is.
    """
    return _LISTED.get(id(kind))


def an_exception(exc) -> str:
    """The type of an exception as a row names it: a listed type's
    name, or "an exception" for any other type."""
    return listed_name(type(exc)) or "an exception"  # :draft


def _a(name: str) -> str:
    """`name` behind its article."""
    return f"{'an' if name[:1].lower() in 'aeiou' else 'a'} {name}"


def _object_called(kind) -> str:
    """An object of type `kind` as a row names it: `a deque object`
    for a listed type, `an object` for any other."""
    name = listed_name(kind)
    return f"{_a(name)} object" if name is not None else "an object"  # :draft


def _is(kind, *kinds) -> bool:
    """Whether `kind` is one of `kinds`, by identity alone."""
    return any(kind is k for k in kinds)


_TYPE_DICT = type.__dict__["__dict__"]
_TYPE_MRO = type.__dict__["__mro__"]


def snapshot(value, depth: int = SNAPSHOT_DEPTH,
             values: int = SNAPSHOT_VALUES):
    """Intent:
        What `value` holds, as nested tuples of plain values that are
        equal exactly when two values hold the same, read without
        calling anything the value's own class defines: a number, text
        or bytes by its type and value (a float by its bits, every nan
        the same); a list, tuple, deque or array by its items in order;
        a set or a dict by its items in any order and an OrderedDict by
        its items in order; a Decimal, a date, a time or a timedelta by
        its text; a compiled pattern by its pattern and flags; a numpy
        array by its type, shape and bytes; a module, class or function
        by which object it is; any other object by its class, the
        built-in value it extends, its `__dict__` and its slots, each
        read through the descriptor its type defines, down to `depth`.
        A value met again inside itself is a marker of how many levels
        up it was met; a container of more than `DIGESTED` items is its
        length and a digest of its items' snapshots. Which object a
        value is (but for a module, class or function), its `__eq__`
        and its `repr` are never read.

    Raises:
        NotCompared: the value is nested deeper than `depth`, holds
            more than `values` values (the budget is reached), is an
            object whose class defines how its attributes or its
            `__dict__` are read, or shadows a slot, or is an object
            with no `__dict__`, no slots and no listed value it
            extends.
    """
    return _snap(value, depth, [values, values], {}, 0)


def _over_budget(left: list) -> NotCompared:
    return NotCompared(f"the comparison's budget of {left[1]} values "  # :draft
                       f"was reached before all of it was read")


def _snap(value, depth: int, left: list, path: dict, level: int):
    import types
    left[0] -= 1
    if left[0] < 0:
        raise _over_budget(left)
    kind = type(value)
    if value is None:
        return ("None",)
    if _is(kind, bool, int, str, bytes):
        return (listed_name(kind), value)
    if kind is float:
        return ("float", "nan" if value != value else value.hex())
    if kind is complex:
        return ("complex", _snap(value.real, depth, left, path, level),
                _snap(value.imag, depth, left, path, level))
    if kind is bytearray:
        return ("bytearray", bytes(value))
    mro = _TYPE_MRO.__get__(kind)
    if any(_is(cls, types.ModuleType, type, types.FunctionType,
               types.BuiltinFunctionType) for cls in mro):
        return ("named", id(value))
    if id(value) in path:
        return ("back", level - path[id(value)])
    if depth <= 0:
        raise NotCompared("it is nested deeper than the comparison reads")  # :draft
    path = {**path, id(value): level}

    def inner(item):
        return _snap(item, depth - 1, left, path, level + 1)

    def items(name: str, iterator, ordered: bool,
              paired: bool = False) -> tuple:
        read = [(inner(k), inner(v)) if paired else inner(v)
                for k, v in (iterator if paired
                             else ((None, v) for v in iterator))]
        if len(read) > DIGESTED:
            import hashlib
            texts = [repr(r) for r in read]
            if not ordered:
                texts.sort()
            digest = hashlib.sha256()
            for text in texts:
                digest.update(text.encode())
                digest.update(b"\0")
            return (name, "digest", len(read), digest.hexdigest())
        if not ordered:
            read.sort(key=repr)
        return (name, tuple(read))

    contents = _contents(value, kind, mro, items, left)
    if contents is not None and (_is(kind, *_LISTED_KINDS)
                                 or contents[0] == "ndarray"):
        return contents
    return _object(value, kind, mro, contents, inner, items)


def _contents(value, kind, mro, items, left) -> "tuple | None":
    """What a value holds as the first listed type in `mro` it extends
    holds it, read through that type's own methods; None when it
    extends none that is read by its contents."""
    import array
    import collections
    import datetime
    import decimal
    import re
    numpy = sys.modules.get("numpy")
    ndarray = getattr(numpy, "ndarray", None) if numpy is not None else None
    if ndarray is not None and kind is ndarray:
        if value.dtype.hasobject:
            raise NotCompared("it is a numpy array of objects")  # :draft
        left[0] -= int(value.size)
        if left[0] < 0:
            raise _over_budget(left)
        return ("ndarray", str(value.dtype), tuple(value.shape),
                value.tobytes())
    for cls in mro:
        if cls is collections.OrderedDict:
            return items("OrderedDict",
                         collections.OrderedDict.items(value), True, True)
        if cls is collections.defaultdict:
            factory = collections.defaultdict.default_factory.__get__(value)
            return ("defaultdict", items("factory", [factory], True),
                    items("items", dict.items(value), False, True))
        if cls is dict:
            return items("dict", dict.items(value), False, True)
        if cls is collections.deque:
            maxlen = collections.deque.maxlen.__get__(value)
            return ("deque", maxlen, items(
                "items", collections.deque.__iter__(value), True))
        if _is(cls, list, tuple):
            return items(cls.__name__, cls.__iter__(value), True)
        if _is(cls, set, frozenset):
            return items(cls.__name__, cls.__iter__(value), False)
        if cls is array.array:
            left[0] -= array.array.__len__(value)
            if left[0] < 0:
                raise _over_budget(left)
            return ("array", array.array.typecode.__get__(value),
                    array.array.tobytes(value))
        if cls is decimal.Decimal:
            return ("Decimal", decimal.Decimal.__str__(value))
        if _is(cls, datetime.datetime, datetime.time):
            zone = cls.tzinfo.__get__(value)
            if zone is not None and type(zone) is not datetime.timezone:
                raise NotCompared(f"{_object_called(cls)} with a time zone "  # :draft
                                  f"of another type cannot be read")
            return (listed_name(cls), cls.isoformat(value),
                    cls.fold.__get__(value))
        if _is(cls, datetime.date, datetime.timedelta):
            return (listed_name(cls), cls.__str__(value))
        if cls is re.Pattern:
            return ("Pattern", re.Pattern.pattern.__get__(value),
                    re.Pattern.flags.__get__(value))
        if cls is str:
            return ("str", str.__str__(value))
        if cls is bytes:
            return ("bytes", bytes.__getitem__(value, slice(None)))
        if cls is int:
            return ("int", int.__int__(value))
        if cls is float:
            number = float.__float__(value)
            return ("float", "nan" if number != number else number.hex())
    return None


def _object(value, kind, mro, contents, inner, items) -> tuple:
    """An object of a class not listed: its class, the listed value it
    extends (`contents`), its `__dict__` and its slots, each read
    through the descriptor its type defines."""
    import types
    own_vars = [_TYPE_DICT.__get__(cls) for cls in mro]
    listed = [_is(cls, *_LISTED_KINDS) or cls is object for cls in mro]
    for cls, names, trusted in zip(mro, own_vars, listed):
        if trusted:
            continue
        if "__getattribute__" in names or (
                "__dict__" in names
                and type(names["__dict__"]) is not types.GetSetDescriptorType):
            raise NotCompared(f"{_object_called(kind)} has a class that "  # :draft
                              f"defines how its attributes are read")
    parts: list = [] if contents is None else [("value", contents)]
    read = contents is not None
    for names in own_vars:
        if "__dict__" in names:
            got = names["__dict__"]
            if type(got) is types.GetSetDescriptorType:
                own = got.__get__(value, kind)
                if type(own) is dict:
                    read = True
                    parts.append(items("dict", dict.items(own), False,
                                       True))
            break
    enumerable = True
    for at, (cls, names, trusted) in enumerate(zip(mro, own_vars, listed)):
        if cls is object:
            continue
        if not trusted and "__slots__" not in names:
            enumerable = False
        for name, held in dict(names).items():
            if type(held) is not types.MemberDescriptorType:
                continue
            if any(name in earlier for earlier in own_vars[:at]):
                raise NotCompared(f"{_object_called(kind)} has a class "  # :draft
                                  f"that shadows one of its slots")
            try:
                got = inner(held.__get__(value, kind))
            except AttributeError:
                got = _ABSENT
            except TypeError:
                raise NotCompared(f"{_object_called(kind)} has a slot the "  # :draft
                                  f"comparison cannot read") from None
            parts.append(("slot", at, name, got))
            read = True
    declared = any(not trusted for trusted in listed)
    if not read and not (enumerable and declared):
        if len(mro) == 1:
            raise NotCompared(f"{_object_called(kind)} has no state the "  # :draft
                              f"comparison can read")
        raise NotCompared(f"{_object_called(kind)} keeps state the "  # :draft
                          f"comparison cannot read")
    return ("object", id(kind), tuple(parts))


def described(value) -> str:
    """Intent:
        A value as words that hold nothing of it: the name of its type
        when that is a listed built-in or standard-library type
        (`listed_name`), "an object" otherwise, and, for text, bytes
        and the listed containers, how many characters, bytes or items
        it holds. `None` is said as `None`.
    """
    import array
    import collections
    if value is None:
        return "None"
    kind = type(value)
    shown = listed_name(kind)
    if shown is None:
        return "an object"  # :draft
    name = _a(shown)

    def counted(n: int, unit: str) -> str:
        return f"{n} {unit}{'' if n == 1 else 's'}"

    if _is(kind, str):
        return f"{name} of {counted(str.__len__(value), 'character')}"
    if _is(kind, bytes, bytearray):
        return f"{name} value of {counted(kind.__len__(value), 'byte')}"
    if _is(kind, dict, collections.OrderedDict, collections.defaultdict,
           collections.Counter):
        return f"{name} of {counted(dict.__len__(value), 'item')}"
    if _is(kind, list, tuple, set, frozenset, collections.deque,
           array.array):
        return f"{name} of {counted(kind.__len__(value), 'item')}"
    if _is(kind, bool, int, float, complex):
        return name
    return f"{name} object"


def witness(fn, kind: str, points: list, watched: list,
            declared: "dict | None" = None, environ: bool = False,
            generators: bool = False, stdout: bool = False,
            entries: "dict | None" = None) -> dict:
    """Intent:
        What a child process saw calling `fn` at `points` (argument
        lists, tried in order until one shows it). `kind` "is_state_safe"
        looks for a call after which one of the `watched` module-level
        values, `(module, name)` pairs, has changed, or, with `environ`,
        after which the child's own environment has (answered as
        `{"seen": "environ", "point": i, "name": variable, "before": n,
        "after": n}`, each `n` the length of the value or None when the
        variable is not set, never the value); with `generators`,
        after which the state of a shared random generator has
        (`{"seen": "generator", "point": i, "name": module}`); with
        `stdout`, during which text was written to standard output
        (`{"seen": "stdout", "point": i, "count": characters}`); with
        `entries`, `{holder: [key, ...]}` for `sys.modules`, after
        which one of those entries has (`{"seen": "entry", "point": i,
        "name": holder, "key": key, "before": words, "after": words}`).
        "is_deterministic" looks for two calls with the same arguments
        whose results differ. A call that raises is compared after the
        raise as one that returns is. The answer is `{"seen": "write",
        "point": i, "name": n, "before": words, "after": words}`,
        `{"seen": "results", "point": i, "first": words, "second":
        words}`, `{"seen": None, "ran": n}` when no point showed it (`n` the
        points called and compared), with
        `"unread": reason` when something could not be compared, or
        `{"failed": reason}`: the child ran past the failsafe wall
        clock, could not import the module, or ended without an answer.
        `words` describe a value (`described`) and never hold it.

    Notes:
        `fn` must be importable (`not_importable(fn) is None`). Values
        are compared by `snapshot`.
    """
    module = sys.modules[fn.__module__]
    try:
        packed = base64.b64encode(
            pickle.dumps({"points": points, "declared": declared})).decode()
    except Exception as exc:
        return {"failed": f"its arguments could not be sent to a child "
                          f"process ({an_exception(exc)})"}
    request = {"sys_path": list(sys.path), "module": fn.__module__,
               "file": os.path.abspath(str(module.__file__)),
               "qualname": fn.__qualname__, "kind": kind,
               "watched": [list(w) for w in watched], "packed": packed,
               "environ": bool(environ), "generators": bool(generators),
               "stdout": bool(stdout),
               "entries": {k: list(v) for k, v in (entries or {}).items()}}
    limit = FAILSAFE_WALL_CLOCK_SECONDS
    try:
        done = subprocess.run([sys.executable, "-c", _BOOTSTRAP],
                              input=json.dumps(request), capture_output=True,
                              text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        return {"failed": "the run did not finish within its budget "  # :draft
                          "and was stopped"}
    except Exception as exc:
        return {"failed": f"no child process could be started "
                          f"({an_exception(exc)})"}
    for line in reversed(done.stdout.splitlines()):
        if line.startswith(_ANSWER):
            try:
                answer = json.loads(line[len(_ANSWER):])
            except ValueError:
                break
            if isinstance(answer, dict):
                return answer
            break
    return {"failed": f"the child process that called it ended without an "
                      f"answer (exit status {done.returncode})"}


_ANSWER = "mathema-witness:"


def _child(request: dict) -> None:
    """The child's side of `witness`: import, call, observe, answer."""
    answer_to = os.fdopen(os.dup(1), "w")
    # what the called code prints is not the answer
    sink = os.open(os.devnull, os.O_WRONLY)
    os.dup2(sink, 1)
    os.dup2(sink, 2)
    answer = _observed(request)
    answer_to.write(_ANSWER + json.dumps(answer) + "\n")
    answer_to.flush()
    os._exit(0)


def _observed(request: dict) -> dict:
    """Intent:
        The answer `witness` documents, made in the child: the module
        is imported by name, once, and must be the file the request
        names, the function is rebuilt as the checking process calls it
        (`runtime_types.calling`), and each point is tried in turn.
    """
    import copy
    import importlib
    try:
        module = importlib.import_module(request["module"])
    except BaseException as exc:
        return {"failed": f"a child process could not import its module "
                          f"{request['module']} ({an_exception(exc)})"}
    path = getattr(module, "__file__", None)
    if not path or os.path.abspath(path) != request["file"]:
        return {"failed": f"a child process importing {request['module']} "
                          f"loaded another file"}
    fn = module
    for part in request["qualname"].split("."):
        fn = getattr(fn, part, None)
    if not callable(fn):
        return {"failed": f"a child process found no function "
                          f"{request['qualname']} in {request['module']}"}
    try:
        from ._examine import _unwrapped
        from .analysis import effective_facts
        from .runtime_types import calling
        sent = pickle.loads(base64.b64decode(request["packed"]))
        run = calling(fn, effective_facts(fn), sent["declared"])
        own = getattr(_unwrapped(fn), "__globals__", None) or {}
    except BaseException as exc:
        return {"failed": f"a child process could not prepare the call "
                          f"({an_exception(exc)})"}
    unread: dict = {}
    # how many points were called and compared
    ran = [0]

    def scope_of(module_name: str) -> dict:
        return (own if own.get("__name__") == module_name
                else vars(sys.modules[module_name]))

    def held() -> dict:
        """Each watched module-level value as (snapshot, words), a name
        that is not set as `_ABSENT`; one that cannot be compared is
        left out and noted in `unread`."""
        out = {}
        for module_name, name in request["watched"]:
            if f"the module-level {name}" in unread:
                # read once and found not comparable: not read again
                continue
            try:
                scope = scope_of(module_name)
            except Exception:
                unread[f"the module-level {name}"] = \
                    "its module is not loaded"
                continue
            if name not in scope:
                out[name] = (_ABSENT, "not set")
                continue
            try:
                out[name] = (snapshot(scope[name]), described(scope[name]))
            except NotCompared as exc:
                unread[f"the module-level {name}"] = str(exc)
            except Exception as exc:
                unread[f"the module-level {name}"] = \
                    f"reading it raised {an_exception(exc)}"
        return out

    def entries() -> dict:
        out = {}
        for holder, keys in (request.get("entries") or {}).items():
            if holder != "sys.modules":
                continue
            for key in keys:
                if key not in sys.modules:
                    out[holder, key] = (_ABSENT, "not set")
                    continue
                try:
                    out[holder, key] = (snapshot(sys.modules[key]),
                                        described(sys.modules[key]))
                except Exception:
                    unread[f"{holder}[{key!r}]"] = "it could not be read"
        return out

    def generators() -> dict:
        out: dict = {}
        if not request.get("generators"):
            return out
        import random
        out["random"] = snapshot(random.getstate())
        mtrand = getattr(sys.modules.get("numpy.random"), "mtrand", None)
        if mtrand is not None:
            try:
                out["numpy.random"] = snapshot(mtrand.get_state())
            except Exception:
                unread["the state of numpy.random"] = "it could not be read"
        return out

    from ._callee_output import _Routed

    class _Counted(_Routed):
        """Standard output for the length of one call: counts what is
        written and keeps none of it. A `_Routed`, so the routing a
        call is run under (`_callee_output.kept_off_terminal`) leaves
        it in place."""
        def __init__(self):
            self.count = 0

        def write(self, text):
            self.count += len(text)
            return len(text)

        def flush(self):
            pass

        def __getattr__(self, name):
            raise AttributeError(name)

    def not_seen() -> dict:
        if not unread:
            return {"seen": None, "ran": ran[0]}
        name, why = sorted(unread.items())[0]
        when = ("" if request["kind"] != "is_state_safe"
                else " before and after the call")
        return {"seen": None,
                "unread": f"{short_name(name)} could not be "  # :draft
                          f"compared{when} ({why})"}

    def state_point(index: int, args) -> "dict | None":
        before, items, drawn = held(), entries(), generators()
        environment = dict(os.environ) if request.get("environ") else None
        counted = _Counted() if request.get("stdout") else None
        kept = sys.stdout
        if counted is not None:
            sys.stdout = counted
        try:
            run(*copy.deepcopy(args))
        except BaseException:
            # what a call changed before it raised is still changed
            pass
        finally:
            sys.stdout = kept
        ran[0] += 1
        after, items_after, drawn_after = held(), entries(), generators()
        for name in before:
            if name in after and before[name][0] != after[name][0]:
                return {"seen": "write", "point": index,
                        "name": short_name(name),
                        "before": before[name][1], "after": after[name][1]}
        if environment is not None:
            now = dict(os.environ)
            moved = sorted(k for k in {*environment, *now}
                           if environment.get(k) != now.get(k))
            if moved:
                def length(value):
                    return None if value is None else len(value)
                return {"seen": "environ", "point": index,
                        "name": short_name(moved[0]),
                        "before": length(environment.get(moved[0])),
                        "after": length(now.get(moved[0]))}
        for name in drawn:
            if name in drawn_after and drawn[name] != drawn_after[name]:
                return {"seen": "generator", "point": index, "name": name}
        for holder, key in items:
            if (holder, key) in items_after and \
                    items[holder, key][0] != items_after[holder, key][0]:
                return {"seen": "entry", "point": index, "name": holder,
                        "key": short_name(key),
                        "before": items[holder, key][1],
                        "after": items_after[holder, key][1]}
        if counted is not None and counted.count > 0:
            return {"seen": "stdout", "point": index, "count": counted.count}
        return None

    def results_point(index: int, args) -> "dict | None":
        try:
            first = run(*copy.deepcopy(args))
            second = run(*copy.deepcopy(args))
        except Exception:
            # a call that raises returns no result to compare
            return None
        try:
            differ = snapshot(first) != snapshot(second)
        except NotCompared as exc:
            unread["the two results"] = str(exc)
            return None
        except Exception as exc:
            unread["the two results"] = (f"reading them raised "
                                         f"{an_exception(exc)}")
            return None
        ran[0] += 1
        if differ:
            return {"seen": "results", "point": index,
                    "first": described(first), "second": described(second)}
        return None

    if request["kind"] == "is_state_safe" and not (
            request["watched"] or request.get("environ")
            or request.get("generators") or request.get("stdout")
            or request.get("entries")):
        return {"seen": None}
    for index, args in enumerate(sent["points"]):
        try:
            found = (state_point(index, args)
                     if request["kind"] == "is_state_safe"
                     else results_point(index, args))
        except Exception:
            continue
        if found is not None:
            return found
    return not_seen()


def short_name(text) -> str:
    """A name the child sends back, as one line no longer than `SHOWN`."""
    text = " ".join(str(text).split())
    return text if len(text) <= SHOWN else text[:SHOWN - 3] + "..."
