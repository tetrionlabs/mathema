# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Language domains: the values `for s in L[ascii]` admits.

A numeric domain is a set of numbers a claim quantifies over. A
language domain is the same thing for strings and structured values:
a named set with a membership test, a generator, the hazard values a
probe must visit, and an explanation of why a value is not a member.
The name is what a claim writes (`L[ascii]`, `L[latin-1]`), and the
`Language` protocol below is what stands behind it.

Three sources supply a name. The built-in alphabets in
`BUILTIN_LANGUAGES` resolve first and are never overridden. A package
registers a named language under the `mathema.languages` entry-point
group (the name is the language name), or an adaptor under
`mathema.language_adaptors` (a callable turning an imported object, a
schema class say, into a `Language`, or `None` for "not mine"), which
is how a dotted reference such as `L[myapp.models.Order]` resolves.
An unknown name refuses loudly with the vocabulary, never a silently
wider domain.

Every language here is a set of `str`. Membership follows Python's
own reading of the alphabet (`str.isascii`, the `latin-1` codec,
`str.isprintable`), and an alphabet language contains the empty
string, the way a Kleene star does; a predicate language (`json`,
`identifier`) contains exactly what its predicate accepts.

Stdlib only, so the domain model, the sampler and the spec store can
all read a language without importing the symbolic engine.
"""
from __future__ import annotations

import functools
import importlib
import json
import random
import string
import unicodedata
import warnings
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Callable, Iterable, Protocol, runtime_checkable

from ._sampling import _STRING_SPECIALS
from .domain import InvalidDomain, LanguageRef

LANGUAGE_GROUP = "mathema.languages"
ADAPTOR_GROUP = "mathema.language_adaptors"

#: what a member of a language IS, in the parameter-kind vocabulary
#: `analysis.param_kinds` uses, so a claim quantifying an `int`
#: parameter over a string language can be flagged.
KINDS = ("string", "mapping", "sequence", "object")

#: how much a language can be decided: a `finite` language is swept
#: point by point and can be proven; an `alphabet`, `regular` or
#: `predicate` language is sampled and holds at best; a `schema`
#: language lifts its fields for the derive route.
LEVELS = ("finite", "alphabet", "regular", "predicate", "schema")

#: the hazard kinds a string language reports: `empty` (the empty
#: string), `whitespace` (nothing but blanks), `control` (control,
#: format, combining and surrogate code points), `length` (a long
#: string), `encoding` (code points past an alphabet boundary) and
#: `text` (ordinary-looking text a parser tends to mishandle: a
#: number, a format string, a path, an injection).
HAZARD_KINDS = ("empty", "whitespace", "control", "length", "encoding", "text")


@dataclass(frozen=True)
class Problem:
    """Why a value is not a member: where in the value (`path`, empty
    for the value itself, `[3]` for a character, `field` for a schema
    field), the predicate it failed, and the offending piece."""
    path: str
    predicate: str
    value: object


@dataclass(frozen=True)
class HazardValue:
    """One value a probe over the language must visit: its hazard
    `kind` (one of `HAZARD_KINDS`), the value, and a short note."""
    kind: str
    value: object
    note: str = ""


@runtime_checkable
class Language(Protocol):
    """One language: a named set of values a claim can quantify over.

    `name` is what a claim writes inside `L[...]`; `kind` says what a
    member is (one of `KINDS`); `level` says how far the engine can
    decide it (one of `LEVELS`). `contains` is membership, `explain`
    the reason for a refusal, `sample` one random member, `members`
    every member when there are at most `limit` of them (else `None`,
    never a prefix), `hazards` the members a probe must visit,
    `outside` a non-member near the boundary or `None`, `shrink`
    smaller members reached from a failing one, `fields` the one-deep
    field domains of a schema language (else `None`), `render` the
    domain text, and `to_json` the persisted form (JSON Schema where
    the language can be written as one)."""

    name: str
    kind: str
    level: str

    def contains(self, value) -> bool: ...

    def explain(self, value) -> "list[Problem] | None": ...

    def sample(self, rng: random.Random): ...

    def members(self, limit: int) -> "tuple | None": ...

    def hazards(self) -> tuple: ...

    def outside(self, rng: random.Random): ...

    def shrink(self, value) -> Iterable: ...

    def fields(self) -> "dict | None": ...

    def render(self, ascii_mode: bool) -> str: ...

    def to_json(self) -> dict: ...


_REQUIRED_CALLABLES = ("contains", "explain", "sample", "members", "hazards",
                       "outside", "shrink", "fields", "render", "to_json")


def language_problems(obj) -> list[str]:
    """Intent:
        Every way `obj` fails the `Language` protocol, as readable
        strings; an empty list means it conforms. The registry checks
        a registered or adapted language through this before serving
        it, so a broken third-party language is refused with a reason
        rather than crashing a probe.
    """
    problems: list[str] = []
    name = getattr(obj, "name", None)
    if not isinstance(name, str) or not name:
        problems.append("language: missing a non-empty str 'name'")
    if getattr(obj, "kind", None) not in KINDS:
        problems.append(f"language: 'kind' must be one of {KINDS}")
    if getattr(obj, "level", None) not in LEVELS:
        problems.append(f"language: 'level' must be one of {LEVELS}")
    for member in _REQUIRED_CALLABLES:
        target = getattr(obj, member, None)
        if target is None:
            problems.append(f"language: missing {member!r}")
        elif not callable(target):
            problems.append(f"language: {member!r} is not callable")
    return problems


# --- the string hazard corpus -----------------------------------------

def _hazard_kind(s: str) -> str:
    """The hazard kind of one corpus string, from its content."""
    if s == "":
        return "empty"
    if s.isspace():
        return "whitespace"
    if len(s) >= 1024:
        return "length"
    if any(unicodedata.category(c) in ("Cc", "Cf", "Mn", "Cs") for c in s):
        return "control"
    if any(ord(c) >= 0x80 for c in s):
        return "encoding"
    return "text"


_HAZARD_NOTES = {
    "": "the empty string",
    "A" * 4096: "a long string",
    "\x00": "NUL",
    "\x7f": "DEL",
    "​": "a zero-width space",
    "á": "a combining mark",
    "﻿": "a byte-order mark",
    "‮": "a right-to-left override",
    "\ud800": "a lone surrogate, which no codec can encode",
    "\x80": "the first code point past ascii",
    "\xff": "the last latin-1 code point",
    "Ā": "the first code point past latin-1",
}

#: the shared corpus (`_sampling._STRING_SPECIALS`, the fuzz family's
#: own inputs) plus the alphabet boundaries and the format code points
#: a language sampler must reach, each tagged with its hazard kind.
STRING_HAZARDS: tuple = tuple(
    HazardValue(_hazard_kind(s), s, _HAZARD_NOTES.get(s, ""))
    for s in list(_STRING_SPECIALS) + [
        "﻿", "‮", "\ud800", "\x80", "\xff", "Ā"])


# --- string languages -------------------------------------------------

_ASCII_POOL = string.printable + "\x00\x7f"
_LATIN1_POOL = _ASCII_POOL + "".join(chr(c) for c in range(0x80, 0x100, 5))
_UNICODE_POOL = (_LATIN1_POOL
                 + "日本語\U0001f642é́​﻿"
                 + "‮ĀΩж")
_LETTERS = string.ascii_letters + "éΩж日"


def _draw_length(rng: random.Random) -> int:
    """A member length: short most of the time, occasionally long
    enough to reach buffer-sized behaviour."""
    if rng.random() < 0.1:
        return rng.randint(64, 300)
    return rng.randint(0, 12)


@dataclass(frozen=True)
class StringLanguage:
    """A language of `str` values, defined by a per-character test
    (`char_ok`, an alphabet: every string over it is a member, the
    empty string included) or a whole-string test (`accepts`, a
    predicate: exactly the strings it accepts). `pool` is the
    character pool random members are drawn from, `generate` an
    optional generator for a predicate language whose members are
    not reachable by drawing characters (a JSON document), and
    `outside_pool` characters known to lie outside the language, for
    a near non-member. `schema` is merged into the persisted form."""
    name: str
    level: str = "alphabet"
    char_ok: "Callable[[str], bool] | None" = None
    accepts: "Callable[[str], bool] | None" = None
    pool: str = _ASCII_POOL
    generate: "Callable[[random.Random], str] | None" = None
    outside_pool: str = ""
    schema: dict = field(default_factory=dict)

    kind: str = "string"

    def contains(self, value) -> bool:
        if not isinstance(value, str):
            return False
        if self.accepts is not None:
            try:
                return bool(self.accepts(value))
            except Exception:
                return False
        assert self.char_ok is not None
        return all(self.char_ok(c) for c in value)

    def explain(self, value) -> "list[Problem] | None":
        if self.contains(value):
            return None
        if not isinstance(value, str):
            return [Problem("", "str", value)]
        if self.char_ok is not None:
            for i, c in enumerate(value):
                if not self.char_ok(c):
                    return [Problem(f"[{i}]", f"{self.name} alphabet", c)]
        return [Problem("", self.name, value)]

    def sample(self, rng: random.Random) -> str:
        if self.generate is not None:
            for _ in range(20):
                s = self.generate(rng)
                if self.contains(s):
                    return s
        for _ in range(20):
            s = "".join(rng.choice(self.pool) for _ in range(_draw_length(rng)))
            if self.contains(s):
                return s
        members = [h.value for h in self.hazards()]
        return rng.choice(members) if members else ""

    def members(self, limit: int) -> "tuple | None":
        return None

    def hazards(self) -> tuple:
        members = [h for h in STRING_HAZARDS if self.contains(h.value)]
        if not any(h.kind == "length" for h in members) and self.pool:
            # the corpus's long string is outside a narrow alphabet, so a
            # long member is built from the alphabet's own first character
            long = self.pool[0] * 4096
            if self.contains(long):
                members.append(HazardValue("length", long, "a long member"))
        return tuple(members)

    def outside(self, rng: random.Random):
        candidates = [h.value for h in STRING_HAZARDS if not self.contains(h.value)]
        if self.outside_pool:
            inside = self.sample(rng)
            at = rng.randint(0, len(inside))
            mutated = inside[:at] + rng.choice(self.outside_pool) + inside[at:]
            if not self.contains(mutated):
                candidates.append(mutated)
        return rng.choice(candidates) if candidates else None

    def shrink(self, value) -> Iterable:
        if not isinstance(value, str):
            return ()
        out: list[str] = []
        seen = {value}

        def offer(s):
            if s not in seen and self.contains(s):
                seen.add(s)
                out.append(s)

        n = len(value)
        size = max(1, n)
        while size >= 1:
            for i in range(0, n, size):
                offer(value[:i] + value[i + size:])
            size //= 2
        for i in range(n):
            for simpler in ("a", " ", "0"):
                if value[i] != simpler:
                    offer(value[:i] + simpler + value[i + 1:])
        return tuple(out)

    def fields(self) -> "dict | None":
        return None

    def render(self, ascii_mode: bool = True) -> str:
        return f"L[{self.name}]"

    def to_json(self) -> dict:
        return {"type": "string", "language": self.name, "level": self.level,
                **self.schema}


def _generate_identifier(rng: random.Random) -> str:
    first = rng.choice(string.ascii_letters + "_")
    rest = "".join(rng.choice(string.ascii_letters + string.digits + "_")
                   for _ in range(rng.randint(0, 11)))
    return first + rest


def _generate_json(rng: random.Random) -> str:
    def value(depth: int):
        choice = rng.random()
        if depth > 1 or choice < 0.4:
            return rng.choice([0, 1, -1, 1.5, 1e300, True, False, None,
                               "", "a", "café", "日本語"])
        if choice < 0.7:
            return [value(depth + 1) for _ in range(rng.randint(0, 3))]
        return {rng.choice(["a", "b", "key", ""]): value(depth + 1)
                for _ in range(rng.randint(0, 3))}
    return json.dumps(value(0), ensure_ascii=False)


def _is_json(s: str) -> bool:
    try:
        json.loads(s)
    except ValueError:
        return False
    return True


def _printable(c: str) -> bool:
    return c.isprintable()


def _is_ascii(c: str) -> bool:
    return ord(c) < 0x80


def _is_latin1(c: str) -> bool:
    return ord(c) < 0x100


def _is_digit(c: str) -> bool:
    return c in string.digits


def _is_alpha(c: str) -> bool:
    return c.isalpha()


def _is_alnum(c: str) -> bool:
    return c.isalnum()


def _every_str(s: str) -> bool:
    return True


BUILTIN_LANGUAGES: dict = {
    lang.name: lang for lang in (
        StringLanguage("ascii", char_ok=_is_ascii, pool=_ASCII_POOL,
                       outside_pool="\x80é日\U0001f642",
                       schema={"pattern": "^[\\x00-\\x7f]*$"}),
        StringLanguage("latin-1", char_ok=_is_latin1, pool=_LATIN1_POOL,
                       outside_pool="Ā日\U0001f642",
                       schema={"pattern": "^[\\x00-\\xff]*$"}),
        StringLanguage("unicode", accepts=_every_str, pool=_UNICODE_POOL),
        StringLanguage("printable", char_ok=_printable,
                       pool="".join(c for c in _UNICODE_POOL if c.isprintable()),
                       outside_pool="\x00\n\x7f​"),
        StringLanguage("digit", char_ok=_is_digit, pool=string.digits,
                       outside_pool="a -.٣",
                       schema={"pattern": "^[0-9]*$"}),
        StringLanguage("alpha", char_ok=_is_alpha, pool=_LETTERS,
                       outside_pool="1 -_"),
        StringLanguage("alnum", char_ok=_is_alnum,
                       pool=_LETTERS + string.digits, outside_pool=" -_."),
        StringLanguage("identifier", level="predicate",
                       accepts=str.isidentifier, generate=_generate_identifier,
                       pool=string.ascii_letters + string.digits + "_",
                       outside_pool=" -.1"),
        StringLanguage("json", level="predicate", accepts=_is_json,
                       generate=_generate_json, pool=_ASCII_POOL,
                       outside_pool="{'"),
    )
}


# --- the registry -----------------------------------------------------

_REGISTRY: dict = {}


class UnknownLanguage(InvalidDomain):
    """Raised when `L[<name>]` names no language: not a built-in, not
    registered in this process, not served by a `mathema.languages`
    entry point, and (for a dotted name) not importable or not
    accepted by any `mathema.language_adaptors` adaptor. The message
    lists the vocabulary and the groups, so the remedy is in the
    error."""

    def __init__(self, name: str, vocabulary: tuple, detail: str = ""):
        self.name = name
        self.vocabulary = vocabulary
        hint = (f"; a dotted name is imported and offered to the "
                f"{ADAPTOR_GROUP!r} adaptors" if "." in name else
                f"; a package adds one under the {LANGUAGE_GROUP!r} "
                f"entry-point group")
        super().__init__(
            f"unknown language L[{name}]: known languages are "
            + ", ".join(vocabulary) + hint
            + (f" ({detail})" if detail else ""))


def register_language(name: str, language) -> None:
    """Intent:
        Make `language` resolvable as `L[<name>]` in this process,
        the in-process half of the seam (the entry-point groups are
        the packaged half). A built-in name is never replaced, and a
        language failing the protocol is refused with the reasons.

    Raises:
        ValueError: `name` is a built-in, or `language` does not
            satisfy `language_problems`.
    """
    if name in BUILTIN_LANGUAGES:
        raise ValueError(f"L[{name}] is a built-in language and cannot be "
                         f"replaced")
    problems = language_problems(language)
    if problems:
        raise ValueError(f"L[{name}] cannot be registered: "
                         + "; ".join(problems))
    _REGISTRY[name] = language


def unregister_language(name: str) -> None:
    """Remove an in-process registration; a name never registered is
    left alone."""
    _REGISTRY.pop(name, None)


@functools.lru_cache(maxsize=1)
def _discovered_languages() -> dict:
    return {ep.name: ep for ep in entry_points(group=LANGUAGE_GROUP)}


@functools.lru_cache(maxsize=1)
def _discovered_adaptors() -> tuple:
    return tuple(sorted(entry_points(group=ADAPTOR_GROUP), key=lambda ep: ep.name))


@functools.lru_cache(maxsize=None)
def _load_language(name: str):
    ep = _discovered_languages().get(name)
    if ep is None:
        return None
    try:
        language = ep.load()
    except Exception as e:
        warnings.warn(f"mathema: language {ep.value!r} registered under "
                      f"{name!r} failed to load ({e!r}), skipping it",
                      stacklevel=2)
        return None
    problems = language_problems(language)
    if problems:
        warnings.warn(f"mathema: language {ep.value!r} registered under "
                      f"{name!r} does not satisfy the Language protocol "
                      f"({'; '.join(problems)}), skipping it", stacklevel=2)
        return None
    return language


@functools.lru_cache(maxsize=1)
def _loaded_adaptors() -> tuple:
    out = []
    for ep in _discovered_adaptors():
        try:
            out.append((ep.name, ep.load()))
        except Exception as e:
            warnings.warn(f"mathema: language adaptor {ep.value!r} registered "
                          f"under {ep.name!r} failed to load ({e!r}), "
                          f"skipping it", stacklevel=2)
    return tuple(out)


def _import_dotted(name: str):
    """The object a dotted path names, importing the longest module
    prefix that imports and walking the rest, or `None`."""
    parts = name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        try:
            for attr in parts[i:]:
                obj = getattr(obj, attr)
        except AttributeError:
            return None
        return obj
    return None


def language_vocabulary() -> tuple:
    """Every name `L[...]` resolves by name alone: the built-ins, the
    in-process registrations and the entry-point languages, sorted."""
    return tuple(sorted(set(BUILTIN_LANGUAGES) | set(_REGISTRY)
                        | set(_discovered_languages())))


def resolve(ref) -> tuple:
    """Intent:
        `(language, source)` for a `LanguageRef` or a bare name, the
        source being `"built-in"`, `"registered"`, `"entry point
        <value>"` or `"adaptor <name>"`, in that precedence.

    Raises:
        UnknownLanguage: nothing serves the name.
    """
    name = ref.name if isinstance(ref, LanguageRef) else str(ref)
    if name in BUILTIN_LANGUAGES:
        return BUILTIN_LANGUAGES[name], "built-in"
    if name in _REGISTRY:
        return _REGISTRY[name], "registered"
    loaded = _load_language(name)
    if loaded is not None:
        return loaded, f"entry point {_discovered_languages()[name].value}"
    detail = ""
    if "." in name:
        obj = _import_dotted(name)
        if obj is None:
            detail = "the dotted name does not import"
        else:
            if not language_problems(obj):
                return obj, "object"
            for adaptor_name, adapt in _loaded_adaptors():
                try:
                    adapted = adapt(obj)
                except Exception as e:
                    warnings.warn(f"mathema: language adaptor {adaptor_name!r} "
                                  f"failed on L[{name}] ({e!r}), skipping it",
                                  stacklevel=2)
                    continue
                if adapted is not None and not language_problems(adapted):
                    return adapted, f"adaptor {adaptor_name}"
            detail = ("the object imports but no adaptor accepts it"
                      if _loaded_adaptors() else
                      "the object imports but no language adaptor is installed")
    raise UnknownLanguage(name, language_vocabulary(), detail)


def resolve_language(ref):
    """The `Language` behind a `LanguageRef` or a bare name; see
    `resolve` for the precedence and the refusal."""
    return resolve(ref)[0]


def describe_language(ref) -> dict:
    """The record's statement of a resolved language: its name, where
    it came from, its level and kind, and its persisted form."""
    language, source = resolve(ref)
    return {"name": ref.name if isinstance(ref, LanguageRef) else str(ref),
            "source": source, "level": language.level,
            "kind": language.kind, "schema": language.to_json()}


__all__ = [
    "ADAPTOR_GROUP", "BUILTIN_LANGUAGES", "HAZARD_KINDS", "HazardValue",
    "KINDS", "LANGUAGE_GROUP", "LEVELS", "Language", "Problem",
    "STRING_HAZARDS", "StringLanguage", "UnknownLanguage",
    "describe_language", "language_problems", "language_vocabulary",
    "register_language", "resolve", "resolve_language",
    "unregister_language",
]
