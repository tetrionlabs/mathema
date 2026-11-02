# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Run pytest while holding slots of the machine's shared test pool.

Every test run on this machine, in this repository and in any other that
uses the same pool, takes its slots from one set of lock files before it
starts, so concurrent runs never oversubscribe the CPU. A proof attempt
is capped on the wall clock, and a slower machine turns `proven` into
`holds`; holding slots keeps the machine's load bounded by the pool's
size.

The pool is `$TETRION_TEST_POOL` (else `~/.cache/tetrion-check/slots`)
with `$TETRION_TEST_SLOTS` slots (else one per CPU): one file per slot,
each held by an exclusive `flock` that names its holder. A run takes all
the slots it asks for at once or none, and the kernel drops a dead
holder's locks, so a crashed run never keeps its slots.

Usage, from the repository root::

    uv run python scripts/test_slots.py -n 2 tests/test_x.py tests/test_y.py
    uv run python scripts/test_slots.py -n 4            # the whole suite
    uv run python scripts/test_slots.py --holders       # who holds what now

`-n N` is both the number of pytest-xdist workers and the number of
slots held; every other argument is passed to pytest unchanged.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import pathlib
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from typing import IO


class SlotPool:
    """Intent:
        The test slots every run on this machine shares: `size` files
        under `root`, each held by an exclusive `flock` and naming its
        holder.
    """

    def __init__(self, root: pathlib.Path, size: int) -> None:
        self.root, self.size = pathlib.Path(root), max(1, size)

    @classmethod
    def default(cls) -> "SlotPool":
        """The pool named by the environment, else the machine default."""
        root = os.environ.get("TETRION_TEST_POOL") or (
            pathlib.Path.home() / ".cache" / "tetrion-check" / "slots")
        size = int(os.environ.get("TETRION_TEST_SLOTS") or os.cpu_count() or 4)
        return cls(pathlib.Path(root), size)

    def wanted(self, n: int) -> int:
        """The slots a request for `n` takes: at least one, at most the pool."""
        return max(1, min(n, self.size))

    def try_take(self, n: int, holder: str) -> list[IO[str]] | None:
        """The open slot files of `wanted(n)` slots now locked for `holder`,
        or None, holding nothing, when that many are not free."""
        self.root.mkdir(parents=True, exist_ok=True)
        want, taken = self.wanted(n), list[IO[str]]()
        for i in range(self.size):
            handle = open(self.root / f"slot-{i}", "a+")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            handle.seek(0)
            handle.truncate()
            handle.write(holder)
            handle.flush()
            taken.append(handle)
            if len(taken) == want:
                return taken
        self.release(taken)
        return None

    @staticmethod
    def release(taken: list[IO[str]]) -> None:
        """Unlock and close every slot in `taken`."""
        for handle in taken:
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()

    def holders(self) -> list[str]:
        """The holder of each slot taken now, in slot order."""
        found = []
        for i in range(self.size):
            path = self.root / f"slot-{i}"
            if not path.exists():
                continue
            with open(path) as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    found.append(handle.read())
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)
        return found

    @contextlib.contextmanager
    def held(self, n: int, holder: str, *, say: Callable[[str], None] = print,
             sleep: Callable[[float], None] = time.sleep,
             poll: float = 5.0) -> Iterator[list[IO[str]]]:
        """Hold `wanted(n)` slots for the body, waiting until they are free
        and saying once who holds them meanwhile."""
        taken = self.try_take(n, holder)
        if taken is None:
            say(f"waiting for {self.wanted(n)} of {self.size} test slots, held by: "
                + "; ".join(sorted(set(self.holders()))))
            while taken is None:
                sleep(poll)
                taken = self.try_take(n, holder)
        try:
            yield taken
        finally:
            self.release(taken)


def split_workers(argv: list[str]) -> tuple[int, list[str]]:
    """The worker count named by `-n N` (one when absent) and the
    remaining pytest arguments."""
    workers, rest, i = 1, [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "-n" and i + 1 < len(argv):
            workers, i = int(argv[i + 1]), i + 2
            continue
        if arg.startswith("-n") and arg[2:].isdigit():
            workers, i = int(arg[2:]), i + 1
            continue
        rest.append(arg)
        i += 1
    return workers, rest


def main(argv: list[str]) -> int:
    """Hold the slots `-n` asks for, run pytest with the rest, return its code."""
    pool = SlotPool.default()
    if argv[:1] == ["--holders"]:
        for line in pool.holders():
            print(line)
        return 0
    workers, rest = split_workers(argv)
    command = [sys.executable, "-m", "pytest", "-q", *(["-n", str(workers)] if workers > 1 else []), *rest]
    holder = f"mathema {pathlib.Path.cwd().name} pid {os.getpid()}: {' '.join(command[2:])[:200]}"
    with pool.held(workers, holder, say=lambda text: print(text, flush=True)):
        return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
