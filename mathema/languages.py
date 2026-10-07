# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Language domains: the values `for s in L[ascii]` admits.

A numeric domain is a set of numbers a claim quantifies over. A
language domain is the same thing for strings and structured values:
a named set with a membership test, a generator, the hazard values a
probe must visit, and an explanation of why a value is not a member.
The name is what a claim writes (`L[ascii]`, `L[latin-1]`), and the
`Language` protocol below is what stands behind it.

Core ships no language of its own. A name resolves through, in
order, an in-process registration (`register_language`), a package's
`mathema.languages` entry point (the name is the language name), a
dotted path to a `Language` object, and the `mathema.language_adaptors`
adaptors (a callable turning an imported object, a schema class say,
into a `Language`, or `None` for "not mine"), which is how a dotted
reference such as `L[myapp.models.Order]` resolves. The alphabets and
predicate languages (`ascii`, `latin-1`, `unicode`, `json`, ...) are
the `mathema-language` package's, installed as `mathema[language]`. An
unknown name refuses loudly with the vocabulary, never a silently
wider domain.

`StringLanguage` is the assembly kit for a language of `str` values:
a per-character test (an alphabet, every string over it a member, the
empty string included, the way a Kleene star reads) or a whole-string
test (a predicate, exactly what it accepts). `STRING_HAZARDS` is the
corpus every string language draws its hazards from.

