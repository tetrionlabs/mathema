# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The golden corpus: every `.koi` file with its frozen canonical and
nominal hashes, or the problems it must report. A changed hash is a change to KOINE's
canonical form, never an edited expectation. Each valid document is
the body of a function in `tests/fixtures/koine_py.py`, and says so
in its envelope."""
import hashlib
import pathlib

import pytest

from mathema.koine import Document, KoineSyntaxError, koine_hash, nominal_hash, validate
from tests._koine_docs import GOLDEN, golden, golden_index, golden_text

INDEX = golden_index()
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "koine_py.py"
VALID = sorted(n for n, e in INDEX.items() if "koine_hash" in e)


def test_every_file_is_indexed_and_every_entry_has_a_file():
    files = {p.stem for p in GOLDEN.glob("*.koi")}
    assert files == set(INDEX)
    assert len(VALID) == 9
    assert len([n for n in INDEX if "problems" in INDEX[n]]) == 5


@pytest.mark.parametrize("name", sorted(INDEX))
def test_golden(name):
    entry = INDEX[name]
    text = golden_text(name)
    if "problems" in entry:
        try:
            problems = validate(Document.parse(text))
        except KoineSyntaxError as e:
            problems = [str(e)]
        for needle in entry["problems"]:
            assert any(needle in p for p in problems), (needle, problems)
        return
    doc = Document.parse(text)
    assert validate(doc) == []
    assert koine_hash(doc) == entry["koine_hash"]
    assert nominal_hash(doc) == entry["nominal_hash"]


@pytest.mark.parametrize("name", VALID)
def test_each_document_names_the_function_it_was_written_from(name):
    d = golden(name)
    assert d.language == "py"
    source = d.first("source")
    assert source.get("file").value == "tests/fixtures/koine_py.py"
    assert source.get("sha256").value == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    lines = FIXTURE.read_text().splitlines()
    assert lines[source.get("line").value - 1].startswith(f"def {d.name}(")
    for st in d.body:
        span = st.get("at")
        assert lines[span.args[0].value - 1].strip() == span.args[2].value, (name, span)


def test_different_mathematics_hashes_apart():
    hashes = [INDEX[n]["koine_hash"] for n in VALID]
    assert len(set(hashes)) == len(hashes)
    nominal = [INDEX[n]["nominal_hash"] for n in VALID]
    assert len(set(nominal)) == len(nominal)
    assert not set(hashes) & set(nominal)
