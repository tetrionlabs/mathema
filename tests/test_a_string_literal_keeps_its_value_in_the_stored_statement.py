# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every string literal in a claim keeps its value in the stored text.

`canonical_claim_text` is the one stored spelling of a claim and the
text its fingerprint hashes. Reading that text back must give the same
claim: the same relation, the same domain, the same functions, and the
same string literal values in the same order. Canonicalising twice is
the same as canonicalising once.

The quoting rule for a literal in the stored text: a value holding no
double quote is written in double quotes; a value holding one is
written as Python writes it (single quotes, a single quote inside
escaped). Each literal is rewritten on its own, so the quotes of one
literal never pair with the quotes of another.
"""
import ast

import pytest

from mathema._scan import mask_strings
from mathema.conjecture import claim
from mathema.spec import canonical_claim_text

_STATEMENTS = [
    # one literal, either quote style
    'f(x, "a") == 1',
    "f(x, 'a') == 1",
    # a literal holding the other quote character
    "f(x, 'it\\'s') == 1",
    "f(x, \"it's\") == 1",
    "f(x, 'a\"b') == 1",
    'f(x, "a\\"b") == 1',
    # a literal holding both
    "f(x, 'a\"b\\'c') == 1",
    'f(x, "a\\"b\'c") == 1',
    # escaped backslashes
    'f(x, "a\\\\b") == 1',
    'f(x, "a\\\\") == 1',
    "f(x, 'a\\\\\"') == 1",
    # grammar characters inside a literal
    'f(x, "a:b") == 1',
    'f(x, "{a}") == 1',
    'f(x, "a}") == 1',
    'f(x, "#c") == 1',
    'f(x, "a,b") == 1',
    'f(x, "a=b") == 1',
    'f(x, "a==b") == 1',
    'f(x, "a-->b") == 1',
    'f(x, "a=>b") == 1',
    # newline and tab written as escapes
    'f(x, "a\\nb") == 1',
    'f(x, "a\\tb") == 1',
    # unicode
    'f(x, "é→∀") == 1',
    'f(x, "日本") == 1',
    # empty
    'f(x, "") == 1',
    "f(x, '') == 1",
    # two and three literals
    'f(x, "a", "b") == 1',
    'f(x, "a", "b", "c") == 1',
    'f(x, body="a: {\\"c\\":\\"\\"}", t="s") == 1',
    "f(x, '}\"', 's') == 1",
    "f(x, ' \"', ',') == 1",
    "f(x, 'a\"', 'b', 'c') == 1",
    "f(x, 'a\"!', 'b', 'c\"!', 'd') == 1",
    "f(x, '\"', \"'\") == 1",
    # literals on both sides of the relation
    'f(x, "a") == "b"',
    "f(x, '\"}') == 'b'",
    "f(x, '\"}') != 'b'",
    "f(x, '\"}', 'c') == 'b'",
    # subscript keys
    "f(x)[\"k\"] == 'v'",
    "f(x)['\"k}'] == 'v'",
    "f(x)['\"k}', 'j'] == 'v'",
    # a literal through a let binding
    'let k = "a:b", f(x, k) == 1',
    "let k = '}\"', f(x, k, 's') == 1",
    # a literal in a premise
    'assuming x != "a", f(x) == 1',
    "assuming x != '}\"', f(x, 's') == 1",
    "assuming x != '}\"' and x != 's', f(x, 't') == 1",
    # a literal in a domain
    'for x in {"a", "b"}, f(x) == 1',
    'for x in {"a:b", "c,d"}, f(x) == 1',
    "for x in {'a\"', 'b'}, f(x) == 1",
    "for x in {'a\"', 'b\"'}, f(x) == 1",
    # a literal beside a language refinement
    'for s in L[unicode, len <= 80], f(s, "a") == 1',
    "for s in L[unicode, len <= 80], f(s, '\"}', 'b') == 1",
]


def _values(text: "str | None") -> list:
    """The string literal values in `text`, in order."""
    _, literals = mask_strings(text or "")
    out = []
    for literal in literals:
        try:
            out.append(ast.literal_eval(literal))
        except (ValueError, SyntaxError):
            out.append(("unreadable", literal))
    return out


def _meaning(cj) -> dict:
    """What a claim states, spelling aside: its relation, domain,
    functions, and every string literal value it holds."""
    sides = [cj.lhs, cj.rhs, cj.assuming]
    sides += [t for link in (cj.links or []) for t in (link[0], link[2])]
    return {"relation": cj.relation,
            "values": [_values(s) for s in sides],
            "domain": repr(cj.domain),
            "funcs": sorted(cj.funcs),
            "negated": getattr(cj, "negated", False)}


@pytest.mark.parametrize("statement", _STATEMENTS)
def test_the_stored_text_reads_back_as_the_same_claim(statement):
    original = claim(statement)
    stored = canonical_claim_text(original)
    restored = claim(stored)
    assert _meaning(restored) == _meaning(original), stored


@pytest.mark.parametrize("statement", _STATEMENTS)
def test_canonicalising_twice_is_canonicalising_once(statement):
    stored = canonical_claim_text(claim(statement))
    assert canonical_claim_text(claim(stored)) == stored


@pytest.mark.parametrize("statement, stored", [
    ('f(x, body="a: {\\"c\\":\\"\\"}", t="s") == 1',
     'f(x, body=\'a: {"c":""}\', t="s") = 1'),
    ("f(x, '}\"', 's') == 1", "f(x, '}\"', \"s\") = 1"),
    ("f(x, 'a\"b\\'c') == 1", "f(x, 'a\"b\\'c') = 1"),
    ("f(x, 'a') == 1", 'f(x, "a") = 1'),
    ("f(x, 'it\\'s') == 1", "f(x, \"it's\") = 1"),
    ("f(x, 'a\"b') == 1", "f(x, 'a\"b') = 1"),
    ("for x in {'a\"', 'b'}, f(x) == 1", "for x in {'a\"', \"b\"}, f(x) = 1"),
])
def test_the_stored_text_follows_the_quoting_rule(statement, stored):
    assert canonical_claim_text(claim(statement)) == stored


def _repo_statements() -> list:
    """Every claim statement in the repository's claims files and test
    sources: each `statement:`/`law:` value in a YAML file, and the
    first argument of each `claim(...)` call in a test, with the table
    above."""
    import pathlib

    import yaml
    root = pathlib.Path(__file__).resolve().parents[1]
    found = list(_STATEMENTS)

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("statement", "law") and isinstance(v, str):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for path in sorted(root.rglob("*.y*ml")):
        if {".venv", ".git", "build", "node_modules"} & set(path.parts):
            continue
        try:
            walk(yaml.safe_load(path.read_text()))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
    for path in sorted((root / "tests").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", getattr(node.func, "attr", None)) == "claim"
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                found.append(node.args[0].value)
    return list(dict.fromkeys(found))


def _reads_back_with_its_values(text: str, original) -> bool:
    try:
        restored = claim(text)
    except Exception:
        return False
    return _meaning(restored)["values"] == _meaning(original)["values"]


def test_only_a_statement_the_old_quoting_misread_changes_its_stored_text():
    from mathema._scan import legacy_quoting
    statements = _repo_statements()
    read = changed = 0
    for statement in statements:
        try:
            cj = claim(statement)
            new = canonical_claim_text(cj)
            with legacy_quoting():
                old = canonical_claim_text(cj)
        except Exception:
            continue
        read += 1
        if new != old:
            changed += 1
            assert _reads_back_with_its_values(new, cj), (statement, new)
            try:
                old_meaning = _meaning(claim(old))
            except Exception:
                old_meaning = None
            assert old_meaning != _meaning(claim(new)), (statement, old, new)
    assert read >= 1000, read
    assert changed >= 1, changed
