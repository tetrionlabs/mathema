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
named and described by its type and size (`described`), so nothing the
called code makes is unpickled here or shown.

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
SNAPSHOT_VALUES = 200_000

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
        return f"{module}.{qualname} is not this function"
    return None


class NotCompared(Exception):
    """A value `snapshot` cannot read; the text says why."""


_ABSENT = ("not set",)
_HEAP_TYPE = 1 << 9


def snapshot(value, depth: int = SNAPSHOT_DEPTH,
             values: int = SNAPSHOT_VALUES):
    """Intent:
        What `value` holds, as nested tuples of plain values that are
        equal exactly when two values hold the same: a number, text or
        bytes by its type and value (a float by its bits, every nan the
        same); a list or tuple by its items in order; a set or a dict
        by its items in any order; a numpy array by its type, shape and
        bytes; a module, class or function by its name; any other
        object by its class's name with its `__dict__` and slots, read
        the same way down to `depth`. Which object it is, its `__eq__`
        and its `repr` are never read.

    Raises:
        NotCompared: the value is nested deeper than `depth`, holds
            more than `values` values, contains itself, or its type
            keeps state that is in neither a `__dict__` nor a slot.
    """
    left = [values]
    return _snap(value, depth, left, frozenset())


def _type_name(kind) -> str:
    """A type's name, as letters, digits, `_` and `.` only."""
    name = str(getattr(kind, "__qualname__", None)
               or getattr(kind, "__name__", "") or "object")
    name = "".join(c for c in name if c.isalnum() or c in "_.")
    return name[:SHOWN] or "object"


def _a(name: str) -> str:
    """`name` behind its article."""
    return f"{'an' if name[:1].lower() in 'aeiou' else 'a'} {name}"


