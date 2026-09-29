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
    module = type(value).__module__.split(".")[0]
    if isinstance(value, (list, tuple)):
        return list(value)
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
    """What the function did at one missing input, as a sentence: `at x =
    nan f gave nan back (missing in, missing out)`, `at x = None f raised
    TypeError`, `at x = nan f returned 1.0: the hole became a value`."""
    at = f"at {point_shown(point)}"
    if raised is not None:
        return f"{at} f raised {raised}"
    shown = value_shown(output)
    kind = kind_of(member) if not _in_slot(point.get(param)) else MISSING
    if behaviour == "propagates":
        pair = "missing in, missing out" if kind == MISSING else "absent in, absent out"
        return f"{at} f gave {shown} back ({pair})"
    if behaviour == "drops":
        became = "the hole" if kind == MISSING else "the absence"
        return f"{at} f returned {shown}: {became} became a value"
    if behaviour == "converts":
        became = ("the absence became a hole" if kind == ABSENT
                  else "the hole became an absence")
        return f"{at} f returned {shown}: {became}"
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


def next_step(kind: str, param: str, member: "str | None", behaviour: str,
              raised: "str | None", origin: str, annotation: "str | None") -> str:
    """Intent:
        What to do about one behaviour, or an empty string when it is
        what the type leads a reader to expect. `origin` says who
        admitted the kind: `type` (the annotation alone, or no
        annotation), `optional` (an `Optional` annotation), `listed` (a
        finite set the claim lists), `written` (a `|missing` or
        `|absent` the claim writes).
    """
    stated = claim_word(kind, param, member, behaviour, raised)
    if origin == "type":
        if behaviour == DEFAULTS[kind] or behaviour == "mixed":
            return ""
        if behaviour == "raises":
            return (f", which no claim accounts for: state {stated}, or make f "
                    f"return a value there")
        if behaviour == "drops":
            return f"; write {stated} to accept this, or guard the input"
        return f"; write {stated} to accept this"
    if behaviour != "raises":
        return ""
    if origin == "optional":
        import re
        plain = re.sub(r"^Optional\[(.+)\]$", r"\1", annotation or "")
        plain = " | ".join(t.strip() for t in plain.split("|")
                           if t.strip() not in ("None", "NoneType")) or plain
        return (f". {param} admits absence because it is {annotation}, and no "
                f"claim says what should happen. Handle None in f, or state "
                f"{stated} if raising is intended, or change the annotation to "
                f"{plain}")
    if origin == "listed":
        word = "None" if kind == ABSENT else (member or "the missing value")
        return (f", a point the claim lists; no claim says what f should do with "
                f"{word}. State {stated} if that is intended, or remove {word} "
                f"from the set")
    return (f", a value the claim admits; no claim says what f should do there. "
            f"State {stated} if that is intended, or remove |{kind} from the "
            f"domain")


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
    they held."""

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
            if form != self.form:
                continue
            shape = (rows, cols if form != "vec" else 1)
            if self.smallest is None or shape < self.smallest:
                self.smallest = shape
            if self.largest is None or shape > self.largest:
                self.largest = shape
            self.entries += shape[0] * shape[1]
            return

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
    """A row's count: `43 draws`; for a container the sizes drawn, rows
    then columns, and the entries over every draw: `57 draws, sizes
    (1, 1) to (8, 1), 224 entries in all`."""
    draws = f"{n} draw{'s' if n != 1 else ''}"
    if not drawn or not drawn.get("smallest"):
        return draws
    lo, hi = tuple(drawn["smallest"]), tuple(drawn["largest"])
    sizes = f"size {lo}" if lo == hi else f"sizes {lo} to {hi}"
    return f"{draws}, {sizes}, {drawn['entries']} entries in all"


def mixed_sentence(param: str, ways_by_member: dict, raised_by_member: dict,
                   container_noun: "str | None") -> str:
    """Intent:
        One sentence for a parameter the function treats more than one
        way, organised by behaviour: `f drops a missing slot when values
        remain (xs = [nan, 0.0649, 1e-06]) and gives a hole back when
        every slot is missing (xs = [nan], [null]); at an all-NA series
        it raises TypeError instead`. `ways_by_member` is `{member:
        {behaviour: witness}}`, the witness a point as the record shows
        it (`xs = [nan]`).
    """
    drops, holes, raises, other = [], [], [], []
    for member, ways in ways_by_member.items():
        for behaviour, at in ways.items():
            shown = at.split(" = ", 1)[1] if " = " in at else at
            if behaviour == "drops":
                drops.append(shown)
            elif behaviour == "propagates":
                holes.append(shown)
            elif behaviour == "raises":
                raises.append((member, shown))
            else:
                other.append(f"{behaviour} at {param} = {shown}")
    clauses = []
    if drops:
        clauses.append(f"drops a missing slot when values remain ({param} = {drops[0]})"
                       if container_noun else f"returns a value at {param} = {drops[0]}")
    if holes:
        seen = ", ".join(dict.fromkeys(holes))
        clauses.append(f"gives a hole back when every slot is missing ({param} = {seen})"
                       if container_noun else f"gives a hole back at {param} = {seen}")
    text = "f " + " and ".join(clauses) if clauses else ""
    for member, shown in raises:
        exc = raised_by_member.get(member) or "an exception"
        where = (f"an all-{member} {container_noun}" if container_noun
                 and _all_member(shown, member) else f"{param} = {shown}")
        tail = f"at {where} it raises {exc} instead"
        text = f"{text}; {tail}" if text else f"f {tail[3:]}"
    for extra in other:
        text = f"{text}; {extra}" if text else f"f {extra}"
    return text


def _all_member(shown: str, member: str) -> bool:
    inner = shown.strip("[]")
    cells = [c.strip() for c in inner.split(",") if c.strip()]
    return bool(cells) and all(c == member for c in cells)
