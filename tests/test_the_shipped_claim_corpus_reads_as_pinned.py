# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every claim text the repository ships reads today as it was pinned.

`tests/data/claim_corpus.json` holds the claim texts found in the test
literals, documentation, examples, claims files and package docstrings
(`scripts/harvest_claim_corpus.py` collects them). For each text it
records whether the text parses, the refusal when it does not, the
ascii and unicode rendering, the identity text, the claims fingerprint
and the rendering of each domain binding. This module covers:

- every pinned value equals what the code computes now;
- the rendering is stable: rendering a parsed rendering gives the same
  rendering, in ascii and in unicode, except for the few texts listed in
  `UNSTABLE`, which do not render as themselves today and are pinned as
  they are;
- the corpus is large enough and spans the spellings it must span.

A reading that changes on purpose is changed in the data file by
re-running the harvester, in the same change that alters the reading.
"""
import importlib.util
import json
import pathlib

import pytest

from mathema.conjecture import claim
from mathema.spec import render_claim_text

DATA = pathlib.Path(__file__).resolve().parent / "data" / "claim_corpus.json"
CORPUS = json.loads(DATA.read_text(encoding="utf-8"))
HARVEST = DATA.parents[2] / "scripts" / "harvest_claim_corpus.py"
_AND_OF_RELATIONS = ("for x in [0,10], lo in [0,3], hi in [7,10], "
                     "f(x, lo, hi) == (not (lo < x and x < hi))")
_HUGE_LITERAL = "for x in [1, 2], f(x) <= x * 1e308 * 10"
_AUTO_LET = ("let compute_square_root = numpy.sqrt, for acceleration in [0, 10], "
             "deceleration in [0, 10], "
             "compute_square_root(acceleration) + deceleration >= 0")
#: texts whose rendering reads back as a different rendering
UNSTABLE = {False: {_HUGE_LITERAL},
            True: {_HUGE_LITERAL, _AUTO_LET}}
PARSING = sorted(t for t, v in CORPUS.items() if v["parses"])


def test_the_corpus_is_large_and_every_source_kind_is_in_it():
    kinds = {s.split(":", 1)[0] for v in CORPUS.values() for s in v["sources"]}
    assert len(CORPUS) >= 3000
    assert len(PARSING) >= 3000
    assert {"tests", "docs", "claims-file", "package", "extra"} <= kinds


def test_every_text_reads_as_pinned():
    spec = importlib.util.spec_from_file_location("harvest_claim_corpus", HARVEST)
    harvest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harvest)
    read_claim = harvest.read_claim
    changed = []
    for text, pinned in CORPUS.items():
        now = read_claim(text)
        expected = {k: v for k, v in pinned.items() if k != "sources"}
        if now != expected:
            diff = sorted(k for k in set(now) | set(expected)
                          if now.get(k) != expected.get(k))
            changed.append((text, diff))
    assert not changed, f"{len(changed)} texts read differently: {changed[:5]}"


@pytest.mark.parametrize("unicode", [False, True], ids=["ascii", "unicode"])
def test_a_rendering_renders_as_itself(unicode):
    unstable = []
    for text in PARSING:
        once = render_claim_text(claim(text), unicode=unicode)
        try:
            twice = render_claim_text(claim(once), unicode=unicode)
        except Exception as exc:  # noqa: BLE001 - recorded as a finding
            twice = f"{type(exc).__name__}: {str(exc)[:80]}"
        if twice != once:
            unstable.append((text, once, twice))
    assert {text for text, _, _ in unstable} == UNSTABLE[unicode]
