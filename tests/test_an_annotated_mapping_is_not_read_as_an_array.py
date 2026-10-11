# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter annotated as a dict or a Mapping is drawn as a dict even
when its module imports numpy or pandas and the body reads an attribute
an array or a table also has (`order.values()`): the annotation decides
the runtime type, never the attribute name. An unannotated parameter
used as `x.values` in a numpy module is still read as an array."""
import os
import sys

import pytest

pytest.importorskip("numpy")

from mathema.analysis import analyze_source  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.runtime_types import realised_parameters  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))
import orders_numpy  # noqa: E402

MAPPINGS = [orders_numpy.total_qty, orders_numpy.total_qty_generic,
            orders_numpy.total_qty_mapping, orders_numpy.item_count]


def _check(fn):
    (p,) = check_conjectures(fn, [claim("f(order) == f(order)")])
    return p


@pytest.mark.parametrize("fn", MAPPINGS, ids=lambda fn: fn.__name__)
def test_a_mapping_in_a_numpy_module_is_not_an_array(fn):
    facts = analyze_source(fn)
    assert "order" not in facts.runtime_types, facts.runtime_types
    assert "order" not in facts.runtime_hints, facts.runtime_hints
    assert facts.param_kinds["order"] == "dict"


@pytest.mark.parametrize("fn", MAPPINGS, ids=lambda fn: fn.__name__)
def test_a_claim_over_a_mapping_in_a_numpy_module_holds(fn):
    p = _check(fn)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample,
                                              p.note)
    assert p.counterexample is None
    assert "numpy" not in (p.note or ""), p.note


def test_the_sampling_note_describes_a_dict_draw():
    p = _check(orders_numpy.total_qty)
    sampling = p.meta.get("mathema.sampling") or ""
    assert "numpy" not in sampling and "U(" not in sampling, sampling


def test_a_mapping_in_a_pandas_module_is_not_a_series():
    pytest.importorskip("pandas")
    import orders_pandas
    facts = analyze_source(orders_pandas.total_qty)
    assert "order" not in facts.runtime_types, facts.runtime_types
    assert "order" not in facts.runtime_hints, facts.runtime_hints
    p = _check(orders_pandas.total_qty)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample,
                                              p.note)
    assert "pd.Series" not in (p.note or ""), p.note


def test_an_annotated_class_with_a_shape_is_not_an_array():
    facts = analyze_source(orders_numpy.box_volume)
    assert "b" not in facts.runtime_types, facts.runtime_types
    assert "b" not in facts.runtime_hints, facts.runtime_hints


def test_an_unannotated_values_read_in_a_numpy_module_is_an_array():
    facts = analyze_source(orders_numpy.unannotated_values)
    assert realised_parameters(facts)["x"].adapter == "numpy.ndarray"
