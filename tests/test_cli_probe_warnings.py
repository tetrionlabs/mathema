# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What the code under test emits while mathema probes it stays out of
the terminal: numpy's RuntimeWarnings for an invalid value or an
overflow are the values mathema is measuring (a nan, an inf), not
messages for the person running `mathema check`, and the verdict still
reads them."""
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("numpy")


def _run(*argv, cwd):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(argv)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(cwd),
                          capture_output=True, text=True)


_QUANT = '''
    import numpy as np


    def avg(xs: list) -> float:
        """Mean of xs."""
        return float(np.mean(xs))


    def logit(p: float) -> float:
        """Log odds."""
        return float(np.log(p / (1 - p)))


    def g(x: float) -> float:
        """Square root through numpy."""
        return float(np.sqrt(x))
'''


def test_check_prints_no_runtime_warning_from_the_probed_code(tmp_path):
    (tmp_path / "quant.py").write_text(textwrap.dedent(_QUANT))
    whole = _run("check", "quant.py", cwd=tmp_path)
    assert "RuntimeWarning" not in whole.stderr, whole.stderr
    assert "RuntimeWarning" not in whole.stdout
    r = _run("check", "quant.py:g", "--claim",
             "for x in [-4, 4], f(x)*f(x) == x", cwd=tmp_path)
    assert "falsified" in r.stdout, r.stdout + r.stderr
    assert r.returncode == 1
    assert "RuntimeWarning" not in r.stderr, r.stderr
