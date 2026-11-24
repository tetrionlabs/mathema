"""The cut of an `assuming` conjunct at the arrow that begins a region
agrees with the regular expression it replaced, and reads a very long
run of whitespace."""
import random
import re

import pytest

from mathema.spec import _before_region_arrow

_PIECES = ["-->", "=>", "⟹", "-", ">", "=", "--", "==", " ", "  ", "\t", "\n", "\r\n",
           "a", "b", "x1", "(", ")", "'", "⟹ ", " --> "]


def _original(part: str) -> str:
    return re.sub(r"\s*(?:-->|=>|⟹).*$", "", part, flags=re.DOTALL).strip()


def _generated(count: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    return ["".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 12)))
            for _ in range(count)]


def test_it_agrees_with_the_original_expression_on_generated_texts():
    texts = _generated(20_000, seed=20261124)
    assert len(texts) >= 20_000
    assert [t for t in texts if _before_region_arrow(t) != _original(t)] == []


@pytest.mark.parametrize("text, expected", [
    ("", ""),
    ("   ", ""),
    ("a", "a"),
    ("  a  ", "a"),
    ("a --> b", "a"),
    ("a=>b", "a"),
    ("a ⟹ b", "a"),
    ("a --> b => c ⟹ d", "a"),
    ("a ⟹ b --> c", "a"),
    ("a =>\n\nb\nc", "a"),
    ("a \t\n --> b", "a"),
    ("--> b", ""),
    ("   => b", ""),
    ("a -- > b", "a -- > b"),
    ("a = > b", "a = > b"),
    ("a\n--> b", "a"),
])
def test_listed_cases(text, expected):
    assert _before_region_arrow(text) == expected
    assert _original(text) == expected


def test_a_very_long_run_of_spaces_is_handled():
    assert _before_region_arrow("a" + " " * 200_000 + "b") == "a" + " " * 200_000 + "b"
    assert _before_region_arrow(" " * 200_000) == ""
    assert _before_region_arrow("a" + " " * 200_000 + "--> b") == "a"
