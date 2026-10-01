# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema claims KEY --suggest` lists its suggestions in three
sections: claims that stand alone, questions with candidate answers
(monotonicity, shape and symmetry per parameter, any number of which
may hold), and claims likely to be unknowable: a state or
repeatability family the examination of the source cannot read far
enough to decide, with the one-line reason. A family whose write or
hidden read the examination already sees stands alone, with the site
on the line below it: adopting it records the falsification."""
import json
import os
import sys
import textwrap

import pytest

from mathema.cli import main
from mathema.suggest import suggest_claims, suggestion_sections

SOURCE = textwrap.dedent('''
    import os


    def discounted(price: float, rate: float) -> float:
        return price * (1 - rate)


    def remember(rate: float) -> float:
        os.environ["SECTIONS_RATE"] = str(rate)
        return rate


    def looked_up(x: float) -> float:
        return getattr(abs, "__call__")(x)
''')


@pytest.fixture
def pkg(tmp_path):
    (tmp_path / "secpkg").mkdir()
    (tmp_path / "secpkg" / "__init__.py").write_text("")
    (tmp_path / "secpkg" / "mod.py").write_text(SOURCE)
    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    sys.path.remove(str(tmp_path))
    for m in [m for m in sys.modules if m.startswith("secpkg")]:
        del sys.modules[m]


def _listing(root, key, *extra, capsys):
    main(["claims", key, "--suggest", "--root", str(root), *extra])
    return capsys.readouterr().out


def test_the_listing_has_its_three_sections_in_order(pkg, capsys):
    out = _listing(pkg, "secpkg.mod.looked_up", capsys=capsys)
    heads = [" individual claims:",
             " questions with candidate answers (adopt every answer that "
             "holds):",
             " likely to be unknowable (adopted only when named):"]
    at = [out.index(h) for h in heads]
    assert at == sorted(at), out


def test_a_question_lists_its_candidate_answers_under_it(pkg, capsys):
    out = _listing(pkg, "secpkg.mod.discounted", capsys=capsys)
    block = out.split("  shape[price]:\n", 1)[1]
    names = [line.split(":")[0].strip("- ").strip()
             for line in block.splitlines()[:3]]
    assert names == ["affine[price]", "convex[price]", "concave[price]"], out
    assert "[aspect:" not in out


def test_what_examine_cannot_read_is_listed_as_unknowable_with_why(pkg,
                                                                    capsys):
    out = _listing(pkg, "secpkg.mod.looked_up", capsys=capsys)
    tail = out.split(" likely to be unknowable (adopted only when named):\n",
                     1)[1]
    assert "  - is_deterministic: f(x) == f(x)" in tail
    assert "      looked_up calls getattr, which mathema cannot read" in tail


def test_a_write_examine_already_sees_stands_alone_with_its_site(pkg,
                                                                  capsys):
    out = _listing(pkg, "secpkg.mod.remember", capsys=capsys)
    head = out.split(" questions with candidate answers", 1)[0]
    assert ("  - is_state_safe: f(rate) == f(rate)  [route best]\n"
            "      examine finds a write: remember changes os.environ "
            "(os.environ['SECTIONS_RATE'] = ...); adopting records it as "
            "falsified") in head, out
    assert "likely to be unknowable" not in out
    # nothing hidden is read, so determinism stands alone too
    assert "  - is_deterministic:" in head
    assert "SECTIONS_RATE" not in os.environ


def test_the_json_rows_carry_the_section_and_the_reason(pkg, capsys):
    out = _listing(pkg, "secpkg.mod.remember", "--format", "json",
                   capsys=capsys)
    payload = json.loads(out)
    assert payload["cols"][-2:] == ["section", "reason"]
    rows = {row[0]: row for row in payload["rows"]}
    assert rows["is_state_safe"][5:] == [
        "individual", "examine finds a write: remember changes os.environ "
                      "(os.environ['SECTIONS_RATE'] = ...); adopting "
                      "records it as falsified"]
    assert rows["convex[rate]"][5:] == ["question", ""]
    assert rows["is_deterministic"][5:] == ["individual", ""]


def test_the_sections_follow_the_suggestions_one_for_one(pkg):
    import secpkg.mod as mod
    suggestions = suggest_claims(mod.discounted)
    sections = suggestion_sections(mod.discounted, suggestions)
    assert len(sections) == len(suggestions)
    assert {s for s, _ in sections} == {"individual", "question"}
