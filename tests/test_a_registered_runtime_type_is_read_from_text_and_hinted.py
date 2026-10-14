# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A runtime type a package registers is read from an annotation's
source text and named by the usage hint, the same as numpy, pandas and
polars.

An adapter's `ALIASES` (`{"tk": "tablekit"}`) are the module aliases
an annotation's text is read through, so `"tk.Frame"` reaches the
adapter as `tablekit.Frame`; a bare `"Frame"` bound in the module to
the library's class is read as its dotted name. A parameter the body
reads as a table, in a module that imports the library, gets the hint
naming the adapter's runtime type, spelled with the module's alias.
The built-in libraries keep their aliases and their hints.
"""
from __future__ import annotations

import importlib
import sys
import textwrap

import pytest

import mathema
import mathema.runtime_types as rt
from mathema.runtime_types import Detection, NotMine

LIBRARY = '''
    class Frame:
        def __init__(self, columns):
            self.columns = dict(columns)

        def __getitem__(self, name):
            return self.columns[name]
'''

MODULE = '''
    import tablekit as tk


    def weighted(df):
        """The first row's price times its weight."""
        return df["price"][0] * df["weight"][0]
'''


class TablekitAdapter:
    name = "tablekit.Frame"
    kinds = frozenset({"table"})
    requires = ("tablekit",)
    ALIASES = {"tk": "tablekit"}

    def detect(self, annotation):
        if isinstance(annotation, str):
            if annotation.split("[", 1)[0].strip() == self.name:
                return Detection(self.name, "table",
                                 f"annotation text: {annotation}")
            return None
        if getattr(annotation, "__module__", "") == "tablekit" \
                and getattr(annotation, "__name__", "") == "Frame":
            return Detection(self.name, "table", f"annotation: {self.name}")
        return None

    def realise(self, abstract, options):
        import tablekit
        return tablekit.Frame({k: list(v.values)
                               for k, v in abstract.columns.items()})

    def observe(self, obj):
        return NotMine


class _EntryPoint:
    name, value = "tablekit", "tests:TablekitAdapter"

    def __init__(self, obj):
        self.obj = obj

    def load(self):
        return self.obj


@pytest.fixture
def tablekit(tmp_path, monkeypatch):
    (tmp_path / "tablekit.py").write_text(textwrap.dedent(LIBRARY))
    (tmp_path / "uses_tablekit.py").write_text(textwrap.dedent(MODULE))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("tablekit", "uses_tablekit"):
        sys.modules.pop(name, None)
    monkeypatch.setattr(rt, "entry_points",
                        lambda **_: [_EntryPoint(TablekitAdapter)])
    rt._discovered.cache_clear()
    yield importlib.import_module("tablekit")
    rt._discovered.cache_clear()
    for name in ("tablekit", "uses_tablekit"):
        sys.modules.pop(name, None)


def test_the_adapters_alias_reads_an_annotations_text(tablekit):
    (found,) = rt.detect_annotation("tk.Frame", {})
    assert found.adapter == "tablekit.Frame"


def test_a_bare_name_bound_to_the_librarys_class_is_read(tablekit):
    (found,) = rt.detect_annotation("Frame", {"Frame": tablekit.Frame})
    assert found.adapter == "tablekit.Frame"


def test_the_hint_names_the_registered_runtime_type(tablekit):
    module = importlib.import_module("uses_tablekit")
    facts = mathema.analyze(module.weighted)
    hint = facts.runtime_hints["df"]
    assert hint["type"] == "tablekit.Frame"
    assert hint["text"] == ("df is used as a table; this module imports "
                            "tablekit: to sample it as one, annotate: "
                            "df: tk.Frame")


def test_the_built_in_aliases_still_read(tablekit):
    np = pytest.importorskip("numpy")
    pytest.importorskip("pandas")
    pytest.importorskip("polars")
    assert [d.adapter for d in rt.detect_annotation(
        "pd.Series | pl.DataFrame | np.ndarray | npt.NDArray", {})] == [
        "pandas.Series", "polars.DataFrame", "numpy.ndarray",
        "numpy.ndarray"]
    (found,) = rt.detect_annotation("ndarray", {"ndarray": np.ndarray})
    assert found.adapter == "numpy.ndarray"


def test_the_dotted_name_reads_without_an_alias(tablekit):
    (found,) = rt.detect_annotation("tablekit.Frame", {})
    assert found.adapter == "tablekit.Frame"
