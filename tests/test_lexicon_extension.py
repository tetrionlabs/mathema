# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A package extends the lexicon through the `mathema.lexicon`
entry-point group: its rows join `entries()`, `search()`, `find()`,
`get()` and `show()`, its sections read `<name>/<section>`, `origin`
says where each row came from, and mathema's own `LEXICON` (and so its
golden snapshot) stays mathema's alone. A row reusing a core key, or a
lexicon that fails to load, is skipped with a warning."""
from types import SimpleNamespace

import pytest

import mathema.lexicon as lexicon
from mathema import lexicon_checks
from mathema.interfaces import extension


def shout(s):
    """Upper case."""
    return s.upper()


DEMO = SimpleNamespace(
    LEXICON={"demo_idempotent": 'for s in {"a", "B"}, f(f(s)) == f(s)',
             "relation_eq": "f(x) == x"},
    SECTIONS={"normalisers": ("demo_idempotent", "relation_eq")},
    TAGS={"demo_idempotent": ("shouting twice",)},
    EXAMPLE_FUNCTIONS={"shout": (shout, ["demo_idempotent"])},
)


class _Entry:
    def __init__(self, name, obj):
        self.name, self.value, self._obj = name, f"pkg:{name}", obj

    def load(self):
        if isinstance(self._obj, Exception):
            raise self._obj
        return self._obj


@pytest.fixture
def registered(monkeypatch):
    def install(*entries):
        monkeypatch.setattr(lexicon, "_entry_points", lambda: tuple(entries))
        lexicon._extensions.cache_clear()
    yield install
    lexicon._extensions.cache_clear()


def test_the_rows_join_every_way_in(registered, capsys):
    with pytest.warns(UserWarning, match="reuses the keys relation_eq"):
        registered(_Entry("demo", DEMO))
        assert "demo_idempotent" in lexicon.entries()
    assert "demo_idempotent" not in lexicon.entries(extensions=False)
    assert "demo_idempotent" not in lexicon.LEXICON
    assert lexicon.entries("demo/normalisers") == {"demo_idempotent": DEMO.LEXICON["demo_idempotent"]}
    assert lexicon.get("demo_idempotent") == DEMO.LEXICON["demo_idempotent"]
    assert lexicon.origin("demo_idempotent") == "demo"
    assert lexicon.origin("relation_eq") == "mathema"
    assert lexicon.get("relation_eq") == lexicon.LEXICON["relation_eq"]
    assert "demo_idempotent" in [k for k, _ in lexicon.search("shouting twice")]
    lexicon.find("shouting twice")
    assert "[demo]" in capsys.readouterr().out
    lexicon.show("demo_idempotent")
    assert "input:" in capsys.readouterr().out


def test_a_lexicon_that_fails_to_load_is_skipped(registered):
    with pytest.warns(UserWarning, match="failed to load"):
        registered(_Entry("broken", ImportError("no module")))
        assert lexicon.entries() == lexicon.entries(extensions=False)


def test_a_package_lexicon_is_held_to_the_same_checks(registered):
    with pytest.warns(UserWarning):
        registered(_Entry("demo", DEMO))
        (_core, demo) = lexicon.sources()
    assert lexicon_checks.lexicon_problems(demo, expected={"demo_idempotent": "proven"}) == {}
    assert lexicon_checks.check_verdicts(demo, {"demo_idempotent": "falsified"})


def test_the_seam_is_on_the_extension_surface():
    assert extension.SURFACE["lexicon"] == (
        "LEXICON_GROUP", "LexiconSource", "lexicon_source", "lexicon_problems",
        "write_lexicon_golden")
    assert extension.LEXICON_GROUP == "mathema.lexicon"
