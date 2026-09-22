# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The licence-header gate, which every tracked .py file must pass.

The gate runs in pre-commit and in CI. It is tested here because a
false pass would let an unlicensed file ship, and a false fail would
block a legitimate executable script.
"""
from mathema._devtools.check_headers import check_headers

HEADER = ("# SPDX-License-Identifier: BUSL-1.1\n"
          "# Copyright 2026 Tetrion Ltd\n")


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_a_correctly_headed_file_passes(tmp_path):
    path = _write(tmp_path, "ok.py", HEADER + "x = 1\n")
    assert check_headers([path]) == []


def test_a_script_may_carry_a_shebang_before_the_header(tmp_path):
    """An executable script's shebang must come first; the SPDX
    convention allows the licence header to follow it."""
    path = _write(tmp_path, "script.py",
                  "#!/usr/bin/env python3\n" + HEADER + "x = 1\n")
    assert check_headers([path]) == []


def test_a_missing_header_is_reported(tmp_path):
    path = _write(tmp_path, "bare.py", "x = 1\n")
    assert check_headers([path]) == [path]


def test_a_wrong_licence_is_reported(tmp_path):
    path = _write(tmp_path, "wrong.py",
                  "# SPDX-License-Identifier: MIT\n"
                  "# Copyright 2026 Tetrion Ltd\n")
    assert check_headers([path]) == [path]


def test_a_header_buried_below_other_code_is_reported(tmp_path):
    """The header must be at the top, not merely present somewhere."""
    path = _write(tmp_path, "buried.py", "import os\n" + HEADER)
    assert check_headers([path]) == [path]
