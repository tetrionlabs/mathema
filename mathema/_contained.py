# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness call made in a child process. A fresh interpreter imports
the function's module, calls the function at the points it is handed,
looks at the module-level values before and after each call, and prints
what it saw as one line of JSON. The checking process calls nothing and
its own module values stay as they were.

The child gets the checking process's `sys.path`, working directory and
environment, so the module it imports is the file the function came
from; it is checked to be. The points travel to the child pickled; the
child answers in JSON only, each value as a `repr` cut to a fixed
length, so nothing the called code makes is ever unpickled here.
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

#: the longest `repr` the child sends back for one value
SHOWN = 60

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


def short(value, limit: int = SHOWN) -> str:
    """`repr(value)`, cut to `limit` characters."""
    try:
        text = repr(value)
    except Exception as exc:
        text = f"<{type(value).__name__}, repr raised {type(exc).__name__}>"
    return text if len(text) <= limit else text[:limit - 3] + "..."


def differs(a, b) -> bool:
    """Whether two values are seen to differ: unequal, and not both the
    same not-a-number. A comparison that raises or gives no plain truth
    value shows no difference."""
    try:
        if isinstance(a, float) and isinstance(b, float) \
                and a != a and b != b:
            return False
        return bool(a != b)
    except Exception:
        return False


def witness(fn, kind: str, points: list, watched: list,
            declared: "dict | None" = None) -> dict:
    """Intent:
        What a child process saw calling `fn` at `points` (argument
        lists, tried in order until one shows it). `kind` "is_state_safe"
        looks for a call after which one of the `watched` module-level
        values, `(module, name)` pairs, has changed; "is_deterministic"
        for two calls with the same arguments whose results differ.
        The answer is `{"seen": "write", "point": i, "name": n,
        "before": text, "after": text}`, `{"seen": "results", "point":
        i, "first": text, "second": text}`, `{"seen": None}` when no
        point showed it, or `{"failed": reason}`: the child ran past
        the failsafe wall clock, could not import the module, or ended
        without an answer.

    Notes:
        `fn` must be importable (`not_importable(fn) is None`).
    """
    module = sys.modules[fn.__module__]
    try:
        packed = base64.b64encode(
            pickle.dumps({"points": points, "declared": declared})).decode()
    except Exception as exc:
        return {"failed": f"its arguments could not be sent to a child "
                          f"process ({type(exc).__name__})"}
    request = {"sys_path": list(sys.path), "module": fn.__module__,
               "file": os.path.abspath(module.__file__),
               "qualname": fn.__qualname__, "kind": kind,
               "watched": [list(w) for w in watched], "packed": packed}
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
        is imported by name and must be the file the request names, the
        function is rebuilt as the checking process calls it
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

    def held():
        out = {}
        for module_name, name in request["watched"]:
            try:
                scope = (own if own.get("__name__") == module_name
                         else vars(sys.modules[module_name]))
                out[name] = copy.deepcopy(scope[name])
            except Exception:
                return None
        return out

    for index, args in enumerate(sent["points"]):
        try:
            if request["kind"] == "is_state_safe":
                before = held()
                if not before:
                    return {"seen": None}
                run(*copy.deepcopy(args))
                after = held()
                if after is None:
                    return {"seen": None}
                changed = [n for n in before if differs(before[n], after[n])]
                if changed:
                    return {"seen": "write", "point": index,
                            "name": changed[0],
                            "before": short(before[changed[0]]),
                            "after": short(after[changed[0]])}
            else:
                first = run(*copy.deepcopy(args))
                second = run(*copy.deepcopy(args))
                if differs(first, second):
                    return {"seen": "results", "point": index,
                            "first": short(first), "second": short(second)}
        except Exception:
            continue
    return {"seen": None}
