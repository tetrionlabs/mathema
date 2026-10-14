# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An attribute a table object carries of its own (`df.schema`,
`df.columns`, `df.rdd`, `df.na`, `df.write`, `df.sparkSession`) is not
read as a column of the table; `df.price` is."""
import ast

import pytest

from mathema.definitions import column_read

OWN_ATTRIBUTES = ["schema", "columns", "rdd", "na", "write", "sparkSession"]


def _read(text: str):
    return column_read(ast.parse(text, mode="eval").body, {"df"})


@pytest.mark.parametrize("attr", OWN_ATTRIBUTES)
def test_a_tables_own_attribute_is_not_a_column(attr):
    assert _read(f"df.{attr}") is None


def test_an_ordinary_attribute_is_a_column():
    assert _read("df.price") == "price"
    assert _read('df["price"]') == "price"
