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


# --- every key the writer emits reads back, or the writer refuses it ---

INDICATORS = list(">|&*!%@`,[]{}#?-:'\"") + [" "]

INDICATOR_KEYS = sorted({k for c in INDICATORS
                         for k in (c, c + " 256 ulp", c + c, "a " + c,
                                   "a" + c + "b", "a " + c + " b")})

# line breaks, control characters and characters YAML does not carry
# literally: each needs an escape inside a quoted scalar
ESCAPED_KEYS = ["\n", "a\nb", "\r", "a\r\nb", "\t", "a\tb", "\x00", "\x07",
                "\x1b", "\x7f", "\x85", "a\x85b", "\x9f", " ", " ",
                "﻿", "￾", "￿", "\xa0", "\xa0x", "x\xa0",
                "\\", "a\\nb", "é", "\U0001F600"]


def _loaders():
    out = [yaml.SafeLoader]
    if hasattr(yaml, "CSafeLoader"):
        out.append(yaml.CSafeLoader)
    return out


def _shapes(key):
    """The places a key can sit in a record: a nested mapping, the
    first and a later key of a mapping inside a list, and a top-level
    key whose value is a mapping."""
    return [{"m": {key: 1, "other": 2}},
            {"m": [{key: 1, "z": 2}]},
            {"m": [{"z": 1, key: 2}]},
            {key: {"a": 1}}]


@pytest.mark.parametrize("key", INDICATOR_KEYS + ESCAPED_KEYS)
def test_a_key_reads_back_wherever_it_sits(key):
    for data in _shapes(key):
        text = dump_yaml(data)
        for loader in _loaders():
            assert yaml.load(text, Loader=loader) == data, (loader, text)


@pytest.mark.parametrize("value", ESCAPED_KEYS + INDICATOR_KEYS)
def test_a_string_value_reads_back_as_itself(value):
    data = {"m": {"v": value}, "l": [value]}
    text = dump_yaml(data)
    for loader in _loaders():
        assert yaml.load(text, Loader=loader) == data, (loader, text)


def _entry(meta):
    return {"identity": {"form": "abc"}, "meta": meta, "claims": []}


def test_no_record_the_writer_emits_is_dropped_by_the_reader(tmp_path):
    from mathema.spec import save_verified_entry, unreadable_verified
    keys = INDICATOR_KEYS + ESCAPED_KEYS
    for i, key in enumerate(keys):
        save_verified_entry(f"pkg.mod.f{i}", _entry({"bands": {key: i},
                                                     "rows": [{key: i}],
                                                     "said": key}),
                            str(tmp_path))
    store = load_verified(str(tmp_path))
    assert unreadable_verified(str(tmp_path)) == {}
    for i, key in enumerate(keys):
        meta = store[f"pkg.mod.f{i}"]["entry"]["meta"]
        assert meta == {"bands": {key: i}, "rows": [{key: i}], "said": key}, key


def test_the_extension_band_key_survives_the_store(tmp_path):
    from mathema.spec import save_verified_entry
    save_verified_entry("pkg.mod.f", _entry({"ext.bands": {"> 256 ulp": 3}}),
                        str(tmp_path))
    meta = load_verified(str(tmp_path))["pkg.mod.f"]["entry"]["meta"]
    assert meta == {"ext.bands": {"> 256 ulp": 3}}


def test_a_key_at_the_length_yaml_reads_is_written():
    key = "k" * 1022
    assert yaml.safe_load(dump_yaml({"m": {key: 1}})) == {"m": {key: 1}}


@pytest.mark.parametrize("key, says", [
    ("k" * 1100, "1024"),
    ("a\ud800b", "surrogate"),
    (("a", 1), "tuple"),
    (b"bytes", "bytes"),
])
def test_a_key_yaml_cannot_carry_is_refused_by_name(key, says, tmp_path):
    from mathema.spec import save_verified_entry
    with pytest.raises(ValueError) as err:
        save_verified_entry("pkg.mod.f", _entry({"bands": {key: 1}}),
                            str(tmp_path))
    text = str(err.value)
    assert says in text, text
    assert repr(key)[:20] in text, text
    assert "pkg.mod.f" not in load_verified(str(tmp_path))


def test_a_value_with_a_lone_surrogate_is_refused():
    with pytest.raises(ValueError, match="surrogate"):
        dump_yaml({"m": {"v": "a\udc80"}})