def _snap(value, depth: int, left: list, path: frozenset):
    import types
    left[0] -= 1
    if left[0] < 0:
        raise NotCompared("it holds more values than the comparison's "  # :draft
                          "budget reads")
    kind = type(value)
    if value is None:
        return ("None",)
    if kind in (bool, int, str, bytes):
        return (kind.__name__, value)
    if kind is float:
        return ("float", "nan" if value != value else value.hex())
    if kind is complex:
        return ("complex", _snap(value.real, depth, left, path),
                _snap(value.imag, depth, left, path))
    if kind is bytearray:
        return ("bytearray", bytes(value))
    if isinstance(value, types.ModuleType):
        return ("module", str(getattr(value, "__name__", "")))
    if isinstance(value, (type, types.FunctionType,
                          types.BuiltinFunctionType)):
        return ("named", kind.__name__,
                str(getattr(value, "__module__", "")),
                str(getattr(value, "__qualname__", "")))
    if depth <= 0:
        raise NotCompared("it is nested deeper than the comparison reads")  # :draft
    if id(value) in path:
        raise NotCompared("it contains itself")  # :draft
    path = path | {id(value)}

    def inner(item):
        return _snap(item, depth - 1, left, path)

    def in_any_order(items) -> tuple:
        return tuple(sorted(items, key=repr))

    if kind in (list, tuple):
        return (kind.__name__, tuple(inner(v) for v in value))
    if kind in (set, frozenset):
        return (kind.__name__, in_any_order(inner(v) for v in value))
    if kind is dict:
        return ("dict", in_any_order((inner(k), inner(v))
                                     for k, v in value.items()))
    if kind.__module__ == "numpy" and kind.__name__ == "ndarray":
        if value.dtype.hasobject:
            raise NotCompared("it is a numpy array of objects")  # :draft
        left[0] -= int(value.size)
        if left[0] < 0:
            raise NotCompared("it holds more values than the comparison's "  # :draft
                              "budget reads")
        return ("ndarray", str(value.dtype), tuple(value.shape),
                value.tobytes())
    # an object: the built-in value it extends, its __dict__, its slots
    parts: list = []
    plain = (list, tuple, set, frozenset, dict, int, float, str)
    for cls in kind.__mro__:
        if cls is object or cls in plain:
            continue
        if not cls.__flags__ & _HEAP_TYPE:
            raise NotCompared(f"{_a(_type_name(kind))} object keeps state "  # :draft
                              f"the comparison cannot read")
    if isinstance(value, tuple):
        parts.append(("items", tuple(inner(v)
                                     for v in tuple.__iter__(value))))
    elif isinstance(value, list):
        parts.append(("items", tuple(inner(v)
                                     for v in list.__iter__(value))))
    elif isinstance(value, (set, frozenset)):
        base = set if isinstance(value, set) else frozenset
        parts.append(("items", in_any_order(
            inner(v) for v in base.__iter__(value))))
    elif isinstance(value, dict):
        parts.append(("items", in_any_order(
            (inner(k), inner(v)) for k, v in dict.items(value))))
    elif isinstance(value, int):
        parts.append(("value", int.__int__(value)))
    elif isinstance(value, float):
        parts.append(("value", inner(float.__float__(value))))
    elif isinstance(value, str):
        parts.append(("value", str.__str__(value)))
    try:
        own = object.__getattribute__(value, "__dict__")
    except AttributeError:
        own = None
    read = bool(parts)
    if type(own) is dict:
        read = True
        parts.append(("dict", in_any_order(
            (inner(k), inner(v)) for k, v in own.items())))
    for cls in kind.__mro__:
        slots = vars(cls).get("__slots__", ())
        for slot in ((slots,) if isinstance(slots, str) else tuple(slots)):
            if slot in ("__dict__", "__weakref__"):
                continue
            read = True
            if slot.startswith("__") and not slot.endswith("__"):
                slot = f"_{cls.__name__.lstrip('_')}{slot}"
            try:
                held = inner(object.__getattribute__(value, slot))
            except AttributeError:
                held = _ABSENT
            parts.append(("slot", cls.__name__, slot, held))
    if not read:
        raise NotCompared(f"{_a(_type_name(kind))} object has no state the "  # :draft
                          f"comparison can read")
    return ("object", str(kind.__module__), _type_name(kind), tuple(parts))


def described(value) -> str:
    """Intent:
        A value as words that hold nothing of it: its type's name and,
        for text, bytes and the built-in containers, how many
        characters, bytes or items it holds. `None` is said as `None`.
    """
    if value is None:
        return "None"
    kind = type(value)
    name = _a(_type_name(kind))

    def counted(n: int, unit: str) -> str:
        return f"{n} {unit}{'' if n == 1 else 's'}"

    try:
        if isinstance(value, str):
            return f"{name} of {counted(str.__len__(value), 'character')}"
        if isinstance(value, (bytes, bytearray)):
            return f"{name} value of {counted(len(bytes(value)), 'byte')}"
        for base in (list, tuple, dict, set, frozenset):
            if isinstance(value, base):
                return f"{name} of {counted(base.__len__(value), 'item')}"
    except Exception:
        pass
    if kind in (bool, int, float, complex):
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
        words}`, `{"seen": None}` when no point showed it, with
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
                          f"process ({type(exc).__name__})"}
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
                          f"({type(exc).__name__})"}
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
                          f"{request['module']} ({type(exc).__name__})"}
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
                          f"({type(exc).__name__})"}
    unread: dict = {}

    def scope_of(module_name: str) -> dict:
        return (own if own.get("__name__") == module_name
                else vars(sys.modules[module_name]))

    def held() -> dict:
        """Each watched module-level value as (snapshot, words), a name
        that is not set as `_ABSENT`; one that cannot be compared is
        left out and noted in `unread`."""
        out = {}
        for module_name, name in request["watched"]:
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
                    f"reading it raised {type(exc).__name__}"
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
            return {"seen": None}
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
                                         f"{type(exc).__name__}")
            return None
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
