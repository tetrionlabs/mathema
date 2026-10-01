# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""How the record says what a function did with a value that is not
there, in one voice everywhere: the kind words (`absent` for the object
not being there, `missing` for a hole in a slot), the member words
(`None`, `nan`, `null`, `NA`, `NaT`), values shown short, and the
sentences that name what happened at each missing input and what to do
next when that is not what the parameter's type leads a reader to expect.

The default behaviour a type implies: a hole the type admits propagates
(a float's `nan` comes back as `nan`), and an absence the type admits
raises (an unannotated parameter called with `None`). A kind the author
admitted (an `Optional` annotation, a listed `None`, a written `|missing`
or `|absent`) has no default: what the function does there is observed,
and a raise there is unaccounted for until a claim states it.
"""
from __future__ import annotations

import math

ABSENT, MISSING = "absent", "missing"

#: the behaviour a type implies for a kind it admits
DEFAULTS = {MISSING: "propagates", ABSENT: "raises"}


def kind_of(member: str) -> str:
    """`absent` for an absence spelling (`None`, `Option::None`), else
    `missing`."""
    from .domain import _ABSENCE_VALUES
    return ABSENT if member in _ABSENCE_VALUES else MISSING


def value_shown(value, in_slot: bool = False) -> str:
    """A value as the record shows it: a missing value by its member
    word (`nan`, `NA`, `NaT`; `None` as an argument and `null` in a
    slot), a float to three significant digits, a container by its
    elements, anything else by its repr cut short."""
    from .domain import member_of
    if value is None:
        return "null" if in_slot else "None"
    if isinstance(value, bool):
        return repr(value)
    if isinstance(value, float):
        if value != value:
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        short = repr(value)
        return short if len(short) <= 6 else f"{value:.3g}"
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, str):
        return f'"{value}"'
    word = None
    try:
        word = member_of(value)
    except Exception:
        word = None
    if word not in (None, "null"):
        return word
    cells = _elements(value)
    if cells is not None:
        shown = [value_shown(v, in_slot=True) for v in cells[:6]]
        if len(cells) > 6:
            shown.append("...")
        return "[" + ", ".join(shown) + "]"
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _elements(value) -> "list | None":
    """The elements of a vector, or the rows of a matrix, as a list."""
    from ._missing_policy import _array_list, _is_ndarray
    module = type(value).__module__.split(".")[0]
    if isinstance(value, (list, tuple)):
        return list(value)
    if _is_ndarray(value):
        return _array_list(value)
    if module in ("numpy", "pandas") and hasattr(value, "tolist"):
        out = value.tolist()
        return out if isinstance(out, list) else None
    if module == "polars" and hasattr(value, "to_list"):
        return value.to_list()
    if isinstance(value, dict):
        return None
    return None


def point_shown(point: dict) -> str:
    """`x = nan`, `xs = [null, 0.609]`, several joined by commas."""
    return ", ".join(f"{p} = {_param_value(v)}" for p, v in point.items())


def _param_value(v) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {value_shown(c, in_slot=True) if not isinstance(c, (list, tuple)) else value_shown(list(c))}"
                               for k, c in v.items()) + "}"
    return value_shown(v)


def outcome_entry(member: str, output=None, raised: "str | None" = None,
                  behaviour: "str | None" = None, respelled: "str | None" = None,
                  in_slot: bool = False) -> str:
    """One entry of `meta["mathema.missing"]["executed"]`: `raised
    TypeError`, `nan in, nan out (propagates)`, `null slot in, nan out
    (propagates, member changed)`, `nan in, 1.0 out (drops)`."""
    if raised is not None:
        return f"raised {raised}"
    what = f"{member} slot in" if in_slot else f"{member} in"
    out = value_shown(output)
    tag = behaviour or ""
    if respelled:
        out = respelled.rsplit(" returned as ", 1)[-1]
        tag = (f"{tag}, member changed: {respelled}" if tag
               else f"member changed: {respelled}")
    return f"{what}, {out} out ({tag})" if tag else f"{what}, {out} out"


def said(param: str, member: str, point: dict, output=None,
         raised: "str | None" = None, behaviour: "str | None" = None) -> str:
    """What the function did at one missing input, as a fact: `at x =
    nan f gave nan back`, `at x = None f raised TypeError`, `at x = nan
    f returned 1.0, so it drops the hole`, `at xs = [null] f returned 0,
    so it drops the null slot`."""
    at = f"at {point_shown(point)}"
    if raised is not None:
        return f"{at} f raised {raised}"
    shown = value_shown(output)
    slot = _in_slot(point.get(param))
    kind = MISSING if slot else kind_of(member)
    what = (f"the {member} slot" if slot else
            "the hole" if kind == MISSING else "the absence")
    if behaviour == "propagates":
        return f"{at} f gave {shown} back"
    if behaviour == "drops":
        return f"{at} f returned {shown}, so it drops {what}"
    if behaviour == "converts":
        to = "a hole" if kind == ABSENT else "an absent result"
        return f"{at} f returned {shown}, so it converts {what} to {to}"
    if behaviour == "introduces":
        return f"{at} f returned {shown}, with a missing value where it was given none"
    return f"{at} f returned {shown}"


def _unset_reason(value, root: str, where: tuple) -> str:
    """Why a path reached no position: `a key left out`, `an attribute
    not there`, `an index past the end`, or `below an absent o.address`
    when a step on the way held None."""
    from .domain import path_text
    current = value
    for step in where:
        if current is None:
            break
        if isinstance(step, int):
            try:
                current = current[step]
            except (IndexError, KeyError, TypeError):
                return "an index past the end"
        elif isinstance(current, dict):
            if step not in current:
                return "a key left out"
            current = current[step]
        elif hasattr(current, step):
            current = getattr(current, step)
        else:
            return "an attribute not there"
    return f"below an absent {path_text(root, where)}"


def _path_case(path: str, member: str, point: dict, kind: "str | None" = None):
    """`(root, where)` of the first case of `member` the path reaches in
    `point`, or None."""
    from ._missing_policy import path_members, path_root
    root = path_root(path)
    for k, m, where in path_members(point.get(root), root, path):
        if m == member and (kind is None or k == kind):
            return root, where
    return None


def path_shown(path: str, member: str, point: dict, kind: "str | None" = None) -> str:
    """What a path reached, as a witness names it: `d.note unset`,
    `d.note = null (absent)`, `o.lines[1] = null (hole)`,
    `o.lines[0].qty = nan`."""
    from .domain import path_text
    found = _path_case(path, member, point, kind)
    if member == "unset":
        return f"{path} unset"
    if found is None:
        return f"{path} = {member}"
    root, where = found
    at = path_text(root, where)
    if member == "null":
        absent = kind == ABSENT if kind else len(where) and not isinstance(where[-1], int)
        return f"{at} = null ({'absent' if absent else 'hole'})"
    return f"{at} = {member}"


def path_place(path: str, member: str, point: dict, kind: "str | None" = None) -> str:
    """Where a path reached no value, in words: `d.note, a key left
    out`, `o.address.zip, below an absent o.address`, `d.note = null
    (absent)`."""
    if member != "unset":
        return path_shown(path, member, point, kind)
    found = _path_case(path, member, point, kind)
    reason = (_unset_reason(point.get(found[0]), found[0], found[1])
              if found is not None else "not there")
    return f"{path}, {reason}"


def path_said(path: str, member: str, point: dict, output=None,
              raised: "str | None" = None, behaviour: "str | None" = None,
              kind: "str | None" = None) -> str:
    """What the function did where a path reached no value, as a fact:
    `at d.note, a key left out, f raised KeyError`, `at d.note = null
    (absent) f returned "-", so it drops the absence`."""
    at = f"at {path_place(path, member, point, kind)}"
    if member == "unset":
        at += ","
    if raised is not None:
        return f"{at} f raised {raised}"
    shown = value_shown(output)
    hole = (kind or (MISSING if member not in ("null", "unset") else ABSENT)) == MISSING
    what = "the hole" if hole else "the absence"
    if behaviour == "propagates":
        return f"{at} f gave {shown} back"
    if behaviour == "drops":
        return f"{at} f returned {shown}, so it drops {what}"
    if behaviour == "converts":
        to = "an absent result" if hole else "a hole"
        return f"{at} f returned {shown}, so it converts {what} to {to}"
    if behaviour == "introduces":
        return f"{at} f returned {shown}, with a missing value where it was given none"
    return f"{at} f returned {shown}"


def _in_slot(value) -> bool:
    return value is not None and _elements(value) is not None


def claim_word(kind: str, param: str, member: "str | None", behaviour: str,
               raised: "str | None" = None) -> str:
    """The policy claim that states a behaviour: `missing(f, x)
    propagates`, `absent(f, x) raises(TypeError)`, `missing(f, xs,
    null) raises(TypeError)`."""
    target = param + (f", {member}" if member else "")
    verb = f"raises({raised})" if behaviour == "raises" and raised else behaviour
    return f"`{kind}(f, {target}) {verb}`"


def unknown_reason(first: dict, relation: str, listed: set) -> str:
    """Intent:
        Why a value claim with no point left to compare is unknown, and
        what to write instead. `first` is `{(param, member): (value,
        output, raised, behaviour)}` for the missing inputs executed;
        `listed` the parameters whose finite set the claim wrote.
    """
    items = list(first.items())
    parts = []
    for (p, member), (value, output, raised, _b) in items:
        did = f"raises {raised}" if raised else f"gives {value_shown(output)} back"
        parts.append(f"{p} = {value_shown(value)}, {did}")
    lead = (f"the only listed point, {parts[0]}" if len(parts) == 1
            else "every point executed has no value to give back ("
            + "; ".join(parts) + ")")
    text = f"{lead}, so there is no value to compare with {relation}."
    (p, member), (value, output, raised, behaviour) = items[0]
    kind = MISSING if _in_slot(value) else kind_of(member)
    if raised:
        stated = claim_word(kind, p, None, "raises", raised)
        word = "None" if kind == ABSENT else value_shown(value)
        where = (f"remove {word} from the set" if p in listed
                 else f"write \\ {{{kind}}} in the domain")
        return f"{text} State {stated} if that is intended, or {where}."
    stated = claim_word(kind, p, None, behaviour or "propagates")
    return (f"{text} To state what f does there, write "
            f"`for {p} in {{{value_shown(value)}}}, f({p}) in {{{kind}}}` or {stated}.")


def declared_optional_return(fn) -> "str | None":
    """The return annotation's text when it declares that the output may
    be absent (`Optional[float]`, `float | None`), else None."""
    import inspect
    import typing
    try:
        ann = inspect.signature(fn).return_annotation
    except (TypeError, ValueError):
        return None
    if ann is inspect.Signature.empty:
        return None
    if isinstance(ann, str):
        text = ann.strip().strip("'\"")
        low = text.replace(" ", "").lower()
        if low.startswith(("optional[", "typing.optional[")) or "|none" in low \
                or low.startswith("none|"):
            return text.replace("typing.", "")
        return None
    args = typing.get_args(ann)
    if type(None) in args:
        return repr(ann).replace("typing.", "").replace("NoneType", "None")
    return None


class DrawTally:
    """The shapes of the containers a row executed, for its count: the
    smallest and largest shape drawn, rows then columns, and the entries
    every container parameter held."""

    def __init__(self) -> None:
        self.draws = 0
        self.form: "str | None" = None
        self.smallest: "tuple | None" = None
        self.largest: "tuple | None" = None
        self.entries = 0

    def add(self, point: dict) -> None:
        self.draws += 1
        for value in point.values():
            form, rows, cols = _shape(value)
            if form is None:
                continue
            if self.form is None:
                self.form = form
            shape = (rows, cols if form != "vec" else 1)
            if self.smallest is None or shape < self.smallest:
                self.smallest = shape
            if self.largest is None or shape > self.largest:
                self.largest = shape
            self.entries += shape[0] * shape[1]

    def meta(self) -> dict:
        if self.form is None:
            return {}
        return {"form": self.form, "smallest": list(self.smallest or ()),
                "largest": list(self.largest or ()), "entries": self.entries}


def _shape(value) -> tuple:
    """`(form, rows, columns)` of a vector, matrix or table, else
    `(None, 0, 0)`."""
    if isinstance(value, dict):
        cols = [c for c in value.values() if isinstance(c, (list, tuple))]
        if cols:
            return "table", max(len(c) for c in cols), len(cols)
        return None, 0, 0
    shape = getattr(value, "shape", None)
    if shape is not None and len(shape) in (1, 2):
        return ("vec", shape[0], 1) if len(shape) == 1 else ("mat", shape[0], shape[1])
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(r, (list, tuple)) for r in value):
            return "mat", len(value), max(len(r) for r in value)
        return "vec", len(value), 1
    return None, 0, 0


def count_words(n: int, drawn: "dict | None") -> str:
    """A row's count: `43 draws`; for a container the entries over every
    draw first, then the draws, then the sizes drawn, rows then columns:
    `257 entries across 57 draws, sizes (1, 1) to (8, 1)`."""
    draws = f"{n} draw{'s' if n != 1 else ''}"
    if not drawn or not drawn.get("smallest"):
        return draws
    lo, hi = tuple(drawn["smallest"]), tuple(drawn["largest"])
    sizes = f"size {lo}" if lo == hi else f"sizes {lo} to {hi}"
    entries = drawn["entries"]
    return f"{entries} entr{'y' if entries == 1 else 'ies'} across {draws}, {sizes}"


def mixed_sentence(param: str, ways_by_member: dict, raised_by_member: dict,
                   container_noun: "str | None") -> str:
    """Intent:
        One sentence for a parameter the function treats more than one
        way, organised by behaviour: `f drops a missing slot when values
        remain (xs = [nan, 0.0649, 1e-06]) and gives a hole back when
        every slot is missing (xs = [nan], [null]); at an all-NA series
        it raises TypeError instead`. `ways_by_member` is `{member:
        {behaviour: witness}}`, the witness a point as the record shows
        it (`xs = [nan]`, `x = [null], alpha = 0.5`).
    """
    drops, holes, raises, other = [], [], [], []
    for member, ways in ways_by_member.items():
        for behaviour, at in ways.items():
            if behaviour == "drops":
                drops.append(at)
            elif behaviour == "propagates":
                holes.append(at)
            elif behaviour == "raises":
                raises.append((member, at))
            else:
                other.append((member, behaviour, at))

    def where(points: list) -> str:
        # one parameter's values alone read `xs = [nan], [null]`
        points = list(dict.fromkeys(points))
        lone = all(pt.startswith(f"{param} = ") and pt.count(" = ") == 1
                   for pt in points)
        if lone:
            return f"{param} = " + ", ".join(pt.split(" = ", 1)[1] for pt in points)
        return "; ".join(points)

    # a phrase about every slot or about values remaining is said only
    # where the witnesses show it
    remain = container_noun and drops and not any(_all_holes(pt, param) for pt in drops)

    def all_hole_seen(member: str) -> bool:
        # another behaviour was seen where every slot held this member
        return any(pt.count(" = ") == 1 and _all_member(pt.split(" = ", 1)[-1], member)
                   for pt in drops + holes)
    clauses = []
    if drops:
        clauses.append(f"drops a missing slot when values remain ({where(drops[:1])})"
                       if remain else f"drops the hole at {where(drops[:1])}")
    if holes:
        every = container_noun and all(_all_holes(pt, param) for pt in holes)
        clauses.append(f"gives a hole back when every slot is missing ({where(holes)})"
                       if every else f"gives a hole back at {where(holes)}")
    text = "f " + " and ".join(clauses) if clauses else ""
    # members that each raise the same exception when every slot holds
    # them are said once
    whole = [(m, at) for m, at in raises if container_noun and not all_hole_seen(m)
             and _all_member(at.split(" = ", 1)[-1], m) and at.count(" = ") == 1]
    excs = {raised_by_member.get(m) for m, _at in whole}
    if len(whole) > 1 and len(excs) == 1:
        exc = next(iter(excs)) or "an exception"
        members = ", ".join(m for m, _at in whole)
        tail = (f"when every slot is missing ({members}) it raises {exc} instead")
        text = f"{text}; {tail}" if text else f"f raises {exc} {tail.split(' it raises')[0]}"
        raises = [r for r in raises if r not in whole]
    for member, at in raises:
        exc = raised_by_member.get(member) or "an exception"
        spot = (f"an all-{member} {container_noun}" if container_noun
                and not all_hole_seen(member)
                and _all_member(at.split(" = ", 1)[-1], member)
                and at.count(" = ") == 1 else where([at]))
        text = (f"{text}; at {spot} it raises {exc} instead" if text
                else f"at {spot} f raised {exc}")
    for member, behaviour, at in other:
        what = f"the {member} slot" if container_noun else "the hole"
        verb = ("converts " + what + " to an absent result" if behaviour == "converts"
                else "returns a value no fill of " + what + " changes"
                if behaviour == "indifferent" else "introduces a missing value")
        text = (f"{text}; at {where([at])} it {verb}" if text
                else f"at {where([at])} f {verb}")
    return text


def _all_holes(point: str, param: str) -> bool:
    """Whether a witness's container for `param` holds no value at all."""
    if not point.startswith(f"{param} = ") or point.count(" = ") != 1:
        return False
    inner = point.split(" = ", 1)[1].strip("[]")
    cells = [c.strip() for c in inner.split(",") if c.strip() and c.strip() != "..."]
    return bool(cells) and all(c in ("nan", "null", "NA", "NaT", "None") for c in cells)


def _all_member(shown: str, member: str) -> bool:
    inner = shown.strip("[]")
    cells = [c.strip() for c in inner.split(",") if c.strip()]
    return bool(cells) and all(c == member for c in cells)
