# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every record file under `.mathema/verified/` and `.mathema/declared/`
is named by one reversible encoding of its key: each character outside
letters, digits and `_.-~` is percent-encoded, so a key holding `/`,
`:` or `#` is one file directly in the store directory and reads back
under the same key. A store written under the older naming (the key
used as the file path as it stood) still loads, and is renamed to the
encoded names the next time the store is written."""
import os

import pytest

from mathema.spec import (load_verified, record_file_name, record_key,
                          save_verified_entry, unreadable_verified,
                          verified_dir, write_yaml)

TAGGED = "lang:src/ema.src#ema"


def _entry(form: str = "abc123") -> dict:
    return {"identity": {"form": form},
            "claims": [{"name": "bounded", "statement": "f(x) <= 1",
                        "verdict": "holds"}]}


@pytest.mark.parametrize("key", [
    TAGGED, "pkg.mod.fn", "pkg.mod.<locals>.inner", "100%:sure#/x",
    "a b", "naïve.fn"])
def test_the_encoding_is_reversible(key):
    name = record_file_name(key)
    assert name.endswith(".yaml")
    assert not set("/:#\\") & set(name)
    assert record_key(name) == key


def test_a_plain_dotted_key_keeps_its_file_name():
    assert record_file_name("pkg.mod.fn") == "pkg.mod.fn.yaml"


def test_a_tagged_key_round_trips_through_save_and_load(tmp_path):
    root = str(tmp_path)
    path = save_verified_entry(TAGGED, _entry(), root)
    assert os.path.dirname(path) == verified_dir(root)
    assert os.path.basename(path) == "lang%3Asrc%2Fema.src%23ema.yaml"
    loaded = load_verified(root)
    assert set(loaded) == {TAGGED}
    assert loaded[TAGGED]["entry"]["claims"][0]["name"] == "bounded"


def test_a_plain_key_round_trips_through_save_and_load(tmp_path):
    root = str(tmp_path)
    path = save_verified_entry("pkg.mod.fn", _entry(), root)
    assert os.path.basename(path) == "pkg.mod.fn.yaml"
    assert set(load_verified(root)) == {"pkg.mod.fn"}


def _legacy(root: str, key: str, form: str) -> str:
    """A record written under the older naming: the key as the path."""
    path = os.path.join(verified_dir(root), f"{key}.yaml")
    write_yaml(path, {key: _entry(form)})
    return path


def test_a_store_under_the_old_names_loads_and_migrates(tmp_path):
    root = str(tmp_path)
    nested = _legacy(root, TAGGED, "f1")
    flat = _legacy(root, "py:pkg.mod#fn", "f2")
    plain = _legacy(root, "pkg.other", "f3")
    loaded = load_verified(root)
    assert set(loaded) == {TAGGED, "py:pkg.mod#fn", "pkg.other"}

    save_verified_entry("pkg.new", _entry("f4"), root)

    assert not os.path.exists(nested)
    assert not os.path.exists(flat)
    assert not os.path.isdir(os.path.join(verified_dir(root), "lang:src"))
    assert os.path.exists(plain)
    names = sorted(os.listdir(verified_dir(root)))
    assert names == sorted(record_file_name(k) for k in (
        TAGGED, "py:pkg.mod#fn", "pkg.other", "pkg.new"))
    after = load_verified(root)
    assert set(after) == {TAGGED, "py:pkg.mod#fn", "pkg.other", "pkg.new"}
    assert after[TAGGED]["entry"]["identity"]["form"] == "f1"


def test_saving_a_key_under_its_old_name_replaces_that_file(tmp_path):
    root = str(tmp_path)
    old = _legacy(root, TAGGED, "f1")
    save_verified_entry(TAGGED, _entry("f2"), root)
    assert not os.path.exists(old)
    loaded = load_verified(root)
    assert loaded[TAGGED]["entry"]["identity"]["form"] == "f2"


def test_an_unreadable_record_is_reported_under_its_key(tmp_path):
    root = str(tmp_path)
    path = os.path.join(verified_dir(root), record_file_name(TAGGED))
    os.makedirs(os.path.dirname(path))
    with open(path, "w") as fh:
        fh.write("<<<<<<< HEAD\n")
    assert set(unreadable_verified(root)) == {TAGGED}


def test_the_declared_layer_uses_the_same_names(tmp_path):
    from mathema.authoring import materialize_declared

    def gain(x: float) -> float:
        return 2 * x
    root = str(tmp_path)
    legacy = os.path.join(root, ".mathema", "declared", f"{TAGGED}.yaml")
    write_yaml(legacy, {TAGGED: {"claims": []}})
    path = materialize_declared(gain, TAGGED, root)
    assert os.path.basename(path) == record_file_name(TAGGED)
    assert os.path.dirname(path) == os.path.join(root, ".mathema",
                                                 "declared")
    assert not os.path.exists(legacy)