Stdlib only, so the domain model, the sampler and the spec store can
all read a language without importing the symbolic engine.
"""
from __future__ import annotations

import functools
import importlib
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
#: parameter over a string language can be flagged. A `row` is one
#: record of a schema, a `table` a frame of named, equal-length
#: columns whose rows are such records.
KINDS = ("string", "mapping", "sequence", "object", "row", "table")

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
#: number, a format string, a path, an injection). A structured
#: language adds `null` (a missing value where one is allowed),
#: `extremity` (a numeric field at its bounds), `duplicate` (repeated
#: keys or rows), `layout` (a physical layout, chunked or sliced),
#: `time` (a timestamp at a boundary) and `shape` (an empty, single-row
#: or wide table).
HAZARD_KINDS = ("empty", "whitespace", "control", "length", "encoding", "text",
                "null", "extremity", "duplicate", "layout", "time", "shape")


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


def language_problems(obj: object) -> list[str]:
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
    "\x80": "the first code point past 0x7f",
    "\xff": "code point 0xff",
    "Ā": "the first code point past 0xff",
}

#: the shared corpus (`_sampling._STRING_SPECIALS`, the fuzz family's
#: own inputs) plus the alphabet boundaries and the format code points
#: a language sampler must reach, each tagged with its hazard kind.
STRING_HAZARDS: tuple = tuple(
    HazardValue(_hazard_kind(s), s, _HAZARD_NOTES.get(s, ""))
    for s in list(_STRING_SPECIALS) + [
        "﻿", "‮", "\ud800", "\x80", "\xff", "Ā"])


# --- string languages -------------------------------------------------

#: the default character pool a `StringLanguage` draws random members
#: from: printable ascii plus the two control code points at its ends
_ASCII_POOL = string.printable + "\x00\x7f"


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
        """Smaller members, one at a time and the largest deletions
        first (the whole value, then halves, quarters and so on down to
        single characters), then each character replaced by a simpler
        one; a caller that stops at the first useful candidate checks
        only the candidates before it."""
        if not isinstance(value, str):
            return
        seen = {value}
        n = len(value)
        size = max(1, n)
        while size >= 1:
            for i in range(0, n, size):
                s = value[:i] + value[i + size:]
                if s not in seen and self.contains(s):
                    seen.add(s)
                    yield s
            size //= 2
        for i in range(n):
            for simpler in ("a", " ", "0"):
                if value[i] != simpler:
                    s = value[:i] + simpler + value[i + 1:]
                    if s not in seen and self.contains(s):
                        seen.add(s)
                        yield s

    def fields(self) -> "dict | None":
        return None

    def render(self, ascii_mode: bool = True) -> str:
        return f"L[{self.name}]"

    def to_json(self) -> dict:
        return {"type": "string", "language": self.name, "level": self.level,
                **self.schema}


# --- the registry -----------------------------------------------------

_REGISTRY: dict = {}


class UnknownLanguage(InvalidDomain):
    """Raised when `L[<name>]` names no language: not registered in
    this process, not served by a `mathema.languages` entry point, and
    (for a dotted name) not importable or not accepted by any
    `mathema.language_adaptors` adaptor. The message lists the
    vocabulary, the groups and the package that ships the common
    languages, so the remedy is in the error."""

    def __init__(self, name: str, vocabulary: tuple, detail: str = ""):
        self.name = name
        self.vocabulary = vocabulary
        known = (", ".join(vocabulary) if vocabulary
                 else "none in this process")
        hint = (f"; a dotted name is imported and offered to the "
                f"{ADAPTOR_GROUP!r} adaptors" if "." in name else
                f"; a package adds one under the {LANGUAGE_GROUP!r} "
                f"entry-point group, and 'pip install \"mathema[language]\"' "
                f"brings the built-in alphabets and languages")
        super().__init__(
            f"unknown language L[{name}]: known languages are {known}"
            + hint + (f" ({detail})" if detail else ""))


REFINEMENT_GROUP = "mathema.language_refinements"

#: refinements registered in this process, by key
_REFINEMENTS: dict = {}


@functools.lru_cache(maxsize=1)
def _discovered_refinements() -> dict:
    return {ep.name: ep for ep in entry_points(group=REFINEMENT_GROUP)}


_GENERATION = [0]


def _changed() -> None:
    """Note that a registration changed, so anything resolved before
    it is resolved again."""
    _GENERATION[0] += 1


def generation() -> int:
    """A number that changes whenever a language or a refinement is
    registered or removed in this process."""
    return _GENERATION[0]


def register_refinement(key: str,
                        refine: Callable[[Language, object], Language]) -> None:
    """Intent:
        Serve the refinement `key` inside `L[...]` in this process:
        `refine(language, interval)` returns the language refined to
        the members whose measure lies in the interval. An in-process
        registration wins over an entry point of the same key.
    """
    _REFINEMENTS[key] = refine
    _changed()


def unregister_refinement(key: str) -> None:
    """Remove an in-process refinement registration."""
    _REFINEMENTS.pop(key, None)
    _changed()


def _refinement(key: str):
    if key in _REFINEMENTS:
        return _REFINEMENTS[key]
    ep = _discovered_refinements().get(key)
    if ep is None:
        return None
    try:
        return ep.load()
    except Exception as e:
        warnings.warn(f"mathema: language refinement {ep.value!r} registered "
                      f"under {key!r} failed to load ({e!r}), skipping it",
                      stacklevel=2)
        return None


def refinement_keys() -> tuple:
    """Every refinement key `L[...]` accepts in this process: the
    in-process registrations and the entry points, sorted. mathema
    itself registers none."""
    return tuple(sorted(set(_REFINEMENTS) | set(_discovered_refinements())))


class UnknownRefinement(UnknownLanguage):
    """Raised when a piece states a refinement no registered language
    refinement serves (`L[json, depth <= 6]` with nothing registered
    under `depth`); the message names the keys that are known and the
    group a package registers one under."""

    def __init__(self, ref, key: str):
        self.key = key
        known = ", ".join(refinement_keys()) or "none in this process"
        InvalidDomain.__init__(
            self,
            f"L[{ref.text}]: no language refinement is registered under "
            f"{key!r}; known keys are {known}; a package adds one under the "
            f"{REFINEMENT_GROUP!r} entry-point group, and "
            f"'pip install \"mathema[language]\"' brings len, depth, nodes "
            f"and width")
        self.name = ref.text
        self.vocabulary = refinement_keys()


#: how many measures inside (or past) a bound are tried when no member
#: has the bound's own measure
_NEAREST = 3


class RefinedLanguage:
    """The members of `base` whose `measure` lies in `interval`, the
    kit a refinement key is built from (`L[ascii, len <= 80]` is
    `RefinedLanguage(ascii, "len", [0, 80], measure=len)`). Random
    members come from the base by rejection, then from `build(rng, n)`,
    a base member of measure exactly `n`, when given. The members at
    each bound are hazards, from `plain(n)` (a simplest member of
    measure `n`, which may or may not be a base member) where given, else
    built, each of kind `hazard_kind`, and a base member one past a
    bound is the outside draw; where no member has a bound's measure
    exactly, the nearest within a few steps inside (or past) it stands
    in. `schema` is merged into the persisted
    form (`{"maxLength": 80}`). A value the measure cannot be taken of
    is not a member."""

    def __init__(self, base, key: str, interval, *, measure, plain=None, build=None,
                 schema: "dict | None" = None, hazard_kind: str = "shape") -> None:
        from .domain import refinement_range, render_refinement
        self.base = base
        self.key = key
        self.interval = interval
        self.measure = measure
        self._plain_of = plain
        self._build_of = build
        self._schema = dict(schema or {})
        self.hazard_kind = hazard_kind
        self.lo, self.hi = refinement_range(interval)
        self.bound_text = render_refinement(key, interval)
        self.name = f"{base.name}, {self.bound_text}"
        self.kind = base.kind
        self.level = base.level

    def _measured(self, value):
        try:
            return self.measure(value)
        except Exception:
            return None

    def _fits(self, value) -> bool:
        n = self._measured(value)
        return n is not None and n >= self.lo and (self.hi is None or n <= self.hi)

    def contains(self, value) -> bool:
        return self._fits(value) and bool(self.base.contains(value))

    def explain(self, value):
        if self.base.contains(value) and not self._fits(value):
            return [Problem("", self.bound_text, value)]
        return self.base.explain(value)

    def _member_of(self, rng: random.Random, n: int):
        """A base member of measure exactly `n`, or None."""
        if n < 0:
            return None
        if self._plain_of is not None:
            try:
                candidate = self._plain_of(n)
            except Exception:
                candidate = None
            if candidate is not None and self.base.contains(candidate) \
                    and self._measured(candidate) == n:
                return candidate
        if self._build_of is not None:
            try:
                candidate = self._build_of(rng, n)
            except Exception:
                candidate = None
            if candidate is not None and self.base.contains(candidate) \
                    and self._measured(candidate) == n:
                return candidate
        return None

    def sample(self, rng: random.Random):
        for _ in range(50):
            value = self.base.sample(rng)
            if self._fits(value):
                return value
        top = self.hi if self.hi is not None else self.lo + 40
        for _ in range(20):
            value = self._member_of(rng, rng.randint(self.lo, max(self.lo, min(top, self.lo + 300))))
            if value is not None and self.contains(value):
                return value
        raise ValueError(f"L[{self.name}]: no member of this {self.key} was found")

    def members(self, limit: int):
        members = self.base.members(limit)
        if members is None:
            return None
        return tuple(m for m in members if self._fits(m))

    def hazards(self) -> tuple:
        """The members at each bound first, then the base's hazards
        that fit."""
        rng = random.Random(0)
        out: list = []
        seen: list = []
        top = self.hi if self.hi is not None else self.lo + 256
        for steps in (range(self.lo, min(self.lo + _NEAREST, top) + 1),
                      range(top, max(top - _NEAREST, self.lo) - 1, -1)):
            for n in steps:
                value = self._member_of(rng, n)
                if value is not None and self.contains(value):
                    if value not in seen:
                        seen.append(value)
                        at = "at the bound" if n in (self.lo, top) else "nearest the bound"
                        out.append(HazardValue(self.hazard_kind, value,
                                               f"a member of {self.key} {n}, {at}"))
                    break
        for h in self.base.hazards():
            try:
                repeated = h.value in seen
            except Exception:
                repeated = False
            if self.contains(h.value) and not repeated:
                out.append(h)
        return tuple(out)

    def outside(self, rng: random.Random):
        past = ([self.hi + i for i in range(1, _NEAREST + 1)] if self.hi is not None else []) \
            + [n for n in range(self.lo - 1, self.lo - 1 - _NEAREST, -1) if n >= 0]
        for n in past:
            value = self._member_of(rng, n)
            if value is not None and not self.contains(value):
                return value
        value = self.base.outside(rng)
        return None if value is None or self.contains(value) else value

    def shrink(self, value) -> Iterable:
        return (s for s in self.base.shrink(value) if self.contains(s))

    def fields(self):
        return self.base.fields()

    def render(self, ascii_mode: bool = True) -> str:
        return f"L[{self.name}]"

    def to_json(self) -> dict:
        out = dict(self.base.to_json())
        out.update(self._schema)
        return out


def register_language(name: str, language: Language) -> None:
    """Intent:
        Make `language` resolvable as `L[<name>]` in this process,
        the in-process half of the seam (the entry-point groups are
        the packaged half). A registration takes precedence over an
        entry point of the same name, and a language failing the
        protocol is refused with the reasons.

    Raises:
        ValueError: `language` does not satisfy `language_problems`.
    """
    problems = language_problems(language)
    if problems:
        raise ValueError(f"L[{name}] cannot be registered: "
                         + "; ".join(problems))
    _REGISTRY[name] = language
    _changed()


def unregister_language(name: str) -> None:
    """Remove an in-process registration; a name never registered is
    left alone."""
    _REGISTRY.pop(name, None)
    _changed()


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
    return tuple(sorted(out, key=lambda item: (-_adaptor_priority(item[1]), item[0])))


def _adaptor_priority(adapt) -> int:
    """Intent:
        An adaptor's `__mathema_adaptor_priority__`, or 0 when it has
        none or it is not an int.
    """
    value = getattr(adapt, "__mathema_adaptor_priority__", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def language_adaptors() -> tuple:
    """The registered `mathema.language_adaptors` adaptors as
    `(name, adapt)` pairs, in the order they are asked: a higher
    `__mathema_adaptor_priority__` first (an int on the adaptor, 0 when
    absent), then by entry-point name. A library-specific adaptor (one
    that recognises a model class of its own library) sets a higher
    priority than a structural one (any dataclass), so a class both
    would accept goes to the specific one. An adaptor that fails to
    load is skipped with a warning."""
    return _loaded_adaptors()


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
    """Every name `L[...]` resolves by name alone: the in-process
    registrations and the entry-point languages, sorted."""
    return tuple(sorted(set(_REGISTRY) | set(_discovered_languages())))


def resolve(ref) -> tuple:
    """Intent:
        `(language, source)` for a `LanguageRef` or a bare name, the
        source being `"registered"`, `"entry point <value>"`,
        `"object"` or `"adaptor <name>"`, in that precedence.

    Raises:
        UnknownLanguage: nothing serves the name.
    """
    if isinstance(ref, LanguageRef) and ref.refinements:
        language, source = resolve(LanguageRef(ref.name))
        for key, interval in ref.refinements:
            refine = _refinement(key)
            if refine is None:
                raise UnknownRefinement(ref, key)
            language = refine(language, interval)
        return language, source
    name = ref.name if isinstance(ref, LanguageRef) else str(ref)
    if name in _REGISTRY:
        return _REGISTRY[name], "registered"
    loaded = _load_language(name)
    if loaded is not None:
        return loaded, f"entry point {_discovered_languages()[name].value}"
    detail = ""
    if "." in name:
        from ._claim_reach import walk_refusal
        refused = walk_refusal(name)
        obj = _import_dotted(name) if refused is None else None
        if refused is not None:
            detail = refused
        elif obj is None:
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


def adapt_annotation(hint) -> "tuple | None":
    """Intent:
        `(language, adaptor_name)` for the first `mathema.language_adaptors`
        adaptor that turns an annotation object (`str`, a schema class,
        an `Annotated[...]`) into a language, or `None` when none does.
        This is how a parameter's own annotation infers a language
        domain: with no adaptor installed, nothing is inferred.
    """
    for adaptor_name, adapt in _loaded_adaptors():
        try:
            adapted = adapt(hint)
        except Exception as e:
            warnings.warn(f"mathema: language adaptor {adaptor_name!r} failed "
                          f"on annotation {hint!r} ({e!r}), skipping it",
                          stacklevel=2)
            continue
        if adapted is not None and not language_problems(adapted):
            return adapted, adaptor_name
    return None


def resolves(name: str) -> bool:
    """Whether `L[<name>]` resolves in this process, by name or by
    dotted path, without raising."""
    try:
        resolve(name)
    except InvalidDomain:
        return False
    return True


def resolve_language(ref: LanguageRef | str) -> Language:
    """The `Language` behind a `LanguageRef` or a bare name; see
    `resolve` for the precedence and the refusal."""
    return resolve(ref)[0]


def describe_language(ref: LanguageRef | str) -> dict:
    """The record's statement of a resolved language: its name, where
    it came from, its level and kind, and its persisted form."""
    language, source = resolve(ref)
    return {"name": ref.text if isinstance(ref, LanguageRef) else str(ref),
            "source": source, "level": language.level,
            "kind": language.kind, "schema": language.to_json()}


def derive_strategy(language) -> "tuple | None":
    """Intent:
        `(derive, refinements)` when the language, beneath any
        refinements wrapped around it, supplies a `derive` method: the
        method, and each refinement key mapped to the closed whole-number
        range `(lo, hi)` it keeps (`hi` None when unbounded, a key
        refined twice keeping the intersection). None when no layer
        supplies one.

    Notes:
        A strategy is called as `derive(param=, lhs=, relation=, rhs=,
        functions=, refinements=)` and returns a `ProofResult` or None.
    """
    refinements: dict = {}
    layer = language
    while isinstance(layer, RefinedLanguage):
        lo, hi = layer.lo, layer.hi
        if layer.key in refinements:
            seen_lo, seen_hi = refinements[layer.key]
            lo = max(lo, seen_lo)
            hi = seen_hi if hi is None else hi if seen_hi is None else min(hi, seen_hi)
        refinements[layer.key] = (lo, hi)
        layer = layer.base
    hook = getattr(layer, "derive", None)
    return (hook, refinements) if callable(hook) else None


__all__ = [
    "ADAPTOR_GROUP", "HAZARD_KINDS", "HazardValue",
    "KINDS", "LANGUAGE_GROUP", "LEVELS", "Language", "Problem",
    "STRING_HAZARDS", "StringLanguage", "UnknownLanguage",
    "REFINEMENT_GROUP", "RefinedLanguage", "UnknownRefinement",
    "adapt_annotation", "describe_language", "language_adaptors", "language_problems",
    "derive_strategy", "refinement_keys", "register_refinement", "unregister_refinement",
    "language_vocabulary", "register_language", "resolve",
    "resolve_language", "resolves", "unregister_language",
]
