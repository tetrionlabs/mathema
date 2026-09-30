# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""State a function can change for the whole process, beyond its own
module's globals: the environment, the working directory, `sys.path`,
the global state of `random` and `numpy.random`, and logging's
configuration (the root logger and every named logger: level, handlers,
propagation, disabled).

`isolated(fn)` owns one trial: it reads that state (`snapshot()`),
records every call to `os.putenv` and `os.unsetenv` (they change the C
environment only, which no Python read can see afterwards), runs the
body, reads the state again, and puts back what the first read saw
(`restore()`), including every name written through putenv or
unsetenv. Restoring runs with SIGALRM blocked in the calling thread,
each step on its own and run again if a signal interrupts it (another
thread can still take the signal), so a wall-clock cap cannot leave it
half done; a step that fails is recorded on the trial, never raised. What cannot be protected: state
outside this list, and a write a thread the function started makes
after the function returns.

`writer_calls(fn, facts)` is the structural reading: the call sites in
the body that resolve to one of these writers.
"""
from __future__ import annotations

import ast
import contextlib
import logging
import os
import random
import signal
import sys
import threading


def _numpy_random():
    """The `numpy.random` module when numpy is already imported, else
    None: a function that never imported numpy cannot have changed it."""
    np = sys.modules.get("numpy")
    return getattr(np, "random", None) if np is not None else None


def _cwd() -> "str | None":
    """The working directory, or None when it no longer exists."""
    try:
        return os.getcwd()
    except OSError:
        return None


def snapshot() -> dict:
    """Intent:
        The process-wide state, keyed by the name a witness gives it,
        plus the `sys.path` list object itself under `_sys.path object`
        (a key starting with `_` is bookkeeping, never reported). A
        part that cannot be read is left out.
    """
    state: dict = {"os.environ": dict(os.environ),
                   "the working directory": _cwd(),
                   "sys.path": list(sys.path),
                   "_sys.path object": sys.path}
    readers = {
        "the global state of random": random.getstate,
        "logging's root configuration": lambda: (
            logging.getLogger().level, tuple(logging.getLogger().handlers),
            logging.root.manager.disable),
        "_loggers": _loggers,
    }
    npr = _numpy_random()
    if npr is not None:
        readers["the global state of numpy.random"] = npr.get_state
    for name, read in readers.items():
        try:
            state[name] = read()
        except Exception:
            continue
    return state


def _logger_state(logger) -> tuple:
    return (logger.level, tuple(logger.handlers), logger.propagate,
            logger.disabled)


_UNCONFIGURED = (logging.NOTSET, (), True, False)


def _loggers() -> dict:
    """Every named logger that exists, by name, as (level, handlers,
    propagate, disabled)."""
    return {name: _logger_state(logger)
            for name, logger in list(logging.Logger.manager.loggerDict.items())
            if isinstance(logger, logging.Logger)}


def _logger_changes(before: dict, after: dict) -> list[str]:
    """The loggers whose configuration differs; a logger created
    meanwhile counts only when it was configured."""
    out = []
    for name, state in after.items():
        was = before.get(name, _UNCONFIGURED)
        if state[0] != was[0] or state[2:] != was[2:] \
                or len(state[1]) != len(was[1]) \
                or any(a is not b for a, b in zip(state[1], was[1])):
            out.append(f"the logger {name!r}")
    return out


def _restore_loggers(before: dict) -> None:
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(logger, logging.Logger):
            continue
        level, handlers, propagate, disabled = before.get(name, _UNCONFIGURED)
        if _logger_state(logger) == (level, tuple(handlers), propagate, disabled):
            continue
        logger.setLevel(level)
        logger.handlers[:] = list(handlers)
        logger.propagate = propagate
        logger.disabled = disabled


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
    if "_loggers" in before and "_loggers" in after:
        out += _logger_changes(before["_loggers"], after["_loggers"])
    for name, value in before.items():
        if name.startswith("_") or name not in after:
            continue
        if name == "the working directory" and after[name] is None:
            out.append("the working directory (deleted)")
            continue
        if _same(name, value, after[name]):
            continue
        if name == "os.environ":
            out.append(f"os.environ ({_environ_change(value, after[name])})")
        elif name == "the working directory":
            out.append(f"{name} ({value!r} became {after[name]!r})")
        else:
            out.append(name)
    if ("the global state of numpy.random" in after
            and "the global state of numpy.random" not in before):
        out.append("the global state of numpy.random")
    return out


def _restore_environ(saved: dict) -> None:
    # by difference, never clear-then-update: the environment is never
    # empty, even for a moment
    for key in [k for k in os.environ if k not in saved]:
        os.environ.pop(key, None)
    for key, value in saved.items():
        if os.environ.get(key) != value:
            os.environ[key] = value


def _restore_c_environ(saved: dict, names) -> None:
    for name in names:
        text = os.fsdecode(name)
        if text in saved:
            os.putenv(text, saved[text])
        else:
            os.unsetenv(text)


def _restore_cwd(saved) -> None:
    if saved is not None and _cwd() != saved:
        os.chdir(saved)


def _restore_sys_path(before: dict) -> None:
    obj = before.get("_sys.path object")
    if obj is not None and sys.path is not obj:
        sys.path = obj
    if sys.path != before["sys.path"]:
        sys.path[:] = before["sys.path"]


def _restore_logging(saved) -> None:
    level, handlers, disable = saved
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = list(handlers)
    logging.disable(disable)


def restore(before: dict, c_environ_names=()) -> list[str]:
    """Intent:
        Put the process-wide state back as `before` read it, and reset
        each name in `c_environ_names` (written through os.putenv or
        os.unsetenv) to its value in `before`, or unset it. Every step
        runs whatever an earlier one did; a step that raises is
        returned as a phrase. An exception that is not an ordinary error
        (a wall-clock alarm, an interrupt) interrupting a step runs that
        step once more, and is raised again once every step has run.
    """
    steps = [("os.environ", lambda: _restore_environ(before["os.environ"])),
             ("the C environment",
              lambda: _restore_c_environ(before["os.environ"], c_environ_names)),
             ("the working directory",
              lambda: _restore_cwd(before["the working directory"])),
             ("sys.path", lambda: _restore_sys_path(before))]
    if "the global state of random" in before:
        steps.append(("the global state of random",
                      lambda: random.setstate(before["the global state of random"])))
    if "_loggers" in before:
        steps.append(("the named loggers",
                      lambda: _restore_loggers(before["_loggers"])))
    if "logging's root configuration" in before:
        steps.append(("logging's root configuration",
                      lambda: _restore_logging(before["logging's root configuration"])))
    npr = _numpy_random()
    if npr is not None and "the global state of numpy.random" in before:
        steps.append(("the global state of numpy.random",
                      lambda: npr.set_state(before["the global state of numpy.random"])))
    failed: list = []
    pending: "BaseException | None" = None
    for name, step in steps:
        for attempt in (1, 2):
            try:
                step()
                break
            except Exception as exc:
                failed.append(f"{name} ({type(exc).__name__}: {exc})")
                break
            except BaseException as exc:
                # an alarm or interrupt delivered mid-step: the step runs
                # once more, so the signal leaves nothing half restored
                pending = pending or exc
                if attempt == 2:
                    failed.append(f"{name} ({type(exc).__name__})")
    if pending is not None:
        raise pending
    return failed


@contextlib.contextmanager
def _alarm_blocked():
    """SIGALRM held back for the length of the block and delivered after
    it, where the platform allows (the main thread of a POSIX process)."""
    mask = getattr(signal, "pthread_sigmask", None)
    if mask is None or threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = mask(signal.SIG_BLOCK, {signal.SIGALRM})
    try:
        yield
    finally:
        mask(signal.SIG_SETMASK, previous)


class Trial:
    """One isolated call: the state before (`before`) and after
    (`after`, None when it could not be read), the putenv and unsetenv
    calls made meanwhile (`c_environ_calls`, `(writer, name)` with the
    name as text), and the restore steps that failed (`restore_failed`)."""

    def __init__(self, before: dict):
        self.before = before
        self.after: "dict | None" = None
        self.c_environ_calls: list = []
        self.restore_failed: list = []

    def changes(self) -> list[str]:
        return changes(self.before, self.after) if self.after is not None else []


@contextlib.contextmanager
def isolated(fn):
    """Intent:
        One trial of `fn` with the process-wide state read before and
        after, putenv and unsetenv recorded (reached as `os.putenv` or
        as a name imported into the function's module), and everything
        put back on the way out, whether the body returned, raised, or
        was interrupted. Yields the `Trial`.
    """
    import warnings

    from ._signatures import module_scope
    trial = Trial(snapshot())
    originals = {"putenv": os.putenv, "unsetenv": os.unsetenv}
    scope = module_scope(fn)
    rebound = {k: v for k, v in scope.items()
               if any(v is o for o in originals.values())}

    def recorder(label, original):
        def call(name, *rest):
            # os.environ's own writes go through os.putenv too; those are
            # judged by the os.environ snapshot, by their net effect. A
            # call passed on by an enclosing trial's recorder (a check
            # run inside the function) was judged by that recorder
            caller = sys._getframe(1).f_globals
            if caller is not vars(os) and caller is not globals():
                trial.c_environ_calls.append((f"os.{label}",
                                              os.fsdecode(name)))
            return original(name, *rest)
        return call

    wrapped = {label: recorder(label, o) for label, o in originals.items()}
    try:
        for label, w in wrapped.items():
            setattr(os, label, w)
        for k, v in rebound.items():
            label = next(lbl for lbl, o in originals.items() if v is o)
            scope[k] = wrapped[label]
        yield trial
    finally:
        with _alarm_blocked():
            for label, o in originals.items():
                setattr(os, label, o)
            for k, v in rebound.items():
                scope[k] = v
            try:
                trial.after = snapshot()
            except Exception:
                trial.after = None
            names = sorted({name for _w, name in trial.c_environ_calls})
            trial.restore_failed = restore(trial.before, names)
        if trial.restore_failed:
            warnings.warn("mathema could not put the process back after "
                          "a trial: " + "; ".join(trial.restore_failed))


#: method names that configure process-wide state, whatever object they
#: are called on (a logger from `getLogger()`, a generator, a module)
_CONFIG_METHODS = frozenset({
    "setLevel", "addHandler", "removeHandler", "addFilter", "removeFilter",
    "setFormatter", "disable", "basicConfig", "seed", "set_state",
    "setstate", "chdir", "putenv", "unsetenv", "simplefilter",
    "filterwarnings", "setrecursionlimit"})


def _writers() -> set:
    import warnings
    writers = {os.putenv, os.unsetenv, os.chdir, random.seed,
               random.setstate, logging.basicConfig, logging.disable,
               warnings.simplefilter, warnings.filterwarnings,
               sys.setrecursionlimit}
    if hasattr(os, "fchdir"):
        writers.add(os.fchdir)
    npr = _numpy_random()
    if npr is not None:
        writers |= {npr.seed, npr.set_state}
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
        The calls in the body that write process-wide state, by the name
        the body calls: a bare name that resolves, through the
        function's module, to a writer (os.putenv, os.chdir,
        random.seed, numpy.random.seed, a draw from the global
        generator, ...), and any call of a configuration method
        (`setLevel`, `addHandler`, `seed`, `set_state`, ...) on any
        object, a call's result included, and a store into an object a
        call returned (`getLogger(name).propagate = False`).
    """
    from ._signatures import module_scope
    tree = getattr(facts, "tree", None)
    if tree is None:
        return []
    scope = module_scope(fn)
    writers = _writers()
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                root = t
                while isinstance(root, (ast.Attribute, ast.Subscript)):
                    root = root.value
                if root is not t and isinstance(root, ast.Call):
                    # a store into an object a call returned
                    # (`getLogger(name).propagate = False`,
                    # `getcontext().prec = 7`)
                    label = ast.unparse(t)
                    if label not in found:
                        found.append(label)
            continue
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in _CONFIG_METHODS):
            # a configuration method on anything, including an object a
            # call returned (`getLogger().setLevel(10)`), which no write
            # site rooted at a name can see
            if node.func.attr not in found:
                found.append(node.func.attr)
            continue
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
