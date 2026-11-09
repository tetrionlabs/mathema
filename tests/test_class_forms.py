# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Class forms: a class carries a form hash as a function does, taken
over its alpha-normalised definition, and a dependency on a class
carries that form and the forms of everything the class rests on (its
bases, the classes its fields are annotated with, the functions its
body calls), so a change anywhere along that chain re-adjudicates the
claims of every function that reads the class."""
import ast
import importlib.util
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema.identity import class_form_hash
from mathema.inventory import class_reach, function_dependencies


def _form(source: str) -> str:
    (cdef,) = ast.parse(textwrap.dedent(source)).body
    return class_form_hash(cdef)


_LOADED: list = []


@pytest.fixture(autouse=True)
def _unload():
    yield
    while _LOADED:
        sys.modules.pop(_LOADED.pop(), None)


def _load(tmp_path, name, source):
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(source))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    _LOADED.append(name)
    spec.loader.exec_module(mod)
    return mod


_ORDER = '''
class Order:
    """An order."""
    total: int

    def doubled(self) -> int:
        """Twice the total."""
        n = self.total
        return n * 2
'''


def test_a_class_form_is_namespaced_and_ignores_docstrings_and_local_names():
    form = _form(_ORDER)
    assert form.startswith("py:")
    assert _form(_ORDER.replace('"""An order."""', '"""Another text."""')
                 .replace('"""Twice the total."""', "")) == form
    assert _form(_ORDER.replace("n = self.total", "m = self.total")
                 .replace("return n * 2", "return m * 2")) == form
    assert _form(_ORDER.replace("self", "me")) == form


def test_the_class_name_is_not_part_of_its_form():
    assert _form(_ORDER.replace("class Order", "class Purchase")) == _form(_ORDER)


@pytest.mark.parametrize("change", [
    ("total: int", "total: float"),
    ("total: int", "total: int\n    note: str"),
    ("return n * 2", "return n * 3"),
    ("def doubled", "def twice"),
    ("class Order:", "class Order(Base):"),
])
def test_a_change_to_a_field_a_method_its_name_or_a_base_changes_the_form(change):
    assert _form(_ORDER.replace(*change)) != _form(_ORDER)


_MODELS = '''
def positive(v):
    return v > 0


class Money:
    amount: int

    def valid(self) -> bool:
        return positive(self.amount)


class Base:
    id: int


class Order(Base):
    price: Money
    items: "list[Money]"


def total(order: Order) -> int:
    return Order.__name__.count("O") + order.price.amount
'''


def test_a_class_reaches_its_bases_its_field_classes_and_the_functions_it_calls(tmp_path):
    mod = _load(tmp_path, "class_form_models", _MODELS)
    reach = {r["key"]: r for r in class_reach(mod.Order)}
    assert set(reach) == {"class_form_models.Base", "class_form_models.Money",
                          "class_form_models.positive"}
    assert reach["class_form_models.Base"]["kind"] == "class"
    assert reach["class_form_models.positive"]["kind"] == "function"
    assert all(r["form"].startswith("py:") for r in reach.values())


def test_a_dependency_on_a_class_carries_its_form_and_its_reach(tmp_path):
    mod = _load(tmp_path, "class_form_dep", _MODELS)
    deps = {d["name"]: d for d in function_dependencies(mod.total)}
    order = deps["Order"]
    assert order["kind"] == "class" and order["form"].startswith("py:")
    assert {r["key"] for r in order["reaches"]} == {
        "class_form_dep.Base", "class_form_dep.Money", "class_form_dep.positive"}


def test_a_class_in_a_parameter_annotation_is_a_dependency_with_a_form(tmp_path):
    mod = _load(tmp_path, "class_form_annot", '''
        class Order:
            total: int


        def same(order: Order) -> Order:
            return order
    ''')
    deps = [d for d in function_dependencies(mod.same) if d["kind"] == "class"]
    assert [d["key"] for d in deps] == ["class_form_annot.Order"]
    assert deps[0]["form"].startswith("py:")


def test_a_class_without_source_has_no_form(tmp_path):
    mod = _load(tmp_path, "class_form_builtin", '''
        from fractions import Fraction


        def half(x: int) -> Fraction:
            return Fraction(x, 2)
    ''')
    deps = {d["name"]: d for d in function_dependencies(mod.half)}
    assert "form" not in deps.get("Fraction", {})


# --- verify re-adjudicates when the chain under a class moves ----------------

def _verify(root):
    script = ("import sys; from mathema.cli import main; "
              "sys.exit(main(['verify', '--root', '.', '--lenient']))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True)


_SHOP = '''\
def positive(v):
    return v > 0


class Base:
    id: int = 0


class Order(Base):
    total: int = 0

    def valid(self) -> bool:
        return positive(self.total)


def same(order: Order) -> Order:
    return order
'''


@pytest.mark.parametrize("change", [
    ("    total: int = 0\n", "    total: int = 1\n"),
    ("    id: int = 0\n", "    id: int = 2\n"),
    ("return v > 0", "return v >= 0"),
])
def test_verify_re_adjudicates_a_function_when_a_class_it_reads_changes(tmp_path, change):
    (tmp_path / "shop.py").write_text(_SHOP)
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "shop.same.claims.yaml").write_text(
        "shop.same:\n  claims:\n"
        "    - name: identity\n"
        '      statement: "for x in [0, 1], f(x) == x"\n'
        "      route: probe\n")
    r = _verify(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    r = _verify(tmp_path)
    assert "dependency changed" not in r.stdout, r.stdout
    doc = yaml.safe_load((tmp_path / ".mathema" / "verified" / "shop.same.yaml").read_text())
    (order,) = [d for d in doc["shop.same"]["dependencies"] if d.get("key") == "shop.Order"]
    assert order["form"].startswith("py:") and order["reaches"]

    (tmp_path / "shop.py").write_text(_SHOP.replace(*change))
    r = _verify(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dependency changed" in r.stdout, r.stdout


def test_a_class_stored_without_a_form_is_read_as_moved_once():
    live = [{"name": "Order", "kind": "class", "key": "shop.Order", "form": "py:aaaaaaaaaaaa",
             "reaches": [{"key": "shop.Base", "kind": "class", "form": "py:bbbbbbbbbbbb"}]}]
    before = [{"name": "Order", "kind": "class", "key": "shop.Order"}]
    from mathema.inventory import class_chain_moved
    assert class_chain_moved(before, live) == ["shop.Base", "shop.Order"]
    assert class_chain_moved(live, live) == []
