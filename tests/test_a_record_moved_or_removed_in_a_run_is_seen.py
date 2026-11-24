# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record file moved or removed inside a run scope is seen by every
later read in the same run.

Renaming a store's older record names (`spec.migrate_record_names`),
including the rename `spec.record` makes before refusing to write over
an unreadable record, and the removal of a renamed record's old file
(`acceptance._apply_rename`) change the verified layer without
`spec.atomic_write_text`; the run's kept record listing and store view
follow each change.
"""
import os

import pytest

from mathema import _run_scope, spec

_OLD_KEY = "lang:src/ema"


def _old_record(root, text: str) -> str:
    """An older-named record of `_OLD_KEY`: the key as a path, its `/`
    making a subdirectory of the verified layer."""
    path = os.path.join(spec.verified_dir(str(root)), "lang:src", "ema.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _new_source(root) -> str:
    return os.path.relpath(
        os.path.join(spec.verified_dir(str(root)),
                     spec.record_file_name(_OLD_KEY)), str(root))


def test_a_migrated_record_is_read_under_its_new_name(tmp_path):
    _old_record(tmp_path, f"'{_OLD_KEY}':\n  claims: []\n")
    root = str(tmp_path)
    with _run_scope.run_scope():
        before = spec.load_verified(root)[_OLD_KEY]["source"]
        assert before != _new_source(tmp_path)
        spec._verified_view(root)
        moved = spec.migrate_record_names(spec.verified_dir(root))
        assert moved
        assert spec.load_verified(root)[_OLD_KEY]["source"] \
            == _new_source(tmp_path)
        assert spec._verified_view(root)[_OLD_KEY]["source"] \
            == _new_source(tmp_path)


def test_a_record_refused_after_its_migration_is_listed_under_its_new_name(
        tmp_path):
    _old_record(tmp_path, "")
    root = str(tmp_path)
    with _run_scope.run_scope():
        before = spec.unreadable_verified(root)[_OLD_KEY]["source"]
        assert before != _new_source(tmp_path)
        with pytest.raises(spec.UnreadableRecord):
            spec.record(None, key=_OLD_KEY, root=root)
        assert spec.unreadable_verified(root)[_OLD_KEY]["source"] \
            == _new_source(tmp_path)


def test_a_renamed_record_is_gone_from_its_old_key(tmp_path):
    from mathema.acceptance import _apply_rename
    root = str(tmp_path)
    old_key, new_key = "pkg.mod.old", "pkg.mod.new"
    store = spec.verified_dir(root)
    old_path = os.path.join(store, spec.record_file_name(old_key))
    spec.write_yaml(old_path, {old_key: {"claims": [],
                                         "identity": {"form": "abc"}}})
    plan = {"path": old_path,
            "new_path": os.path.join(store, spec.record_file_name(new_key)),
            "doc": spec.read_verified_file(old_path)[0],
            "key": new_key, "from": old_key, "root": root,
            "form_matches": True, "recorded_form": "abc",
            "live_form": "abc"}
    with _run_scope.run_scope():
        assert old_key in spec.load_verified(root)
        spec._verified_view(root)
        _apply_rename(plan, None)
        assert old_key not in spec.load_verified(root)
        assert new_key in spec.load_verified(root)
        assert old_key not in spec._verified_view(root)
