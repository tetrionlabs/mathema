# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema --version` prints the installed version on one line and
exits 0."""
import subprocess
import sys

import mathema


def test_version_prints_the_package_version_and_exits_0(tmp_path):
    script = ("import sys; from mathema.cli import main; "
              "sys.exit(main(['--version']))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == f"mathema {mathema.__version__}"
    assert "Traceback" not in r.stderr
