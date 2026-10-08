# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library row whose region cannot be built registers nothing. A row
of the project's own claims file is reported with a warning, once per
process, since the project can fix it; a row mathema ships is not
warned about on every run, and `mathema compendium status` names it
beside the function it belongs to."""
import textwrap
import warnings

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


@pytest.fixture
def unbuildable(monkeypatch):
    """`_row_region` refuses the rows named in the returned set."""
    from mathema import compendium
    refused: set = set()
    real = compendium._row_region

    def refusing(key, row):
        if (key, str(row.get("name"))) in refused:
            raise compendium._Unbuildable("no call order for its names")
        return real(key, row)
    monkeypatch.setattr(compendium, "_row_region", refusing)
    compendium.uninstall()
    compendium._REPORTED.clear()
    yield refused
    compendium.uninstall()
    compendium._REPORTED.clear()


def test_a_bundled_row_that_does_not_register_is_not_warned(unbuildable):
    from mathema import compendium
    unbuildable.add(("numpy.divide", "is_overflow_safe"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        names = compendium.register_library_claims(None)
    assert ("numpy.divide", "is_overflow_safe") not in names
    assert ("numpy.divide", "is_defined") in names


def test_a_project_row_that_does_not_register_is_warned_once(
        unbuildable, tmp_path):
    from mathema import compendium
    _write(tmp_path / "claims" / "npx.claims.yaml", """
        compendium: numpy
        numpy.sqrt:
          claims:
            - name: is_defined
              statement: "x >= 0"
    """)
    unbuildable.add(("numpy.sqrt", "is_defined"))
    with pytest.warns(UserWarning, match=r"'is_defined' of numpy\.sqrt "
                      r"\(claims/npx\.claims\.yaml\) registers no region"):
        compendium.register_library_claims(str(tmp_path))
    compendium.uninstall()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compendium.register_library_claims(str(tmp_path))


def test_status_names_a_row_that_does_not_register(unbuildable, tmp_path):
    from mathema.compendium.status import compendium_status, render_status
    _write(tmp_path / "qpkg" / "__init__.py", "")
    _write(tmp_path / "qpkg" / "mod.py", '''
        import numpy as np


        def ratio(a: float, b: float) -> float:
            """The quotient of a by b."""
            return float(np.divide(a, b))
    ''')
    _write(tmp_path / "claims" / "qpkg.claims.yaml", """
        qpkg.mod.ratio:
          claims:
            - name: unit
              statement: 'for a in [1, 2], b in [1, 2], f(a, b) > 0'
    """)
    unbuildable.add(("numpy.divide", "is_overflow_safe"))
    data = compendium_status(str(tmp_path), library="numpy")
    (lib,) = data["libraries"]
    row = lib["functions"]["numpy.divide"]
    assert row["unregistered"] == {
        "is_overflow_safe": "no call order for its names"}
    text = render_status(data)
    assert ("not registered: is_overflow_safe (no call order for its "
            "names)") in text


def test_status_names_nothing_when_every_row_registers(tmp_path):
    from mathema.compendium.status import compendium_status, render_status
    _write(tmp_path / "rpkg" / "__init__.py", "")
    _write(tmp_path / "rpkg" / "mod.py", '''
        import numpy as np


        def ratio(a: float, b: float) -> float:
            """The quotient of a by b."""
            return float(np.divide(a, b))
    ''')
    _write(tmp_path / "claims" / "rpkg.claims.yaml", """
        rpkg.mod.ratio:
          claims:
            - name: unit
              statement: 'for a in [1, 2], b in [1, 2], f(a, b) > 0'
    """)
    data = compendium_status(str(tmp_path), library="numpy")
    assert data["libraries"][0]["functions"]["numpy.divide"][
        "unregistered"] == {}
    assert "not registered" not in render_status(data)
