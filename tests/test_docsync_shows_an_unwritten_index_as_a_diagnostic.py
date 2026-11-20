# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When docsync cannot write the index it says so as a diagnostic: a
title, the index file it could not write, and one explanation saying
the claims were synced and how to write the index."""
from mathema.cli import main
from tests import test_docsync_says_when_the_index_is_not_written as _index

project = _index.project


def test_the_index_error_has_a_title_a_location_and_the_fix(project, capsys):
    main(["docsync", "--root", str(project), "--yes"])
    err = capsys.readouterr().err
    lines = err.rstrip("\n").split("\n")
    assert lines[:4] == ["Error: the index was not written", "",
                         "  on .mathema/index.yaml", ""], err
    (explanation,) = lines[4:]
    assert explanation.startswith(
        "index not written: PermissionError: index.yaml is read only. "), err
    assert "synced" in explanation and "mathema docsync" in explanation, err
