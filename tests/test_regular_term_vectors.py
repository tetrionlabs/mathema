# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The canonical form and the hash of a regular-language definition are
the ones the shared test vectors state: each valid document with its
canonical text and its hash as literals, and each document outside the
schema refused. The vector file is the copy of the one the package that
compiles terms holds, so two implementations of the specification are
held to the same answers."""
import json
import pathlib

import pytest

from mathema import regular

VECTORS = json.loads((pathlib.Path(__file__).resolve().parent / "data"
                      / "regular_term_vectors.json").read_text(encoding="utf-8"))["vectors"]
VALID = [v for v in VECTORS if not v.get("invalid")]
INVALID = [v for v in VECTORS if v.get("invalid")]


def test_the_vector_file_holds_what_it_is_expected_to():
    assert (len(VALID), len(INVALID)) == (57, 11)


@pytest.mark.parametrize("vector", VALID, ids=[v["name"] for v in VALID])
def test_a_valid_document_has_the_stated_canonical_text_and_hash(vector):
    assert regular.canonical_text(vector["document"]) == vector["canonical"]
    assert regular.term_hash(vector["document"]) == vector["hash"]


@pytest.mark.parametrize("vector", INVALID, ids=[v["name"] for v in INVALID])
def test_a_document_outside_the_schema_is_refused(vector):
    with pytest.raises(ValueError):
        regular.term_hash(vector["document"])
    with pytest.raises(ValueError):
        regular.canonical_text(vector["document"])
