# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An unannotated parameter the body uses in a way only one runtime
type supports is drawn as that type, when the function's module imports
the type's library: each runtime type adapter declares the uses its
type supports and a list does not (`USES`), and the record says why
(`the body uses it as a pandas DataFrame`). Uses two imported libraries
both support promote nothing, and the hint names both. A module that
imports no such library is read as before."""
import importlib
import os
import sys
import textwrap

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("polars")

import mathema.runtime_types as rt  # noqa: E402
from mathema.analysis import analyze_source  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.runtime_types import (AbstractTable, AbstractVec,  # noqa: E402
                                   BodyUses, Detection, NotMine,
                                   realised_parameters)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))
import promote_no_library  # noqa: E402
import promote_numpy_and_pandas  # noqa: E402
import promote_numpy_only  # noqa: E402
import promote_pandas  # noqa: E402
import promote_polars  # noqa: E402


def _drawn(fn, param):
    return analyze_source(fn).runtime_types.get(param)


@pytest.mark.parametrize("fn, param, detection", [
    (promote_pandas.first_row_share, "df", Detection(
        "pandas.DataFrame", "table", "the body uses it as a pandas DataFrame")),
    (promote_pandas.scaled, "df", Detection(
        "pandas.DataFrame", "table", "the body uses it as a pandas DataFrame")),
    (promote_pandas.spread, "xs", Detection(
        "pandas.Series", "vec", "the body uses it as a pandas Series")),
    (promote_polars.groups_per_row, "df", Detection(
        "polars.DataFrame", "table", "the body uses it as a polars DataFrame")),
    (promote_polars.scaled, "df", Detection(
        "polars.DataFrame", "table", "the body uses it as a polars DataFrame")),
    (promote_polars.spread, "xs", Detection(
        "polars.Series", "vec", "the body uses it as a polars Series")),
    (promote_numpy_and_pandas.first_by_position, "xs", Detection(
        "pandas.Series", "vec", "the body uses it as a pandas Series")),
    (promote_numpy_only.gram_trace, "A", Detection(
        "numpy.ndarray", "mat", "the body uses it as a numpy array")),
    (promote_numpy_only.spread, "xs", Detection(
        "numpy.ndarray", "vec", "the body uses it as a numpy array")),
], ids=lambda v: f"{v.__module__}.{v.__name__}" if callable(v) else "")
def test_a_use_one_imported_library_supports_draws_its_type(fn, param,
                                                            detection):
    facts = analyze_source(fn)
    assert facts.runtime_types[param] == (detection,)
    assert facts.param_kinds[param] == detection.kind
    assert param not in facts.runtime_hints, facts.runtime_hints


@pytest.mark.parametrize("module, runtime", [
    (promote_pandas, "pandas.DataFrame"), (promote_polars, "polars.DataFrame")])
def test_a_promoted_table_is_drawn_as_the_annotated_table_is(module, runtime):
    assert realised_parameters(analyze_source(module.scaled))["df"].adapter \
        == runtime
    law = ('for df in [-1e6, 1e6]^n, c in [-2, 2], '
           'f(df, c) == c * df["returns"]')
    (p,) = check_conjectures(module.scaled, [claim(law, route="probe")])
    (annotated,) = check_conjectures(module.scaled_annotated,
                                     [claim(law, route="probe")])
    assert p.verdict == annotated.verdict == "holds", (p.verdict, p.note)
    # the unannotated parameter may also be None, so the run counts differ
    drawn = p.meta["mathema.sampling"].rsplit(", n=", 1)[0]
    assert drawn == annotated.meta["mathema.sampling"].rsplit(", n=", 1)[0]


def test_uses_two_imported_libraries_support_promote_nothing():
    facts = analyze_source(promote_numpy_and_pandas.spread)
    assert "xs" not in facts.runtime_types, facts.runtime_types
    hint = facts.runtime_hints["xs"]
    assert hint["types"] == ["pandas.Series", "numpy.ndarray"]
    assert hint["text"] == (
        "xs is used as a vector; this module imports pandas and numpy, "
        "whose types both support that use: to sample it as one, "
        "annotate: xs: pd.Series or xs: np.ndarray")
    assert hint["strong"] is True


def test_a_use_the_imported_library_does_not_support_promotes_nothing():
    facts = analyze_source(promote_numpy_only.first_by_position)
    assert "xs" not in facts.runtime_types, facts.runtime_types
    assert facts.runtime_hints["xs"]["text"] == (
        "xs is used as a vector; this module imports numpy: to sample it "
        "as one, annotate: xs: np.ndarray")


def test_a_module_importing_no_such_library_is_unchanged():
    facts = analyze_source(promote_no_library.spread)
    assert facts.runtime_types == {}
    assert facts.runtime_hints == {}


_TYPES = {"numpy.ndarray": ("numpy", "ndarray"),
          "pandas.Series": ("pandas", "Series"),
          "pandas.DataFrame": ("pandas", "DataFrame"),
          "polars.Series": ("polars", "Series"),
          "polars.DataFrame": ("polars", "DataFrame")}


@pytest.mark.parametrize("name", sorted(_TYPES))
def test_every_declared_use_is_one_the_type_has_and_a_list_lacks(name):
    module, cls_name = _TYPES[name]
    cls = getattr(importlib.import_module(module), cls_name)
    uses = rt.adapter(name).USES
    assert isinstance(uses, BodyUses)
    declared = uses.attributes | uses.methods | uses.keyed
    assert declared
    for attr in declared:
        assert hasattr(cls, attr), (name, attr)
        assert not hasattr(list, attr), (name, attr)
    for method in uses.methods | uses.keyed:
        assert callable(getattr(cls, method)), (name, method)
    assert uses.matmul == hasattr(cls, "__matmul__")


@pytest.mark.parametrize("name", ["pandas.DataFrame", "polars.DataFrame"])
def test_every_keyed_use_runs_on_a_drawn_table_with_that_column(name):
    adapter = rt.adapter(name)
    table = adapter.realise(AbstractTable({
        "k": AbstractVec((1.0, 2.0, 1.0)), "v": AbstractVec((3.0, 4.0, 5.0))}),
        {})
    assert adapter.USES.keyed
    for method in adapter.USES.keyed:
        getattr(table, method)("k")


def test_the_list_adapter_declares_no_uses():
    assert getattr(rt.adapter("list"), "USES", None) is None


LIBRARY = '''
    class Frame:
        def __init__(self, columns):
            self.columns = dict(columns)

        def pivot_wide(self, key):
            return self.columns[key]
'''

MODULE = '''
    import tablekit as tk


    def widened(df):
        """The frame pivoted wide on k."""
        return df.pivot_wide("k")
'''


class TablekitAdapter:
    name = "tablekit.Frame"
    kinds = frozenset({"table"})
    requires = ("tablekit",)
    ALIASES = {"tk": "tablekit"}
    USES = BodyUses(keyed=frozenset({"pivot_wide"}),
                    described="a tablekit Frame")

    def detect(self, annotation):
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


def test_a_registered_adapter_promotes_through_its_declared_uses(
        tmp_path, monkeypatch):
    (tmp_path / "tablekit.py").write_text(textwrap.dedent(LIBRARY))
    (tmp_path / "uses_tablekit.py").write_text(textwrap.dedent(MODULE))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("tablekit", "uses_tablekit"):
        sys.modules.pop(name, None)
    monkeypatch.setattr(rt, "entry_points",
                        lambda **_: [_EntryPoint(TablekitAdapter)])
    rt._discovered.cache_clear()
    try:
        module = importlib.import_module("uses_tablekit")
        facts = analyze_source(module.widened)
        assert facts.runtime_types["df"] == (Detection(
            "tablekit.Frame", "table", "the body uses it as a tablekit Frame"),)
    finally:
        rt._discovered.cache_clear()
        for name in ("tablekit", "uses_tablekit"):
            sys.modules.pop(name, None)
