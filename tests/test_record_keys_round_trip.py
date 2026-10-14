# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record's mapping keys read back as the keys that were written.

A key YAML would read as another type (`null`, `true`, `~`, `1`) is
quoted when written, a record already on disk with such a key bare
reads its `null` and boolean keys back as their words, and the badges
cache digests a record whatever types its keys hold.
"""
import os

import pytest
import yaml

from mathema.spec import dump_yaml, load_verified

KEYS = ["null", "Null", "NULL", "~", "true", "false", "yes", "no", "on",
        "off", "1", "1.5", "-3", "0x10", ".nan", ".inf", "nan", "a: b",
        "- x", "#c", "", "plain", "with space", "key_1"]


@pytest.mark.parametrize("key", KEYS)
def test_a_written_key_reads_back_as_itself(key):
    back = yaml.safe_load(dump_yaml({"m": {key: 1, "other": 2}}))
    assert back == {"m": {key: 1, "other": 2}}


def test_keys_that_would_collide_stay_apart():
    written = {"executed": {"null": 1, "nan": 2, "true": 3, "1": 4}}
    assert yaml.safe_load(dump_yaml(written)) == written


def test_an_ordinary_key_is_written_bare():
    assert dump_yaml({"identity": {"form": "abc"}}) == \
        'identity:\n  form: "abc"\n'


def test_a_record_written_with_a_bare_null_key_reads_its_word(tmp_path):
    store = tmp_path / ".mathema" / "verified"
    store.mkdir(parents=True)
    (store / "pkg.mod.f.yaml").write_text(
        "pkg.mod.f:\n"
        "  meta:\n"
        "    mathema.missing:\n"
        "      x:\n"
        "        executed:\n"
        "          null: 1\n"
        "          nan: 2\n")
    record = load_verified(str(tmp_path))["pkg.mod.f"]["entry"]
    held = record["meta"]["mathema.missing"]["x"]["executed"]
    assert held == {"null": 1, "nan": 2}


def test_the_badges_digest_takes_keys_of_mixed_types():
    import hashlib

    from mathema._badges_cache import _put
    h = hashlib.sha256()
    _put(h, {"a": {None: 1, "nan": 2, 3: 4, True: 5}})
    assert len(h.hexdigest()) == 64


def test_the_badges_digest_of_a_mapping_is_its_key_order_free():
    import hashlib

    from mathema._badges_cache import _put
    one, two = hashlib.sha256(), hashlib.sha256()
    _put(one, {"b": 1, 2: "x", None: 0})
    _put(two, {None: 0, 2: "x", "b": 1})
    assert one.hexdigest() == two.hexdigest()


def test_no_record_under_this_repository_holds_a_non_string_key():
    def keys_ok(node):
        if isinstance(node, dict):
            return all(isinstance(k, (str, int)) and not isinstance(k, bool)
                       and keys_ok(v) for k, v in node.items())
        if isinstance(node, list):
            return all(keys_ok(v) for v in node)
        return True
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert keys_ok(load_verified(root))
