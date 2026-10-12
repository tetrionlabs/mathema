# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Frontends registered under the `mathema.frontends` entry-point group.

Each entry is a callable `(fn) -> Document | str | None`: a KOINE
document (or its text) for the body of `fn`, or None when it does not
write that callable. `analyze_source` asks the entries before the
Python frontend, ordered by distribution name and then entry name; the
first document the engine takes is the body the claims are proved from.
An entry that fails to load, raises, or returns a document the engine
declines is skipped with a warning, and the next is asked; so is an
entry named `python`, the name the Python frontend's body hash is kept
under.

`registered_facts(frontend, body, python)` is the `Facts` a registered frontend's
document gives: the body fields (tree, structure, guards, form) from
the document, every other field from the Python frontend's facts when
it can read `fn` too. `provenance` names the frontend (its entry name,
distribution, version and the document's language) and the document's
`koine_hash`; `body_hashes` holds the hash of the body each frontend
wrote, by frontend name, the Python frontend's under `python`.
"""
from __future__ import annotations

import functools
import warnings
from dataclasses import dataclass, replace
from importlib.metadata import entry_points
from typing import Any, Callable

from ..analysis import Facts
from .canonical import koine_hash
from .document import Document
from .facts import KoineDeclined, facts_from_koine

GROUP = "mathema.frontends"

#: the key the Python frontend's body hash is kept under in `body_hashes`
PYTHON = "python"


@dataclass(frozen=True)
class Frontend:
    """A registered frontend: its entry name, the distribution that
    registers it and that distribution's version."""
    name: str
    distribution: str | None
    version: str | None
    entry: Any


@functools.lru_cache(maxsize=1)
def _entry_points() -> tuple:
    """The entries under `GROUP`, ordered by distribution name and then
    entry name, read once per process and none of them loaded."""
    def order(ep):
        dist = getattr(ep, "dist", None)
        return (getattr(dist, "name", None) or "", ep.name)
    return tuple(sorted(entry_points(group=GROUP), key=order))


#: the frontends loaded so far, by entry name and value
_LOADED: dict[tuple, Callable] = {}


def _reset_discovery() -> None:
    """Forget the entries read and the frontends loaded, so the next call
    discovers afresh."""
    _entry_points.cache_clear()
    _LOADED.clear()


def frontends() -> tuple:
    """Intent:
        Every registered frontend that loads, in the order they are
        asked. One whose load fails is skipped with a warning and tried
        again on the next call; one registered under `python`, the
        Python frontend's own name, is skipped with a warning.
    """
    out = []
    for ep in _entry_points():
        key = (ep.name, ep.value)
        if ep.name == PYTHON:
            warnings.warn(f"mathema: frontend {ep.value!r} is registered under "
                          f"{PYTHON!r}, the Python frontend's own name; skipping it",
                          stacklevel=3)
            continue
        if key not in _LOADED:
            try:
                _LOADED[key] = ep.load()
            except Exception as e:
                warnings.warn(f"mathema: frontend {ep.value!r} registered under "
                              f"{ep.name!r} failed to load ({e!r}), skipping it",
                              stacklevel=3)
                continue
        dist = getattr(ep, "dist", None)
        out.append(Frontend(ep.name, getattr(dist, "name", None),
                            getattr(dist, "version", None), _LOADED[key]))
    return tuple(out)


def registered_body(fn) -> "tuple[Frontend, Facts] | None":
    """Intent:
        The first registered frontend that writes a body for `fn` the
        engine takes, with the `Facts` its document reads into; None
        when there is none (always, when nothing is registered).
    """
    for frontend in frontends():
        try:
            written = frontend.entry(fn)
        except Exception as e:
            _skipped(frontend, f"raised {e!r}")
            continue
        if written is None:
            continue
        if not isinstance(written, (Document, str)):
            _skipped(frontend, f"returned a {type(written).__name__}, not a document")
            continue
        try:
            return frontend, facts_from_koine(written)
        except KoineDeclined as e:
            _skipped(frontend, f"wrote a body the engine declines ({e})")
    return None


def _skipped(frontend: Frontend, why: str) -> None:
    warnings.warn(f"mathema: frontend {frontend.name!r} {why}; asking the next "
                  f"frontend", stacklevel=4)


#: the body fields a registered frontend's document supplies
_BODY_FIELDS = ("tree", "source", "loops", "comprehensions", "recursion",
                "branch_count", "call_groups", "max_loop_depth", "lines",
                "form", "guards", "koine")


def registered_facts(frontend: Frontend, body: Facts,
                     python: "Facts | None") -> Facts:
    """Intent:
        The facts of a callable whose body `frontend` wrote (`body`, read
        from its document): with no `python` facts, `body` itself; else
        `python` with its body fields replaced by the document's, so the
        name, signature, kinds, docstring and effects stay the Python
        frontend's. Either way `provenance` names `frontend` and the
        document's `koine_hash`, and `body_hashes` holds each frontend's
        body hash.
    """
    doc = body.koine
    assert doc is not None
    digest = koine_hash(doc)
    named = {"name": frontend.name, "distribution": frontend.distribution,
             "version": frontend.version, "language": doc.language}
    provenance = {"frontend": {k: v for k, v in named.items() if v is not None},
                  "koine_hash": digest}
    hashes = {frontend.name: digest}
    if python is None:
        return replace(body, provenance=provenance, body_hashes=hashes)
    hashes[PYTHON] = python.form
    return replace(python, **{f: getattr(body, f) for f in _BODY_FIELDS},
                   _computed_form=None, provenance=provenance, body_hashes=hashes)

